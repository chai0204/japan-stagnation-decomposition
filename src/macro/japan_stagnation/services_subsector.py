"""サービス業 sub-sector 分解：日本のサービス業のどこが弱いか.

OECD STAN ベースの 2019 年データで日本対 G7 比較.

仮説 H11:
    日本のサービス業生産性低下は、特定 sub-sector（金融、専門サービス、ICT）に集中.

データ:
    - oecd_stan_collector: 9 サブセクターの付加価値 % of GDP（2019）
    - WDI: 雇用シェア（業種大分類）
    - 仮定: サービス業内の雇用配分は VA 配分とほぼ比例

注意：
    厳密な sub-sector 別労働生産性計算には sub-sector 別雇用が必要.
    本分析は付加価値構成の差から「日本のサービス業構造」の特徴を識別.

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - services_subsector_radar.png
        - services_subsector_japan_gap.png
    data/processed/
        - japan_stagnation_subsector.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.collectors.oecd_stan_collector import (
    OECD_STAN_2019, SUBSECTOR_LABELS, load as load_stan,
)
from src.macro.japan_stagnation.stylized_facts import (
    COLOR, COUNTRY_LABEL, COUNTRY_ORDER, FIG_DIR, PROCESSED_DIR,
)


def compute_japan_gaps(df: pd.DataFrame) -> pd.DataFrame:
    """日本のサブセクター対他国比較."""
    pivot = df.pivot(index="subsector", columns="country", values="va_pct")
    if "JPN" not in pivot.columns:
        return pd.DataFrame()
    jp = pivot["JPN"]

    rows = []
    for sub in pivot.index:
        for c in pivot.columns:
            if c == "JPN":
                continue
            other = pivot.loc[sub, c]
            rows.append({
                "subsector": sub,
                "label":     SUBSECTOR_LABELS.get(sub, sub),
                "country":   c,
                "japan_va_pct": jp[sub],
                "other_va_pct": other,
                "diff_pct":  jp[sub] - other,
            })
    return pd.DataFrame(rows)


# ── 図1: 日本 vs 米独韓 のレーダーチャート ─────────────────────────────────

def plot_radar(df: pd.DataFrame) -> Path:
    pivot = df.pivot(index="subsector", columns="country", values="va_pct")
    pivot = pivot.reindex([
        "G_wholesale_retail", "H_transport", "I_hotels_food",
        "J_ict", "K_finance", "L_realestate",
        "MN_professional", "OPQ_public_edu_health", "RSTU_other",
    ])

    countries_show = ["JPN", "USA", "DEU", "KOR"]
    angles = np.linspace(0, 2 * np.pi, len(pivot.index), endpoint=False).tolist()
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(9, 9), subplot_kw={"projection": "polar"})
    for c in countries_show:
        if c not in pivot.columns:
            continue
        values = pivot[c].tolist()
        values += values[:1]
        lw = 3.0 if c == "JPN" else 1.5
        alpha = 1.0 if c == "JPN" else 0.65
        ax.plot(angles, values, label=COUNTRY_LABEL[c],
                color=COLOR[c], linewidth=lw, alpha=alpha)
        ax.fill(angles, values, color=COLOR[c],
                alpha=0.10 if c == "JPN" else 0.05)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels([SUBSECTOR_LABELS[s] for s in pivot.index],
                        fontsize=9)
    ax.set_ylim(0, 25)
    ax.set_title("Service Subsector Composition (% of GDP, 2019)\n"
                  "Japan vs USA, Germany, Korea",
                  fontsize=11, fontweight="bold", y=1.08)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.05),
              fontsize=9, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / "services_subsector_radar.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── 図2: 日本対 G7 平均のサブセクター差 ────────────────────────────────────

def plot_japan_vs_g7avg(df: pd.DataFrame) -> Path:
    pivot = df.pivot(index="subsector", columns="country", values="va_pct")
    g7 = ["USA", "DEU", "FRA", "GBR", "CAN", "ITA"]
    g7_avg = pivot[g7].mean(axis=1)
    jp = pivot["JPN"]
    diff = jp - g7_avg

    diff = diff.reindex([
        "K_finance", "MN_professional", "J_ict",
        "I_hotels_food", "RSTU_other",
        "L_realestate", "OPQ_public_edu_health",
        "H_transport", "G_wholesale_retail",
    ])

    labels = [SUBSECTOR_LABELS[s] for s in diff.index]
    colors = ["#d62728" if v < 0 else "#2ca02c" for v in diff.values]

    fig, ax = plt.subplots(figsize=(10, 6))
    bars = ax.barh(labels, diff.values, color=colors, alpha=0.85,
                    edgecolor="black", linewidth=0.5)
    ax.axvline(0, color="black", linewidth=0.6)
    ax.set_xlabel("Japan − G7 average (% of GDP, 2019)")
    ax.set_title("Japan vs G7 Average: Service Subsector VA Shares\n"
                  "(negative = Japan smaller share than G7 avg)",
                  fontsize=11, fontweight="bold")
    ax.grid(True, axis="x", alpha=0.3)
    for bar, v in zip(bars, diff.values):
        ax.text(v + (0.1 if v >= 0 else -0.1), bar.get_y() + bar.get_height() / 2,
                f"{v:+.1f}", va="center",
                ha="left" if v >= 0 else "right",
                fontsize=9)
    fig.tight_layout()

    out = FIG_DIR / "services_subsector_japan_gap.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== A-3: Service Sub-sector Decomposition ===")

    df = load_stan()
    gaps = compute_japan_gaps(df)

    p1 = plot_radar(df)
    p2 = plot_japan_vs_g7avg(df)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = PROCESSED_DIR / "japan_stagnation_subsector.csv"
    gaps.to_csv(out_csv, index=False)

    if verbose:
        print("\n=== サービス業内訳：日本 vs G7 平均（% of GDP, 2019） ===")
        pivot = df.pivot(index="subsector", columns="country", values="va_pct")
        g7 = ["USA", "DEU", "FRA", "GBR", "CAN", "ITA"]
        g7_avg = pivot[g7].mean(axis=1)
        comparison = pd.DataFrame({
            "Japan":     pivot["JPN"],
            "G7_avg":    g7_avg,
            "diff_pp":   pivot["JPN"] - g7_avg,
            "Korea":     pivot["KOR"],
        })
        comparison.index = [SUBSECTOR_LABELS[s] for s in comparison.index]
        print(comparison.round(2).sort_values("diff_pp").to_string())

        print(f"\n  図1 (レーダー): {p1}")
        print(f"  図2 (差分棒): {p2}")

    return {"df": df, "gaps": gaps}


def main() -> None:
    parser = argparse.ArgumentParser(description="サービス業 sub-sector 分解")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
