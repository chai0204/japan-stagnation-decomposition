"""G7 + 韓国の年間平均労働時間を FRED（OECD MEI）から収集する.

OECD "Average annual hours actually worked per worker" シリーズ.

FRED 命名規則: AVHWPE<CCC>A065N が一部、または ANTOTAVH<CC>A661S 形式.
試行錯誤で正しい ID を探る.
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

# OECD 平均年間労働時間（FRED）
HOURS_SERIES: dict[str, str] = {
    "USA": "AVHWPEUSA065NRUG",   # 試行
    "JPN": "AVHWPEJPA065NRUG",
    "DEU": "AVHWPEDEA065NRUG",
    "FRA": "AVHWPEFRA065NRUG",
    "GBR": "AVHWPEGBA065NRUG",
    "CAN": "AVHWPECAA065NRUG",
    "ITA": "AVHWPEITA065NRUG",
    "KOR": "AVHWPEKRA065NRUG",
}

# Penn World Tables 経由の代替 ID（OECD MEI 廃止に対応）
# AvhwHO: Average annual hours worked by persons engaged
ALT_HOURS_SERIES: dict[str, str] = {
    "USA": "ANTOTAVH USA661S",
    "JPN": "ANTOTAVH JPA661S",
    "DEU": "ANTOTAVH DEA661S",
    "FRA": "ANTOTAVH FRA661S",
    "GBR": "ANTOTAVH GBA661S",
    "CAN": "ANTOTAVH CAA661S",
    "ITA": "ANTOTAVH ITA661S",
    "KOR": "ANTOTAVH KRA661S",
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


def try_series_for_country(country: str, start: str = "1990-01-01",
                              verbose: bool = True) -> pd.Series:
    """複数候補を試す."""
    candidates = [
        HOURS_SERIES.get(country, ""),
        ALT_HOURS_SERIES.get(country, "").replace(" ", ""),
        f"AVHWPE{country[:2]}A065NRUG",
    ]
    for sid in candidates:
        if not sid:
            continue
        s = fetch_one(sid, start)
        if not s.empty:
            if verbose:
                print(f"    [{country}] {sid}: {len(s)} 件")
            return s
        time.sleep(0.3)
    if verbose:
        print(f"    [{country}] 全候補失敗")
    return pd.Series(dtype=float)


def fetch_all(start: str = "1990-01-01", verbose: bool = True) -> pd.DataFrame:
    rows = []
    for c in HOURS_SERIES:
        s = try_series_for_country(c, start, verbose)
        if s.empty:
            continue
        for date, value in s.items():
            rows.append({
                "year":    date.year if hasattr(date, "year") else int(date),
                "country": c,
                "hours_per_worker": value,
            })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    return df


def save(df: pd.DataFrame) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / "g7_hours_per_worker.csv"
    df.to_csv(path, index=False)
    print(f"  保存: {path} ({len(df)} 行)")
    return path


def load() -> pd.DataFrame:
    path = RAW_DIR / "g7_hours_per_worker.csv"
    if not path.exists():
        return pd.DataFrame()
    return pd.read_csv(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="G7 + 韓国 労働時間収集")
    parser.add_argument("--start", default="1990-01-01")
    args = parser.parse_args()

    print("=== G7 + 韓国 年間労働時間収集 ===")
    df = fetch_all(args.start)
    if df.empty:
        print("\nデータ取得失敗")
        return
    save(df)
    print(f"\n国別データ範囲:")
    print(df.groupby("country")["year"].agg(["min", "max", "count"]).to_string())


if __name__ == "__main__":
    main()
