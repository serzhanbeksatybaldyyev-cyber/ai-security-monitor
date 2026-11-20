import pytest
from django.contrib.auth.models import User
from django.core.cache import cache

from apps.accounts.models import UserProfile
from apps.analysis.models import Check, DetectedFeature
from apps.analysis.services import mask_text
from ml.language import detect_language
from ml.risk import sms_risk, url_risk
from ml.url_features import FEATURE_NAMES, analyse_url, extract_url_features, find_urls, normalize_url

FRAUD_SMS = "Ваша карта заблокирована! Срочно подтвердите данные по ссылке: http://secure-bank-verify.example/login"


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


@pytest.fixture
def user(db):
    return User.objects.create_user("student", "student@example.com", "secret12345")


@pytest.fixture
def auth_client(client, user):
    client.force_login(user)
    return client


def test_pages_require_login(client, db):
    for url in ["/", "/check/sms/", "/check/url/", "/history/", "/profile/"]:
        response = client.get(url)
        assert response.status_code == 302
        assert "/login/" in response.url


def test_register_creates_user_and_logs_in(client, db):
    response = client.post("/register/", {"username": "new_user", "email": "n@example.com", "password1": "strongpass77", "password2": "strongpass77"})
    assert response.status_code == 302
    assert User.objects.filter(username="new_user").exists()
    assert client.get("/").status_code == 200


def test_register_rejects_bad_login_and_duplicate_email(client, user):
    response = client.post("/register/", {"username": "ab", "email": "student@example.com", "password1": "strongpass77", "password2": "strongpass77"})
    text = response.content.decode("utf-8")
    assert "от 3 до 30 символов" in text
    assert "уже зарегистрирован" in text


def test_login_locks_after_five_failures(client, user):
    for _ in range(5):
        client.post("/login/", {"username": "student", "password": "wrong"})
    response = client.post("/login/", {"username": "student", "password": "secret12345"})
    assert "Слишком много неудачных попыток" in response.content.decode("utf-8")
    assert "_auth_user_id" not in client.session


def test_sms_check_saves_masked_record_and_redirects(auth_client, user):
    response = auth_client.post("/check/sms/", {"text": FRAUD_SMS})
    check = Check.objects.get(user=user)
    assert response.status_code == 302
    assert response.url == f"/check/sms/?result={check.pk}"
    assert check.input_text is None
    assert check.input_masked
    assert check.category == "fraud"
    assert check.language == "ru"
    assert check.url_results.get().domain == "secure-bank-verify.example"
    assert set(check.features.values_list("code", flat=True)) >= {"URGENCY", "ACCOUNT_BLOCK"}
    assert check.sms_model_version.version == "sms_multilingual_v2"
    page = auth_client.get(response.url).content.decode("utf-8")
    assert "оценка текста ненадёжна" in page
    assert "<a href=\"http://secure-bank-verify" not in page


def test_sms_check_keeps_text_with_consent(auth_client, user):
    profile = UserProfile.for_user(user)
    profile.store_sms_text = True
    profile.save()
    auth_client.post("/check/sms/", {"text": FRAUD_SMS})
    assert Check.objects.get(user=user).input_text == FRAUD_SMS


def test_empty_sms_is_rejected_without_500(auth_client, user):
    response = auth_client.post("/check/sms/", {"text": "    "})
    assert response.status_code == 200
    assert "не может быть пустым" in response.content.decode("utf-8")
    assert not Check.objects.exists()


def test_script_tag_is_escaped(auth_client, user):
    UserProfile.objects.update_or_create(user=user, defaults={"store_sms_text": True})
    response = auth_client.post("/check/sms/", {"text": "<script>alert(1)</script> hello"}, follow=True)
    page = response.content.decode("utf-8")
    assert "<script>alert(1)</script>" not in page
    assert "&lt;script&gt;" in page


def test_url_check_and_validation(auth_client, user):
    response = auth_client.post("/check/url/", {"url": "http://192.0.2.15:8080/account-update"})
    check = Check.objects.get(user=user)
    assert response.status_code == 302
    assert check.check_type == "url"
    assert check.input_text == "http://192.0.2.15:8080/account-update"
    assert check.category == "fraud"
    bad = auth_client.post("/check/url/", {"url": "ftp://example.com"})
    assert "Поддерживаются только" in bad.content.decode("utf-8")


def test_foreign_check_returns_404(auth_client, db):
    other = User.objects.create_user("other", "o@example.com", "secret12345")
    check = Check.objects.create(user=other, check_type="url", input_text="https://example.com", input_masked="https://example.com", category="safe", risk_score=5, risk_level="low")
    assert auth_client.get(f"/checks/{check.pk}/").status_code == 404
    assert auth_client.post(f"/checks/{check.pk}/delete/").status_code == 404


def test_history_filters_pagination_delete_and_export(auth_client, user):
    for index in range(22):
        Check.objects.create(user=user, check_type="sms" if index % 2 else "url", input_masked=f"text {index}", category="safe", risk_score=5, risk_level="low")
    page = auth_client.get("/history/").content.decode("utf-8")
    assert "Показано 1–20 из 22" in page
    assert "Показано 21–22 из 22" in auth_client.get("/history/?page=2").content.decode("utf-8")
    assert "Всего записей: 11" in auth_client.get("/history/?type=url").content.decode("utf-8")
    target = Check.objects.filter(user=user).first()
    assert "Удалить запись из истории?" in auth_client.get(f"/checks/{target.pk}/delete/").content.decode("utf-8")
    assert Check.objects.filter(pk=target.pk).exists()
    auth_client.post(f"/checks/{target.pk}/delete/")
    assert not Check.objects.filter(pk=target.pk).exists()
    export = auth_client.get("/history/export/")
    assert export["Content-Type"].startswith("text/csv")
    assert export.content.decode("utf-8-sig").count("\n") == 22


def test_dashboard_counts(auth_client, user):
    first = Check.objects.create(user=user, check_type="sms", input_masked="a", category="fraud", risk_score=90, risk_level="high")
    DetectedFeature.objects.create(check_record=first, code="URGENCY", title="Срочность")
    Check.objects.create(user=user, check_type="url", input_masked="b", category="safe", risk_score=5, risk_level="low")
    response = auth_client.get("/")
    assert response.context["total"] == 2
    assert response.context["sms_total"] == 1
    assert response.context["top_signs"][0]["label"] == "Срочность"
    assert response.context["average_score"] == 48
    assert auth_client.get("/?period=90").context["period"] == "90"


def test_profile_consent_toggle(auth_client, user):
    auth_client.post("/profile/", {"section": "settings", "store_sms_text": "on", "preferred_language": "kk"})
    profile = UserProfile.for_user(user)
    assert profile.store_sms_text
    assert profile.preferred_language == "kk"


def test_url_features_and_helpers():
    features = extract_url_features("http://user@xn--bnk-sna.test:8080//a/b?x=1&y=2")
    assert set(FEATURE_NAMES) <= set(features)
    assert len(FEATURE_NAMES) >= 20
    assert features["has_at"] == features["has_punycode"] == features["nonstandard_port"] == features["double_slash_in_path"] == 1
    assert features["query_params"] == 2
    assert analyse_url("https://www.example.com/about")["probability"] < 0.35
    assert normalize_url("example.com") == "http://example.com"
    with pytest.raises(ValueError):
        normalize_url("has space.com")
    assert find_urls("Перейдите: bit.ly/abc, и www.example.com!") == ["bit.ly/abc", "www.example.com"]


def test_language_risk_and_mask():
    assert detect_language("Сәлем, қалайсың?") == "kk"
    assert detect_language("Привет") == "ru"
    assert detect_language("Hello there") == "en"
    assert detect_language("12345") == "other"
    assert sms_risk(0.95, [0.8], 3, "en").category == "fraud"
    assert sms_risk(0.02, [], 0, "en").category == "safe"
    assert sms_risk(None, [], 2, "ru").score > 0
    assert url_risk(0.5).level == "medium"
    assert mask_text("Оплатите 500 тг на http://x.example, тел. +7 000 000 00 00") == "Оплатите *** на http://x.example, тел. ***"
    assert mask_text("Карта 4400 0000 0000 0000, код 4821, встреча в 18:00") == "Карта ***, код ***, встреча в 18:00"


def test_result_is_shown_next_to_form(auth_client, user):
    auth_client.post("/check/sms/", {"text": FRAUD_SMS})
    check = Check.objects.get(user=user)
    page = auth_client.get(f"/check/sms/?result={check.pk}").content.decode("utf-8")
    assert "Похоже на мошенничество" in page
    assert "Почему такой результат" in page
    assert "Здесь появится результат" not in page
    empty = auth_client.get("/check/sms/").content.decode("utf-8")
    assert "Здесь появится результат" in empty


def test_foreign_result_param_is_hidden(auth_client, user, db):
    from django.contrib.auth.models import User

    other = User.objects.create_user("other", "other@example.com", "secret12345")
    check = Check.objects.create(user=other, check_type="sms", input_masked="x", category="safe", risk_score=5, risk_level="low")
    assert auth_client.get(f"/check/sms/?result={check.pk}").status_code == 404
    assert auth_client.get("/check/sms/?result=abc").status_code == 200


def test_url_result_and_features_on_same_page(auth_client, user):
    response = auth_client.post("/check/url/", {"url": "http://192.0.2.15:8080/account-update"})
    check = Check.objects.get(user=user)
    assert response.url == f"/check/url/?result={check.pk}"
    page = auth_client.get(response.url).content.decode("utf-8")
    assert "Признаки адреса" in page
    assert "Опасная ссылка" in page or "Ссылка вызывает сомнения" in page


def test_history_filter_form_keeps_values(auth_client, user):
    page = auth_client.get("/history/?type=sms&level=high").content.decode("utf-8")
    assert 'name="type"' in page and 'name="level"' in page
    assert '<option value="sms" selected>' in page
    assert "Сбросить" in page


def test_stats_page_and_dashboard_chart_payload(auth_client, user):
    Check.objects.create(user=user, check_type="sms", input_masked="a", category="fraud", risk_score=90, risk_level="high")
    response = auth_client.get("/stats/?period=7")
    assert response.status_code == 200
    assert response.context["period"] == "7"
    daily = response.context["chart"]["daily"]
    assert len(daily["labels"]) == 7 and sum(daily["totals"]) == 1
    assert len(auth_client.get("/").context["chart"]["daily"]["labels"]) == 30


def test_double_submit_does_not_duplicate(auth_client, user):
    auth_client.post("/check/sms/", {"text": FRAUD_SMS})
    auth_client.post("/check/sms/", {"text": FRAUD_SMS})
    assert Check.objects.filter(user=user).count() == 1
