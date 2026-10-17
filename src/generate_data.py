"""
Генератор учебного NetFlow-подобного датасета (вариант 8 + элементы CIC-IDS2017).

Создаёт data/raw/netflow_raw.csv — «сырые» записи сетевых потоков за сутки:
  * нормальный трафик ~300 внутренних хостов с суточной цикличностью;
  * кампании атак: PortScan, DDoS, SSH/FTP BruteForce, Exfiltration (скрытная);
  * «трудная норма»: резервное копирование, мониторинг/сканер администратора;
  * загрязнения, как в реальных логах: ~12.5% записей с пропусками,
    повторы одного и того же события (ретраи, heartbeat) с общим group_id,
    технический идентификатор conn_id и признак-суррогат метки flagged_by_ids.

Запуск:  python -m src.generate_data
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

RANDOM_STATE = 42
ROOT = Path(__file__).resolve().parents[1]
RAW_PATH = ROOT / "data" / "raw" / "netflow_raw.csv"
DAY_START = pd.Timestamp("2026-09-14 00:00:00")

SERVICES = {  # service -> (protocol, port)
    "http": ("tcp", 80), "https": ("tcp", 443), "dns": ("udp", 53),
    "ssh": ("tcp", 22), "ftp": ("tcp", 21), "smtp": ("tcp", 25),
    "rdp": ("tcp", 3389), "ntp": ("udp", 123), "icmp": ("icmp", 0),
}
SERVERS = [f"10.0.1.{i}" for i in range(1, 51)]
HOSTS = [f"10.0.{2 + i // 250}.{i % 250 + 1}" for i in range(300)]


def _diurnal_seconds(rng, n):
    """Время событий нормального трафика: пик днём (9–19 ч), спад ночью."""
    hours = rng.choice(24, n, p=_hour_weights())
    return hours * 3600 + rng.uniform(0, 3600, n)


def _hour_weights():
    w = np.array([1, 1, 1, 1, 1, 1.5, 2, 4, 7, 9, 10, 10, 9, 10, 10, 9, 8, 7, 5, 4, 3, 2, 1.5, 1.2])
    return w / w.sum()


def _normal(rng, n):
    service = rng.choice(list(SERVICES), n, p=[.18, .40, .20, .05, .02, .05, .03, .04, .03])
    duration = rng.lognormal(0.5, 1.4, n)
    packets = rng.poisson(14, n) + 2
    src_bytes = packets * rng.lognormal(5.0, 0.7, n)
    dst_bytes = packets * rng.lognormal(6.0, 0.9, n)
    total_req = rng.poisson(6, n) + 1
    failed = rng.binomial(total_req, 0.04)
    df = pd.DataFrame({
        "t": _diurnal_seconds(rng, n),
        "src_ip": rng.choice(HOSTS, n),
        "dst_ip": rng.choice(SERVERS, n),
        "service": service, "duration": duration, "packet_count": packets,
        "src_bytes": src_bytes, "dst_bytes": dst_bytes,
        "total_requests": total_req, "failed_requests": failed,
        "attack_type": "Normal",
    })
    # «трудная норма» 1: ночное резервное копирование — большие объёмы
    k = int(0.04 * n)
    idx = rng.choice(n, k, replace=False)
    df.loc[idx, "src_bytes"] *= rng.uniform(20, 80, k)
    df.loc[idx, "duration"] *= rng.uniform(10, 40, k)
    df.loc[idx, "t"] = rng.uniform(0, 5, k) * 3600
    # «трудная норма» 2: системный мониторинг опрашивает много серверов подряд
    k = int(0.03 * n)
    idx = rng.choice(np.setdiff1d(np.arange(n), idx), k, replace=False)
    monitor_hosts = ["10.0.9.10", "10.0.9.11"]
    df.loc[idx, "src_ip"] = rng.choice(monitor_hosts, k)
    df.loc[idx, "service"] = "icmp"
    df.loc[idx, "packet_count"] = rng.integers(2, 6, k)
    burst_start = rng.uniform(0, 23, 6) * 3600
    df.loc[idx, "t"] = rng.choice(burst_start, k) + rng.uniform(0, 90, k)
    df.loc[idx, "dst_ip"] = rng.choice(SERVERS, k)
    return df


def _campaign(rng, kind, n, src, start, span):
    t = start + np.sort(rng.uniform(0, span, n))
    if kind == "PortScan":
        service = rng.choice(list(SERVICES), n)
        dst = rng.choice(SERVERS + HOSTS[:60], n)
        duration = rng.exponential(0.05, n)
        packets = rng.integers(1, 4, n)
        src_b = packets * rng.normal(60, 10, n).clip(40)
        dst_b = packets * rng.normal(50, 20, n).clip(0)
        total = rng.integers(1, 3, n)
        failed = rng.binomial(total, 0.75)
    elif kind == "DDoS":
        service = np.full(n, "http")
        dst = np.full(n, rng.choice(SERVERS[:5]))
        duration = rng.exponential(0.3, n)
        packets = rng.poisson(60, n) + 10
        src_b = packets * rng.normal(70, 15, n).clip(40)
        dst_b = packets * rng.normal(30, 15, n).clip(0)
        total = rng.poisson(30, n) + 5
        failed = rng.binomial(total, 0.35)
    elif kind == "BruteForce":
        service = rng.choice(["ssh", "ftp", "rdp"], n, p=[.6, .25, .15])
        dst = np.full(n, rng.choice(SERVERS))
        duration = rng.lognormal(0.8, 0.5, n)
        packets = rng.poisson(20, n) + 6
        src_b = packets * rng.normal(90, 20, n).clip(40)
        dst_b = packets * rng.normal(110, 25, n).clip(40)
        total = rng.poisson(5, n) + 2
        failed = rng.binomial(total, 0.8)
    elif kind == "Exfiltration":
        service = rng.choice(["https", "dns", "ftp"], n, p=[.6, .3, .1])
        dst = np.array([f"185.{rng.integers(1, 255)}.{rng.integers(1, 255)}.{rng.integers(1, 255)}"
                        for _ in range(n)])
        duration = rng.lognormal(2.5, 1.0, n)
        packets = rng.poisson(40, n) + 5
        src_b = packets * rng.lognormal(7.0, 0.6, n)
        dst_b = packets * rng.lognormal(4.5, 0.6, n)
        total = rng.poisson(4, n) + 1
        failed = rng.binomial(total, 0.05)
    else:
        raise ValueError(kind)
    return pd.DataFrame({
        "t": t, "src_ip": src if np.ndim(src) else np.full(n, src), "dst_ip": dst,
        "service": service, "duration": duration, "packet_count": packets,
        "src_bytes": src_b, "dst_bytes": dst_b,
        "total_requests": total, "failed_requests": failed, "attack_type": kind,
    })


def _attacks(rng):
    parts = []
    night = lambda: rng.choice([rng.uniform(0, 6), rng.uniform(19, 24), rng.uniform(6, 19)],
                               p=[.45, .3, .25]) * 3600
    ext = lambda: f"203.0.{rng.integers(1, 255)}.{rng.integers(1, 255)}"
    for _ in range(9):     # быстрые сканирования
        parts.append(_campaign(rng, "PortScan", int(rng.integers(25, 40)), ext(), night(), 120))
    for _ in range(4):     # медленные (скрытные) сканирования — растянуты на часы
        parts.append(_campaign(rng, "PortScan", 12, ext(), night(), 4 * 3600))
    for _ in range(3):     # DDoS: много источников одновременно бьют в один сервер
        start, n = night(), 110
        srcs = np.array([ext() for _ in range(40)])
        parts.append(_campaign(rng, "DDoS", n, rng.choice(srcs, n), start, 45))
    for _ in range(7):     # перебор паролей
        parts.append(_campaign(rng, "BruteForce", int(rng.integers(25, 40)), ext(), night(), 300))
    for _ in range(25):    # утечка данных со скомпрометированных внутренних хостов
        parts.append(_campaign(rng, "Exfiltration", int(rng.integers(2, 6)),
                               rng.choice(HOSTS), rng.uniform(0, 24) * 3600, 3600))
    return pd.concat(parts, ignore_index=True)


def make_dataset(n_normal: int = 4000, seed: int = RANDOM_STATE) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    normal = _normal(rng, n_normal)
    attacks = _attacks(rng)
    # Перекрытие классов: часть атак маскируется под норму (шумит метки и признаки)
    k = int(0.15 * len(attacks))
    idx = rng.choice(len(attacks), k, replace=False)
    cam = ["packet_count", "src_bytes", "dst_bytes", "duration", "total_requests", "failed_requests"]
    attacks.loc[idx, cam] = normal[cam].sample(k, random_state=seed).to_numpy()

    # conn_id выдаётся сенсором в порядке выгрузки: сначала норма, затем
    # инциденты (типичная ситуация, когда атаки дозагружены из расследований)
    df = pd.concat([normal, attacks], ignore_index=True)
    df["conn_id"] = np.arange(100000, 100000 + len(df))
    df["group_id"] = np.arange(len(df))
    df["t"] = df["t"].clip(0, 24 * 3600 - 1)
    df["timestamp"] = (DAY_START + pd.to_timedelta(df["t"], unit="s")).dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    df["protocol"] = df["service"].map(lambda s: SERVICES[s][0])
    df["dst_port"] = df["service"].map(lambda s: SERVICES[s][1])
    scan = df["attack_type"] == "PortScan"
    df.loc[scan, "dst_port"] = rng.integers(1, 65535, scan.sum())
    df["label"] = (df["attack_type"] != "Normal").astype(int)

    # Признак-суррогат метки: алерт IDS, проставленный по итогам того же расследования
    p = np.where(df["label"] == 1, 0.93, 0.015)
    df["flagged_by_ids"] = (rng.random(len(df)) < p).astype(int)

    # Пропуски (~12.5% строк): сбой сенсора не пишет часть полей
    miss_rows = rng.choice(len(df), int(0.125 * len(df)), replace=False)
    for col in ["duration", "dst_bytes", "service", "failed_requests"]:
        sub = rng.choice(miss_rows, len(miss_rows) // 2, replace=False)
        df.loc[sub, col] = np.nan

    # Повторы событий: ретраи / heartbeat / повторное срабатывание сенсора.
    # Копия получает новый conn_id, но тот же group_id и почти то же время.
    rep = df.sample(frac=0.35, random_state=seed)
    copies = rep.loc[rep.index.repeat(rng.integers(1, 4, len(rep)))].copy()
    copies["conn_id"] = np.arange(200000, 200000 + len(copies))
    copies["timestamp"] = (pd.to_datetime(copies["timestamp"])
                           + pd.to_timedelta(rng.uniform(0.01, 2, len(copies)), unit="s")
                           ).dt.strftime("%Y-%m-%d %H:%M:%S.%f")
    df = pd.concat([df, copies], ignore_index=True)

    # Некорректные типы, как при выгрузке из разных сенсоров
    bad = rng.choice(len(df), 25, replace=False)
    df["packet_count"] = df["packet_count"].astype(object)
    df.loc[bad, "packet_count"] = "n/a"

    df = df.sample(frac=1, random_state=seed).reset_index(drop=True)
    cols = ["conn_id", "group_id", "timestamp", "src_ip", "dst_ip", "dst_port", "protocol",
            "service", "duration", "packet_count", "src_bytes", "dst_bytes",
            "total_requests", "failed_requests", "flagged_by_ids", "attack_type", "label"]
    for c in ["duration", "src_bytes", "dst_bytes"]:
        df[c] = df[c].astype(float).round(3)
    return df[cols]


def main() -> None:
    RAW_PATH.parent.mkdir(parents=True, exist_ok=True)
    df = make_dataset()
    df.to_csv(RAW_PATH, index=False)
    print(f"{len(df)} записей ({df['group_id'].nunique()} уникальных событий) -> {RAW_PATH}")
    print(df.drop_duplicates("group_id")["attack_type"].value_counts())


if __name__ == "__main__":
    main()
