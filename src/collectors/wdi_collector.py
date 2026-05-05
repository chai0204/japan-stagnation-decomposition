"""World Bank WDI（World Development Indicators）から G7 + 韓国の年次データを取得する.

対象変数（年次）:
    gdp_real            : 実質GDP（2015年USドル基準、定価）
    gdp_per_capita      : 1人あたり実質GDP（2015年USドル）
    population          : 総人口
    population_15_64    : 生産年齢人口（15-64歳）
    gni_real            : 実質GNI（国民総所得、2015年USドル）
    gni_per_capita      : 1人あたり実質GNI
    exports_gdp_share   : 財・サービス輸出/GDP（%）
    fdi_outflows_gdp    : 対外直接投資フロー/GDP（%）
    services_exports    : サービス輸出（USドル）

対象国: G7 + 韓国（KR）

出力: data/raw/wdi_<country>.csv
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import pandas as pd
import requests

RAW_DIR = Path(__file__).parents[2] / "data" / "raw"

COUNTRIES: dict[str, str] = {
    "USA": "米国",
    "JPN": "日本",
    "DEU": "ドイツ",
    "FRA": "フランス",
    "GBR": "英国",
    "CAN": "カナダ",
    "ITA": "イタリア",
    "KOR": "韓国",
    "FIN": "フィンランド",
    "SWE": "スウェーデン",
    "DNK": "デンマーク",
    "NOR": "ノルウェー",
}

WDI_INDICATORS: dict[str, str] = {
    "gdp_real":          "NY.GDP.MKTP.KD",   # GDP (constant 2015 US$)
    "gdp_per_capita":    "NY.GDP.PCAP.KD",   # GDP per capita (constant 2015 US$)
    "population":        "SP.POP.TOTL",      # 総人口
    "population_15_64":  "SP.POP.1564.TO",   # 生産年齢人口（15-64歳）
    "gni_real":          "NY.GNP.MKTP.KD",   # GNI (constant 2015 US$)
    "gni_per_capita":    "NY.GNP.PCAP.KD",   # GNI per capita (constant 2015 US$)
    "exports_gdp_share": "NE.EXP.GNFS.ZS",   # Exports of goods and services (% of GDP)
    "fdi_outflows_gdp":  "BM.KLT.DINV.WD.GD.ZS",  # FDI net outflows (% of GDP)
    "services_exports":  "BX.GSR.NFSV.CD",   # Service exports (BoP, current US$)
}

API_BASE = "https://api.worldbank.org/v2"


def _fetch_indicator(
    country: str,
    indicator: str,
    start_year: int = 1990,
    end_year: int = 2024,
) -> pd.Series:
    """単一指標を取得する（World Bank API）.

    Returns:
        pd.Series: index=年（int）, values=値
    """
    url = f"{API_BASE}/country/{country}/indicator/{indicator}"
    params = {
        "format": "json",
        "date": f"{start_year}:{end_year}",
        "per_page": 100,
    }
    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            break
        except Exception:
            if attempt == 2:
                return pd.Series(dtype=float)
            time.sleep(2)

    if not isinstance(data, list) or len(data) < 2 or data[1] is None:
        return pd.Series(dtype=float)

    rows = data[1]
    parsed = {int(r["date"]): r["value"] for r in rows if r["value"] is not None}
    if not parsed:
        return pd.Series(dtype=float)
    s = pd.Series(parsed).sort_index()
    s.index.name = "year"
    return s


def fetch_country(
    country: str,
    start_year: int = 1990,
    end_year: int = 2024,
    verbose: bool = True,
) -> pd.DataFrame:
    """1 国の全 WDI 指標を取得し DataFrame にまとめる."""
    if country not in COUNTRIES:
        raise ValueError(f"未定義の国コード: {country}. 利用可能: {list(COUNTRIES)}")

    if verbose:
        print(f"  [{country}] {COUNTRIES[country]} 取得中...")

    pieces: dict[str, pd.Series] = {}
    for var, indicator in WDI_INDICATORS.items():
        s = _fetch_indicator(country, indicator, start_year, end_year)
        pieces[var] = s
        if verbose:
            n = s.notna().sum()
            print(f"    {var}: {n} 件")
        time.sleep(0.5)

    df = pd.DataFrame(pieces)
    df.index.name = "year"
    return df.sort_index()


def fetch_all(
    start_year: int = 1990,
    end_year: int = 2024,
    countries: list[str] | None = None,
    verbose: bool = True,
) -> dict[str, pd.DataFrame]:
    targets = countries or list(COUNTRIES)
    result: dict[str, pd.DataFrame] = {}
    for c in targets:
        if verbose:
            print()
        try:
            result[c] = fetch_country(c, start_year, end_year, verbose)
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
        path = RAW_DIR / f"wdi_{c}.csv"
        df.to_csv(path)
        print(f"  保存: {path} ({len(df)} 行)")
        paths[c] = path
    return paths


def load_country(country: str) -> pd.DataFrame:
    path = RAW_DIR / f"wdi_{country}.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, index_col="year")


def main() -> None:
    parser = argparse.ArgumentParser(description="World Bank WDI 年次データ収集")
    parser.add_argument("--country", default="all")
    parser.add_argument("--start", type=int, default=1990)
    parser.add_argument("--end", type=int, default=2024)
    args = parser.parse_args()

    targets = list(COUNTRIES) if args.country == "all" else [c.upper() for c in args.country.split(",")]

    print("=== World Bank WDI 年次データ収集 ===")
    print(f"  対象国: {targets}")
    print(f"  期間: {args.start}-{args.end}")

    data = fetch_all(args.start, args.end, targets)
    paths = save_raw(data)
    print(f"\n完了: {len(paths)} 国")


if __name__ == "__main__":
    main()
