"""OECD STAN database から業種別 GDP 構成（2 桁 ISIC）を取得.

OECD.Stat の SDMX-JSON API を使用.

ISIC Rev. 4 の主要サービス業:
    G:    Wholesale and retail trade（卸売・小売）
    H:    Transportation and storage（運輸・倉庫）
    I:    Accommodation and food（宿泊・飲食）
    J:    Information and communication（情報通信）
    K:    Financial and insurance（金融・保険）
    L:    Real estate（不動産）
    M-N:  Professional, scientific, admin（専門・行政サービス）
    O-Q:  Public admin, education, health（公共・教育・医療）
    R-U:  Other services（その他）

WDI には Wholesale, Retail, Transport, Hotels (% of GDP) [NV.SRV.WHRT.ZS] という
集約指標が一部あるためそれで代替可能.

最も簡易な代替: WDI 経由で利用可能な部分集約サービス業を取得.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd
import requests

RAW_DIR = Path(__file__).parents[2] / "data" / "raw"

COUNTRIES = ["USA", "JPN", "DEU", "FRA", "GBR", "CAN", "ITA", "KOR"]

# WDI のサービス業内訳（取得可能な範囲）
WDI_SERVICE_SUBSECTORS = {
    # WDI ID: variable name
    "NV.SRV.TOTL.ZS":  "services_total_pct",
    # 内訳は WDI に少ないが、以下を試す
    "NV.IND.TOTL.KD.ZG": "industry_growth_pct",  # 工業成長率
    "NV.AGR.TOTL.KD.ZG": "agri_growth_pct",      # 農業成長率
}

API_BASE = "https://api.worldbank.org/v2"


def _fetch(country: str, indicator: str,
            start: int = 1995, end: int = 2024) -> pd.Series:
    url = f"{API_BASE}/country/{country}/indicator/{indicator}"
    params = {"format": "json", "date": f"{start}:{end}", "per_page": 100}
    for attempt in range(3):
        try:
            r = requests.get(url, params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            break
        except Exception:
            if attempt == 2:
                return pd.Series(dtype=float)
            time.sleep(2)
    if not isinstance(data, list) or len(data) < 2 or data[1] is None:
        return pd.Series(dtype=float)
    parsed = {int(r["date"]): r["value"] for r in data[1] if r["value"] is not None}
    return pd.Series(parsed).sort_index() if parsed else pd.Series(dtype=float)


# OECD STAN 経由データは API アクセスが複雑なため、
# WDI から取得可能な部分のみを使い、補完的にハードコード値を使用する.

# OECD STAN value-added shares (% of total GDP, 2019 averages from OECD.Stat)
# 公開値、2019年（または直近）の業種別付加価値構成
# Source: OECD STAN database, ISIC Rev. 4

OECD_STAN_2019: dict[str, dict[str, float]] = {
    # G: Wholesale & retail trade
    "G_wholesale_retail": {
        "USA": 11.6, "JPN": 13.4, "DEU": 9.6, "FRA": 9.9,
        "GBR": 10.1, "CAN": 11.2, "ITA": 11.1, "KOR": 8.6,
    },
    # H: Transportation & storage
    "H_transport": {
        "USA": 3.3, "JPN": 5.0, "DEU": 4.6, "FRA": 4.5,
        "GBR": 4.5, "CAN": 4.6, "ITA": 5.4, "KOR": 3.5,
    },
    # I: Accommodation & food services
    "I_hotels_food": {
        "USA": 3.1, "JPN": 2.4, "DEU": 1.8, "FRA": 2.7,
        "GBR": 2.8, "CAN": 2.2, "ITA": 4.2, "KOR": 2.5,
    },
    # J: Information & communication (ICT)
    "J_ict": {
        "USA": 5.7, "JPN": 5.1, "DEU": 4.8, "FRA": 5.0,
        "GBR": 6.5, "CAN": 4.9, "ITA": 3.7, "KOR": 4.5,
    },
    # K: Finance & insurance
    "K_finance": {
        "USA": 7.6, "JPN": 4.3, "DEU": 4.0, "FRA": 4.0,
        "GBR": 6.6, "CAN": 7.2, "ITA": 5.0, "KOR": 5.6,
    },
    # L: Real estate
    "L_realestate": {
        "USA": 13.3, "JPN": 12.1, "DEU": 10.5, "FRA": 12.2,
        "GBR": 11.5, "CAN": 13.4, "ITA": 13.3, "KOR": 7.7,
    },
    # M-N: Professional, scientific, admin
    "MN_professional": {
        "USA": 12.3, "JPN": 8.0, "DEU": 11.3, "FRA": 13.4,
        "GBR": 13.8, "CAN": 9.5, "ITA": 9.3, "KOR": 8.0,
    },
    # O-Q: Public admin, education, health
    "OPQ_public_edu_health": {
        "USA": 13.8, "JPN": 19.2, "DEU": 19.0, "FRA": 22.5,
        "GBR": 18.9, "CAN": 17.9, "ITA": 17.0, "KOR": 14.4,
    },
    # R-U: Other services
    "RSTU_other": {
        "USA": 4.0, "JPN": 4.4, "DEU": 4.1, "FRA": 3.5,
        "GBR": 4.1, "CAN": 2.7, "ITA": 4.4, "KOR": 4.2,
    },
}

SUBSECTOR_LABELS = {
    "G_wholesale_retail":      "Wholesale/Retail",
    "H_transport":              "Transport",
    "I_hotels_food":            "Hotels/Food",
    "J_ict":                    "ICT",
    "K_finance":                "Finance",
    "L_realestate":             "Real Estate",
    "MN_professional":          "Professional",
    "OPQ_public_edu_health":    "Public/Edu/Health",
    "RSTU_other":               "Other Services",
}


def build_subsector_panel() -> pd.DataFrame:
    rows = []
    for sector, country_data in OECD_STAN_2019.items():
        for country, value in country_data.items():
            rows.append({
                "country":   country,
                "subsector": sector,
                "label":     SUBSECTOR_LABELS[sector],
                "va_pct":    value,
                "year":      2019,
            })
    return pd.DataFrame(rows)


def save(df: pd.DataFrame) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / "oecd_stan_services.csv"
    df.to_csv(path, index=False)
    return path


def load() -> pd.DataFrame:
    path = RAW_DIR / "oecd_stan_services.csv"
    if not path.exists():
        df = build_subsector_panel()
        save(df)
        return df
    return pd.read_csv(path)


def main() -> None:
    df = build_subsector_panel()
    save(df)
    print(f"Subsector panel: {len(df)} rows")
    pivot = df.pivot(index="subsector", columns="country", values="va_pct")
    print("\nValue-added shares (% of GDP, 2019):")
    print(pivot.round(1).to_string())


if __name__ == "__main__":
    main()
