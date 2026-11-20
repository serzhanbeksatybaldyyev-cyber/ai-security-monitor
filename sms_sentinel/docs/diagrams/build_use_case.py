"""Строит диаграмму вариантов использования (docs/diagrams/use_case.png).

Запуск из корня проекта: python docs/diagrams/build_use_case.py
Источник диаграммы — этот скрипт: чтобы изменить прецедент, правьте списки ниже.
"""
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Ellipse, FancyBboxPatch

OUT = Path(__file__).with_name("use_case.png")

W, H = 15.0, 11.4
USER_X, ADMIN_X = 1.1, 13.9
LEFT_X, RIGHT_X = 5.15, 9.85
INK = "#1f2933"
LINE = "#7b8794"
SHARED = "#e8f0fb"
ADMIN = "#fdf1dc"
INCL = "#edf7ee"

# (id, подпись, x, y, цвет)
CASES = [
    ("uc1", "UC-01\nЗарегистрироваться", LEFT_X, 9.9, SHARED),
    ("uc2", "UC-02\nВойти в систему", LEFT_X, 8.9, SHARED),
    ("uc3", "UC-03\nПроверить SMS", LEFT_X, 7.9, SHARED),
    ("uc4", "UC-04\nПроверить отдельную ссылку", LEFT_X, 6.9, SHARED),
    ("uc5", "UC-05\nПросмотреть результат\nи объяснение", LEFT_X, 5.8, SHARED),
    ("uc6", "UC-06\nПросмотреть и отфильтровать\nисторию", LEFT_X, 4.6, SHARED),
    ("uc7", "UC-07\nУдалить свою запись", LEFT_X, 3.55, SHARED),
    ("uc8", "UC-08\nЭкспортировать историю в CSV", LEFT_X, 2.6, SHARED),
    ("uc9", "UC-09\nПросмотреть Dashboard", LEFT_X, 1.65, SHARED),
    ("uc10", "UC-10\nУправлять согласием\nна хранение текста", LEFT_X, 0.6, SHARED),
    ("uc11", "UC-11\nПросмотреть статистику\nпо всем пользователям", RIGHT_X, 3.4, ADMIN),
    ("uc12", "UC-12\nПросмотреть состояние\nсистемы и версии моделей", RIGHT_X, 2.05, ADMIN),
    ("uc13", "UC-13\nРассчитать Risk Score\nи причины", RIGHT_X, 7.4, INCL),
    ("uc14", "UC-14\nПроанализировать ссылку\nкак строку", RIGHT_X, 5.9, INCL),
]
USER_LINKS = ["uc1", "uc2", "uc3", "uc4", "uc5", "uc6", "uc7", "uc8", "uc9", "uc10"]
ADMIN_LINKS = ["uc11", "uc12"]
INCLUDES = [("uc3", "uc13"), ("uc4", "uc13"), ("uc3", "uc14"), ("uc4", "uc14")]

fig, ax = plt.subplots(figsize=(W, H), dpi=170)
ax.set_xlim(0, W)
ax.set_ylim(-0.1, H - 0.1)
ax.axis("off")

ax.text(W / 2, 11.05, "Диаграмма вариантов использования: SMS Guard", ha="center",
        fontsize=15, fontweight="bold", color=INK)
ax.add_patch(FancyBboxPatch((2.75, -0.02), 9.5, 10.78, boxstyle="round,pad=0.02,rounding_size=0.12",
                            fc="#fbfcfd", ec=LINE, lw=1.3))
ax.text(7.5, 10.52, "Система SMS Guard", ha="center", fontsize=11.5, fontweight="bold", color=INK)


def actor(x, y, name):
    ax.add_patch(Ellipse((x, y + 0.62), 0.32, 0.32, fc="white", ec=INK, lw=1.8, zorder=4))
    ax.plot([x, x], [y + 0.46, y - 0.12], color=INK, lw=1.8, zorder=4)
    ax.plot([x - 0.3, x + 0.3], [y + 0.28, y + 0.28], color=INK, lw=1.8, zorder=4)
    ax.plot([x - 0.26, x, x + 0.26], [y - 0.55, y - 0.12, y - 0.55], color=INK, lw=1.8, zorder=4)
    ax.text(x, y - 0.82, name, ha="center", fontsize=11, fontweight="bold", color=INK, zorder=6,
            bbox=dict(fc="white", ec="none", pad=1.5))


user_y, admin_y = 5.4, 3.0
actor(USER_X, user_y, "Пользователь")
actor(ADMIN_X, admin_y, "Администратор")

pos = {cid: (x, y) for cid, _, x, y, _ in CASES}
for cid in USER_LINKS:
    x, y = pos[cid]
    ax.plot([USER_X + 0.34, x - 1.72], [user_y + 0.1, y], color=LINE, lw=0.95, zorder=1)
for cid in ADMIN_LINKS:
    x, y = pos[cid]
    ax.plot([ADMIN_X - 0.34, x + 1.72], [admin_y + 0.1, y], color=LINE, lw=0.95, zorder=1)

# Вход администратора ведём ломаной, чтобы линия не пересекала UC-13 и UC-14.
x, y = pos["uc2"]
ax.plot([ADMIN_X - 0.34, 12.0, x + 1.72], [admin_y + 0.1, y, y], color=LINE, lw=0.95, zorder=1)

for a, b in INCLUDES:
    (x1, y1), (x2, y2) = pos[a], pos[b]
    ax.annotate("", xy=(x2 - 1.72, y2), xytext=(x1 + 1.72, y1),
                arrowprops=dict(arrowstyle="-|>", ls="--", lw=1.0, color="#3e7c4a"), zorder=2)
ax.text(7.5, 7.98, "«include»", ha="center", fontsize=9, color="#3e7c4a", style="italic",
        bbox=dict(fc="#fbfcfd", ec="none", pad=1.2))

for cid, label, x, y, color in CASES:
    h = 0.92 if label.count("\n") == 2 else 0.74
    ax.add_patch(Ellipse((x, y), 3.45, h, fc=color, ec=INK, lw=1.0, zorder=3))
    ax.text(x, y, label, ha="center", va="center", fontsize=8.8, color=INK, zorder=5, linespacing=1.15)

fig.savefig(OUT, bbox_inches="tight", facecolor="white")
print(f"сохранено: {OUT}")
