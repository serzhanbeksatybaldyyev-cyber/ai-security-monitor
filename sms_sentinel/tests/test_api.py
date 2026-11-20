import json

import pytest
from django.contrib.auth.models import User
from django.core.cache import cache

from apps.analysis.models import Check

FRAUD_SMS = "Ваша карта заблокирована! Срочно подтвердите данные по ссылке: http://secure-bank-verify.example/login"


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


@pytest.fixture
def user(db):
    return User.objects.create_user("apiuser", "api@example.com", "secret12345")


@pytest.fixture
def api(client, user):
    client.force_login(user)
    return client


def post(client, url, payload):
    return client.post(url, data=json.dumps(payload), content_type="application/json")


def test_check_sms_returns_spec_fields(api):
    response = post(api, "/api/v1/check/sms/", {"text": FRAUD_SMS})
    body = response.json()
    assert response.status_code == 200
    for key in ["id", "type", "language", "category", "risk_level", "risk_score", "p_sms", "urls", "features", "explanation", "recommendation", "disclaimer", "model_versions", "created_at"]:
        assert key in body
    assert body["type"] == "SMS" and body["category"] == "FRAUDULENT" and body["risk_level"] == "HIGH"
    assert body["urls"][0]["category"] in {"SUSPICIOUS", "DANGEROUS"}
    assert "URGENCY" in body["features"]


def test_check_url_and_validation_errors(api):
    ok = post(api, "/api/v1/check/url/", {"url": "http://192.0.2.15:8080/account-update"})
    assert ok.status_code == 200 and ok.json()["category"] == "DANGEROUS"
    empty = post(api, "/api/v1/check/sms/", {"text": "   "})
    assert empty.status_code == 400
    assert empty.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "text" in empty.json()["error"]["fields"]
    bad = post(api, "/api/v1/check/url/", {"url": "ftp://example.com"})
    assert bad.status_code == 400


def test_requires_login_returns_401(client, db):
    response = post(client, "/api/v1/check/sms/", {"text": "hi"})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_rate_limit_returns_429(api):
    codes = [post(api, "/api/v1/check/sms/", {"text": f"Привет, встреча в {i}:00"}).status_code for i in range(32)]
    assert codes[:30] == [200] * 30
    assert 429 in codes[30:]


def test_history_detail_delete_and_ownership(api, user):
    created = post(api, "/api/v1/check/sms/", {"text": FRAUD_SMS}).json()
    listing = api.get("/api/v1/checks/?type=sms").json()
    assert listing["count"] == 1 and listing["results"][0]["id"] == created["id"]
    assert api.get(f"/api/v1/checks/{created['id']}/").status_code == 200
    other = User.objects.create_user("other", "o@example.com", "secret12345")
    foreign = Check.objects.create(user=other, check_type="url", input_masked="x", category="safe", risk_score=1, risk_level="low")
    assert api.get(f"/api/v1/checks/{foreign.pk}/").status_code == 404
    assert api.delete(f"/api/v1/checks/{foreign.pk}/").status_code == 404
    assert api.delete(f"/api/v1/checks/{created['id']}/").status_code == 204
    assert api.get("/api/v1/checks/?category=BAD").status_code == 400


def test_stats_summary(api):
    post(api, "/api/v1/check/sms/", {"text": FRAUD_SMS})
    body = api.get("/api/v1/stats/summary/").json()
    assert body["total"] == 1 and len(body["chart"]["daily"]["labels"]) == 30


def test_auth_endpoints(client, db):
    register = post(client, "/api/v1/auth/register/", {"username": "newbie", "email": "n@example.com", "password1": "strongpass77", "password2": "strongpass77"})
    assert register.status_code == 201 and register.json()["username"] == "newbie"
    assert client.post("/api/v1/auth/logout/").status_code == 204
    assert post(client, "/api/v1/auth/login/", {"username": "newbie", "password": "wrong"}).status_code == 401
    assert post(client, "/api/v1/auth/login/", {"username": "newbie", "password": "strongpass77"}).status_code == 200
    for _ in range(5):
        post(client, "/api/v1/auth/login/", {"username": "newbie", "password": "bad"})
    assert post(client, "/api/v1/auth/login/", {"username": "newbie", "password": "strongpass77"}).status_code == 429
