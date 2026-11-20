import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command

from apps.analysis.models import Check, DetectedFeature, ModelVersion, UrlResult
from apps.analysis.services import save_sms_check
from apps.panel.models import AdminAction

SECRET_SMS = "Секретное сообщение: переведи 50 000 тг на +7 000 000 00 01"


@pytest.fixture(autouse=True)
def clear_cache():
    cache.clear()


@pytest.fixture
def admin_user(db):
    return User.objects.create_user("boss", "boss@example.com", "secret12345", is_staff=True)


@pytest.fixture
def plain_user(db):
    return User.objects.create_user("student", "student@example.com", "secret12345")


@pytest.fixture
def admin_client(client, admin_user):
    client.force_login(admin_user)
    return client


PANEL_PAGES = ["/panel/", "/panel/users/", "/panel/checks/", "/panel/models/", "/panel/audit/"]


def test_panel_is_closed_for_guests_and_users(client, plain_user):
    for url in PANEL_PAGES:
        assert "/login/" in client.get(url).url
    client.force_login(plain_user)
    for url in PANEL_PAGES:
        assert client.get(url).status_code == 403
    assert "Панель администратора" not in client.get("/").content.decode("utf-8")


def test_admin_sees_all_pages_and_both_panels(admin_client):
    for url in PANEL_PAGES:
        assert admin_client.get(url).status_code == 200
    assert "Панель администратора" in admin_client.get("/").content.decode("utf-8")


def test_login_sends_admin_to_panel_and_user_to_dashboard(client, admin_user, plain_user):
    response = client.post("/login/", {"username": "boss", "password": "secret12345"})
    assert response.url == "/panel/"
    client.logout()
    response = client.post("/login/", {"username": "student", "password": "secret12345"})
    assert response.url == "/"


def test_admin_stats_cover_everyone_without_texts(admin_client, plain_user, admin_user):
    save_sms_check(plain_user, SECRET_SMS, store_text=True)
    save_sms_check(admin_user, "Привет! Встречаемся завтра в 18:00.", store_text=True)
    overview = admin_client.get("/panel/")
    assert overview.context["total"] == 2
    assert overview.context["users_total"] == 2
    for url in ["/panel/", "/panel/checks/", f"/panel/users/{plain_user.pk}/", "/panel/checks/export/"]:
        page = admin_client.get(url).content.decode("utf-8-sig")
        assert "Секретное сообщение" not in page
        assert "+7 000 000 00 01" not in page
    assert admin_client.get("/panel/checks/?user=student").context["total"] == 1


def test_admin_cannot_open_foreign_check_page(admin_client, plain_user):
    check = save_sms_check(plain_user, SECRET_SMS, store_text=True)
    assert admin_client.get(f"/checks/{check.pk}/").status_code == 404


def test_block_unblock_and_roles_are_logged(admin_client, plain_user, client):
    url = f"/panel/users/{plain_user.pk}/block/"
    assert "Заблокировать пользователя?" in admin_client.get(url).content.decode("utf-8")
    plain_user.refresh_from_db()
    assert plain_user.is_active
    admin_client.post(url)
    plain_user.refresh_from_db()
    assert not plain_user.is_active
    admin_client.post(f"/panel/users/{plain_user.pk}/grant_admin/")
    plain_user.refresh_from_db()
    assert plain_user.is_staff
    admin_client.post(f"/panel/users/{plain_user.pk}/unblock/")
    admin_client.post(f"/panel/users/{plain_user.pk}/revoke_admin/")
    plain_user.refresh_from_db()
    assert plain_user.is_active and not plain_user.is_staff
    actions = list(AdminAction.objects.order_by("id").values_list("action", flat=True))
    assert actions == ["block", "grant_admin", "unblock", "revoke_admin"]
    assert admin_client.get("/panel/audit/").context["total"] == 4


def test_blocked_user_cannot_login(admin_client, plain_user, client):
    admin_client.post(f"/panel/users/{plain_user.pk}/block/")
    client.logout()
    response = client.post("/login/", {"username": "student", "password": "secret12345"})
    assert "_auth_user_id" not in client.session
    assert "заблокирована администратором" in response.content.decode("utf-8")


def test_admin_cannot_manage_self_or_superuser(admin_client, admin_user, db):
    admin_client.post(f"/panel/users/{admin_user.pk}/block/")
    admin_user.refresh_from_db()
    assert admin_user.is_active
    root = User.objects.create_superuser("root", "root@example.com", "secret12345")
    admin_client.post(f"/panel/users/{root.pk}/revoke_admin/")
    root.refresh_from_db()
    assert root.is_staff
    assert not AdminAction.objects.exists()
    assert admin_client.get(f"/panel/users/{root.pk}/unknown/").status_code == 404


def test_clear_history_removes_related_rows(admin_client, plain_user):
    save_sms_check(plain_user, "Ваша карта заблокирована! Срочно: http://secure-bank-verify.example/login", store_text=False)
    admin_client.post(f"/panel/users/{plain_user.pk}/clear_history/")
    assert not Check.objects.filter(user=plain_user).exists()
    assert not UrlResult.objects.exists()
    assert not DetectedFeature.objects.exists()


def test_model_activation_switches_one_version(admin_client, db):
    ModelVersion.objects.create(model_type="sms", version="sms_test_v2", algorithm="test")
    new = ModelVersion.objects.get(version="sms_test_v2")
    admin_client.post(f"/panel/models/{new.pk}/activate/")
    active = list(ModelVersion.objects.filter(model_type="sms", is_active=True).values_list("version", flat=True))
    assert active == ["sms_test_v2"]
    assert ModelVersion.objects.filter(model_type="url", is_active=True).count() == 1


def test_login_lockout_appears_in_audit(client, plain_user):
    for _ in range(5):
        client.post("/login/", {"username": "student", "password": "wrong"})
    entry = AdminAction.objects.get()
    assert entry.action == "login_locked"
    assert entry.target == "student"


def test_seed_demo_creates_users_and_checks(db):
    call_command("seed_demo")
    assert User.objects.get(username="admin").is_superuser
    assert Check.objects.filter(user__username="demo").count() == 30
    assert Check.objects.count() == 48
    call_command("seed_demo", "--reset")
    assert Check.objects.count() == 48
