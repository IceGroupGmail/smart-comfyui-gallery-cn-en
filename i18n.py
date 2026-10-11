"""SmartGallery i18n module.

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
