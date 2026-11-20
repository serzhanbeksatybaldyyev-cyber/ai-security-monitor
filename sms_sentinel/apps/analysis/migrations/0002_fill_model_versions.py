from django.db import migrations


def fill(apps, schema_editor):
    from ml.registry import model_cards

    ModelVersion = apps.get_model("analysis", "ModelVersion")
    for card in model_cards():
        ModelVersion.objects.update_or_create(
            model_type=card["model_type"],
            version=card["version"],
            defaults={
                "algorithm": card["algorithm"],
                "metrics_json": card.get("metrics", {}),
                "threshold": card.get("threshold", 0.5),
                "trained_at": card.get("trained_at"),
                "is_active": True,
            },
        )


def clear(apps, schema_editor):
    apps.get_model("analysis", "ModelVersion").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("analysis", "0001_initial")]

    operations = [migrations.RunPython(fill, clear)]
