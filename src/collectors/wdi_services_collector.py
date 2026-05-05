"""WDI からサービス輸出・輸入とライセンス収支を G7 + 韓国で取得.

対象指標（年次）:
    services_exports_usd     : サービス輸出（BoP, US$）            [BX.GSR.NFSV.CD]
    services_imports_usd     : サービス輸入（BoP, US$）            [BM.GSR.NFSV.CD]
    royalty_receipts_usd     : 知財ライセンス受取（US$）           [BX.GSR.ROYL.CD]
    royalty_payments_usd     : 知財ライセンス支払（US$）           [BM.GSR.ROYL.CD]
    ict_services_exports     : ICT サービス輸出（％ サービス輸出） [BX.GSR.CCIS.ZS]
    ict_services_imports     : ICT サービス輸入（％ サービス輸入） [BM.GSR.CMCP.ZS]
    nominal_gdp_usd          : 名目 GDP（US$）                     [NY.GDP.MKTP.CD]

「デジタル赤字」近似値:
    services_balance = services_exports_usd - services_imports_usd
    royalty_balance  = royalty_receipts_usd - royalty_payments_usd
    ICT 関連サービス収支 (proxy) = (services_exports * ict_share_ex) - (services_imports * ict_share_im)

出力: data/raw/wdi_services_<country>.csv
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
    "services_exports_usd":  "BX.GSR.NFSV.CD",
    "services_imports_usd":  "BM.GSR.NFSV.CD",
    "royalty_receipts_usd":  "BX.GSR.ROYL.CD",
    "royalty_payments_usd":  "BM.GSR.ROYL.CD",
    "ict_services_exports":  "BX.GSR.CCIS.ZS",
    "ict_services_imports":  "BM.GSR.CMCP.ZS",
    "nominal_gdp_usd":       "NY.GDP.MKTP.CD",
}

API_BASE = "https://api.worldbank.org/v2"


def _fetch(country: str, indicator: str,
            start: int = 2000, end: int = 2024) -> pd.Series:
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


def fetch_country(country: str, start: int = 2000, end: int = 2024,
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


def fetch_all(start: int = 2000, end: int = 2024, verbose: bool = True) -> dict:
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
        path = RAW_DIR / f"wdi_services_{c}.csv"
        df.to_csv(path)
        print(f"  保存: {path} ({len(df)} 行)")
        paths[c] = path
    return paths


def load_country(country: str) -> pd.DataFrame:
    path = RAW_DIR / f"wdi_services_{country}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, index_col="year")


def main() -> None:
    parser = argparse.ArgumentParser(description="WDI サービス収支データ収集")
    parser.add_argument("--start", type=int, default=2000)
    parser.add_argument("--end", type=int, default=2024)
    args = parser.parse_args()

    print("=== WDI サービス収支データ収集 ===")
    data = fetch_all(args.start, args.end)
    save_raw(data)


if __name__ == "__main__":
    main()
