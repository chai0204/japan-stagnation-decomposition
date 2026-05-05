"""北欧 4 国 vs 日本：サービス業生産性高水準モデルの比較.

仮説 H12:
    北欧諸国（FIN, SWE, DNK, NOR）はサービス業生産性が高く、
    日本のサービス業改革の参考モデルになる.

分析:
    - 4 水準 GDP 成長（per-WA, per-hour）
    - 輸出/GDP（小国の高開放度）
    - 労働分配率（PWT で利用可能なら）
    - サービス業 va_pct

データ:
    - WDI（北欧 4 国を追加済み）
    - 既存の G7 + 韓国データと統合

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - nordic_vs_japan_growth.png
        - nordic_vs_japan_indicators.png
    data/processed/
        - japan_stagnation_nordic.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.collectors.wdi_collector import load_country
from src.macro.japan_stagnation.stylized_facts import FIG_DIR, PROCESSED_DIR

NORDIC = ["FIN", "SWE", "DNK", "NOR"]
JAPAN_AND_PEERS = ["JPN", "USA", "DEU", "KOR"]
ALL_COUNTRIES = JAPAN_AND_PEERS + NORDIC

LABEL = {
    "JPN": "Japan", "USA": "USA", "DEU": "Germany", "KOR": "Korea",
    "FIN": "Finland", "SWE": "Sweden", "DNK": "Denmark", "NOR": "Norway",
}
COLOR = {
    "JPN": "#d62728",
    "USA": "#1f77b4",
    "DEU": "#2ca02c",
    "KOR": "#ff7f0e",
    "FIN": "#17becf",
    "SWE": "#9467bd",
    "DNK": "#bcbd22",
    "NOR": "#8c564b",
}


def load_panel() -> pd.DataFrame:
    frames = []
    for c in ALL_COUNTRIES:
        df = load_country(c)
        if df.empty:
            continue
        df = df.copy()
        df["country"] = c
        frames.append(df.reset_index())
    return pd.concat(frames, ignore_index=True)


def compute_growth_levels(panel: pd.DataFrame, base: int = 1995, end: int = 2024) -> pd.DataFrame:
    panel["gdp_per_wa"] = panel["gdp_real"] / panel["population_15_64"]

    rows = []
    for c in panel["country"].unique():
        sub = panel[panel["country"] == c]
        if base not in sub["year"].values or end not in sub["year"].values:
            continue
        for var, label in [
            ("gdp_real",       "total_gdp"),
            ("gdp_per_capita", "per_capita"),
            ("gdp_per_wa",     "per_wa"),
            ("gni_per_capita", "gni_pc"),
        ]:
            sub_v = sub.dropna(subset=[var])
            if base not in sub_v["year"].values or end not in sub_v["year"].values:
                continue
            v0 = sub_v.loc[sub_v["year"] == base, var].iloc[0]
            v1 = sub_v.loc[sub_v["year"] == end, var].iloc[0]
            if v0 > 0:
                rows.append({
                    "country": c, "var": label,
                    "growth_pct": (v1 / v0 - 1) * 100,
                })
    return pd.DataFrame(rows)


def plot_growth_comparison(growth: pd.DataFrame) -> Path:
    pivot = growth.pivot(index="country", columns="var", values="growth_pct")
    pivot = pivot.reindex(ALL_COUNTRIES)

    fig, ax = plt.subplots(figsize=(11, 6))
    x = np.arange(len(pivot.index))
    width = 0.2

    for i, var in enumerate(["total_gdp", "per_capita", "per_wa", "gni_pc"]):
        if var not in pivot.columns:
            continue
        offset = (i - 1.5) * width
        ax.bar(x + offset, pivot[var].values, width,
               label={
                   "total_gdp": "Total GDP",
                   "per_capita": "Per capita",
                   "per_wa": "Per WA",
                   "gni_pc": "Per capita GNI",
               }[var], alpha=0.85)

    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels([LABEL[c] for c in pivot.index], rotation=15)
    ax.set_ylabel("Cumulative growth 1995-2024 (%)")
    ax.set_title("Nordic Countries vs Japan: 1995-2024 Growth\n"
                  "Nordic countries achieved both high per-capita growth and high openness",
                  fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="best", fontsize=9, framealpha=0.85)

    if "JPN" in pivot.index:
        jp_idx = pivot.index.get_loc("JPN")
        ax.axvspan(jp_idx - 0.45, jp_idx + 0.45, alpha=0.08, color="red")

    fig.tight_layout()
    out = FIG_DIR / "nordic_vs_japan_growth.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_indicators(panel: pd.DataFrame) -> Path:
    """直近 5 年平均の輸出/GDP, FDI/GDP, GNI-GDP を国別比較."""
    recent = panel[(panel["year"] >= 2019) & (panel["year"] <= 2023)]
    avg = recent.groupby("country").agg(
        exports=("exports_gdp_share", "mean"),
        fdi=("fdi_outflows_gdp", "mean"),
    ).reindex(ALL_COUNTRIES)
    avg["gni_gdp_gap"] = recent.groupby("country").apply(
        lambda d: ((d["gni_real"] - d["gdp_real"]) / d["gdp_real"] * 100).mean()
    ).reindex(ALL_COUNTRIES)

    fig, axes = plt.subplots(1, 3, figsize=(15, 5))
    titles = ["Exports / GDP (%)", "Outward FDI / GDP (%)", "GNI − GDP (% of GDP)"]
    for ax, var, title in zip(axes, ["exports", "fdi", "gni_gdp_gap"], titles):
        colors = ["#d62728" if c == "JPN" else
                   "#17becf" if c in NORDIC else "gray"
                   for c in avg.index]
        ax.bar([LABEL[c] for c in avg.index], avg[var].values,
                color=colors, alpha=0.85, edgecolor="black", linewidth=0.5)
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.grid(True, axis="y", alpha=0.3)
        ax.tick_params(axis="x", rotation=20)

    fig.suptitle("Nordic vs Japan: Trade and FDI Indicators (2019-2023 avg)",
                 fontsize=12, fontweight="bold", y=1.02)
    fig.tight_layout()
    out = FIG_DIR / "nordic_vs_japan_indicators.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== B-4: Nordic Countries vs Japan ===")

    panel = load_panel()
    if verbose:
        print(f"  パネル: {len(panel)} 行 × {panel['country'].nunique()} 国")

    growth = compute_growth_levels(panel)
    p1 = plot_growth_comparison(growth)
    p2 = plot_indicators(panel)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = PROCESSED_DIR / "japan_stagnation_nordic.csv"
    pivot = growth.pivot(index="country", columns="var", values="growth_pct")
    pivot.to_csv(out_csv)

    if verbose:
        print("\n=== 累積成長率 1995-2024（%） ===")
        print(pivot.reindex(ALL_COUNTRIES).round(1).to_string())

        print("\n=== 直近 5 年平均（2019-2023） ===")
        recent = panel[(panel["year"] >= 2019) & (panel["year"] <= 2023)]
        summary = recent.groupby("country").agg(
            exports_gdp_share=("exports_gdp_share", "mean"),
            fdi_outflows_gdp=("fdi_outflows_gdp", "mean"),
        ).reindex(ALL_COUNTRIES)
        print(summary.round(2).to_string())

        print(f"\n  図1: {p1}")
        print(f"  図2: {p2}")

    return {"growth": growth, "panel": panel}


def main() -> None:
    parser = argparse.ArgumentParser(description="北欧 4 国比較")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
