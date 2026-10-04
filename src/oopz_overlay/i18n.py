"""Approved copy, translated only where the application presents it."""
from functools import lru_cache
import json
import os
from pathlib import Path
import re
from PySide6.QtCore import QLocale


def language() -> str:
    preference = os.environ.get('LC_ALL') or os.environ.get('LC_MESSAGES') or os.environ.get('LANG')
    if preference and preference.split('.')[0] not in ('C', 'POSIX'):
        return 'en' if preference.lower().startswith('en') else 'zh'
    return 'en' if QLocale.system().language() == QLocale.Language.English else 'zh'


@lru_cache(maxsize=1)
def _catalog():
    entries = json.loads(Path(__file__).with_name('copy_catalog.json').read_text(encoding='utf-8'))
    entries.sort(key=lambda e: len(''.join(e['source'])), reverse=True)
    return [(entry, re.compile(r'\A' + '(.*?)'.join(re.escape(p) for p in entry['source']) + r'\Z', re.S)) for entry in entries]


def tr(value: str, locale: str | None = None, _depth: int = 0) -> str:
    locale = locale or language()
    for entry, pattern in _catalog():
        match = pattern.fullmatch(value)
        if match is None:
            continue
        parts = entry[locale]
        result = parts[0]
        for index, parameter in enumerate(match.groups()):
            if entry['trusted'][index] and _depth < 4:
                parameter = tr(parameter, locale, _depth + 1)
            result += parameter + parts[index+1]
        return result
    return value
