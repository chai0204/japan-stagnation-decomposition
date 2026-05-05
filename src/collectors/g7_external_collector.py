"""G7 全国の四半期データを FRED から収集する（クロスカントリー SVAR 用）.

対象（四半期）:
    real_gdp        : 実質 GDP（国別単位、SAAR）
    wage_real_idx   : 実質賃金指数（OECD MEI）
    fx_reer         : 実質実効為替レート（BIS Broad）
    current_account : 経常収支対 GDP 比（%）

国: USA, JPN, DEU, FRA, GBR, CAN, ITA + KOR

期間: 1995Q1 ~ 最新

出力: data/raw/g7_external_<country>.csv
"""

from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import pandas as pd
from fredapi import Fred

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

RAW_DIR = Path(__file__).parents[2] / "data" / "raw"

# FRED 系列定義（各国別）
COUNTRIES_SERIES: dict[str, dict[str, dict]] = {
    "JPN": {
        "real_gdp":         {"id": "JPNRGDPEXP",          "freq": "Q"},
        "wage_real_idx":    {"id": "LCEAMN01JPQ661S",     "freq": "Q"},
        "reer":             {"id": "RBJPBIS",             "freq": "M"},
        "current_account":  {"id": "JPNB6BLTT02STSAQ",    "freq": "Q"},  # CA % of GDP
    },
    "USA": {
        "real_gdp":         {"id": "GDPC1",               "freq": "Q"},
        "wage_real_idx":    {"id": "LCEAMN01USQ661S",     "freq": "Q"},
        "reer":             {"id": "RBUSBIS",             "freq": "M"},
        "current_account":  {"id": "USAB6BLTT02STSAQ",    "freq": "Q"},
    },
    "DEU": {
        "real_gdp":         {"id": "CLVMNACSCAB1GQDE",    "freq": "Q"},
        "wage_real_idx":    {"id": "LCEAMN01DEQ661S",     "freq": "Q"},
        "reer":             {"id": "RBDEBIS",             "freq": "M"},
        "current_account":  {"id": "DEUB6BLTT02STSAQ",    "freq": "Q"},
    },
    "FRA": {
        "real_gdp":         {"id": "CLVMNACSCAB1GQFR",    "freq": "Q"},
        "wage_real_idx":    {"id": "LCEAMN01FRQ661S",     "freq": "Q"},
        "reer":             {"id": "RBFRBIS",             "freq": "M"},
        "current_account":  {"id": "FRAB6BLTT02STSAQ",    "freq": "Q"},
    },
    "GBR": {
        "real_gdp":         {"id": "CLVMNACSCAB1GQUK",    "freq": "Q"},
        "wage_real_idx":    {"id": "LCEAMN01GBQ661S",     "freq": "Q"},
        "reer":             {"id": "RBGBBIS",             "freq": "M"},
        "current_account":  {"id": "GBRB6BLTT02STSAQ",    "freq": "Q"},
    },
    "CAN": {
        "real_gdp":         {"id": "NAEXKP01CAQ661S",     "freq": "Q"},
        "wage_real_idx":    {"id": "LCEAMN01CAQ661S",     "freq": "Q"},
        "reer":             {"id": "RBCABIS",             "freq": "M"},
        "current_account":  {"id": "CANB6BLTT02STSAQ",    "freq": "Q"},
    },
    "ITA": {
        "real_gdp":         {"id": "CLVMNACSCAB1GQIT",    "freq": "Q"},
        "wage_real_idx":    {"id": "LCEAMN01ITQ661S",     "freq": "Q"},
        "reer":             {"id": "RBITBIS",             "freq": "M"},
        "current_account":  {"id": "ITAB6BLTT02STSAQ",    "freq": "Q"},
    },
    "KOR": {
        "real_gdp":         {"id": "NAEXKP01KRQ661S",     "freq": "Q"},
        "wage_real_idx":    {"id": "LCEAMN01KRQ661S",     "freq": "Q"},
        "reer":             {"id": "RBKRBIS",             "freq": "M"},
        "current_account":  {"id": "KORB6BLTT02STSAQ",    "freq": "Q"},
    },
}


def _get_fred() -> Fred:
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        raise ValueError("FRED_API_KEY が未設定です。.env を確認してください。")
    return Fred(api_key=api_key)


def fetch_one(series_id: str, start: str = "1995-01-01") -> pd.Series:
    fred = _get_fred()
    for attempt in range(3):
        try:
            return fred.get_series(series_id, observation_start=start)
        except Exception as e:
            if attempt == 2:
                return pd.Series(dtype=float)
            time.sleep(2)
    return pd.Series(dtype=float)


def to_quarterly(s: pd.Series, freq: str) -> pd.Series:
    if s.empty:
        return s
    if freq == "M":
        return s.resample("QE").mean()
    return s.resample("QE").last()


def fetch_country(country: str, start: str = "1995-01-01", verbose: bool = True) -> pd.DataFrame:
    spec_dict = COUNTRIES_SERIES[country]
    pieces: dict[str, pd.Series] = {}
    if verbose:
        print(f"  [{country}] 取得中...")
    for var, spec in spec_dict.items():
        s = fetch_one(spec["id"], start=start)
        if s.empty:
            if verbose:
                print(f"    {var} ({spec['id']}): 失敗")
            continue
        s_q = to_quarterly(s, spec["freq"])
        pieces[var] = s_q
        if verbose:
            print(f"    {var} ({spec['id']}): {len(s_q)} 期")
        time.sleep(0.3)
    if not pieces:
        return pd.DataFrame()
    df = pd.concat(pieces, axis=1)
    df.index.name = "date"
    return df.sort_index()


def fetch_all(start: str = "1995-01-01", countries: list[str] | None = None,
              verbose: bool = True) -> dict[str, pd.DataFrame]:
    targets = countries or list(COUNTRIES_SERIES)
    result: dict[str, pd.DataFrame] = {}
    for c in targets:
        if verbose:
            print()
        try:
            result[c] = fetch_country(c, start, verbose)
        except Exception as e:
            if verbose:
                print(f"  [{c}] エラー: {e}")
    return result


def save_raw(data: dict[str, pd.DataFrame]) -> dict[str, Path]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    paths: dict[str, Path] = {}
    for c, df in data.items():
        if df.empty:
            continue
        path = RAW_DIR / f"g7_external_{c}.csv"
        df.to_csv(path)
        print(f"  保存: {path} ({len(df)} 行 × {df.shape[1]} 列)")
        paths[c] = path
    return paths


def load_country(country: str) -> pd.DataFrame:
    path = RAW_DIR / f"g7_external_{country}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, index_col="date", parse_dates=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="G7 + 韓国 四半期データ収集")
    parser.add_argument("--country", default="all")
    parser.add_argument("--start", default="1995-01-01")
    args = parser.parse_args()

    targets = (list(COUNTRIES_SERIES)
               if args.country == "all"
               else [c.upper() for c in args.country.split(",")])

    print("=== G7 + 韓国 四半期外的データ収集（FRED） ===")
    print(f"  対象: {targets}")
    print(f"  期間: {args.start} ~ 最新")

    data = fetch_all(args.start, targets)
    paths = save_raw(data)
    print(f"\n完了: {len(paths)} 国")


if __name__ == "__main__":
    main()
