"""
Feature Engineering для сетевых потоков.

Все оконные признаки вычисляются только по ПРОШЛЫМ событиям того же
источника (окно (t - 60 c, t]), поэтому используют лишь информацию,
доступную в момент самого события, — без временной утечки.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

WINDOW = "60s"

NUM_FEATURES = [
    "duration", "packet_count", "src_bytes", "dst_bytes", "avg_packet_size",
    "bytes_ratio", "error_rate", "unique_dst_ips", "unique_dst_ports",
    "conn_per_sec", "hour_sin", "hour_cos", "is_night", "is_well_known_port",
    "host_activity_score",
]
CAT_FEATURES = ["protocol", "service"]
LEAKY_FEATURES = ["flagged_by_ids", "conn_id"]


def _window_counts(df: pd.DataFrame) -> pd.DataFrame:
    """Для каждого события: число соединений, уникальных dst_ip и dst_port
    у того же src_ip за предыдущие 60 секунд (включая текущее)."""
    d = df[["timestamp", "src_ip", "dst_ip", "dst_port"]].copy()
    d["_pos"] = np.arange(len(d))
    d["dst_ip_code"] = d["dst_ip"].astype("category").cat.codes
    d["dst_port_code"] = d["dst_port"].fillna(-1).astype(int)
    res = np.zeros((len(d), 3))
    for _, g in d.sort_values("timestamp").groupby("src_ip", sort=False):
        ts = g["timestamp"].to_numpy()
        ips = g["dst_ip_code"].to_numpy()
        ports = g["dst_port_code"].to_numpy()
        left = np.searchsorted(ts, ts - np.timedelta64(60, "s"), side="right")
        for i, (lo, pos) in enumerate(zip(left, g["_pos"].to_numpy())):
            res[pos] = (i - lo + 1, len(set(ips[lo:i + 1])), len(set(ports[lo:i + 1])))
    return pd.DataFrame(res, columns=["conn_last_60s", "unique_dst_ips", "unique_dst_ports"],
                        index=df.index)


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    pk = out["packet_count"]
    out["avg_packet_size"] = (out["src_bytes"] + out["dst_bytes"]) / pk.where(pk > 0)
    out["bytes_ratio"] = np.log1p(out["src_bytes"]) - np.log1p(out["dst_bytes"])
    out["error_rate"] = out["failed_requests"] / out["total_requests"].where(out["total_requests"] > 0)
    win = _window_counts(out)
    out[["unique_dst_ips", "unique_dst_ports"]] = win[["unique_dst_ips", "unique_dst_ports"]]
    out["conn_per_sec"] = win["conn_last_60s"] / 60.0
    hour = out["timestamp"].dt.hour + out["timestamp"].dt.minute / 60
    out["hour_of_day"] = out["timestamp"].dt.hour
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24)
    out["is_night"] = ((hour < 7) | (hour >= 21)).astype(int)
    out["is_well_known_port"] = (out["dst_port"] < 1024).astype(int)
    # активность хоста: суммарный объём источника за предыдущие 60 c (log)
    acc = []
    for _, g in out.sort_values("timestamp").groupby("src_ip", sort=False):
        r = g.set_index("timestamp")["src_bytes"].fillna(0).rolling(WINDOW).sum()
        acc.append(pd.Series(r.to_numpy(), index=g.index))
    out["host_activity_score"] = np.log1p(pd.concat(acc).reindex(out.index))
    return out
