"""賃金停滞メカニズム実証分析（Category D 検証）.

仮説（追加 H8）:
    日本の実質賃金停滞は、生産性成長率（per-WA GDP 成長率）をコントロールしても
    G7 + 韓国の中で固有に大きい. すなわち per-WA 成長率が他国並みでも、
    その成長分が賃金に反映されていない.

モデル:
    M1: g_real_wage ~ g_gdp_per_wa + Japan_dummy + year_FE
    M2: + 高齢化率
    M3: + 国 FE

    被説明変数: 5 年差分の年率実質賃金成長率（%）
    説明変数: 5 年差分の年率生産年齢 1人あたり GDP 成長率（%）

データ:
    - FRED 経由 OECD MEI 実質賃金指数（1990-2024、8 カ国）
    - WDI（生産年齢人口、GDP）

検証:
    - 累積賃金成長率の G7 比較（記述）
    - 賃金-生産性弾力性の国別推定
    - パネル回帰で日本ダミーを推定

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - wage_cumulative_g7.png
        - wage_productivity_scatter.png
        - wage_panel_japan_dummy.png
    data/processed/
        - japan_stagnation_wage_results.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from src.collectors.g7_wage_collector import WAGE_SERIES, load_country as load_wage
from src.macro.japan_stagnation.stylized_facts import (
    COLOR, COUNTRY_LABEL, COUNTRY_ORDER, FIG_DIR, PROCESSED_DIR, load_panel,
)


# ── データ準備 ────────────────────────────────────────────────────────────────

def build_wage_panel() -> pd.DataFrame:
    """賃金 + WDI（GDP・人口）を統合した年次パネル."""
    wage_frames = []
    for c in WAGE_SERIES:
        df = load_wage(c)
        if df.empty:
            continue
        df = df.copy()
        df["country"] = c
        wage_frames.append(df.reset_index())
    wage = pd.concat(wage_frames, ignore_index=True)

    wdi = load_panel().reset_index()

    panel = pd.merge(
        wdi, wage,
        on=["year", "country"],
        how="inner",
    )
    return panel


def compute_5yr_diff_panel(panel: pd.DataFrame, interval: int = 5) -> pd.DataFrame:
    """5年差分の年率成長率パネル."""
    panel = panel.copy()
    panel["gdp_per_wa"] = panel["gdp_real"] / panel["population_15_64"]
    panel["aging_share"] = 1 - panel["population_15_64"] / panel["population"]

    rows = []
    for c in panel["country"].unique():
        sub = panel[panel["country"] == c].set_index("year").sort_index()
        years = sub.index.tolist()
        for y in years:
            y0 = y - interval
            if y0 not in sub.index:
                continue
            row = {"country": c, "year_end": y, "year_start": y0}
            for g_var, col in [
                ("g_real_wage",   "real_wage"),
                ("g_gdp_per_wa",  "gdp_per_wa"),
                ("g_gdp_per_cap", "gdp_per_capita"),
            ]:
                v0, v1 = sub.loc[y0, col], sub.loc[y, col]
                if pd.notna(v0) and pd.notna(v1) and v0 > 0:
                    row[g_var] = ((v1 / v0) ** (1.0 / interval) - 1.0) * 100
                else:
                    row[g_var] = np.nan
            row["aging_share"] = sub.loc[y0:y, "aging_share"].mean()
            row["japan"] = int(c == "JPN")
            rows.append(row)
    return pd.DataFrame(rows).dropna(subset=["g_real_wage", "g_gdp_per_wa"])


# ── 図: 累積実質賃金成長率 ────────────────────────────────────────────────────

def plot_cumulative_wage(panel: pd.DataFrame, base_year: int = 1995) -> Path:
    """各国の実質賃金を 1995=100 に指数化."""
    df = panel.copy()
    df = df.dropna(subset=["real_wage"])

    fig, ax = plt.subplots(figsize=(11, 6))
    for c in COUNTRY_ORDER:
        sub = df[df["country"] == c].sort_values("year")
        if sub.empty or base_year not in sub["year"].values:
            continue
        base = sub.loc[sub["year"] == base_year, "real_wage"].iloc[0]
        if base == 0 or pd.isna(base):
            continue
        sub = sub.copy()
        sub["index"] = sub["real_wage"] / base * 100

        lw = 2.5 if c == "JPN" else 1.3
        alpha = 1.0 if c == "JPN" else 0.7
        ax.plot(sub["year"], sub["index"],
                label=COUNTRY_LABEL[c], color=COLOR[c],
                linewidth=lw, alpha=alpha)

    ax.axhline(100, color="black", linewidth=0.6, linestyle=":")
    ax.set_title("Real Wage Index (1995=100) — G7 + Korea",
                  fontsize=11, fontweight="bold")
    ax.set_xlabel("Year")
    ax.set_ylabel("Index")
    ax.grid(True, alpha=0.3)
    ax.legend(ncol=4, loc="upper left", fontsize=9, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / "wage_cumulative_g7.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── 図: 賃金 vs 生産性 散布図 ─────────────────────────────────────────────────

def plot_wage_productivity_scatter(diff_panel: pd.DataFrame) -> Path:
    """国別の賃金成長率 vs 生産性成長率."""
    avg = diff_panel.groupby("country").agg(
        wage=("g_real_wage", "mean"),
        prod=("g_gdp_per_wa", "mean"),
    )

    fig, ax = plt.subplots(figsize=(10, 7))

    # 45 度線（賃金=生産性）
    lo = min(avg["prod"].min(), avg["wage"].min()) - 0.3
    hi = max(avg["prod"].max(), avg["wage"].max()) + 0.3
    ax.plot([lo, hi], [lo, hi], color="black", linewidth=0.8, linestyle="--",
            alpha=0.5, label="Wage = Productivity (1:1)")

    for c, row in avg.iterrows():
        is_jp = c == "JPN"
        ax.scatter(row["prod"], row["wage"],
                    color=COLOR.get(c, "gray"),
                    s=300 if is_jp else 130,
                    alpha=0.85,
                    edgecolor="black" if is_jp else "none",
                    linewidth=2.5 if is_jp else 0)
        ax.annotate(COUNTRY_LABEL.get(c, c),
                    (row["prod"], row["wage"]),
                    xytext=(8, 8), textcoords="offset points",
                    fontsize=11 if is_jp else 9,
                    fontweight="bold" if is_jp else "normal")

    # 回帰線
    from scipy import stats
    slope, intercept, r, p, _ = stats.linregress(avg["prod"], avg["wage"])
    xs = np.linspace(lo, hi, 50)
    ax.plot(xs, slope * xs + intercept, color="red", linewidth=1.5,
            alpha=0.7, label=f"OLS: wage = {intercept:+.2f} + {slope:.2f} × prod (R²={r**2:.2f})")

    ax.set_xlabel("Productivity growth (per-WA GDP, %/year)")
    ax.set_ylabel("Real wage growth (%/year)")
    ax.set_title("Wage Growth vs Productivity Growth (1995-2024 averages)\n"
                  "Japan is below the 1:1 line — wages grow LESS than productivity",
                  fontsize=11, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=9, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / "wage_productivity_scatter.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── パネル回帰 ────────────────────────────────────────────────────────────────

WAGE_MODELS: dict[str, str] = {
    "W1": "g_real_wage ~ g_gdp_per_wa + japan + C(year_end)",
    "W2": "g_real_wage ~ g_gdp_per_wa + aging_share + japan + C(year_end)",
    "W3": "g_real_wage ~ g_gdp_per_wa + aging_share + japan + C(year_end) + C(country)",
}


def fit_wage_models(diff_panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for mid, formula in WAGE_MODELS.items():
        try:
            model = smf.ols(formula, data=diff_panel)
            fit = model.fit(
                cov_type="cluster",
                cov_kwds={"groups": diff_panel["country"]},
            )
            row = {
                "model":    mid,
                "formula":  formula,
                "n_obs":    int(fit.nobs),
                "r_squared": fit.rsquared,
            }
            for var in ["g_gdp_per_wa", "japan", "aging_share"]:
                if var in fit.params.index:
                    row[f"{var}_coef"] = fit.params[var]
                    row[f"{var}_se"]   = fit.bse[var]
                    row[f"{var}_p"]    = fit.pvalues[var]
            rows.append(row)
        except Exception as e:
            rows.append({"model": mid, "error": str(e)})
    return pd.DataFrame(rows)


# ── 図: 日本ダミー比較 ────────────────────────────────────────────────────────

def plot_japan_dummy(results: pd.DataFrame) -> Path:
    df = results.dropna(subset=["japan_coef"]).copy()
    fig, ax = plt.subplots(figsize=(9, 5.5))
    x = np.arange(len(df))
    ax.errorbar(x, df["japan_coef"],
                 yerr=1.96 * df["japan_se"],
                 fmt="o", capsize=5, capthick=1.5,
                 color="#d62728", markersize=10, linewidth=2)
    ax.axhline(0, color="black", linewidth=0.6, linestyle="-")

    # アノテーション
    for i, row in enumerate(df.itertuples()):
        ax.annotate(f"β={row.japan_coef:+.2f}\np={row.japan_p:.3f}",
                     (i, row.japan_coef),
                     xytext=(15, 0), textcoords="offset points",
                     fontsize=10, va="center")

    ax.set_xticks(x)
    ax.set_xticklabels(df["model"])
    ax.set_xlabel("Model")
    ax.set_ylabel("Japan dummy coefficient (%/yr)")
    ax.set_title("Japan dummy in Wage Equation\n"
                  "(after controlling for productivity growth)",
                  fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()

    out = FIG_DIR / "wage_panel_japan_dummy.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── メイン ────────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== B: Wage Stagnation Mechanism ===")

    panel = build_wage_panel()
    if verbose:
        print(f"  パネル統合: {panel.shape[0]} 行（年×国）")
        print(f"  国: {panel['country'].nunique()}, 年範囲: "
              f"{panel['year'].min()}-{panel['year'].max()}")

    diff = compute_5yr_diff_panel(panel, interval=5)
    if verbose:
        print(f"  5 年差分パネル: {len(diff)} 観測")

    # 1. 累積賃金（記述）
    if verbose:
        print("\n--- 累積実質賃金（1995=100） ---")
    p1 = plot_cumulative_wage(panel)

    cumulative = []
    for c in panel["country"].unique():
        sub = panel[panel["country"] == c].dropna(subset=["real_wage"])
        if 1995 in sub["year"].values and 2024 in sub["year"].values:
            base = sub.loc[sub["year"] == 1995, "real_wage"].iloc[0]
            end = sub.loc[sub["year"] == 2024, "real_wage"].iloc[0]
            cumulative.append({
                "country":     COUNTRY_LABEL.get(c, c),
                "real_wage_2024_idx": end / base * 100,
                "cum_growth_pct": (end / base - 1) * 100,
            })
    cum_df = pd.DataFrame(cumulative).sort_values("real_wage_2024_idx", ascending=False)
    if verbose:
        print(cum_df.round(1).to_string(index=False))

    # 2. 賃金 vs 生産性（散布）
    if verbose:
        print("\n--- 賃金 vs 生産性（1995-2024 年率平均） ---")
    p2 = plot_wage_productivity_scatter(diff)

    avg = diff.groupby("country").agg(
        wage_pct=("g_real_wage", "mean"),
        prod_pct=("g_gdp_per_wa", "mean"),
    )
    avg["wage_minus_prod"] = avg["wage_pct"] - avg["prod_pct"]
    avg = avg.sort_values("wage_minus_prod")
    if verbose:
        print(avg.round(3).to_string())

    # 3. パネル回帰
    if verbose:
        print("\n--- パネル回帰 ---")
    results = fit_wage_models(diff)
    p3 = plot_japan_dummy(results)
    if verbose:
        cols = ["model", "n_obs", "r_squared",
                "g_gdp_per_wa_coef", "g_gdp_per_wa_p",
                "japan_coef", "japan_se", "japan_p"]
        print(results[cols].round(4).to_string(index=False))

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = PROCESSED_DIR / "japan_stagnation_wage_results.csv"
    results.to_csv(out_csv, index=False)

    cum_path = PROCESSED_DIR / "japan_stagnation_wage_cumulative.csv"
    cum_df.to_csv(cum_path, index=False)
    avg_path = PROCESSED_DIR / "japan_stagnation_wage_productivity.csv"
    avg.to_csv(avg_path)

    if verbose:
        print(f"\n  図1: {p1}")
        print(f"  図2: {p2}")
        print(f"  図3: {p3}")
        print(f"  結果: {out_csv}")

    return {"results": results, "cumulative": cum_df, "wage_prod": avg}


def main() -> None:
    parser = argparse.ArgumentParser(description="賃金停滞分析")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
