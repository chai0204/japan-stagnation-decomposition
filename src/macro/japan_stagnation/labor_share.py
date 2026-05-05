"""労働分配率（labor share）の G7 + 韓国比較.

PWT 10.01 の labsh 系列を用い、1995-2019 年の労働所得対 GDP 比を比較.

仮説 H10:
    日本の労働分配率は G7 諸国の中で減少傾向が顕著であり、
    H8（賃金 - 生産性分配の機能不全）の独立証拠となる.

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - labor_share_g7.png
    data/processed/
        - japan_stagnation_labor_share.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.collectors.pwt_collector import load as load_pwt
from src.macro.japan_stagnation.stylized_facts import (
    COLOR, COUNTRY_LABEL, COUNTRY_ORDER, FIG_DIR, PROCESSED_DIR,
)


def plot_labor_share(df: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(11, 6))
    for c in COUNTRY_ORDER:
        sub = df[df["country"] == c].sort_values("year")
        if sub.empty:
            continue
        lw = 2.5 if c == "JPN" else 1.3
        alpha = 1.0 if c == "JPN" else 0.7
        ax.plot(sub["year"], sub["labor_share"],
                label=COUNTRY_LABEL[c], color=COLOR[c],
                linewidth=lw, alpha=alpha,
                marker="o", markersize=4)
    ax.set_title("Labor Share (PWT 10.01) — G7 + Korea, 1995-2019",
                  fontsize=11, fontweight="bold")
    ax.set_xlabel("Year")
    ax.set_ylabel("Labor compensation / GDP")
    ax.set_ylim(0.45, 0.75)
    ax.grid(True, alpha=0.3)
    ax.legend(ncol=4, loc="best", fontsize=9, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / "labor_share_g7.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def compute_decline(df: pd.DataFrame) -> pd.DataFrame:
    """各国の 1995→2019 ラボーシェア変化."""
    rows = []
    for c in df["country"].unique():
        sub = df[df["country"] == c].sort_values("year")
        if 1995 not in sub["year"].values or 2019 not in sub["year"].values:
            continue
        v95 = sub.loc[sub["year"] == 1995, "labor_share"].iloc[0]
        v19 = sub.loc[sub["year"] == 2019, "labor_share"].iloc[0]
        rows.append({
            "country":     COUNTRY_LABEL[c],
            "1995":        v95,
            "2019":        v19,
            "change_pp":   (v19 - v95) * 100,
            "min_year":    int(sub.loc[sub["labor_share"].idxmin(), "year"]),
            "min_value":   sub["labor_share"].min(),
        })
    return pd.DataFrame(rows).sort_values("change_pp")


def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== B-3: Labor Share Analysis (PWT 10.01) ===")

    df = load_pwt()
    if verbose:
        print(f"  パネル: {len(df)} 行 ({df['country'].nunique()} 国)")

    p1 = plot_labor_share(df)
    decline = compute_decline(df)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = PROCESSED_DIR / "japan_stagnation_labor_share.csv"
    decline.to_csv(out_csv, index=False)

    if verbose:
        print("\n=== 労働分配率の変化（1995→2019、ポイント） ===")
        print(decline.round(3).to_string(index=False))
        print(f"\n  図: {p1}")

    return {"df": df, "decline": decline}


def main() -> None:
    parser = argparse.ArgumentParser(description="労働分配率分析")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
