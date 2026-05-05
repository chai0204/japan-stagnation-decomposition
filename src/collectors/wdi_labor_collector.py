"""WDI から労働市場構成データを取得（構成効果分析用）.

対象指標（年次）:
    lfp_total_15_64        : 労働力参加率（15-64 歳合計）   [SL.TLF.CACT.ZS]
    lfp_female_15_64       : 女性労働力参加率（15-64）      [SL.TLF.CACT.FE.ZS]
    lfp_male_15_64         : 男性労働力参加率（15-64）      [SL.TLF.CACT.MA.ZS]
    employment_rate_total  : 就業率（雇用 / 15-64 人口）    [SL.EMP.TOTL.SP.ZS]
    employment_rate_female : 女性就業率                     [SL.EMP.TOTL.SP.FE.ZS]
    self_employed_total    : 自営業者比率                   [SL.EMP.SELF.ZS]
    vulnerable_employment  : 不安定雇用比率（自営+家族労働） [SL.EMP.VULN.ZS]

注意：パート比率は WDI 直接にはないが、FRED または OECD MEI で取得可能.

出力: data/raw/wdi_labor_<country>.csv
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd
import requests

RAW_DIR = Path(__file__).parents[2] / "data" / "raw"

COUNTRIES: dict[str, str] = {
    "USA": "米国", "JPN": "日本", "DEU": "ドイツ", "FRA": "フランス",
    "GBR": "英国", "CAN": "カナダ", "ITA": "イタリア", "KOR": "韓国",
}

INDICATORS: dict[str, str] = {
    "lfp_total_15_64":        "SL.TLF.ACTI.ZS",     # Labor force participation rate, total (% of population ages 15-64)
    "lfp_female_15_64":       "SL.TLF.ACTI.FE.ZS",
    "lfp_male_15_64":         "SL.TLF.ACTI.MA.ZS",
    "employment_rate_total":  "SL.EMP.TOTL.SP.ZS",  # Employment to population ratio, 15+
    "employment_rate_female": "SL.EMP.TOTL.SP.FE.ZS",
    "self_employed_total":    "SL.EMP.SELF.ZS",
    "vulnerable_employment":  "SL.EMP.VULN.ZS",
}

API_BASE = "https://api.worldbank.org/v2"


def _fetch(country: str, indicator: str,
            start: int = 1990, end: int = 2024) -> pd.Series:
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
    if not parsed:
        return pd.Series(dtype=float)
    s = pd.Series(parsed).sort_index()
    s.index.name = "year"
    return s


def fetch_country(country: str, start: int = 1990, end: int = 2024,
                   verbose: bool = True) -> pd.DataFrame:
    if verbose:
        print(f"  [{country}] {COUNTRIES[country]}...")
    pieces = {}
    for var, ind in INDICATORS.items():
        s = _fetch(country, ind, start, end)
        pieces[var] = s
        if verbose:
            print(f"    {var}: {s.notna().sum()} 件")
        time.sleep(0.4)
    return pd.DataFrame(pieces)


def fetch_all(start: int = 1990, end: int = 2024, verbose: bool = True) -> dict:
    out = {}
    for c in COUNTRIES:
        if verbose:
            print()
        out[c] = fetch_country(c, start, end, verbose)
    return out


def save_raw(data: dict) -> dict:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    paths = {}
    for c, df in data.items():
        if df.empty:
            continue
        path = RAW_DIR / f"wdi_labor_{c}.csv"
        df.to_csv(path)
        print(f"  保存: {path} ({len(df)} 行)")
        paths[c] = path
    return paths


def load_country(country: str) -> pd.DataFrame:
    path = RAW_DIR / f"wdi_labor_{country}.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, index_col=0)
    df.index.name = "year"
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="WDI 労働構成データ収集")
    parser.add_argument("--start", type=int, default=1990)
    parser.add_argument("--end", type=int, default=2024)
    args = parser.parse_args()

    print("=== WDI 労働構成データ収集 ===")
    data = fetch_all(args.start, args.end)
    save_raw(data)


if __name__ == "__main__":
    main()
