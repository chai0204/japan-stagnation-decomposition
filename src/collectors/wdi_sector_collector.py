"""WDI から業種別付加価値・雇用データを取得（業種別労働生産性比較用）.

対象指標（年次）:
    industry_va_pct        : 工業（製造業含む）付加価値 % of GDP    [NV.IND.TOTL.ZS]
    manufacturing_va_pct   : 製造業付加価値 % of GDP                [NV.IND.MANF.ZS]
    services_va_pct        : サービス業付加価値 % of GDP            [NV.SRV.TOTL.ZS]
    agri_va_pct            : 農林水産 % of GDP                      [NV.AGR.TOTL.ZS]
    industry_emp_pct       : 工業雇用 % of total employment         [SL.IND.EMPL.ZS]
    services_emp_pct       : サービス業雇用 % of total              [SL.SRV.EMPL.ZS]
    agri_emp_pct           : 農林水産雇用 % of total                [SL.AGR.EMPL.ZS]
    employment_total       : 総雇用者数                             [SL.EMP.TOTL]
    nominal_gdp_usd        : 名目 GDP（US$）                        [NY.GDP.MKTP.CD]

業種別労働生産性 = (sector VA % × GDP) / (sector employment % × total employment)

出力: data/raw/wdi_sector_<country>.csv
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
    "industry_va_pct":      "NV.IND.TOTL.ZS",
    "manufacturing_va_pct": "NV.IND.MANF.ZS",
    "services_va_pct":      "NV.SRV.TOTL.ZS",
    "agri_va_pct":          "NV.AGR.TOTL.ZS",
    "industry_emp_pct":     "SL.IND.EMPL.ZS",
    "services_emp_pct":     "SL.SRV.EMPL.ZS",
    "agri_emp_pct":         "SL.AGR.EMPL.ZS",
    "employment_total":     "SL.EMP.TOTL",
    "nominal_gdp_usd":      "NY.GDP.MKTP.CD",
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
    if not parsed:
        return pd.Series(dtype=float)
    s = pd.Series(parsed).sort_index()
    s.index.name = "year"
    return s


def fetch_country(country: str, start: int = 1995, end: int = 2024,
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


def fetch_all(start: int = 1995, end: int = 2024, verbose: bool = True) -> dict:
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
        path = RAW_DIR / f"wdi_sector_{c}.csv"
        df.to_csv(path)
        print(f"  保存: {path} ({len(df)} 行)")
        paths[c] = path
    return paths


def load_country(country: str) -> pd.DataFrame:
    path = RAW_DIR / f"wdi_sector_{country}.csv"
    if not path.exists():
        return pd.DataFrame()
    df = pd.read_csv(path, index_col=0)
    df.index.name = "year"
    return df


def main() -> None:
    parser = argparse.ArgumentParser(description="WDI 業種別データ収集")
    parser.add_argument("--start", type=int, default=1995)
    parser.add_argument("--end", type=int, default=2024)
    args = parser.parse_args()

    print("=== WDI 業種別データ収集 ===")
    data = fetch_all(args.start, args.end)
    save_raw(data)


if __name__ == "__main__":
    main()
