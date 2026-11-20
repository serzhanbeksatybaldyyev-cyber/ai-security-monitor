import pytest
from django.contrib.auth.models import User
from django.db import connection

from apps.analysis.models import Check, DetectedFeature, ModelVersion, UrlResult
from apps.analysis.services import save_sms_check, save_url_check

FRAUD_SMS = "Ваша карта заблокирована! Срочно переведите 5 000 тг и подтвердите: http://secure-bank-verify.example/login"


@pytest.fixture
def user(db):
    return User.objects.create_user("student", "student@example.com", "secret12345")


def test_tables_match_specification(db):
    tables = set(connection.introspection.table_names())
    assert {"user_profile", "checks", "url_results", "detected_features", "model_versions"} <= tables
    columns = {column.name for column in connection.introspection.get_table_description(connection.cursor(), "checks")}
    assert {"user_id", "check_type", "input_text", "input_masked", "language", "category", "risk_level", "risk_score", "p_sms", "explanation", "recommendation", "sms_model_version_id", "url_model_version_id", "created_at"} <= columns
    with connection.cursor() as cursor:
        indexes = connection.introspection.get_constraints(cursor, "checks")
    index_columns = [tuple(item["columns"]) for item in indexes.values() if item["index"]]
    assert ("user_id", "created_at") in index_columns
    assert ("category",) in index_columns


def test_migration_fills_active_model_versions(db):
    assert ModelVersion.objects.filter(is_active=True).count() == 2
    sms = ModelVersion.objects.get(model_type="sms", is_active=True)
    assert sms.metrics_json["recall"] > 0.9


def test_sms_check_saves_related_rows_without_text(user):
    check = save_sms_check(user, FRAUD_SMS, store_text=False)
    assert check.input_text is None
    assert "5 000" not in check.input_masked
    assert UrlResult.objects.filter(check_record=check, domain="secure-bank-verify.example").exists()
    assert DetectedFeature.objects.filter(check_record=check).count() >= 3


def test_url_check_saves_one_result(user):
    check = save_url_check(user, "http://192.0.2.15:8080/account-update")
    result = check.url_results.get()
    assert result.features_json["features"]["has_ip"] == 1
    assert len(result.checks) >= 10
    assert check.url_model_version.version == "url_rules_v1"


def test_cascade_delete_removes_results_and_features(user):
    check = save_sms_check(user, FRAUD_SMS, store_text=True)
    check.delete()
    assert not UrlResult.objects.exists()
    assert not DetectedFeature.objects.exists()


def test_failed_save_rolls_back_everything(user, monkeypatch):
    def broken(*args, **kwargs):
        raise RuntimeError("сбой")

    monkeypatch.setattr(DetectedFeature.objects, "bulk_create", broken)
    with pytest.raises(RuntimeError):
        save_sms_check(user, FRAUD_SMS, store_text=True)
    assert not Check.objects.exists()
    assert not UrlResult.objects.exists()


def test_deleting_user_removes_history(user):
    save_sms_check(user, FRAUD_SMS, store_text=True)
    user.delete()
    assert not Check.objects.exists()
