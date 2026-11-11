# -*- coding: utf-8 -*-
"""
SmartGallery 增量汉化扫描器

用途：上游更新后，只找出「这次新增或改动、还没汉化」的字符串，避免全量重做。

做四件事：
  1. 扫 templates/*.html，找出「应该汉化但还没用 _() 包起来」的英文界面文本（文本节点 + 常用属性）
  2. 找出「已经包了 _() 但 zh.json 里没有译文」的键
  3. --apply  把第 1 类自动包成 {{ _('原文') }}，并补进 en.json
  4. --emit / --merge  生成待翻译清单（JSON），填完再合并回 zh.json

用法：
  python zh_scan.py                 # 只体检，不改文件
  python zh_scan.py --apply         # 自动包裹未包裹的字符串
  python zh_scan.py --emit          # 生成 reports/待翻译.json（键 -> 空串）
  python zh_scan.py --merge reports/待翻译.json   # 把填好的译文合并进 zh.json
  python zh_scan.py --stale         # 额外列出 zh.json 里已没人引用的旧键
"""
import argparse
import io
import json
import os
import re
import sys
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TPL_DIR = os.path.join(REPO, "templates")
TRANS_DIR = os.path.join(REPO, "translations")
REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reports")
SKIP_DIRS = {".git", "__pycache__", "translations", "zh-tools", ".trae", "node_modules", "reports"}

# ---------- 文件读写：严格保持原编码（UTF-8 无 BOM）与换行 ----------

def read_text(path):
    with io.open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path, text):
    with io.open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def load_json(name):
    with io.open(os.path.join(TRANS_DIR, name), "r", encoding="utf-8", newline="") as f:
        return json.loads(f.read())


def append_keys(name, pairs):
    """往字典末尾追加键，自动给上一行补逗号，保持 CRLF 与 2 空格缩进，最后校验 JSON"""
    path = os.path.join(TRANS_DIR, name)
    text = read_text(path)
    for key, val in pairs:
        if '"%s":' % key in text:
            continue
        if not text.endswith("}\r\n") and not text.endswith("}\n"):
            raise RuntimeError("%s 尾部格式非预期，已中止" % name)
        tail_nl = "\r\n" if text.endswith("}\r\n") else "\n"
        body = text[: -len("}" + tail_nl)]
        if not body.rstrip("\r\n").rstrip().endswith(","):
            body = body.rstrip("\r\n") + "," + tail_nl
        esc_key = key.replace("\\", "\\\\").replace('"', '\\"')
        esc_val = val.replace("\\", "\\\\").replace('"', '\\"')
        text = body + '  "%s": "%s"%s}%s' % (esc_key, esc_val, tail_nl, tail_nl)
    json.loads(text)  # 校验合法
    write_text(path, text)
    return len(pairs)

# ---------- 模板预处理：把不该扫的区域抹成空白（保持偏移与行号不变）----------

MASK_PATTERNS = [
    r"<script\b[^>]*>.*?</script>",
    r"<style\b[^>]*>.*?</style>",
    r"<!--.*?-->",
    r"<pre\b[^>]*>.*?</pre>",
    r"<textarea\b[^>]*>.*?</textarea>",
]


def mask(text, pattern):
    def repl(m):
        # 非换行字符统一替换为空格：长度不变，行号不变
        return re.sub(r"[^\r\n]", " ", m.group(0))

    return re.sub(pattern, repl, text, flags=re.S | re.I)


def masked_view(text):
    for p in MASK_PATTERNS:
        text = mask(text, p)
    return text


# ---------- 判断一个字符串值不值得汉化 ----------

SKIP_WORDS = {    "utf-8", "http", "https", "json", "png", "jpg", "jpeg", "svg", "css", "html",
    "js", "gif", "webp", "mp4", "api", "id", "url", "ok", "px", "kb", "mb", "gb",
}


def is_candidate(raw, ignore=None):
    t = raw.strip()
    if ignore and t in ignore:
        return False
    if not (2 <= len(t) <= 140):
        return False
    if not re.search(r"[A-Za-z]{2,}", t):
        return False
    # 含 HTML 实体、路径、模板语法、URL 的一律跳过（避免误伤代码）
    if re.search(r"[{}<>/&=#@\\|^~`]", t):
        return False
    # 命令行参数（--admin-pass 之类）
    if t.startswith("--") or t.startswith("-"):
        return False
    # 引号 / 感叹号 / 逗号 / 括号 / 方括号：多为搜索示例、语法说明，不是界面文案
    if re.search(r'["!，,\[\]()]', t):
        return False
    # 单个纯英文标识符（如 JSON、v2.24.4）
    if " " not in t and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+-]*", t):
        return False
    if t.lower() in SKIP_WORDS:
        return False
    return True


WRAP_RE = re.compile(r"\{\{\s*_\('((?:[^'\\]|\\.)*)'\)\s*\}\}")
# 兼容单引号与双引号两种写法，用于模板与 Python 侧的键提取
KEY_RE = re.compile(r"""(?<![A-Za-z0-9_])_\s*\(\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")""")
ATTR_RE = re.compile(
    r'(?P<attr>placeholder|title|aria-label|alt|data-tooltip|data-title)="(?P<val>[^"{}<>]+)"',
    re.I,
)
TEXT_RE = re.compile(r">([^<>]*?)<")


def unescape_key(s):
    return s.replace("\\'", "'").replace('\\"', '"').replace("\\\\", "\\")


def escape_key(s):
    return s.replace("\\", "\\\\").replace("'", "\\'")


def line_of(text, offset):
    return text.count("\n", 0, offset) + 1


# ---------- 扫描 ----------

def extract_keys(text):
    """从源码里提取所有 _('...') / _("...") 的键（模板与 Python 通用）"""
    out = []
    for m in KEY_RE.finditer(text):
        k = m.group(1) if m.group(1) is not None else m.group(2)
        if k is not None:
            out.append(unescape_key(k))
    return out


def scan_file(path, zh, en, ignore=None):
    text = read_text(path)
    view = masked_view(text)

    wrapped = set(extract_keys(text))

    unwrapped = []   # (line, 原文, 位置start, 位置end, kind)
    missing_zh = []  # key
    manual = []      # 跨行文本块：自动工具不处理，只报告

    for m in TEXT_RE.finditer(view):
        raw = text[m.start(1):m.end(1)]
        if "\n" in raw or "\r" in raw:
            if is_candidate(raw, ignore):
                core = " ".join(raw.split())
                if core not in wrapped:
                    manual.append((line_of(text, m.start(1)), core))
            continue
        if not is_candidate(raw, ignore):
            # 含 {{ 插值但没走 _() 的文案（如 "Page {{ n }} of {{ total }}"），自动工具不处理
            if "{{" in raw and "_(" not in raw:
                literal = re.sub(r"\{\{.*?\}\}", "", raw, flags=re.S)
                literal = re.sub(r"\{%.*?%\}", "", literal, flags=re.S)
                if re.search(r"[A-Za-z]{2,}", literal) and " ".join(raw.split()) not in wrapped:
                    manual.append((line_of(text, m.start(1)), " ".join(raw.split())))
            continue
        core = raw.strip()
        if core in wrapped:
            continue  # 本文件里同样的文字已包过（可能只是缩进不同）
        unwrapped.append((line_of(text, m.start(1)), core, m.start(1), m.end(1), "text"))

    for m in ATTR_RE.finditer(view):
        raw = text[m.start("val"):m.end("val")]
        if not is_candidate(raw, ignore):
            continue
        core = raw.strip()
        if core in wrapped:
            continue
        unwrapped.append((line_of(text, m.start("val")), core, m.start("val"), m.end("val"), "attr"))

    for key in wrapped:
        if key not in zh:
            missing_zh.append(key)

    return text, unwrapped, missing_zh, manual


def load_ignore():
    """ignore.txt：一行一个字符串，命中则视为“故意不汉化”（品牌名、参数、示例语法等）"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ignore.txt")
    out = set()
    if os.path.isfile(path):
        with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
            for line in f:
                s = line.strip()
                if s and not s.startswith("#"):
                    out.add(s)
    return out


def walk_sources(suffixes, base=None):
    """遍历仓库内的源码文件（排除 .git / 字典目录 / 工具目录）"""
    base = base or REPO
    for root, dirs, files in os.walk(base):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in sorted(files):
            if f.lower().endswith(suffixes):
                yield os.path.join(root, f)


def walk_templates():
    for root, dirs, files in os.walk(TPL_DIR):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__", ".trae")]
        for f in sorted(files):
            if f.endswith(".html"):
                yield os.path.join(root, f)


# ---------- 自动包裹 ----------

def apply_wraps(path, text, items):
    """文本节点与属性值都包裹；从后往前替换，避免偏移错乱"""
    targets = list(items)
    targets.sort(key=lambda x: x[2], reverse=True)
    for line, core, start, end, kind in targets:
        raw = text[start:end]
        new_core = "{{ _('%s') }}" % escape_key(core)
        if kind == "attr":
            text = text[:start] + new_core + text[end:]
        else:
            lead = raw[: len(raw) - len(raw.lstrip())]
            trail = raw[len(raw.rstrip()):]
            text = text[:start] + lead + new_core + trail + text[end:]
    return text, len(targets)


# ---------- 主流程 ----------

def main():
    ap = argparse.ArgumentParser(description="SmartGallery 增量汉化扫描器")
    ap.add_argument("--apply", action="store_true", help="自动把未包裹的文本包成 {{ _('原文') }}")
    ap.add_argument("--emit", action="store_true", help="生成待翻译清单 reports/待翻译.json")
    ap.add_argument("--merge", metavar="JSON", help="把填好的译文合并进 zh.json")
    ap.add_argument("--stale", action="store_true", help="列出 zh.json 中已无人引用的键")
    ap.add_argument("--root", metavar="DIR", help="指定 templates 目录（自测用）")
    args = ap.parse_args()

    global TPL_DIR
    if args.root:
        TPL_DIR = args.root

    if not os.path.isdir(TPL_DIR):
        print("找不到 templates 目录:", TPL_DIR)
        return 2

    zh = load_json("zh.json")
    en = load_json("en.json")
    ignore = load_ignore()

    if args.merge:
        path = args.merge
        with io.open(path, "r", encoding="utf-8-sig", newline="") as f:
            patch = json.loads(f.read())
        pairs = [(k, v) for k, v in patch.items() if isinstance(v, str) and v.strip()]
        n = append_keys("zh.json", pairs)
        print("已合并 %d 条译文到 zh.json（空值已跳过）" % n)
        zh = load_json("zh.json")

    results = []
    total_unwrapped = 0
    total_missing = 0
    total_manual = 0
    new_keys = []

    for path in walk_templates():
        rel = os.path.relpath(path, TPL_DIR).replace(os.sep, "/")
        text, unwrapped, missing, manual = scan_file(path, zh, en, ignore)

        if args.apply and unwrapped:
            text2, n = apply_wraps(path, text, unwrapped)
            if n:
                write_text(path, text2)
        results.append((rel, unwrapped, missing, manual))
        total_unwrapped += len(unwrapped)
        total_missing += len(missing)
        total_manual += len(manual)
        for k in missing:
            if k not in new_keys:
                new_keys.append(k)
        for it in unwrapped:
            if it[1] not in new_keys:
                new_keys.append(it[1])

    # 控制台报告
    print("=" * 68)
    print("增量汉化体检  %s" % datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("=" * 68)
    for rel, unwrapped, missing, manual in results:
        if not unwrapped and not missing and not manual:
            continue
        print("\n[%s]" % rel)
        if unwrapped:
            print("  未包裹 %d 处：" % len(unwrapped))
            for line, core, s, e, kind in unwrapped[:15]:
                print("    L%-5d %s  %s" % (line, "属性" if kind == "attr" else "文本", core))
            if len(unwrapped) > 15:
                print("    … 其余 %d 处见报告文件" % (len(unwrapped) - 15))
        if missing:
            print("  缺中文译文 %d 个：" % len(missing))
            for k in missing[:15]:
                print("    %s" % k)
            if len(missing) > 15:
                print("    … 其余 %d 个见报告文件" % (len(missing) - 15))
        if manual:
            print("  跨行文本块 %d 处（需人工处理）：" % len(manual))
            for line, core in manual[:5]:
                print("    L%-5d %s" % (line, core[:60]))
            if len(manual) > 5:
                print("    … 其余 %d 处见报告文件" % (len(manual) - 5))

    print("\n合计：未包裹 %d 处，缺译文 %d 个，跨行待人工 %d 处"
          % (total_unwrapped, total_missing, total_manual))
    if args.apply:
        print("已自动包裹（请 git diff 复核后再提交）")
    if not total_unwrapped and not total_missing:
        print("这份上游版本已经全部汉化完毕。")

    # 把新出现的英文原文补进 en.json（en 是恒等映射，只用于记录全量键）
    if args.apply and total_unwrapped:
        fresh = [(k, k) for k in new_keys if k not in en]
        if fresh:
            append_keys("en.json", fresh)
            print("en.json 新增 %d 个键" % len(fresh))

    # 写报告
    os.makedirs(REPORT_DIR, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    report_path = os.path.join(REPORT_DIR, "体检-%s.md" % stamp)
    with io.open(report_path, "w", encoding="utf-8", newline="\r\n") as f:
        f.write("# 增量汉化体检报告 %s\n\n" % datetime.now().strftime("%Y-%m-%d %H:%M"))
        f.write("- 未包裹（需汉化）：%d 处\n- 缺中文译文：%d 个\n- 跨行文本块（人工）：%d 处\n\n"
                % (total_unwrapped, total_missing, total_manual))
        for rel, unwrapped, missing, manual in results:
            if not unwrapped and not missing and not manual:
                continue
            f.write("\n## %s\n" % rel)
            if unwrapped:
                f.write("\n### 未包裹\n\n| 行号 | 类型 | 原文 |\n| --- | --- | --- |\n")
                for line, core, s, e, kind in unwrapped:
                    f.write("| %d | %s | %s |\n" % (line, "属性" if kind == "attr" else "文本", core.replace("|", "\\|")))
            if missing:
                f.write("\n### 缺中文译文\n\n")
                for k in missing:
                    f.write("- `%s`\n" % k)
            if manual:
                f.write("\n### 跨行文本块（需人工确认）\n\n")
                for line, core in manual:
                    f.write("- L%d `%s`\n" % (line, core.replace("|", "\\|")))

    # Python 侧（smartgallery.py 里的 flash 文案等）缺译文检查
    py_missing = []
    for p in walk_sources((".py",)):
        for key in extract_keys(read_text(p)):
            if key not in zh and key not in py_missing:
                py_missing.append(key)
    if py_missing:
        print("\n[Python 侧] 缺中文译文 %d 个：" % len(py_missing))
        for k in py_missing[:10]:
            print("    %s" % k)
        if len(py_missing) > 10:
            print("    … 其余 %d 个见报告文件" % (len(py_missing) - 10))

    if args.stale:
        # 键可能在模板、JS、Python 任一处被引用，按“全仓库字面出现”判断，避免误杀
        # 注意：字典里的键含真实换行，源码里多写成 \n 转义，两种形态都要比
        sources = {p: read_text(p) for p in walk_sources((".html", ".js", ".py"))}
        def used(k):
            variants = (k, k.replace("\n", "\\n"), k.replace("\\n", "\n"),
                        k.replace('"', '\\"'), k.replace("\\n", "\n").replace('"', '\\"'))
            return any(v in t for t in sources.values() for v in variants)
        stale = sorted(k for k in zh if k.strip() and not used(k))
        print("\n疑似无用键（全仓库都找不到引用）%d 个：" % len(stale))
        for k in stale[:20]:
            print("  %s" % k)
        if len(stale) > 20:
            print("  …其余 %d 个" % (len(stale) - 20))
        with io.open(os.path.join(REPORT_DIR, "疑似无用键-%s.txt" % stamp), "w", encoding="utf-8", newline="\r\n") as f:
            f.write("\n".join(stale))

    if args.emit:
        todo = {}
        for k in new_keys:
            if k not in zh:
                todo[k] = ""
        emit_path = os.path.join(REPORT_DIR, "待翻译.json")
        with io.open(emit_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(todo, ensure_ascii=False, indent=2) + "\n")
        print("\n待翻译清单已写出：%s（%d 个键，填好值后执行 --merge）" % (emit_path, len(todo)))

    return 1 if (total_unwrapped or total_missing) else 0


if __name__ == "__main__":
    sys.exit(main())
