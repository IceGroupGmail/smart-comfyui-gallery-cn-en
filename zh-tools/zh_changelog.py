# -*- coding: utf-8 -*-
"""
「新功能弹框」增量汉化工具

背景：首页的 ✨What's New 弹框不是普通模板，而是把
templates/modals/changelog.html 里的 Markdown 由 JS 解析成幻灯片。
所以文案不会出现在 zh_scan 的体检里，需要单独处理。

这个工具做的事：
  1. 从 changelog.html 抽出「弹框实际会显示的那几版」的每一行文案
  2. 对照 translations/zh.json，报出还没翻译的行
  3. --emit 生成 reports/待翻译-changelog.json（键=英文原文，值=空）
  4. --merge 把填好的译文写进 zh.json（同时登记 en.json）

用法：
  python zh_changelog.py                       # 只体检
  python zh_changelog.py --emit                # 生成待翻译清单
  python zh_changelog.py --merge reports/待翻译-changelog.json
  python zh_changelog.py --versions 5          # 弹框改成显示 5 版时用
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import zh_scan  # 复用它的字典读写与追加逻辑

REPO = os.path.dirname(HERE)
CHANGELOG = os.path.join(REPO, "templates", "modals", "changelog.html")
REPORT_DIR = os.path.join(HERE, "reports")

VER_RE = re.compile(r"^###\s*\*\*\[(.*?)\]\s*-\s*(.*?)\*\*$")
SEC_RE = re.compile(r"^###\s+(.*)$")
BULLET_RE = re.compile(r"^\*\s+(.*)$")


def read(path):
    with io.open(path, "r", encoding="utf-8", newline="") as f:
        return f.read()


def extract_blocks(versions):
    """返回 [(版本号, [每行原文...])]，只取弹框会显示的前 N 版"""
    text = read(CHANGELOG)
    m = re.search(r'<script[^>]*id="changelog-data"[^>]*>(.*?)</script>', text, re.S)
    if not m:
        raise RuntimeError("changelog.html 里没找到 #changelog-data 数据块")
    md = m.group(1).strip()
    md = re.sub(r"^#\s*Changelog", "", md, flags=re.I | re.M).strip()
    raw_blocks = re.split(r"[\r\n]+---[\r\n]+", md)
    blocks = []
    for b in raw_blocks[:versions]:
        b = b.strip()
        if not b:
            continue
        lines = []
        ver = "?"
        for line in b.splitlines():
            line = line.strip()
            if not line:
                continue
            vm = VER_RE.match(line)
            if vm:
                if ver == "?":
                    ver = vm.group(1)
                continue
            sm = SEC_RE.match(line)
            if sm:
                lines.append(sm.group(1).strip())
                continue
            bm = BULLET_RE.match(line)
            if bm:
                lines.append(bm.group(1).strip())
                continue
            lines.append(line)
        blocks.append((ver, lines))
    return blocks


def main():
    ap = argparse.ArgumentParser(description="新功能弹框增量汉化")
    ap.add_argument("--versions", type=int, default=3, help="弹框显示多少版（默认 3，与前端一致）")
    ap.add_argument("--emit", action="store_true", help="生成 reports/待翻译-changelog.json")
    ap.add_argument("--merge", metavar="JSON", help="把填好的译文合并进 zh.json")
    args = ap.parse_args()

    zh = zh_scan.load_json("zh.json")
    en = zh_scan.load_json("en.json")

    if args.merge:
        patch_path = args.merge
        with io.open(patch_path, "r", encoding="utf-8-sig", newline="") as f:
            patch = json.loads(f.read())
        pairs = [(k, v) for k, v in patch.items() if isinstance(v, str) and v.strip()]
        zh_scan.append_keys("zh.json", pairs)
        zh_scan.append_keys("en.json", [(k, k) for k, _ in pairs if k not in en])
        print("已合并 %d 条译文（空值跳过）" % len(pairs))
        zh = zh_scan.load_json("zh.json")

    blocks = extract_blocks(args.versions)
    missing = []
    total = 0
    for ver, lines in blocks:
        print("\n[版本 %s] %d 行" % (ver, len(lines)))
        for line in lines:
            total += 1
            if line in zh:
                continue
            missing.append(line)
            print("  未翻译: %s" % (line[:70] + ("…" if len(line) > 70 else "")))

    print("\n合计 %d 行，未翻译 %d 行" % (total, len(missing)))
    if not missing:
        print("这个弹框的内容已经全部汉化。")

    if args.emit:
        os.makedirs(REPORT_DIR, exist_ok=True)
        out = {k: "" for k in missing}
        p = os.path.join(REPORT_DIR, "待翻译-changelog.json")
        with io.open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
        print("待翻译清单：%s" % p)

    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
