# SmartGallery 国际化(中文界面)实现计划

## Context(背景与目标)

SmartGallery 当前是一个纯英文界面的 Flask + Jinja2 模板应用,UI 文本硬编码在 `index.html`(~12659 行)、`exhibition.html`、`exhibition_login.html` 以及 `templates/modals/` 下 8 个子模板和大量 JS 模板字符串中。项目无任何 i18n 基础设施,`requirements.txt` 不含 `flask-babel`。

**目标**:为项目增加语言选择能力,并新增中文界面。用户决策:
1. **方案**:混合方案 — Jinja2 后端字典注入 + JS 字典处理动态字符串(不引入 `flask-babel`)。
2. **覆盖范围**:一次性全覆盖 — 所有用户可见文本(静态 HTML + JS 动态渲染)。
3. **默认语言**:中文设为新默认,英文为可选;按 `session → cookie → Accept-Language → zh` 顺序探测。

预期结果:服务器首次渲染即为中文,`<html lang="zh">`;用户可在"设置"弹窗内切换中/英,选择持久化(cookie + session);切换后页面 reload,所有静态/动态文本一致。

---

## 实现步骤

### 第 1 步:新建翻译字典与加载模块

**新建文件**:
- `e:\AI\smart-comfyui-gallery\translations\zh.json` — 中文翻译(默认)
- `e:\AI\smart-comfyui-gallery\translations\en.json` — 英文(key 与 value 相同,保持结构对齐)
- `e:\AI\smart-comfyui-gallery\i18n.py` — 加载器 + 探测 + 翻译函数

**键约定**:以英文源字符串作为 key,避免人工造键,便于全覆盖时直接从模板提取。带插值的用 `{name}` 占位符。

字典示例:
```json
// zh.json
{
  "Settings & Info": "设置与信息",
  "List View": "列表视图",
  "Folders": "文件夹",
  "Collections": "集合",
  "Page {n} of {total}": "第 {n} 页 / 共 {total} 页",
  "{count} Selected": "已选 {count} 项",
  "Move here": "移动到此处",
  "Please select at least one item.": "请至少选择一项。"
}
```

`i18n.py` 核心结构:
```python
import json, os
_TRANSLATIONS = None
def _load():
    global _TRANSLATIONS
    if _TRANSLATIONS is None:
        base = os.path.join(os.path.dirname(__file__), 'translations')
        _TRANSLATIONS = {}
        for code in ('zh','en'):
            with open(os.path.join(base, f'{code}.json'), encoding='utf-8') as f:
                _TRANSLATIONS[code] = json.load(f)
    return _TRANSLATIONS
def detect_lang(session, request):
    lang = session.get('lang') or request.cookies.get('lang')
    if not lang:
        al = request.headers.get('Accept-Language','').lower()
        lang = 'en' if al.startswith('en') else 'zh'
    return lang if lang in ('zh','en') else 'zh'
def translate(key, lang, **kwargs):
    d = _load()
    s = d.get(lang, d['zh']).get(key, d['zh'].get(key, key))  # zh -> 原文
    for k,v in kwargs.items():
        s = s.replace('{'+k+'}', str(v))
    return s
```

### 第 2 步:后端接入(`smartgallery.py`)

**位置**:紧跟 [smartgallery.py#L690-L691](file:///e:/AI/smart-comfyui-gallery/smartgallery.py#L690-L691) `app = Flask(...)` / `app.secret_key = ...` 之后。

新增:
```python
from i18n import detect_lang, translate, _load

@app.context_processor
def inject_i18n():
    lang = detect_lang(session, request)
    return {'lang': lang, 't': _load().get(lang, _load()['zh'])}

@app.template_filter('_')
def _i18n_filter(key):
    return translate(key, detect_lang(session, request))
```

**新增切换路由**(复用 [smartgallery.py#L9176-L9179](file:///e:/AI/smart-comfyui-gallery/smartgallery.py#L9176-L9179) `toggle_my_ratings` 模式):
```python
@app.route('/galleryout/api/set_lang', methods=['POST'])
def set_lang():
    lang = request.form.get('lang', 'zh')
    if lang not in ('zh','en'): lang = 'zh'
    session['lang'] = lang
    resp = jsonify({'status':'success','lang':lang})
    resp.set_cookie('lang', lang, max_age=60*60*24*365)
    return resp
```

### 第 3 步:前端接入(每个顶层模板)

**对 `index.html`、`exhibition.html`、`exhibition_login.html` 各做一次**:

1. `<html lang="en">` → `<html lang="{{ lang }}">`(参考 [index.html#L4](file:///e:/AI/smart-comfyui-gallery/templates/index.html#L4))
2. 紧跟 `<title>` 后(参考 [index.html#L8](file:///e:/AI/smart-comfyui-gallery/templates/index.html#L8))注入:
   ```html
   <script>window.lang = {{ lang | tojson }}; window.i18n = {{ t | tojson }};</script>
   ```
3. 在已有早期 `<script>` 块(参考 [index.html#L13](file:///e:/AI/smart-comfyui-gallery/templates/index.html#L13))内补一个 JS `t()` 函数:
   ```javascript
   function t(key, vars){
     let s = (window.i18n && window.i18n[key]) || key;
     if (vars) for (const k in vars) s = s.split('{'+k+'}').join(vars[k]);
     return s;
   }
   ```

服务器端 Jinja `{{ _('...') }}` 已在首次 paint 时输出正确语言,无 FOUC;JS 渲染的动态文本依赖 `<head>` 中同步注入的 `window.i18n`,在所有 DOM 脚本运行前可用。

### 第 4 步:静态 HTML 文本改造模式(代表性 before/after)

对 `index.html` 中所有硬编码英文文本套用 `{{ _('...') }}` 过滤器。代表性示例:

| 位置 | before | after |
|---|---|---|
| [L270](file:///e:/AI/smart-comfyui-gallery/templates/index.html#L270) 弹窗标题 | `⚙️ Settings & Info` | `⚙️ {{ _('Settings & Info') }}` |
| [L271](file:///e:/AI/smart-comfyui-gallery/templates/index.html#L271) title 属性 | `title="Close Menu"` | `title="{{ _('Close Menu') }}"` |
| [L296](file:///e:/AI/smart-comfyui-gallery/templates/index.html#L296) 选项标签 | `📑 List View` | `📑 {{ _('List View') }}` |
| [L297-L298](file:///e:/AI/smart-comfyui-gallery/templates/index.html#L297-L298) 选项描述 | `Switch between the standard Grid and the compact List layout.` | `{{ _('Switch between the standard Grid and the compact List layout.') }}` |
| [L301](file:///e:/AI/smart-comfyui-gallery/templates/index.html#L301) 状态值 | `GRID` | `{{ _('GRID') }}` |
| 侧栏 tab(参考 [L617-L687](file:///e:/AI/smart-comfyui-gallery/templates/index.html#L617-L687)) | `Folders` / `Collections` / `Status` | `{{ _('Folders') }}` 等 |
| 搜索框 placeholder | `placeholder="Search folders..."` | `placeholder="{{ _('Search folders...') }}"` |

**`list_view.html` 列表表头**([L7 注释列出的列](file:///e:/AI/smart-comfyui-gallery/templates/list_view.html#L7) `Index|Thumb|Name|Rating|Comments|Size|Dims|Duration|Type|Date|Actions`)在 [L1201](file:///e:/AI/smart-comfyui-gallery/templates/index.html#L1201) `list-view-header` 中渲染,每列文本套 `{{ _('Index') }}` 等。

### 第 5 步:JS 动态字符串改造模式

对 `index.html` 内联 JS 中的模板字符串、`alert()`、`confirm()` 套用 `t('key')`:

| 位置 | before | after |
|---|---|---|
| [L3034-L3086](file:///e:/AI/smart-comfyui-gallery/templates/index.html#L3034-L3086) 批量菜单 | `>ℹ️ Info</button>`, `>✏️ Rename</button>`, `>⛓️ Unmount</button>`, `title="Move here"` | `` `>`+t('Info')+`</button>` ``, `t('Rename')`, `t('Unmount')`, `` title="${t('Move here')}" `` |
| 同上文件数提示 | `title="${fileCount} direct files"` | `` title="${t('{n} direct files',{n:fileCount})}" `` |
| 任意 alert/confirm | `alert('Please select at least one item.')` | `alert(t('Please select at least one item.'))` |

`js/generation_metadata.js` 若含用户可见字符串,同样用 `window.t()` 处理(`window.i18n` 已通过 `index.html` 注入,所有外部 JS 可访问)。

### 第 6 步:语言切换器 UI

**插入位置**:`#options-popover` 末尾闭合 `</div>` 前(参考 [index.html#L386-L387](file:///e:/AI/smart-comfyui-gallery/templates/index.html#L386-L387),"What's New" 选项之后)。沿用现有 `.opt-item` 模式:

```html
<div class="opt-item" id="opt-btn-lang" onclick="toggleLanguage()">
    <div>
        <div class="opt-label" style="display:flex;align-items:center;gap:8px;">🌐 {{ _('Language') }}</div>
        <div style="font-size:0.75rem;color:var(--text-muted);line-height:1.3;margin-top:4px;">
            {{ _('Switch interface language between Chinese and English.') }}
        </div>
    </div>
    <span class="opt-status" id="opt-status-lang" style="align-self:center;">{{ '中文' if lang=='zh' else 'English' }}</span>
</div>
```

JS(放入 index.html 既有 `<script>` 块):
```javascript
function toggleLanguage(){
  const next = window.lang === 'zh' ? 'en' : 'zh';
  fetch('/galleryout/api/set_lang',{
      method:'POST',
      headers:{'Content-Type':'application/x-www-form-urlencoded'},
      body:'lang='+next
  }).then(()=>location.reload());
}
```

**`exhibition.html`**:在其 options popover 内加同样选项项 + 同一 `toggleLanguage()` 函数。
**`exhibition_login.html`**:在登录卡片底部加一个 `🌐 中文 / English` 链接,点击调同一 fetch 接口后 reload。登录页无 session,靠 cookie 持久化即可(`detect_lang` 会读 cookie)。

### 第 7 步:模态子模板全覆盖

对 `templates/modals/` 下每个文件,把所有用户可见英文套 `{{ _('...') }}`:
- `changelog.html`、`clustering_modal.html`、`comfy_queue_manager.html`(~178KB,重点)、`generation_metadata.html`、`omniquery_modal.html`(~65KB)、`remix_modal.html`(~332KB,最大单文件,重点)、`user_manager_module.html`、`whats_new_modal.html`。

它们通过 `{% include %}`(参考 [index.html#L2547-L2553](file:///e:/AI/smart-comfyui-gallery/templates/index.html#L2547-L2553)、[L12656](file:///e:/AI/smart-comfyui-gallery/templates/index.html#L12656))注入,自动享有 `{{ _('...') }}` 过滤器与 `{{ t }}` 字典;无需各自注入 `window.i18n`。

### 第 8 步:提取 key 并填充字典

完成模板改造后:
1. 用正则在所有模板中提取 `{{ _('X') }}` 与 `t('X')` 内的 `X`,去重得到全部 key。
2. 写入 `translations/en.json`(key=value 自身)。
3. 人工翻译为 `translations/zh.json`。
4. 重复文本(同一英文多处出现)对应同一 key,字典只留一条 — 翻译去重。

---

## 关键改动文件清单

**新建**:
- `e:\AI\smart-comfyui-gallery\i18n.py`
- `e:\AI\smart-comfyui-gallery\translations\zh.json`
- `e:\AI\smart-comfyui-gallery\translations\en.json`

**修改**:
- `e:\AI\smart-comfyui-gallery\smartgallery.py` — context processor + `_` 过滤器 + `/set_lang` 路由(紧跟 L690-L691 与 L9179 模式)
- `e:\AI\smart-comfyui-gallery\templates\index.html` — L4 lang 属性、L8 注入、L13+ `t()` 函数、L266-L387 切换器 UI、全部静态文本与 JS 模板字符串
- `e:\AI\smart-comfyui-gallery\templates\exhibition.html` — 同 index.html 的接入三件套 + 切换器
- `e:\AI\smart-comfyui-gallery\templates\exhibition_login.html` — 接入三件套 + 底部语言链接
- `e:\AI\smart-comfyui-gallery\templates\collections.html`、`list_view.html` — 模态/表头文本
- `e:\AI\smart-comfyui-gallery\templates\modals\*.html`(8 个)— 全部用户可见文本
- `e:\AI\smart-comfyui-gallery\templates\js\generation_metadata.js` — 若含可见字符串

---

## 验证步骤

1. **启动**:`python e:\AI\smart-comfyui-gallery\smartgallery.py`,浏览器访问主路由。
2. **默认中文**:首页渲染为中文,DevTools 检查 `<html lang="zh">`;侧栏、工具栏、设置弹窗均为中文。
3. **切换持久化**:打开"设置"弹窗 → 点"🌐 语言"(状态显示"中文")→ 页面 reload 为英文,`<html lang="en">`;再次 reload 仍为英文(cookie 生效)。切回中文同理。
4. **模态中文**:打开 Remix / What's New / OmniQuery 模态,确认中文。
5. **JS 动态菜单**:右键文件夹 → 确认菜单项为"信息/重命名/卸载/移动到此处";选中多个项目 → 确认"已选 N 项"。
6. **Accept-Language 探测**:清除 cookie + session,浏览器设 `Accept-Language: en-US` → reload → 自动英文;改为 `zh-CN` → 自动中文。
7. **展览模式**:访问展览路由 + 登录页,确认同样可切换且默认中文。
8. **Network 检查**:首页源码中 `window.i18n` 已填充;JS 渲染的 DOM 无英文漏译。

---

## 风险与工作量提示

- **体量**:约 1.4MB 模板(index 722KB、exhibition 347KB、remix_modal 332KB、comfy_queue_manager 178KB、omniquery 65KB)。预计 **1500-2500 条**唯一可翻译字符串,60-70% 在 JS 模板字符串中。这是大量机械性工作,建议按"先高频可见 UI → 再模态 → 再 JS 动态"的顺序推进,每完成一段即可阶段性自测。
- **重复文本**:同一英文多处出现是正常的,key 去重后字典只留一条。
- **插值**:统一用 `{name}` 占位;JS `t()` 与 Python `translate()` 的替换逻辑一致。
- **FOUC**:仅 JS 渲染文本可能闪;`window.i18n` 在 `<head>` 同步注入,先于任何 DOM 脚本,已规避。
- **`exhibition_login.html`**:登录前无 session,语言完全靠 cookie + Accept-Language,已由 `detect_lang` 处理。
