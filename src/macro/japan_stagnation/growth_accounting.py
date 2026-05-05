"""成長会計分解：日本の総 GDP 成長率を人口・労働参加・生産性に分解する.

恒等式:
    Y/N_total = (Y/N_wa) × (N_wa/N_total)

両辺対数を取り差分すると:
    g(Y/N_total) = g(Y/N_wa) + g(N_wa/N_total)

さらに総 GDP 成長率は:
    g(Y) = g(N_total) + g(Y/N_wa) + g(N_wa/N_total)
         = g(N_total) + g(Y/N_total)
         = g(N_total) + [g(Y/N_wa) + g(N_wa/N_total)]

これを「人口要因」「労働参加率変化要因」「労働者あたり生産性要因」に分解する.

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - growth_decomposition_bars.png
    data/processed/
        - japan_stagnation_growth_decomposition.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.collectors.wdi_collector import load_country
from src.macro.japan_stagnation.stylized_facts import (
    COLOR, COUNTRY_LABEL, COUNTRY_ORDER, FIG_DIR, PROCESSED_DIR, load_panel,
)


def annualized_growth(series: pd.Series, start: int, end: int) -> float:
    """期間 [start, end] の年率成長率（%）."""
    s = series.dropna()
    if start not in s.index or end not in s.index:
        return np.nan
    n = end - start
    if n <= 0:
        return np.nan
    ratio = s.loc[end] / s.loc[start]
    if ratio <= 0:
        return np.nan
    return (ratio ** (1.0 / n) - 1.0) * 100


def decompose_country(
    panel: pd.DataFrame, country: str, start: int, end: int,
) -> dict:
    """1 国の成長会計分解.

    Returns:
        dict with keys:
            g_gdp_total:    総 GDP 成長率
            g_pop_total:    総人口成長率
            g_pop_wa:       生産年齢人口成長率
            g_wa_share:     生産年齢人口比率の変化（参加要因）
            g_gdp_per_wa:   生産年齢 1人あたり GDP 成長率
            g_gdp_per_cap:  1人あたり GDP 成長率
            residual:       恒等式の残差（数値誤差）
    """
    df = panel.xs(country, level="country").copy()
    df["pop_wa_share"] = df["population_15_64"] / df["population"]
    df["gdp_per_wa"] = df["gdp_real"] / df["population_15_64"]

    g_gdp_total   = annualized_growth(df["gdp_real"], start, end)
    g_pop_total   = annualized_growth(df["population"], start, end)
    g_pop_wa      = annualized_growth(df["population_15_64"], start, end)
    g_wa_share    = annualized_growth(df["pop_wa_share"], start, end)
    g_gdp_per_wa  = annualized_growth(df["gdp_per_wa"], start, end)
    g_gdp_per_cap = annualized_growth(df["gdp_per_capita"], start, end)

    # 恒等式: g(Y) ≈ g(N_total) + g(N_wa/N_total) + g(Y/N_wa)
    identity_sum = g_pop_total + g_wa_share + g_gdp_per_wa
    residual = g_gdp_total - identity_sum

    return {
        "country":      country,
        "start":        start,
        "end":          end,
        "g_gdp_total":  g_gdp_total,
        "g_pop_total":  g_pop_total,
        "g_pop_wa":     g_pop_wa,
        "g_wa_share":   g_wa_share,
        "g_gdp_per_wa": g_gdp_per_wa,
        "g_gdp_per_cap": g_gdp_per_cap,
        "identity_sum": identity_sum,
        "residual":     residual,
    }


def decompose_all(
    panel: pd.DataFrame, start: int = 1995, end: int = 2024,
) -> pd.DataFrame:
    rows = []
    for c in COUNTRY_ORDER:
        rows.append(decompose_country(panel, c, start, end))
    return pd.DataFrame(rows)


# ── 図: 成長会計分解の積み上げ棒グラフ ────────────────────────────────────────

def plot_decomposition_bars(decomp: pd.DataFrame, start: int, end: int) -> Path:
    fig, ax = plt.subplots(figsize=(11, 6.5))

    countries = decomp["country"].tolist()
    labels = [COUNTRY_LABEL[c] for c in countries]
    x = np.arange(len(countries))
    width = 0.6

    pop = decomp["g_pop_total"].values
    wa_share = decomp["g_wa_share"].values
    productivity = decomp["g_gdp_per_wa"].values

    # 積み上げ棒（負値も対応）
    bottom_pos = np.zeros(len(countries))
    bottom_neg = np.zeros(len(countries))

    def stack(values, label, color):
        nonlocal bottom_pos, bottom_neg
        pos = np.where(values >= 0, values, 0)
        neg = np.where(values < 0, values, 0)
        ax.bar(x, pos, width, bottom=bottom_pos, label=label, color=color, edgecolor="white", linewidth=0.5)
        ax.bar(x, neg, width, bottom=bottom_neg, color=color, edgecolor="white", linewidth=0.5)
        bottom_pos = bottom_pos + pos
        bottom_neg = bottom_neg + neg

    stack(pop, "Population growth", "#9467bd")
    stack(wa_share, "Working-age share change", "#ff7f0e")
    stack(productivity, "GDP per working-age (productivity)", "#2ca02c")

    # 総 GDP 成長率の点（参考）
    ax.scatter(x, decomp["g_gdp_total"], color="black", s=70, zorder=5,
               label="Total GDP growth (sum)")

    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=0)
    ax.set_ylabel("Annualized growth rate (%)")
    ax.set_title(f"Growth Accounting Decomposition: {start}–{end}",
                 fontsize=12, fontweight="bold")
    ax.legend(loc="upper left", fontsize=9, framealpha=0.85)
    ax.grid(True, axis="y", alpha=0.3)

    # 日本に強調枠
    jp_idx = countries.index("JPN") if "JPN" in countries else None
    if jp_idx is not None:
        ax.axvspan(jp_idx - 0.4, jp_idx + 0.4, alpha=0.08, color="red")

    fig.tight_layout()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / "growth_decomposition_bars.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── 図: 日本の人口寄与の時系列（10年窓ローリング） ───────────────────────────

def plot_japan_rolling(panel: pd.DataFrame, window: int = 10) -> Path:
    df = panel.xs("JPN", level="country").copy()
    df["gdp_per_wa"] = df["gdp_real"] / df["population_15_64"]
    df["pop_wa_share"] = df["population_15_64"] / df["population"]

    years = sorted(df.index.unique())
    rows = []
    for end in years:
        start = end - window
        if start < years[0]:
            continue
        rec = {
            "end_year": end,
            "g_gdp": annualized_growth(df["gdp_real"], start, end),
            "g_pop": annualized_growth(df["population"], start, end),
            "g_wa_share": annualized_growth(df["pop_wa_share"], start, end),
            "g_per_wa": annualized_growth(df["gdp_per_wa"], start, end),
        }
        rows.append(rec)
    rolling = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.plot(rolling["end_year"], rolling["g_gdp"], label="Total GDP",
            color="black", linewidth=2.0)
    ax.plot(rolling["end_year"], rolling["g_per_wa"], label="GDP per working-age",
            color="#2ca02c", linewidth=2.0)
    ax.plot(rolling["end_year"], rolling["g_pop"], label="Population",
            color="#9467bd", linewidth=1.5, linestyle="--")
    ax.plot(rolling["end_year"], rolling["g_wa_share"], label="Working-age share",
            color="#ff7f0e", linewidth=1.5, linestyle="--")

    ax.axhline(0, color="black", linewidth=0.6)
    ax.set_title(f"Japan: Growth Accounting Components ({window}-year rolling annualized)",
                 fontsize=12, fontweight="bold")
    ax.set_xlabel("End of rolling window (year)")
    ax.set_ylabel("Annualized growth rate (%)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper right", fontsize=9, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / "japan_growth_rolling.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── 「日本の停滞のうち何%が人口要因か」算出 ──────────────────────────────────

def compute_demographic_share(decomp: pd.DataFrame, reference: str = "USA") -> pd.DataFrame:
    """日本と参照国の総 GDP 成長率ギャップを、各要素の差分で分解.

    ギャップ = (g_pop_jp - g_pop_ref) + (g_wa_share_jp - g_wa_share_ref) + (g_per_wa_jp - g_per_wa_ref)
    """
    jp = decomp[decomp["country"] == "JPN"].iloc[0]
    rows = []
    for _, ref in decomp.iterrows():
        if ref["country"] == "JPN":
            continue
        gap_total = jp["g_gdp_total"] - ref["g_gdp_total"]
        gap_pop = jp["g_pop_total"] - ref["g_pop_total"]
        gap_wa_share = jp["g_wa_share"] - ref["g_wa_share"]
        gap_prod = jp["g_gdp_per_wa"] - ref["g_gdp_per_wa"]
        rows.append({
            "vs_country": COUNTRY_LABEL[ref["country"]],
            "gap_total":     gap_total,
            "gap_population": gap_pop,
            "gap_wa_share":   gap_wa_share,
            "gap_productivity": gap_prod,
            "demographic_share_pct": (gap_pop + gap_wa_share) / gap_total * 100 if gap_total != 0 else np.nan,
        })
    return pd.DataFrame(rows)


# ── メイン ────────────────────────────────────────────────────────────────────

def run(start: int = 1995, end: int = 2024, verbose: bool = True) -> dict:
    if verbose:
        print("=== Phase 0: Growth Accounting Decomposition ===")
        print(f"  期間: {start}-{end}")

    panel = load_panel()
    decomp = decompose_all(panel, start, end)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    decomp_path = PROCESSED_DIR / "japan_stagnation_growth_decomposition.csv"
    decomp.to_csv(decomp_path, index=False)

    p1 = plot_decomposition_bars(decomp, start, end)
    p2 = plot_japan_rolling(panel)

    demo_share = compute_demographic_share(decomp)
    demo_path = PROCESSED_DIR / "japan_stagnation_demographic_share.csv"
    demo_share.to_csv(demo_path, index=False)

    if verbose:
        print("\n=== 成長会計分解（年率%、1995-2024） ===")
        cols_disp = ["country", "g_gdp_total", "g_pop_total", "g_wa_share",
                     "g_gdp_per_wa", "g_gdp_per_cap"]
        print(decomp[cols_disp].round(3).to_string(index=False))

        print("\n=== 「日本の停滞は何%が人口要因か」 ===")
        print(f"日本 vs 各国の総 GDP 成長率ギャップ（年率%、1995-2024）の分解:")
        print(demo_share.round(3).to_string(index=False))

        print(f"\n  図: {p1}")
        print(f"  図: {p2}")
        print(f"  分解結果: {decomp_path}")
        print(f"  人口寄与表: {demo_path}")

    return {"decomp": decomp, "demographic_share": demo_share}


def main() -> None:
    parser = argparse.ArgumentParser(description="日本停滞 成長会計分解")
    parser.add_argument("--start", type=int, default=1995)
    parser.add_argument("--end", type=int, default=2024)
    args = parser.parse_args()
    run(args.start, args.end)


if __name__ == "__main__":
    main()
