import math
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

MAX_URL_LENGTH = 2048

SHORTENERS = {
    "bit.ly", "tinyurl.com", "goo.gl", "t.co", "is.gd", "cutt.ly", "ow.ly", "clck.ru", "rb.gy",
    "shorturl.at", "tiny.cc", "buff.ly", "rebrand.ly", "bl.ink", "v.gd", "u.to", "qps.ru",
}
SUSPICIOUS_WORDS = (
    "login", "verify", "secure", "account", "update", "bank", "confirm", "password", "bonus",
    "free", "prize", "signin", "wallet", "unlock", "kaspi", "halyk",
)
SUSPICIOUS_TLDS = {"xyz", "top", "click", "zip", "work", "rest", "fit", "gq", "tk", "ml", "cf", "ga", "country", "loan"}

FEATURE_NAMES = (
    "url_length",
    "host_length",
    "path_length",
    "query_length",
    "dots",
    "hyphens",
    "digits",
    "special_chars",
    "subdomains",
    "path_depth",
    "query_params",
    "has_ip",
    "has_https",
    "nonstandard_port",
    "has_at",
    "double_slash_in_path",
    "is_shortener",
    "suspicious_words",
    "has_punycode",
    "mixed_scripts",
    "suspicious_tld",
    "host_entropy",
)

URL_IN_TEXT = re.compile(
    r"(?:https?://|www\.)[^\s<>\"']+"
    r"|(?<![\w@.-])(?:[\w-]+\.)+[^\W\d_]{2,}/[^\s<>\"']+"
    r"|(?<![\w@.-])(?:[\w-]+\.)+(?:com|net|org|info|biz|ru|kz|su|uk|рф|қаз|xyz|top|click|zip|example|test)(?:/[^\s<>\"']*)?",
    re.IGNORECASE,
)
TRAILING = ".,!?;:)]»\"'"


@dataclass
class UrlParts:
    scheme: str
    host: str
    port: int | None
    path: str
    query: str
    has_at: bool


def normalize_url(raw: str) -> str:
    value = raw.strip()
    if not value:
        raise ValueError("Введите ссылку.")
    if len(value) > MAX_URL_LENGTH:
        raise ValueError(f"Ссылка длиннее {MAX_URL_LENGTH} символов.")
    if re.search(r"\s", value):
        raise ValueError("В ссылке не должно быть пробелов.")
    if not re.match(r"^[a-z][a-z0-9+.-]*://", value, re.IGNORECASE):
        value = "http://" + value
    scheme = value.split("://", 1)[0].lower()
    if scheme not in {"http", "https"}:
        raise ValueError("Поддерживаются только ссылки http:// и https://.")
    if not split_url(value).host:
        raise ValueError("В ссылке нет адреса сайта.")
    return value


def split_url(url: str) -> UrlParts:
    parts = urlsplit(url)
    authority = parts.netloc
    host_port = authority.rsplit("@", 1)[-1]
    port = None
    match = re.search(r":(\d+)$", host_port)
    if match:
        port = int(match.group(1))
        host_port = host_port[: match.start()]
    return UrlParts(
        scheme=parts.scheme.lower(),
        host=host_port.lower().strip("[]"),
        port=port,
        path=parts.path,
        query=parts.query,
        has_at="@" in authority,
    )


def find_urls(text: str, limit: int = 3) -> list[str]:
    found = []
    for match in URL_IN_TEXT.finditer(text):
        url = match.group().rstrip(TRAILING)
        if url and url not in found:
            found.append(url)
        if len(found) == limit:
            break
    return found


def _entropy(value: str) -> float:
    if not value:
        return 0.0
    counts = {char: value.count(char) for char in set(value)}
    return -sum(count / len(value) * math.log2(count / len(value)) for count in counts.values())


def extract_url_features(url: str) -> dict[str, float]:
    parts = split_url(url)
    host = parts.host
    labels = [label for label in host.split(".") if label]
    is_ip = bool(re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host)) or ":" in host
    lowered = url.lower()
    return {
        "url_length": len(url),
        "host_length": len(host),
        "path_length": len(parts.path),
        "query_length": len(parts.query),
        "dots": url.count("."),
        "hyphens": host.count("-"),
        "digits": sum(char.isdigit() for char in url),
        "special_chars": sum(url.count(char) for char in "@~%&=_+"),
        "subdomains": 0 if is_ip else max(len(labels) - 2, 0),
        "path_depth": len([piece for piece in parts.path.split("/") if piece]),
        "query_params": len([piece for piece in parts.query.split("&") if piece]),
        "has_ip": float(is_ip),
        "has_https": float(parts.scheme == "https"),
        "nonstandard_port": float(parts.port not in (None, 80, 443)),
        "has_at": float(parts.has_at),
        "double_slash_in_path": float("//" in parts.path),
        "is_shortener": float(host in SHORTENERS),
        "suspicious_words": sum(word in lowered for word in SUSPICIOUS_WORDS),
        "has_punycode": float("xn--" in host),
        "mixed_scripts": float(bool(re.search(r"[a-z]", host)) and bool(re.search(r"[а-яё]", host))),
        "suspicious_tld": float(bool(labels) and labels[-1] in SUSPICIOUS_TLDS),
        "host_entropy": round(_entropy(host.replace(".", "")), 3),
    }


URL_CHECKS = (
    ("has_https", "Защищённое соединение HTTPS", lambda v: v == 0, lambda v: "есть" if v else "нет", 1, "нет защищённого соединения HTTPS"),
    ("has_ip", "IP-адрес вместо домена", lambda v: v == 1, lambda v: "да" if v else "нет", 2, "IP-адрес вместо имени сайта"),
    ("has_at", "Символ @ в адресе", lambda v: v == 1, lambda v: "да" if v else "нет", 2, "символ @ подменяет настоящий адрес"),
    ("has_punycode", "Punycode в домене", lambda v: v == 1, lambda v: "да" if v else "нет", 2, "домен в Punycode может маскироваться под знакомый"),
    ("mixed_scripts", "Смешение латиницы и кириллицы", lambda v: v == 1, lambda v: "да" if v else "нет", 2, "в домене смешаны латиница и кириллица"),
    ("is_shortener", "Сокращатель ссылок", lambda v: v == 1, lambda v: "да" if v else "нет", 1, "сокращатель скрывает настоящий адрес"),
    ("suspicious_words", "Подозрительные слова", lambda v: v > 0, lambda v: str(int(v)), 1, "подозрительные слова в адресе"),
    ("subdomains", "Поддомены", lambda v: v >= 2, lambda v: str(int(v)), 1, "много поддоменов"),
    ("hyphens", "Дефисы в домене", lambda v: v >= 2, lambda v: str(int(v)), 1, "много дефисов в домене"),
    ("suspicious_tld", "Подозрительная доменная зона", lambda v: v == 1, lambda v: "да" if v else "нет", 1, "доменная зона часто используется мошенниками"),
    ("nonstandard_port", "Нестандартный порт", lambda v: v == 1, lambda v: "да" if v else "нет", 1, "нестандартный порт"),
    ("double_slash_in_path", "Двойной // в пути", lambda v: v == 1, lambda v: "да" if v else "нет", 1, "двойной // в пути"),
    ("url_length", "Длина ссылки", lambda v: v > 75, lambda v: f"{int(v)} симв.", 1, "очень длинная ссылка"),
)


def explain_url(features: dict[str, float]) -> list[dict]:
    rows = []
    for key, label, is_hit, show, weight, reason in URL_CHECKS:
        value = features[key]
        rows.append({"key": key, "label": label, "value": show(value), "hit": bool(is_hit(value)), "weight": weight, "reason": reason})
    return rows


def rule_url_probability(features: dict[str, float]) -> float:
    weight = 0
    for row in explain_url(features):
        if row["hit"]:
            weight += min(int(features["suspicious_words"]), 2) if row["key"] == "suspicious_words" else row["weight"]
    return round(min(0.05 + weight * 0.15, 0.97), 2)


def analyse_url(url: str) -> dict:
    features = extract_url_features(url)
    return {
        "url": url,
        "host": split_url(url).host,
        "features": features,
        "checks": explain_url(features),
        "probability": rule_url_probability(features),
    }
