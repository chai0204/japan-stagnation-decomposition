"""日本の対外金融フロー・家計指標を FRED 経由で収集する.

対象（四半期）:
    real_gdp        : 実質 GDP（10 億円、SAAR）           [JPNRGDPEXP]
    nominal_gdp     : 名目 GDP（10 億円）                  [JPNNGDP]
    real_wage_idx   : 実質賃金指数                         [LCEAMN01JPM659S → 四半期化]
    nominal_wage    : 名目賃金（時給ベース）               [LCEAMN01JPQ659S]
    fx_jpy_usd      : JPY/USD 為替レート（月次→四半期平均）[DEXJPUS]
    reer            : 実質実効為替レート                   [RBJPBIS]
    portfolio_out   : 対外証券投資（純流出、四半期）       [BPBLPNRI01JPQ188N]
    current_account : 経常収支（四半期、10億円）          [BPBLTD01JPQ637N]
    nfa             : 対外純資産（IIP、年次→四半期内挿）  [JPNNFA — 推定]

出力: data/raw/japan_external_quarterly.csv （四半期インデックス）
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

# ── FRED 系列定義 ────────────────────────────────────────────────────────────

SERIES: dict[str, dict] = {
    "real_gdp":         {"id": "JPNRGDPEXP",          "freq": "Q"},
    "nominal_gdp":      {"id": "JPNNGDP",             "freq": "Q"},
    "wage_real_idx":    {"id": "LCEAMN01JPQ661S",     "freq": "Q"},
    "fx_jpy_usd":       {"id": "EXJPUS",              "freq": "M"},
    "reer":             {"id": "RBJPBIS",             "freq": "M"},
    "current_account":  {"id": "JPNB6BLTT02STSAQ",    "freq": "Q"},
    "portfolio_assets": {"id": "JPNB6FAFLPRDOXDCQ",   "freq": "Q"},
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
                print(f"    {series_id} 取得失敗: {e}")
                return pd.Series(dtype=float)
            time.sleep(2)
    return pd.Series(dtype=float)


def to_quarterly(s: pd.Series, freq: str) -> pd.Series:
    """月次は四半期平均、四半期はそのまま."""
    if s.empty:
        return s
    if freq == "M":
        return s.resample("QE").mean()
    if freq == "Q":
        return s.resample("QE").last()
    return s


def fetch_japan_external(start: str = "1995-01-01", verbose: bool = True) -> pd.DataFrame:
    if verbose:
        print(f"=== 日本対外フロー・家計指標収集（FRED） ===")
        print(f"  期間: {start} ~ 最新")

    pieces: dict[str, pd.Series] = {}
    for var, spec in SERIES.items():
        if verbose:
            print(f"  [{var}] {spec['id']} ({spec['freq']})...", end=" ")
        s = fetch_one(spec["id"], start=start)
        if s.empty:
            if verbose:
                print("空")
            continue
        s_q = to_quarterly(s, spec["freq"])
        pieces[var] = s_q
        if verbose:
            print(f"{len(s_q)} 期 ({s_q.index.min().date()} ~ {s_q.index.max().date()})")
        time.sleep(0.3)

    if not pieces:
        return pd.DataFrame()

    df = pd.concat(pieces, axis=1)
    df.index.name = "date"
    return df.sort_index()


def save(df: pd.DataFrame) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / "japan_external_quarterly.csv"
    df.to_csv(path)
    print(f"  保存: {path} ({len(df)} 行 × {df.shape[1]} 列)")
    return path


def load() -> pd.DataFrame:
    path = RAW_DIR / "japan_external_quarterly.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path, index_col="date", parse_dates=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="日本対外フロー収集")
    parser.add_argument("--start", default="1995-01-01")
    args = parser.parse_args()

    df = fetch_japan_external(args.start)
    if df.empty:
        print("\nデータが取得できませんでした。")
        return
    save(df)
    print(f"\n=== サマリー ===")
    print(df.describe().round(2).to_string())


if __name__ == "__main__":
    main()
