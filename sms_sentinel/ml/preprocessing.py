"""Очистка и нормализация SMS (задание 4).

Одна и та же функция normalize_sms используется при обучении и в веб-приложении.
"""
import html
import re
import unicodedata
from pathlib import Path

RESOURCES = Path(__file__).resolve().parent / "resources"


def _load_stopwords() -> frozenset[str]:
    """Стоп-слова NLTK (corpora/stopwords) лежат в проекте, скачивание не требуется."""
    words: set[str] = set()
    for language in ("en", "ru", "kk"):
        path = RESOURCES / f"stopwords_{language}.txt"
        words.update(line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    return frozenset(words)


STOPWORDS = _load_stopwords()

# В наборе UCI встречаются символы Windows-1252, ошибочно записанные как управляющие.
_CP1252 = str.maketrans({"\x91": "'", "\x92": "'", "\x93": '"', "\x94": '"', "\x96": "-", "\x97": "-"})

# Заглушки авторов UCI вместо скрытых значений. Без замены они попали бы в модель
# как признак ham: в спаме их почти нет.
_PLACEHOLDERS = (("<#>", "<num>"), ("<decimal>", "<num>"), ("<time>", "<num>"), ("<ukp>", "<money>"))

_END_OF_LINK = r"[^\s.,!?;:)\]»\"']"
_DOMAIN_ZONES = "com|net|org|info|biz|ru|kz|su|uk|рф|қаз|xyz|top|click|zip|example|test"
_NUMBER = r"\d{1,3}(?: \d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?"
_CURRENCY_SIGN = r"[$£€₸₽]"
_CURRENCY_WORD = r"(?:руб(?:\.|лей|ля|ль)?|тг|тенге|теңге|usd|kzt|rub|eur|gbp|pounds?|dollars?)(?!\w)"

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
URL_RE = re.compile(
    rf"(?:https?://|ftp://|www\.)\S*{_END_OF_LINK}"
    rf"|(?<![\w@.-])(?:[\w-]+\.)+(?:{_DOMAIN_ZONES})(?![\w-])(?:[/?#:]\S*{_END_OF_LINK})?"
    rf"|(?<![\w@.-])(?:[\w-]+\.)+[^\W\d_]{{2,}}/\S*{_END_OF_LINK}"
)
MONEY_RE = re.compile(
    rf"(?<!\w)(?:{_CURRENCY_SIGN} ?(?:{_NUMBER})|(?:{_NUMBER}) ?(?:{_CURRENCY_SIGN}|{_CURRENCY_WORD}))"
)
PHONE_CANDIDATE_RE = re.compile(r"(?<![\w+])\+?\d[\d ()\-]{7,}\d(?!\w)")
NUMBER_RE = re.compile(r"(?<![\w<])\d+(?:[.,]\d+)*(?![\w>])")
PUNCTUATION_RE = re.compile(r"!+|\?+")
SPACES_RE = re.compile(r"\s+")

MIN_PHONE_DIGITS, MAX_PHONE_DIGITS = 10, 15


def _replace_phone(match: re.Match) -> str:
    digits = sum(char.isdigit() for char in match.group())
    return "<phone>" if MIN_PHONE_DIGITS <= digits <= MAX_PHONE_DIGITS else match.group()


def _drop_control_characters(text: str) -> str:
    """Управляющие символы становятся пробелом, невидимые символы формата удаляются."""
    result = []
    for char in text:
        category = unicodedata.category(char)
        if category == "Cc":
            result.append(" ")
        elif category != "Cf":
            result.append(char)
    return "".join(result)


def strip_stopwords(text_clean: str) -> str:
    """Удаляет стоп-слова из уже нормализованного текста."""
    return " ".join(word for word in text_clean.split() if word not in STOPWORDS)


def normalize_sms(text: str, remove_stopwords: bool = False) -> str:
    """Возвращает нормализованный текст. Чистая функция: вход не изменяется, состояния нет."""
    if not isinstance(text, str):
        raise TypeError("normalize_sms ожидает строку")

    result = html.unescape(text).translate(_CP1252)
    result = unicodedata.normalize("NFKC", result)
    result = _drop_control_characters(result.lower())

    for placeholder, token in _PLACEHOLDERS:
        result = result.replace(placeholder, f" {token} ")

    # Порядок важен: e-mail содержит домен, а сумма и телефон содержат числа.
    result = EMAIL_RE.sub(" <email> ", result)
    result = URL_RE.sub(" <url> ", result)
    result = MONEY_RE.sub(" <money> ", result)
    result = PHONE_CANDIDATE_RE.sub(_replace_phone, result)
    result = NUMBER_RE.sub("<num>", result)
    result = PUNCTUATION_RE.sub(lambda match: f" {match.group()[0]} ", result)
    result = SPACES_RE.sub(" ", result).strip()

    return strip_stopwords(result) if remove_stopwords else result
