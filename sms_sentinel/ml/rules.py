"""Словарь признаков социальной инженерии.

Первая версия для ручного признака из задания 6. Полный словарь (10+ выражений
в каждой группе) и объяснения для пользователя появятся в задании 12.
Выражения проверяются по нормализованному тексту, поэтому числа записаны как <num>.
"""
import re

RULE_GROUPS: dict[str, tuple[str, ...]] = {
    "URGENCY": (
        r"urgent", r"immediately", r"act now", r"expires?\b", r"final notice", r"last chance", r"within <num>",
        r"срочн", r"немедленно", r"в течение <num>", r"до конца дня", r"сегодня же",
        r"шұғыл", r"тез арада", r"дереу", r"бүгін ғана", r"сағат ішінде",
    ),
    "MONEY_TRANSFER": (
        r"transfer", r"send money", r"pay\b", r"payment", r"\bfee\b",
        r"перевед", r"перевод", r"оплат", r"скинь", r"комисси",
        r"аудар", r"ақша жібер", r"төле", r"теңге жібер",
    ),
    "BANK_CARD": (
        r"bank", r"\bcard\b", r"account", r"credit", r"debit",
        r"банк", r"карт[аыуе]", r"сч[её]т", r"кредит",
        r"картаң", r"шот", r"несие",
    ),
    "ACCOUNT_BLOCK": (
        r"blocked", r"suspended", r"locked", r"deactivat", r"unauthori[sz]ed", r"compromised",
        r"заблокир", r"блокировк", r"заморож", r"взлом",
        r"бұғатта", r"шектел", r"бұзылды", r"жабылады",
    ),
    "PRIZE": (
        r"won\b", r"winner", r"prize", r"claim", r"reward", r"congratulations", r"bonus", r"guaranteed",
        r"выигр", r"приз", r"подарок", r"бонус", r"поздравляем",
        r"ұтып", r"жүлде", r"сыйлық", r"құттықтаймыз",
    ),
    "CODE_REQUEST": (
        r"verification code", r"password", r"\bpin\b", r"\botp\b",
        r"код из sms", r"сообщите код", r"назовите код", r"пароль", r"cvv",
        r"кодты айт", r"кодын айт", r"кодты хабарла", r"құпиясөз",
    ),
}

_COMPILED = {
    code: re.compile("|".join(rf"(?<!\w){pattern}" for pattern in patterns))
    for code, patterns in RULE_GROUPS.items()
}


def find_rule_groups(text_clean: str) -> list[str]:
    """Возвращает коды сработавших групп для нормализованного текста."""
    return [code for code, pattern in _COMPILED.items() if pattern.search(text_clean)]
