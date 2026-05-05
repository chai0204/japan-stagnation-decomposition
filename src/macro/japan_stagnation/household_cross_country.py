"""家計金融資産構成のクロスカントリー比較 + H6 再検証.

OECD データから G7+韓国の家計金融資産構成を比較し、
日本の特異性（預金偏重、リスク資産過小）を識別.

仮説 H6 の精緻化:
    家計のリスク資産（株式 + 投信）比率が低い国は、
    国内資産リターン低下時に対外シフトを起こしにくい（換言：「シフトする土台がない」）.

    日本：リスク資産比率が低い → 新NISA以前は対外シフト基盤が未整備
    新NISA は「シフトの障壁を下げた」という意味で重要.

検証:
    - 各国の家計金融資産構成（2000-2024）
    - 日本対他国の差を可視化
    - リスク資産比率と GDP 成長率の関係（パネル回帰）
    - 新NISA 構造変化の予備的検証

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - household_composition_g7.png
        - household_risk_assets_japan_focus.png
    data/processed/
        - japan_stagnation_household_cross_country.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.collectors.oecd_household_collector import COUNTRIES, load_country
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
    # リスク資産比率（株 + 投信）
    panel["risk_assets_pct"] = (
        panel.get("listed_equity_pct", 0).fillna(0)
        + panel.get("investment_funds_pct", 0).fillna(0)
    )
    # 安全資産（預金 + 保険）
    panel["safe_assets_pct"] = (
        panel.get("currency_deposits_pct", 0).fillna(0)
        + panel.get("insurance_pension_pct", 0).fillna(0)
    )
    return panel


# ── 図1: 各国の家計資産構成（時系列） ───────────────────────────────────────

def plot_composition_time(panel: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharex=True)
    axes = axes.flatten()

    indicators = [
        ("currency_deposits_pct", "Currency & Deposits"),
        ("listed_equity_pct",     "Listed Equity"),
        ("investment_funds_pct",  "Investment Funds"),
        ("insurance_pension_pct", "Insurance & Pension"),
    ]

    for ax, (var, title) in zip(axes, indicators):
        for c in COUNTRY_ORDER:
            sub = panel[panel["country"] == c].sort_values("year")
            if sub.empty or var not in sub.columns:
                continue
            sub = sub.dropna(subset=[var])
            if sub.empty:
                continue
            lw = 2.5 if c == "JPN" else 1.3
            alpha = 1.0 if c == "JPN" else 0.7
            ax.plot(sub["year"], sub[var],
                    label=COUNTRY_LABEL[c], color=COLOR[c],
                    linewidth=lw, alpha=alpha)
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_ylabel("% of household financial assets")
        ax.grid(True, alpha=0.3)

    axes[0].legend(ncol=4, loc="best", fontsize=8, framealpha=0.85)
    for ax in axes[2:]:
        ax.set_xlabel("Year")

    fig.suptitle("Household Financial Asset Composition: G7 + Korea",
                 fontsize=12, fontweight="bold", y=1.00)
    fig.tight_layout()

    out = FIG_DIR / "household_composition_g7.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── 図2: リスク資産比率（日本焦点） ─────────────────────────────────────────

def plot_risk_assets(panel: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(11, 6))
    for c in COUNTRY_ORDER:
        sub = panel[panel["country"] == c].sort_values("year")
        if sub.empty:
            continue
        sub = sub.dropna(subset=["risk_assets_pct"])
        if sub.empty:
            continue
        lw = 2.5 if c == "JPN" else 1.3
        alpha = 1.0 if c == "JPN" else 0.7
        ax.plot(sub["year"], sub["risk_assets_pct"],
                label=COUNTRY_LABEL[c], color=COLOR[c],
                linewidth=lw, alpha=alpha)

    # 新NISA 開始の縦線
    ax.axvline(2024, color="red", linewidth=1.5, linestyle=":",
                alpha=0.6, label="New NISA (2024Q1)")
    ax.set_title("Household Risk Assets (Equity + Investment Funds, % of FAS)",
                  fontsize=11, fontweight="bold")
    ax.set_xlabel("Year")
    ax.set_ylabel("% of household financial assets")
    ax.grid(True, alpha=0.3)
    ax.legend(ncol=4, loc="best", fontsize=9, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / "household_risk_assets_japan_focus.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── 直近 5 年（2019-2023）の構成比較 ──────────────────────────────────────

def compute_recent_summary(panel: pd.DataFrame) -> pd.DataFrame:
    recent = panel[(panel["year"] >= 2019) & (panel["year"] <= 2023)]
    summary = recent.groupby("country").agg(
        deposits=("currency_deposits_pct", "mean"),
        equity=("listed_equity_pct", "mean"),
        funds=("investment_funds_pct", "mean"),
        insurance=("insurance_pension_pct", "mean"),
        debt=("debt_securities_pct", "mean"),
        risk_assets=("risk_assets_pct", "mean"),
        safe_assets=("safe_assets_pct", "mean"),
    ).reindex(COUNTRY_ORDER)
    return summary


# ── メイン ────────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== クロスカントリー家計金融資産分析 ===")

    panel = build_panel()
    if verbose:
        print(f"  パネル: {len(panel)} 行 ({panel['country'].nunique()} 国)")

    p1 = plot_composition_time(panel)
    p2 = plot_risk_assets(panel)

    summary = compute_recent_summary(panel)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = PROCESSED_DIR / "japan_stagnation_household_cross_country.csv"
    summary.to_csv(out_csv)

    if verbose:
        print("\n=== 直近 5 年（2019-2023）平均、% of household financial assets ===")
        print(summary.round(2).to_string())

        print("\n=== 日本の特異性ハイライト ===")
        if "JPN" in summary.index:
            jp = summary.loc["JPN"]
            others = summary.drop("JPN")
            for var in ["deposits", "equity", "funds", "risk_assets"]:
                if var in jp.index and not pd.isna(jp[var]):
                    other_avg = others[var].mean()
                    diff = jp[var] - other_avg
                    print(f"  {var:15s}: 日本 {jp[var]:5.1f}% vs 他国平均 {other_avg:5.1f}% (差 {diff:+5.1f}pp)")

        print(f"\n  図1 (構成時系列): {p1}")
        print(f"  図2 (リスク資産): {p2}")

    return {"panel": panel, "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="家計クロスカントリー分析")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
