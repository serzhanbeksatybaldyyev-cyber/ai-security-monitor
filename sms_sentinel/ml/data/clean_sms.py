"""Предобработка набора SMS (задание 4).

Запуск из корня проекта: python -m ml.data.clean_sms
Читает data/processed/sms_raw.csv, сохраняет data/processed/sms_clean.csv
и отчёт docs/04_preprocessing_report.md.
"""
import unicodedata
from pathlib import Path

import pandas as pd

from ml.data.load_sms import PROJECT_ROOT
from ml.preprocessing import normalize_sms

RAW_CSV = PROJECT_ROOT / "data" / "processed" / "sms_raw.csv"
CLEAN_CSV = PROJECT_ROOT / "data" / "processed" / "sms_clean.csv"
REPORT = PROJECT_ROOT / "docs" / "04_preprocessing_report.md"


def clean_dataset(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Возвращает очищенный набор и статистику по шагам."""
    result = df.rename(columns={"text": "text_raw"}).copy()
    result["text_raw"] = result["text_raw"].fillna("")
    result["text_clean"] = result["text_raw"].map(normalize_sms)

    raw, clean = result["text_raw"], result["text_clean"]
    stats = {
        "rows_in": len(result),
        "html": int(raw.str.contains(r"&(?:lt|gt|amp);", regex=True).sum()),
        "nfkc": int(raw.map(lambda text: unicodedata.normalize("NFKC", text) != text).sum()),
        "lower": int(raw.map(lambda text: text != text.lower()).sum()),
        "url": int(clean.str.contains("<url>", regex=False).sum()),
        "email": int(clean.str.contains("<email>", regex=False).sum()),
        "phone": int(clean.str.contains("<phone>", regex=False).sum()),
        "money": int(clean.str.contains("<money>", regex=False).sum()),
        "num": int(clean.str.contains("<num>", regex=False).sum()),
        "control": int(raw.map(lambda t: any(unicodedata.category(c) in ("Cc", "Cf") for c in t)).sum()),
        "punctuation": int(raw.str.contains(r"!!|\?\?", regex=True).sum()),
        "spaces": int(raw.str.contains(r"\s{2,}|^\s|\s$", regex=True).sum()),
    }

    empty = clean.str.len() == 0
    stats["empty"] = int(empty.sum())
    result = result[~empty]

    labels_per_text = result.groupby("text_clean")["label"].nunique()
    stats["conflicts"] = int((labels_per_text > 1).sum())

    duplicated = result.duplicated("text_clean", keep="first")
    stats["duplicates_ham"] = int((duplicated & (result["label"] == 0)).sum())
    stats["duplicates_spam"] = int((duplicated & (result["label"] == 1)).sum())
    result = result[~duplicated].reset_index(drop=True)

    stats["rows_out"] = len(result)
    stats["ham_out"] = int((result["label"] == 0).sum())
    stats["spam_out"] = int((result["label"] == 1).sum())
    return result[["id", "text_raw", "text_clean", "label"]], stats


def build_report(stats: dict) -> str:
    share = stats["spam_out"] / stats["rows_out"]
    rows = [
        ("Исходные записи", stats["rows_in"]),
        ("Раскодированы HTML-сущности (`&lt;`, `&gt;`, `&amp;`)", stats["html"]),
        ("Изменились при NFKC", stats["nfkc"]),
        ("Приведены к нижнему регистру", stats["lower"]),
        ("Есть `<url>`", stats["url"]),
        ("Есть `<email>`", stats["email"]),
        ("Есть `<phone>`", stats["phone"]),
        ("Есть `<money>`", stats["money"]),
        ("Есть `<num>`", stats["num"]),
        ("Удалены управляющие символы", stats["control"]),
        ("Сжаты повторы `!` и `?`", stats["punctuation"]),
        ("Убраны лишние пробелы", stats["spaces"]),
        ("Удалены как пустые", stats["empty"]),
        ("Удалены дубликаты класса ham (0)", stats["duplicates_ham"]),
        ("Удалены дубликаты класса spam (1)", stats["duplicates_spam"]),
        ("Итого записей", stats["rows_out"]),
    ]
    table = "\n".join(f"| {name} | {count} |" for name, count in rows)
    return f"""# Задание 4. Отчёт о предобработке SMS

Отчёт создан автоматически командой `python -m ml.data.clean_sms`.

| Шаг | Число записей |
|---|---:|
{table}

После очистки: ham — {stats['ham_out']}, spam — {stats['spam_out']}, доля spam {share:.2%}.
Текстов с разными метками после нормализации: {stats['conflicts']}.

## Порядок обработки

1. Раскодирование HTML-сущностей и исправление символов Windows-1252.
2. Нормализация Unicode NFKC и приведение к нижнему регистру.
3. Удаление управляющих и невидимых символов.
4. Замена заглушек набора UCI (`<#>`, `<decimal>`, `<time>`, `<ukp>`).
5. Замена сущностей: `<email>`, затем `<url>`, `<money>`, `<phone>`, `<num>`.
6. Сжатие повторов `!` и `?`, удаление лишних пробелов.

## Решения

- **Регистр токенов.** В ФТ-2.3 токены записаны заглавными буквами (`<URL>`), а в задании 4 строчными (`<url>`). Выбран вариант задания 4, потому что токены вставляются в текст, уже приведённый к нижнему регистру.
- **HTML-сущности и заглушки.** В наборе UCI скрытые значения заменены на `&lt;#&gt;`, `&lt;DECIMAL&gt;` и подобные. Этого нет в требованиях, но такие заглушки встречаются почти только в ham. Без замены модель выучила бы артефакт сбора данных, а не признак сообщения.
- **Числа внутри слов не заменяются.** Запись `fr33` и `b@nk` остаётся как есть, чтобы символьные N-граммы видели намеренные искажения.
- **Стоп-слова.** Удаление реализовано как опция `remove_stopwords=True`, по умолчанию выключено. Эффект проверяется в задании 8.
"""


def main() -> None:
    clean, stats = clean_dataset(pd.read_csv(RAW_CSV, encoding="utf-8", keep_default_na=False))
    clean.to_csv(CLEAN_CSV, index=False, encoding="utf-8")
    REPORT.write_text(build_report(stats), encoding="utf-8")
    for key, value in stats.items():
        print(f"{key}: {value}")
    print(f"Сохранено: {Path(CLEAN_CSV).relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
