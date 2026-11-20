"""Демонстрационные тексты для кнопок-примеров (ТЗ, п. 8.3). Все сообщения искусственные,
ссылки ведут только на зарезервированные домены .example и .test."""

SMS_SAMPLES = [
    {"tone": "safe", "label": "Безопасное", "text": "Привет! Встречаемся завтра в 18:00 у входа в библиотеку."},
    {"tone": "warn", "label": "Подозрительное", "text": "Ваша посылка ожидает оплаты таможенного сбора 350 ₸: http://post-delivery-pay.example"},
    {"tone": "fraud", "label": "Мошенническое", "text": "Ваша карта заблокирована! Срочно подтвердите данные по ссылке: http://secure-bank-verify.example/login"},
]

URL_SAMPLES = [
    {"tone": "safe", "label": "Обычный сайт", "text": "https://www.example.com/about"},
    {"tone": "warn", "label": "Короткая ссылка", "text": "http://bit.ly/prize-claim-test"},
    {"tone": "fraud", "label": "Подмена домена", "text": "http://xn--exmple-cua.test/secure/login?verify=1"},
]
