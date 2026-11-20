import random
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.analysis.models import Check
from apps.analysis.services import save_sms_check, save_url_check, sync_model_versions
from apps.panel.models import AdminAction

SMS_SAMPLES = [
    "Ваша карта заблокирована! Срочно подтвердите данные по ссылке: http://secure-bank-verify.example/login",
    "Поздравляем! Вы выиграли приз 500 000 тг. Для получения оплатите комиссию 2 000 тг: http://prize-center.test/get",
    "Мама, я попал в беду, срочно переведи 50 000 тг на этот номер +7 000 000 00 01, потом объясню",
    "Служба безопасности банка: на ваш счёт попытка входа. Сообщите код из SMS оператору",
    "Ваш аккаунт будет заблокирован через 24 часа. Подтвердите вход: bit.ly/acc-check",
    "Вам начислен бонус 10 000 тг! Заберите сегодня же по ссылке http://bonus-shop.xyz/claim",
    "Привет! Встречаемся завтра в 18:00 у входа в библиотеку.",
    "Ваш заказ №4821 передан в доставку, ожидайте курьера в понедельник.",
    "Напоминаем: занятие по математике перенесено на среду, кабинет 214.",
    "Ваш код подтверждения: 4821. Никому не сообщайте этот код.",
    "Купи хлеба и молока по дороге домой, пожалуйста.",
    "Құттықтаймыз! Сіз 300 000 теңге ұтып алдыңыз. Жүлдені алу үшін комиссия төлеңіз: http://lucky-kz.test/prize",
    "Картаңыз бұғатталды! Шұғыл түрде деректерді растаңыз: http://karta-tekseru.example/login",
    "Сәлем! Ертең сағат 10:00-де кездесеміз бе?",
    "Ата-аналар жиналысы жұма күні сағат 18:00-де өтеді.",
    "URGENT: Your account will be suspended in 24 hours. Verify now at http://account-verify.example/login",
    "Congratulations! You won a 1000 pound prize. Call 09061701461 to claim now",
    "Your parcel is held at customs. Pay the 2 GBP fee here: http://parcel-fee.test/pay",
    "Hey, are we still on for lunch tomorrow at noon?",
    "Your order #5521 has been shipped and will arrive on Monday.",
    "Reminder: the team meeting moved to 3pm in room B.",
    "Free entry! Text WIN to 80086 to claim your guaranteed reward today",
]

URL_SAMPLES = [
    "https://login-account.example.com/update",
    "http://192.0.2.15:8080/account-update",
    "https://www.example.com/about",
    "http://secure-bank-verify.example/login",
    "https://docs.example.org/guide",
    "bit.ly/free-bonus",
    "http://xn--bnk-sna.test/verify",
    "https://university.example.edu/schedule",
]

USERS = [
    {"username": "demo", "email": "demo@example.com", "password": "DemoUser2026", "checks": 30, "store": False},
    {"username": "student_demo", "email": "student@example.com", "password": "Student2026", "checks": 12, "store": True},
    {"username": "tester_demo", "email": "tester@example.com", "password": "Tester2026", "checks": 6, "store": False},
]


class Command(BaseCommand):
    help = "Создаёт администратора, демонстрационных пользователей и проверки из искусственных сообщений."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Удалить демонстрационные учётные записи и создать заново.")
        parser.add_argument("--admin-password", default="AdminDemo2026", help="Пароль для учётной записи admin.")

    def handle(self, *args, **options):
        names = ["admin"] + [item["username"] for item in USERS]
        if options["reset"]:
            User.objects.filter(username__in=names).delete()
            AdminAction.objects.all().delete()
        elif User.objects.filter(username__in=names).exists():
            self.stdout.write(self.style.WARNING("Демо-данные уже есть. Чтобы пересоздать их, запустите: python manage.py seed_demo --reset"))
            return

        sync_model_versions()
        generator = random.Random(42)
        now = timezone.now()

        with transaction.atomic():
            admin = User.objects.create_superuser("admin", "admin@example.com", options["admin_password"])
            UserProfile.for_user(admin)
            created = 0
            for item in USERS:
                user = User.objects.create_user(item["username"], item["email"], item["password"])
                user.date_joined = now - timedelta(days=35)
                user.save(update_fields=["date_joined"])
                UserProfile.objects.update_or_create(user=user, defaults={"store_sms_text": item["store"]})
                for index in range(item["checks"]):
                    if index % 4 == 3:
                        check = save_url_check(user, URL_SAMPLES[generator.randrange(len(URL_SAMPLES))])
                    else:
                        check = save_sms_check(user, SMS_SAMPLES[generator.randrange(len(SMS_SAMPLES))], item["store"])
                    moment = now - timedelta(days=generator.randrange(30), hours=generator.randrange(10), minutes=generator.randrange(60))
                    Check.objects.filter(pk=check.pk).update(created_at=moment)
                    created += 1

        self.stdout.write(self.style.SUCCESS(f"Создано пользователей: {len(USERS) + 1}, проверок: {created}."))
        self.stdout.write(f"Администратор: admin / {options['admin_password']}")
        for item in USERS:
            self.stdout.write(f"Пользователь: {item['username']} / {item['password']} ({item['checks']} проверок)")
