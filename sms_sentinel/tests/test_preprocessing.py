"""Модульные тесты предобработки (задание 4)."""
import pandas as pd
import pytest

from ml.data.clean_sms import clean_dataset
from ml.preprocessing import normalize_sms, strip_stopwords


def test_empty_string():
    assert normalize_sms("") == ""


def test_only_spaces():
    assert normalize_sms(" \t\n  ") == ""


def test_only_url():
    assert normalize_sms("https://example.com/login?id=5") == "<url>"


@pytest.mark.parametrize("text", ["www.example.com", "bit.ly/abc123", "example.test", "пример.рф", "tinyurl.com/x"])
def test_url_without_scheme(text):
    assert normalize_sms(text) == "<url>"


def test_url_does_not_swallow_pressure_mark():
    assert normalize_sms("go http://secure.example!") == "go <url> !"


def test_mixed_case():
    assert normalize_sms("СрОчНо ПроВерьте CARD") == "срочно проверьте card"


def test_cyrillic_kept():
    assert normalize_sms("Ваша карта заблокирована") == "ваша карта заблокирована"


def test_kazakh_letters_kept():
    assert normalize_sms("ӘҒҚҢӨҰҮҺІ әғқңөұүһі") == "әғқңөұүһі әғқңөұүһі"


@pytest.mark.parametrize(
    "text",
    ["$100", "£1.50", "₸500", "5000 руб", "50 000 тг", "10 000 теңге", "1 500,50 руб."],
)
def test_money(text):
    assert normalize_sms(text) == "<money>"


@pytest.mark.parametrize("text", ["+7 700 000 00 00", "8 (700) 000-00-00", "09061701461", "0800 195 6669"])
def test_phone(text):
    assert normalize_sms(text) == "<phone>"


def test_short_code_is_number_not_phone():
    assert normalize_sms("text to 87121") == "text to <num>"


def test_plain_numbers_and_time():
    assert normalize_sms("в 18:00 кабинет 12") == "в <num>:<num> кабинет <num>"


def test_email():
    assert normalize_sms("Write to user.name@example.org now") == "write to <email> now"


def test_emoji_kept_without_error():
    assert normalize_sms("Привет 😀👍") == "привет 😀👍"


def test_repeated_marks_collapsed_and_separated():
    assert normalize_sms("WIN!!! Really???") == "win ! really ?"


def test_control_and_invisible_characters_removed():
    assert normalize_sms("a\x00b​c\td") == "a bc d"


def test_cp1252_apostrophe_fixed():
    assert normalize_sms("I\x92m") == "i'm"


def test_nfkc_applied():
    assert normalize_sms("ＦＲＥＥ") == "free"


def test_obfuscated_words_kept_for_char_ngrams():
    assert normalize_sms("fr33 b@nk") == "fr33 b@nk"


def test_uci_placeholders_become_tokens():
    assert normalize_sms("call &lt;#&gt; at &lt;TIME&gt; &amp; pay &lt;UKP&gt;") == "call <num> at <num> & pay <money>"


def test_stopwords_are_optional():
    text = "this is the bank"
    assert normalize_sms(text) == text
    assert normalize_sms(text, remove_stopwords=True) == "bank"
    assert strip_stopwords("мен банк") == "банк"


def test_function_is_pure_and_repeatable():
    text = "Срочно! Оплатите 100 тг"
    first = normalize_sms(text)
    assert normalize_sms(text) == first
    assert text == "Срочно! Оплатите 100 тг"


def test_non_string_rejected():
    with pytest.raises(TypeError):
        normalize_sms(None)


def test_clean_dataset_removes_empty_and_duplicates_by_class():
    df = pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "text": ["Hello", "HELLO", "   ", "win $5", "WIN $9"],
            "label": [0, 0, 0, 1, 1],
        }
    )
    clean, stats = clean_dataset(df)
    assert clean["id"].tolist() == [1, 4]
    assert clean.columns.tolist() == ["id", "text_raw", "text_clean", "label"]
    assert stats["empty"] == 1
    assert stats["duplicates_ham"] == 1
    assert stats["duplicates_spam"] == 1
