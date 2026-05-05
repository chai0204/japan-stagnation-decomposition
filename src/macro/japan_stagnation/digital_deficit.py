"""デジタル赤字 G7 比較：サービス収支とライセンス収支の国際比較.

仮説 H7 の検証:
    日本のデジタル赤字（サービス収支のうち ICT 関連）は対 GDP 比で G7 最大.

分析:
    1. サービス収支対 GDP 比の時系列（2000-2024）
    2. ICT サービス収支対 GDP 比の推計（ICT シェア × サービス輸出入）
    3. 知財ライセンス収支対 GDP 比
    4. 直近 5 年（2019-2023）の G7 比較

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - services_balance_g7.png
        - digital_deficit_proxy.png
        - royalty_balance_g7.png
    data/processed/
        - japan_stagnation_digital_deficit.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.collectors.wdi_services_collector import COUNTRIES, load_country
from src.macro.japan_stagnation.stylized_facts import (
    COLOR, COUNTRY_LABEL, COUNTRY_ORDER, FIG_DIR, PROCESSED_DIR,
)


def build_panel() -> pd.DataFrame:
    frames = []
    for c in COUNTRIES:
        df = load_country(c)
        if df.empty:
            continue
        df = df.copy()
        df["country"] = c
        frames.append(df.reset_index())
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.set_index(["year", "country"]).sort_index()

    # 派生変数
    df = panel.reset_index().copy()
    df["services_balance"]      = df["services_exports_usd"] - df["services_imports_usd"]
    df["services_balance_pct"]  = df["services_balance"] / df["nominal_gdp_usd"] * 100
    df["royalty_balance"]       = df["royalty_receipts_usd"] - df["royalty_payments_usd"]
    df["royalty_balance_pct"]   = df["royalty_balance"] / df["nominal_gdp_usd"] * 100

    # ICT 推計値（シェア × 全体）
    df["ict_exports_usd"] = (
        df["services_exports_usd"] * df["ict_services_exports"] / 100
    )
    df["ict_imports_usd"] = (
        df["services_imports_usd"] * df["ict_services_imports"] / 100
    )
    df["ict_balance"]     = df["ict_exports_usd"] - df["ict_imports_usd"]
    df["ict_balance_pct"] = df["ict_balance"] / df["nominal_gdp_usd"] * 100

    return df.set_index(["year", "country"]).sort_index()


# ── プロット: サービス収支対 GDP 比 ──────────────────────────────────────────

def plot_services_balance(panel: pd.DataFrame) -> Path:
    df = panel.reset_index()
    fig, ax = plt.subplots(figsize=(11, 6))
    for c in COUNTRY_ORDER:
        sub = df[df["country"] == c].sort_values("year")
        if sub.empty:
            continue
        lw = 2.5 if c == "JPN" else 1.3
        alpha = 1.0 if c == "JPN" else 0.7
        ax.plot(sub["year"], sub["services_balance_pct"],
                label=COUNTRY_LABEL[c], color=COLOR[c],
                linewidth=lw, alpha=alpha)
    ax.axhline(0, color="black", linewidth=0.6, linestyle=":")
    ax.set_title("Services Balance as % of GDP — G7 + Korea",
                  fontsize=11, fontweight="bold")
    ax.set_xlabel("Year")
    ax.set_ylabel("% of GDP")
    ax.grid(True, alpha=0.3)
    ax.legend(ncol=4, loc="best", fontsize=9, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / "services_balance_g7.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_ict_balance(panel: pd.DataFrame) -> Path:
    df = panel.reset_index().copy()
    df = df[df["ict_balance_pct"].notna()]
    fig, ax = plt.subplots(figsize=(11, 6))
    for c in COUNTRY_ORDER:
        sub = df[df["country"] == c].sort_values("year")
        if sub.empty:
            continue
        lw = 2.5 if c == "JPN" else 1.3
        alpha = 1.0 if c == "JPN" else 0.7
        ax.plot(sub["year"], sub["ict_balance_pct"],
                label=COUNTRY_LABEL[c], color=COLOR[c],
                linewidth=lw, alpha=alpha)
    ax.axhline(0, color="black", linewidth=0.6, linestyle=":")
    ax.set_title("ICT Services Balance as % of GDP — Estimate (ICT share × total)",
                  fontsize=11, fontweight="bold")
    ax.set_xlabel("Year")
    ax.set_ylabel("% of GDP")
    ax.grid(True, alpha=0.3)
    ax.legend(ncol=4, loc="best", fontsize=9, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / "digital_deficit_proxy.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_royalty_balance(panel: pd.DataFrame) -> Path:
    df = panel.reset_index()
    fig, ax = plt.subplots(figsize=(11, 6))
    for c in COUNTRY_ORDER:
        sub = df[df["country"] == c].sort_values("year")
        if sub.empty:
            continue
        lw = 2.5 if c == "JPN" else 1.3
        alpha = 1.0 if c == "JPN" else 0.7
        ax.plot(sub["year"], sub["royalty_balance_pct"],
                label=COUNTRY_LABEL[c], color=COLOR[c],
                linewidth=lw, alpha=alpha)
    ax.axhline(0, color="black", linewidth=0.6, linestyle=":")
    ax.set_title("IP Royalty / License Balance as % of GDP — G7 + Korea",
                  fontsize=11, fontweight="bold")
    ax.set_xlabel("Year")
    ax.set_ylabel("% of GDP")
    ax.grid(True, alpha=0.3)
    ax.legend(ncol=4, loc="best", fontsize=9, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / "royalty_balance_g7.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── メイン ────────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== Phase 4: Digital Deficit G7 Comparison ===")

    panel = build_panel()

    if verbose:
        print(f"  パネル: {panel.shape[0]} obs × {panel.shape[1]} 列")
        print(f"  対象期間: {panel.index.get_level_values('year').min()} - "
              f"{panel.index.get_level_values('year').max()}")

    # 直近 5 年（2019-2023）平均
    df = panel.reset_index().copy()
    recent = df[(df["year"] >= 2019) & (df["year"] <= 2023)]
    summary = recent.groupby("country").agg(
        services_balance_pct=("services_balance_pct", "mean"),
        ict_balance_pct=("ict_balance_pct", "mean"),
        royalty_balance_pct=("royalty_balance_pct", "mean"),
    ).reindex(COUNTRY_ORDER)

    p1 = plot_services_balance(panel)
    p2 = plot_ict_balance(panel)
    p3 = plot_royalty_balance(panel)

    out_csv = PROCESSED_DIR / "japan_stagnation_digital_deficit.csv"
    summary.to_csv(out_csv)

    if verbose:
        print("\n=== 直近 5 年（2019-2023）G7 + 韓国比較 ===")
        print(summary.round(3).to_string())

        print(f"\n  図1: {p1}")
        print(f"  図2: {p2}")
        print(f"  図3: {p3}")
        print(f"  サマリー: {out_csv}")

    return {"panel": panel, "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="デジタル赤字 G7 比較")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
