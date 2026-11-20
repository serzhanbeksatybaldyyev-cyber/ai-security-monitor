"""Сверяет data/raw/SMSSpamCollection с архивом на официальном сайте UCI.

Запуск из корня проекта: python -m ml.data.verify_source
Нужен доступ в интернет. Локальный файл скрипт не изменяет.
"""
import hashlib
import io
import urllib.request
import zipfile

from ml.data.load_sms import RAW_PATH

OFFICIAL_URL = "https://archive.ics.uci.edu/static/public/228/sms+spam+collection.zip"
MEMBER = "SMSSpamCollection"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compare_with_archive(archive: bytes, local: bytes) -> bool:
    """Возвращает True, если файл в архиве побайтно равен локальному."""
    with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
        official = zipped.read(MEMBER)
    print(f"SHA-256 на сайте UCI: {sha256(official)}")
    print(f"SHA-256 локальный:    {sha256(local)}")
    return official == local


def main() -> None:
    with urllib.request.urlopen(OFFICIAL_URL, timeout=60) as response:
        archive = response.read()
    if compare_with_archive(archive, RAW_PATH.read_bytes()):
        print("Файлы совпадают.")
    else:
        print("Файлы различаются: распакуйте архив UCI в data/raw/ и повторите подготовку данных.")


if __name__ == "__main__":
    main()
