# -*- coding: utf-8 -*-
"""
镜像内自检：确认汉化成果真的进了这个镜像，而不是"构建成功"就完事。

用法（由 build-push-harbor.ps1 自动调用，也可手工跑）：
  docker run --rm -v "<仓库>/zh-tools:/chk:ro" --entrypoint /app/venv/bin/python <镜像> /chk/verify_image.py
"""
import io
import os
import sys

sys.path.insert(0, "/app")

problems = []


def check(label, ok, detail=""):
    print("  %-46s %s %s" % (label, "[OK]" if ok else "[!]", detail))
    if not ok:
        problems.append(label)


try:
    import i18n
except Exception as e:  # noqa: BLE001
    print("导入 i18n 失败: %s" % e)
    sys.exit(1)

zh = i18n.get_dict("zh")
en = i18n.get_dict("en")
print("字典: zh=%d en=%d 缺 %d" % (len(zh), len(en), len(set(en) - set(zh))))
check("字典条数与 en 对齐", not (set(en) - set(zh)), "%d 条缺失" % len(set(en) - set(zh)) if set(en) - set(zh) else "")

samples = [
    "Continue browsing",
    "Mouse Drag",
    "Key: P",
    "**Sync Watchdog triggered: force releasing lock**",
    "🚀 Highlights & Architectural Improvements",
]
print("译文抽样:")
for k in samples:
    v = i18n.translate(k, "zh")
    same = v == k
    print("  %-56s -> %s" % (k[:54], v))
    check("译文存在: %s" % k[:40], not same, "" if not same else "仍是英文原文")

check("补丁样式 zh-local.css 存在", os.path.exists("/app/templates/css/zh-local.css"))
with io.open("/app/templates/index.html", encoding="utf-8") as f:
    html = f.read()
check("index.html 引用了 zh-local.css", "zh-local.css" in html)

with io.open("/app/templates/modals/whats_new_modal.html", encoding="utf-8") as f:
    wn = f.read()
check("弹框解析器含 wnT 补丁", "function wnT" in wn)
check("changelog.html 存在", os.path.exists("/app/templates/modals/changelog.html"))

# --- 补丁: 忽略群晖 @eaDir 元数据目录 ---
with io.open("/app/smartgallery.py", encoding="utf-8") as f:
    sg = f.read()
check("smartgallery.py 含 @eaDir 忽略常量", "IGNORED_SYSTEM_FOLDER_NAMES = {'@eadir'}" in sg)
check("@eaDir 过滤器已接入目录树扫描", "not is_ignored_system_folder(d) and d not in [THUMBNAIL_CACHE_FOLDER_NAME" in sg)
check("@eaDir 过滤器已接入路径浏览器", "not is_ignored_system_folder(entry.name)" in sg)
check("@eaDir 过滤器已接入递归统计/索引", sg.count("is_ignored_system_folder") >= 6, "共 %d 处" % sg.count("is_ignored_system_folder"))

print("\n结论:", "全部通过" if not problems else ("有 %d 项未通过 -> %s" % (len(problems), problems)))
sys.exit(0 if not problems else 1)
