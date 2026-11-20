import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("DEBUG", "True")

import django

django.setup()

from django.contrib.auth.models import User
from django.db import models

from apps.accounts.models import UserProfile
from apps.analysis.models import Check, DetectedFeature, ModelVersion, UrlResult
from apps.panel.models import AdminAction

USER_FIELDS = {"id", "username", "email", "password", "date_joined", "is_staff", "is_active", "is_superuser", "last_login"}
TABLES = [User, UserProfile, Check, UrlResult, DetectedFeature, ModelVersion, AdminAction]
COLORS = {"auth_user": "#e8eef6", "admin_actions": "#efe7fa"}


def column_type(field):
    if isinstance(field, models.ForeignKey):
        return "FK"
    return field.get_internal_type().replace("Field", "").replace("PositiveSmallInteger", "SmallInt").replace("BigAuto", "BigInt")


def table_label(model):
    table = model._meta.db_table
    rows = []
    for field in model._meta.concrete_fields:
        if model is User and field.name not in USER_FIELDS:
            continue
        key = "PK" if field.primary_key else ("FK" if isinstance(field, models.ForeignKey) else "")
        null = " NULL" if field.null else ""
        rows.append(
            f'<TR><TD ALIGN="LEFT" PORT="{field.column}_in">{f"<B>{key}</B>" if key else " "}</TD><TD ALIGN="LEFT">{field.column}</TD>'
            f'<TD ALIGN="LEFT" PORT="{field.column}_out"><FONT COLOR="#555555">{column_type(field)}{null}</FONT></TD></TR>'
        )
    color = COLORS.get(table, "#ffffff")
    header = f'<TR><TD COLSPAN="3" BGCOLOR="#17324d"><FONT COLOR="white"><B>{table}</B></FONT></TD></TR>'
    return f'<<TABLE BORDER="1" CELLBORDER="0" CELLSPACING="0" CELLPADDING="4" BGCOLOR="{color}">{header}{"".join(rows)}</TABLE>>'


def build():
    lines = [
        "digraph ER {",
        'graph [rankdir=LR, fontname="DejaVu Sans", nodesep=0.5, ranksep=1.1, label="ER-диаграмма базы данных SMS Guard (построена из моделей Django)", labelloc=t, fontsize=18];',
        'node [shape=plaintext, fontname="DejaVu Sans", fontsize=11];',
        'edge [fontname="DejaVu Sans", fontsize=10, color="#47586a", arrowhead=none];',
    ]
    for model in TABLES:
        lines.append(f'"{model._meta.db_table}" [label={table_label(model)}];')
    for model in TABLES:
        for field in model._meta.concrete_fields:
            if isinstance(field, models.ForeignKey):
                target = field.related_model._meta.db_table
                ratio = "1 : 1" if isinstance(field, models.OneToOneField) else "N : 1"
                lines.append(f'"{model._meta.db_table}":"{field.column}_out":e -> "{target}":"id_in":w [label="{ratio}"];')
    lines.append("}")
    source = "\n".join(lines)
    out_dir = Path(__file__).resolve().parent
    (out_dir / "er_diagram.dot").write_text(source, encoding="utf-8")
    subprocess.run(["dot", "-Tpng", "-Gdpi=130", "-o", str(out_dir / "er_diagram.png")], input=source.encode("utf-8"), check=True)
    print(out_dir / "er_diagram.png")


if __name__ == "__main__":
    build()
