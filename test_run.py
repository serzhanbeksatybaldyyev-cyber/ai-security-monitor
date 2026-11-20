"""Тестовый файл: проверка, что репозиторий скачан и запускается.

Запуск:  python test_run.py
"""
import sys
import importlib

print("OK: файл запустился")
print(f"Python: {sys.version.split()[0]}")

for name in ("numpy", "pandas", "sklearn", "matplotlib"):
    try:
        mod = importlib.import_module(name)
        print(f"  {name}: {getattr(mod, '__version__', 'установлен')}")
    except ImportError:
        print(f"  {name}: не установлен (pip install -r requirements.txt)")
