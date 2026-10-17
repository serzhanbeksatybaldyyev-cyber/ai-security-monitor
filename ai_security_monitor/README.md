# AI Security Monitor

Учебный прототип интеллектуальной системы безопасности веб-приложений:
мониторинг сетевой активности (Isolation Forest, Random Forest) и
NLP-классификация HTTP-запросов на Normal / SQL Injection / XSS
(TF-IDF + Logistic Regression, сравнение с Naive Bayes), объединённые в
панели на Streamlit.

Полное техническое задание, план работ и критерии приёмки — в
[`docs/TECHNICAL_SPEC.md`](docs/TECHNICAL_SPEC.md).

## Быстрый старт

```bash
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 1. Сетевые данные: синтетический учебный набор (или CIC-IDS2017, см. ТЗ, раздел 8)
python scripts/generate_network_data.py

# 2. Текстовые данные: скачайте открытые датасеты SQLi и XSS и объедините их
python scripts/prepare_text_dataset.py \
    --sqli raw/sqli.csv --sqli-text-col Query --sqli-label-col Label \
    --xss  raw/xss.csv  --xss-text-col Sentence --xss-label-col Label \
    --max-per-class 8000 --add-timestamps

# 3. Обучение и оценка обеих частей
python train_all.py

# 4. Тесты (включая проверку ложных срабатываний после обучения)
pytest -q

# 5. Панель мониторинга → http://127.0.0.1:8501
streamlit run app.py
```

Шаги 1 и 3 работают и без текстового датасета: тогда панель покажет только
сетевой модуль и подскажет, что сделать для NLP-части.

## Структура

```
config.py                     общие пути, имена столбцов, пороги, схема событий
train_all.py                  обучение, оценка, выгрузка событий для панели
app.py                        панель Streamlit
src/common/io_utils.py        безопасная загрузка CSV, контракт событий, экспорт
src/common/metrics.py         метрики и матрицы ошибок
src/network/preprocess.py     очистка сетевых данных (Студент 1)
src/network/models.py         Isolation Forest, Random Forest, события (Студент 1)
src/nlp/preprocess.py         декодирование и нормализация запросов (Студент 2)
src/nlp/models.py             TF-IDF + LogReg / NB, объяснение прогноза (Студент 2)
scripts/generate_network_data.py   синтетический сетевой датасет
scripts/prepare_text_dataset.py    сборка трёхклассового текстового датасета
notebooks/01_network_eda.ipynb     исследование сетевых данных
tests/                        модульные, интеграционные тесты, тест ложных срабатываний
data/fp_benign_requests.csv   «трудные» нормальные запросы для проверки FPR
```

## Важно

* Результаты — **прогнозы моделей**, а не подтверждённые атаки.
* Работайте только с открытыми, синтетическими данными или своей локальной
  тестовой системой. Система анализирует данные и не выполняет атак.
* Загружайте модели (`.joblib`) только из собственного обучения.
