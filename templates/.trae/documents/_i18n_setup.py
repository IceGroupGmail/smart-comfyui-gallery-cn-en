"""One-shot setup script for i18n infrastructure.

Creates project-root files (i18n.py, translations/zh.json, translations/en.json)
and patches smartgallery.py to register the context processor, the `_` Jinja
filter, and the /set_lang route. Idempotent: re-running it is safe because all
insertions are guarded by unique marker strings.

Run from project root with: python "e:/AI/smart-comfyui-gallery/templates/.trae/documents/_i18n_setup.py"
"""
import json
import os
import re
import sys

PROJECT_ROOT = r"e:\AI\smart-comfyui-gallery"
TEMPLATES_DIR = os.path.join(PROJECT_ROOT, "templates")
TRANSLATIONS_DIR = os.path.join(PROJECT_ROOT, "translations")
SG_PATH = os.path.join(PROJECT_ROOT, "smartgallery.py")

# ---------------------------------------------------------------------------
# 1. Create i18n.py at project root
# ---------------------------------------------------------------------------
I18N_PY = '''"""SmartGallery i18n module.

Loads JSON translation dictionaries from the `translations/` folder,
detects the user's preferred language (session -> cookie -> Accept-Language -> zh),
and exposes a `translate()` helper plus a Jinja2 `_` filter.

Keys are English source strings; values are localized strings.
Interpolation uses `{name}` placeholders, e.g. "Page {n} of {total}".
"""
import json
import os

_TRANSLATIONS = None
SUPPORTED_LANGS = ("zh", "en")
DEFAULT_LANG = "zh"


def _load():
    """Load translation JSON files once, cached in module scope."""
    global _TRANSLATIONS
    if _TRANSLATIONS is None:
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "translations")
        loaded = {}
        for code in SUPPORTED_LANGS:
            path = os.path.join(base, "{}.json".format(code))
            try:
                with open(path, encoding="utf-8") as f:
                    loaded[code] = json.load(f)
            except (OSError, ValueError):
                loaded[code] = {}
        _TRANSLATIONS = loaded
    return _TRANSLATIONS


def detect_lang(session, request):
    """Determine the active language.

    Priority: session['lang'] -> cookie['lang'] -> Accept-Language -> DEFAULT_LANG.
    """
    lang = None
    try:
        lang = session.get("lang")
    except Exception:
        pass
    if not lang:
        lang = request.cookies.get("lang")
    if not lang:
        al = (request.headers.get("Accept-Language", "") or "").lower()
        lang = "en" if al.startswith("en") else DEFAULT_LANG
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG
    return lang


def translate(key, lang, **kwargs):
    """Look up `key` in the `lang` dictionary, falling back to zh then the key itself."""
    d = _load()
    table = d.get(lang) or {}
    if key in table:
        s = table[key]
    elif key in d.get(DEFAULT_LANG, {}):
        s = d[DEFAULT_LANG][key]
    else:
        s = key
    if kwargs:
        for k, v in kwargs.items():
            s = s.replace("{" + k + "}", str(v))
    return s


def get_dict(lang):
    """Return the full dictionary for `lang` (used to inject into templates as `t`)."""
    d = _load()
    return d.get(lang) or d.get(DEFAULT_LANG) or {}


def reload():
    """Force reload of translation files (useful during development)."""
    global _TRANSLATIONS
    _TRANSLATIONS = None
    return _load()
'''

# ---------------------------------------------------------------------------
# 2. Initial translation dictionaries (seeded from plan examples; will grow)
# ---------------------------------------------------------------------------
INITIAL_ZH = {
    "SmartGallery": "SmartGallery",
    "Settings & Info": "设置与信息",
    "Close Menu": "关闭菜单",
    "Generation Data": "生成数据",
    "Anchored inspector showing prompts, models, and sampling parameters next to the active thumbnail. (Pin: Alt+M)": "锚定检视器,在当前缩略图旁显示提示词、模型与采样参数。(固定:Alt+M)",
    "List View": "列表视图",
    "Switch between the standard Grid and the compact List layout.": "在标准网格视图与紧凑列表布局之间切换。",
    "2-Column Grid": "双列网格",
    "Show 2 compact thumbnails per row.": "每行显示 2 个紧凑缩略图。",
    "Thumbnail Size": "缩略图大小",
    "Toggle between Normal (320px) and Compact (220px) view.": "在「标准」(320px) 与「紧凑」(220px) 视图之间切换。",
    "Useful for viewing more items at once on smaller screens.": "在小屏幕上一次查看更多项目时很有用。",
    "Normal": "标准",
    "Compact": "紧凑",
    "Cluster Badges": "聚类徽章",
    "Display cluster hash badges on normal grid thumbnails instead of the standard workflow badge.": "在标准网格缩略图上显示聚类哈希徽章,替代标准的工作流徽章。",
    "Video Autoplay": "视频自动播放",
    "When enabled, videos play automatically on hover (Desktop) or load instantly.": "启用后,鼠标悬停时视频将自动播放(桌面端),或加载后立即播放。",
    "Disable to save bandwidth/CPU or if scrolling feels choppy.": "如需节省带宽/CPU,或滚动卡顿,请关闭。",
    "Documentation & Help": "文档与帮助",
    "Read the manual, discover features, and stay updated on the official website.": "在官方网站阅读手册、了解功能并获取最新动态。",
    "What's New": "新功能",
    "View recent updates, new features, and changelogs.": "查看最近更新、新功能与变更日志。",
    "Language": "语言",
    "Switch interface language between Chinese and English.": "在中文与英文界面之间切换。",
    "中文": "中文",
    "English": "English",
    "Tools": "工具",
    "Folders": "文件夹",
    "Collections": "集合",
    "Status": "状态",
    "Search folders...": "搜索文件夹…",
    "Search collections...": "搜索集合…",
    "Create New Collection": "新建集合",
    "Filters": "筛选",
    "AI Search": "AI 搜索",
    "Upload": "上传",
    "Rescan": "重新扫描",
    "Auto-Refresh": "自动刷新",
    "OmniQuery": "OmniQuery",
    "Info": "信息",
    "Rename": "重命名",
    "Delete": "删除",
    "Unmount": "卸载",
    "Move here": "移动到此处",
    "{n} direct files": "{n} 个直接文件",
    "Please select at least one item.": "请至少选择一项。",
    "{count} Selected": "已选 {count} 项",
    "0 Selected": "已选 0 项",
    "Page {n} of {total}": "第 {n} 页 / 共 {total} 页",
    "Load More": "加载更多",
    "Back to Top": "回到顶部",
    "Index": "索引",
    "Thumb": "缩略",
    "Name": "名称",
    "Rating": "评分",
    "Comments": "评论",
    "Size": "大小",
    "Dims": "尺寸",
    "Duration": "时长",
    "Type": "类型",
    "Date": "日期",
    "Actions": "操作",
    "GRID": "网格",
    "ON": "开",
    "OFF": "关",
    "Cancel": "取消",
    "Submit": "提交",
    "Reset": "重置",
    "Close": "关闭",
    "Search": "搜索",
    "Search...": "搜索…",
    "Collection Notes": "集合备注",
    "Documentation & Help": "文档与帮助",
    "App Controls": "应用控制",
    "Page Nav (Std)": "页面导航(标准)",
    "Selection (Std)": "选择(标准)",
    "Batch Actions": "批量操作",
    "Status Tags": "状态标签",
    "Lightbox View": "灯箱视图",
    "Workflow Tags": "工作流标签",
    "Favorite": "收藏",
    "Tag": "标签",
    "Compare": "对比",
    "More": "更多",
    "Settings": "设置",
    "Documentation": "文档",
    "Shortcuts": "快捷键",
    "Focus Mode": "专注模式",
    "AI Manager": "AI 管理",
    "Open ComfyUI": "打开 ComfyUI",
    "Open LoRA Manager": "打开 LoRA 管理器",
    "Smart Clustering": "智能聚类",
    "Remix Workflow": "Remix 工作流",
    "ComfyUI Queue Deck": "ComfyUI 队列面板",
}

INITIAL_EN = dict((k, k) for k in INITIAL_ZH.keys())


# ---------------------------------------------------------------------------
# 3. Patch smartgallery.py
# ---------------------------------------------------------------------------
I18N_MARKER = "# __SG_I18N_PATCH__"

I18N_PATCH_BLOCK = '''
# __SG_I18N_PATCH__
from i18n import detect_lang as _i18n_detect_lang, translate as _i18n_translate, get_dict as _i18n_get_dict

@app.context_processor
def inject_i18n():
    lang = _i18n_detect_lang(session, request)
    return {"lang": lang, "t": _i18n_get_dict(lang)}

@app.template_filter("_")
def _i18n_filter(key):
    return _i18n_translate(key, _i18n_detect_lang(session, request))

@app.route("/galleryout/api/set_lang", methods=["POST"])
def set_lang():
    lang = request.form.get("lang", "zh")
    if lang not in ("zh", "en"):
        lang = "zh"
    session["lang"] = lang
    resp = jsonify({"status": "success", "lang": lang})
    resp.set_cookie("lang", lang, max_age=60 * 60 * 24 * 365)
    return resp
# __SG_I18N_PATCH_END__
'''


def main():
    os.makedirs(TRANSLATIONS_DIR, exist_ok=True)

    # Write i18n.py
    i18n_path = os.path.join(PROJECT_ROOT, "i18n.py")
    with open(i18n_path, "w", encoding="utf-8") as f:
        f.write(I18N_PY)
    print("[ok] wrote {}".format(i18n_path))

    # Write translation JSON files
    zh_path = os.path.join(TRANSLATIONS_DIR, "zh.json")
    en_path = os.path.join(TRANSLATIONS_DIR, "en.json")
    with open(zh_path, "w", encoding="utf-8") as f:
        json.dump(INITIAL_ZH, f, ensure_ascii=False, indent=2, sort_keys=True)
    with open(en_path, "w", encoding="utf-8") as f:
        json.dump(INITIAL_EN, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("[ok] wrote {} ({} entries)".format(zh_path, len(INITIAL_ZH)))
    print("[ok] wrote {} ({} entries)".format(en_path, len(INITIAL_EN)))

    # Patch smartgallery.py (idempotent)
    with open(SG_PATH, "r", encoding="utf-8") as f:
        src = f.read()

    if I18N_MARKER in src:
        # Remove existing block (non-greedy) then re-add
        src = re.sub(
            re.escape(I18N_MARKER) + r".*?" + re.escape("# __SG_I18N_PATCH_END__\n"),
            "",
            src,
            flags=re.DOTALL,
        )

    # Insert immediately after the app.secret_key line
    anchor = "app.secret_key = SECRET_KEY"
    if anchor not in src:
        print("[error] anchor {!r} not found in smartgallery.py".format(anchor))
        return 1
    src = src.replace(anchor, anchor + "\n" + I18N_PATCH_BLOCK, 1)

    with open(SG_PATH, "w", encoding="utf-8") as f:
        f.write(src)
    print("[ok] patched smartgallery.py with i18n block (after {!r})".format(anchor))

    print("\nDone. Next: wire the three top-level templates (index.html, exhibition.html, exhibition_login.html).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
