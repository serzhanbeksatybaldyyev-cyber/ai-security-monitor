import re

KAZAKH_LETTERS = set("әғқңөұүһі")
CYRILLIC = re.compile(r"[а-яё]")
LATIN = re.compile(r"[a-z]")

LANGUAGE_NAMES = {
    "ru": "русский",
    "kk": "казахский",
    "en": "английский",
    "other": "не определён",
}


def detect_language(text: str) -> str:
    lowered = text.lower()
    if any(char in KAZAKH_LETTERS for char in lowered):
        return "kk"
    cyrillic = len(CYRILLIC.findall(lowered))
    latin = len(LATIN.findall(lowered))
    if cyrillic == 0 and latin == 0:
        return "other"
    return "ru" if cyrillic >= latin else "en"
