import pytest


@pytest.mark.django_db
def test_home_redirects_guest_to_login(client):
    response = client.get("/")
    assert response.status_code == 302
    assert response.url.startswith("/login/")


@pytest.mark.django_db
def test_login_page_opens(client):
    response = client.get("/login/")
    assert response.status_code == 200
    assert "Sentinel" in response.content.decode("utf-8")


def test_health_endpoint(client):
    response = client.get("/api/v1/health/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert set(response.json()["models"]) == {"sms", "url"}
