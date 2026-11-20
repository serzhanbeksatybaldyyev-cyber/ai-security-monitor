from ml.risk import load_config


def risk_zones(request):
    """Границы зон шкалы Risk Score для всех шаблонов; значения берутся из risk_config.yaml."""
    zones = load_config()["thresholds"]
    return {"zone_mid": zones["medium"], "zone_high": zones["high"]}
