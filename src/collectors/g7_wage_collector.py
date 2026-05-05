"""G7 + 韓国の年次/四半期賃金データを FRED から収集する.

対象（年次）:
    nominal_wage    : 名目賃金水準（OECD MEI、年次平均、自国通貨）
    real_wage_idx   : 実質賃金指数（CPI デフレート）

国別 FRED 系列:
    US: LCEAMN01USA659S（年次平均、実質）  / 名目: LCEATT01USA661S
    JP: LCEAMN01JPA659S 等

注意: FRED の OECD 系列で年次（A）コードがある国を使用.
       一部の国はこのバンクで取得できないため、別系列で代替.

簡略化: ここでは「実質賃金指数（OECD-MEI）」を年次平均値として取得し、
       Japan dummy 推定に十分な G7 + 韓国の長期パネルを作る.

出力: data/raw/wage_<country>.csv
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

# OECD Main Economic Indicators 経由の年次実質賃金指数（FRED）
# 命名規則: LCEAMN01<CC>A659S = wages from employment, real, annual

WAGE_SERIES: dict[str, str] = {
    "USA": "LCEAMN01USA659N",   # nominal earnings, all employees, annual
    "JPN": "LCEAMN01JPA659N",
    "DEU": "LCEAMN01DEA659N",
    "FRA": "LCEAMN01FRA659N",
    "GBR": "LCEAMN01GBA659N",
    "CAN": "LCEAMN01CAA659N",
    "ITA": "LCEAMN01ITA659N",
    "KOR": "LCEAMN01KRA659N",
}

# 実質版（インフレ調整済み、index 2015=100）
REAL_WAGE_SERIES: dict[str, str] = {
    "USA": "LCEAMN01USA661N",
    "JPN": "LCEAMN01JPA661N",
    "DEU": "LCEAMN01DEA661N",
    "FRA": "LCEAMN01FRA661N",
    "GBR": "LCEAMN01GBA661N",
    "CAN": "LCEAMN01CAA661N",
    "ITA": "LCEAMN01ITA661N",
    "KOR": "LCEAMN01KRA661N",
}


def _get_fred() -> Fred:
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        raise ValueError("FRED_API_KEY が未設定です。.env を確認してください。")
    return Fred(api_key=api_key)


def fetch_one(series_id: str, start: str = "1990-01-01") -> pd.Series:
    fred = _get_fred()
    for attempt in range(3):
        try:
            return fred.get_series(series_id, observation_start=start)
        except Exception:
            if attempt == 2:
                return pd.Series(dtype=float)
            time.sleep(2)
    return pd.Series(dtype=float)


def fetch_country(country: str, start: str = "1990-01-01",
                   verbose: bool = True) -> pd.DataFrame:
    pieces: dict[str, pd.Series] = {}

    # 名目賃金
    nominal_id = WAGE_SERIES.get(country, "")
    if nominal_id:
        s = fetch_one(nominal_id, start)
        if not s.empty:
            s.index = s.index.year
            pieces["nominal_wage"] = s
            if verbose:
                print(f"  [{country}] {nominal_id}: {s.notna().sum()} 件")
        time.sleep(0.3)

    # 実質賃金
    real_id = REAL_WAGE_SERIES.get(country, "")
    if real_id:
        s = fetch_one(real_id, start)
        if not s.empty:
            s.index = s.index.year
            pieces["real_wage"] = s
            if verbose:
                print(f"  [{country}] {real_id}: {s.notna().sum()} 件")
        time.sleep(0.3)

    if not pieces:
        return pd.DataFrame()
    df = pd.DataFrame(pieces)
    df.index.name = "year"
    return df.sort_index()


def fetch_all(start: str = "1990-01-01", verbose: bool = True) -> dict[str, pd.DataFrame]:
    out = {}
    for c in WAGE_SERIES:
        if verbose:
            print()
        out[c] = fetch_country(c, start, verbose)
    return out


def save_raw(data: dict[str, pd.DataFrame]) -> dict[str, Path]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    paths = {}
    for c, df in data.items():
        if df.empty:
            continue
        path = RAW_DIR / f"wage_{c}.csv"
        df.to_csv(path)
        print(f"  保存: {path} ({len(df)} 行)")
        paths[c] = path
    return paths


def load_country(country: str) -> pd.DataFrame:
    path = RAW_DIR / f"wage_{country}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, index_col="year")


def main() -> None:
    parser = argparse.ArgumentParser(description="G7 + 韓国 賃金データ収集")
    parser.add_argument("--start", default="1990-01-01")
    args = parser.parse_args()

    print("=== G7 + 韓国 年次賃金データ収集 ===")
    data = fetch_all(args.start)
    save_raw(data)


if __name__ == "__main__":
    main()
