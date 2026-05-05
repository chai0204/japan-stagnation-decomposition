"""OECD SDMX API から G7+韓国の家計金融資産構成を取得.

データソース: OECD.SDD.NAD,DSD_FIN_DASH@DF_FIN_DASH_S1M

主要 MEASURE (% of household financial assets):
    LES1M_F2AS    : 通貨・預金 Currency & deposits
    LES1M_F3AS    : 債券 Debt securities
    LES1M_F51AS   : 株式（上場）Listed equity
    LES1M_F52AS   : 投資信託 Investment fund shares
    LES1M_F62AS   : 保険・年金 Insurance & pension
    LES1M_F6MAS   : 保険 (sub)
    LES1M_FO2AS   : その他預金 Other deposits（外貨預金含む可能性）
    LES1M_FR3AAS  : 準備資産

注意：
    OECD 標準家計勘定は INSTRUMENT 別（預金・株式・投信）の構成データであり、
    「居住地別（国内 vs 海外）」の直接的内訳ではない. しかし投信 + 株式の
    比率は「リスク資産選好」の代理として国際比較に有用.

出力: data/raw/oecd_household_<country>.csv
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd
import requests

RAW_DIR = Path(__file__).parents[2] / "data" / "raw"

COUNTRIES = ["USA", "JPN", "DEU", "FRA", "GBR", "CAN", "ITA", "KOR"]

MEASURES = {
    "LES1M_F2AS":    "currency_deposits_pct",
    "LES1M_F3AS":    "debt_securities_pct",
    "LES1M_F51AS":   "listed_equity_pct",
    "LES1M_F52AS":   "investment_funds_pct",
    "LES1M_F62AS":   "insurance_pension_pct",
    "LES1M_FO2AS":   "other_deposits_pct",
}

API_BASE = "https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_FIN_DASH@DF_FIN_DASH_S1M,1.0"


def fetch_country(country: str, start: int = 2000, end: int = 2024,
                   verbose: bool = True) -> pd.DataFrame:
    """1 国の家計金融資産構成を取得."""
    url = f"{API_BASE}/.{country}.....?startPeriod={start}&endPeriod={end}"
    headers = {"Accept": "application/vnd.sdmx.data+csv"}
    if verbose:
        print(f"  [{country}] 取得中...")
    for attempt in range(3):
        try:
            r = requests.get(url, headers=headers, timeout=60, allow_redirects=True)
            if r.status_code != 200:
                if attempt == 2:
                    if verbose:
                        print(f"    HTTP {r.status_code}")
                    return pd.DataFrame()
                time.sleep(2)
                continue
            from io import StringIO
            df = pd.read_csv(StringIO(r.text))
            break
        except Exception as e:
            if attempt == 2:
                if verbose:
                    print(f"    エラー: {e}")
                return pd.DataFrame()
            time.sleep(2)

    # ターゲット MEASURE のみ抽出、年次のみ
    if df.empty or "MEASURE" not in df.columns:
        return pd.DataFrame()
    df = df[df["MEASURE"].isin(MEASURES.keys())].copy()
    df = df[df["FREQ"] == "A"].copy()  # 年次
    if df.empty:
        return pd.DataFrame()

    # 必要な列のみ
    df = df[["TIME_PERIOD", "MEASURE", "OBS_VALUE", "UNIT_MEASURE"]].copy()
    # 単位が PT_FAS_S1M（家計金融資産対比%）のもののみ
    df = df[df["UNIT_MEASURE"] == "PT_FAS_S1M"].copy()
    if df.empty:
        return pd.DataFrame()

    # ピボット
    pivot = df.pivot_table(
        index="TIME_PERIOD",
        columns="MEASURE",
        values="OBS_VALUE",
        aggfunc="mean",
    )
    pivot = pivot.rename(columns=MEASURES)
    pivot.index.name = "year"
    pivot.index = pivot.index.astype(int)

    if verbose:
        print(f"    取得: {len(pivot)} 期 × {pivot.shape[1]} 指標")
    return pivot


def fetch_all(start: int = 2000, end: int = 2024,
               verbose: bool = True) -> dict[str, pd.DataFrame]:
    out = {}
    for c in COUNTRIES:
        df = fetch_country(c, start, end, verbose)
        if not df.empty:
            out[c] = df
        time.sleep(1)
    return out


def save_raw(data: dict[str, pd.DataFrame]) -> dict:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    paths = {}
    for c, df in data.items():
        path = RAW_DIR / f"oecd_household_{c}.csv"
        df.to_csv(path)
        print(f"  保存: {path} ({len(df)} 行 × {df.shape[1]} 列)")
        paths[c] = path
    return paths


def load_country(country: str) -> pd.DataFrame:
    path = RAW_DIR / f"oecd_household_{country}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, index_col="year")


def main() -> None:
    parser = argparse.ArgumentParser(description="OECD 家計金融資産構成収集")
    parser.add_argument("--start", type=int, default=2000)
    parser.add_argument("--end", type=int, default=2024)
    args = parser.parse_args()

    print("=== OECD 家計金融資産構成収集 ===")
    data = fetch_all(args.start, args.end)
    save_raw(data)
    print(f"\n完了: {len(data)} 国")


if __name__ == "__main__":
    main()
