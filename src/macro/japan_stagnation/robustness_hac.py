"""ロバストネス R-3：HAC（Newey-West）標準誤差での再推定.

時系列の自己相関と heteroskedasticity に対応する HAC SE で
主要パネル回帰（H1、H8）を再推定し、結果の頑健性を確認.

通常 SE: 観測独立を仮定
クラスタ SE: グループ内相関のみ吸収
HAC SE: グループ内 + 時系列自己相関 + heteroskedasticity を吸収

Lag truncation: Newey-West (1987) 推奨 m = floor(4 × (n/100)^(2/9))

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - robustness_hac_comparison.png
    data/processed/
        - japan_stagnation_hac_results.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from src.macro.japan_stagnation.panel_regression import build_long_panel
from src.macro.japan_stagnation.wage_stagnation import (
    build_wage_panel, compute_5yr_diff_panel,
)
from src.macro.japan_stagnation.stylized_facts import (
    FIG_DIR, PROCESSED_DIR, load_panel,
)


def newey_west_lag(n: int) -> int:
    """Newey-West 推奨ラグ."""
    return int(np.floor(4 * (n / 100) ** (2 / 9)))


def fit_with_hac(formula: str, data: pd.DataFrame) -> dict:
    """HAC SE で OLS を推定."""
    n = len(data)
    lag = newey_west_lag(n)
    fit = smf.ols(formula, data=data).fit(
        cov_type="HAC", cov_kwds={"maxlags": lag},
    )
    return {
        "n_obs":      int(fit.nobs),
        "lag":        lag,
        "japan_coef": fit.params.get("japan", np.nan),
        "japan_se":   fit.bse.get("japan", np.nan),
        "japan_p":    fit.pvalues.get("japan", np.nan),
        "r_squared":  fit.rsquared,
    }


def fit_with_cluster(formula: str, data: pd.DataFrame, group_col: str) -> dict:
    fit = smf.ols(formula, data=data).fit(
        cov_type="cluster", cov_kwds={"groups": data[group_col]},
    )
    return {
        "n_obs":      int(fit.nobs),
        "japan_coef": fit.params.get("japan", np.nan),
        "japan_se":   fit.bse.get("japan", np.nan),
        "japan_p":    fit.pvalues.get("japan", np.nan),
        "r_squared":  fit.rsquared,
    }


def fit_with_robust(formula: str, data: pd.DataFrame) -> dict:
    fit = smf.ols(formula, data=data).fit(cov_type="HC3")
    return {
        "n_obs":      int(fit.nobs),
        "japan_coef": fit.params.get("japan", np.nan),
        "japan_se":   fit.bse.get("japan", np.nan),
        "japan_p":    fit.pvalues.get("japan", np.nan),
        "r_squared":  fit.rsquared,
    }


def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== R-3: HAC Standard Errors ===")

    panel = load_panel()
    diff = build_long_panel(panel, interval=5, start=1995, end=2024)
    diff_ex_kor = diff[diff["country"] != "KOR"]

    wage_panel = build_wage_panel()
    wage_diff = compute_5yr_diff_panel(wage_panel, interval=5)

    results = []

    # H1 (Model 1B, ex-Korea)
    formula_h1b = "g_gdp_per_wa ~ japan + C(year_end)"
    formula_h1c = "g_gdp_per_wa ~ japan + aging_share + wa_pop_growth + C(year_end)"

    for label, formula, data in [
        ("H1 1B ex-Korea", formula_h1b, diff_ex_kor),
        ("H1 1C ex-Korea", formula_h1c, diff_ex_kor),
        ("H1 1B Full",     formula_h1b, diff),
        ("H1 1C Full",     formula_h1c, diff),
    ]:
        for se_type, fitter in [
            ("Cluster", lambda f, d: fit_with_cluster(f, d, "country")),
            ("HAC", fit_with_hac),
            ("HC3", fit_with_robust),
        ]:
            r = fitter(formula, data)
            r["regression"] = label
            r["SE_type"] = se_type
            results.append(r)

    # H8 (Wage panel)
    formula_w1 = "g_real_wage ~ g_gdp_per_wa + japan + C(year_end)"
    formula_w3 = "g_real_wage ~ g_gdp_per_wa + aging_share + japan + C(year_end) + C(country)"

    for label, formula, data in [
        ("H8 W1", formula_w1, wage_diff),
        ("H8 W3", formula_w3, wage_diff),
    ]:
        for se_type, fitter in [
            ("Cluster", lambda f, d: fit_with_cluster(f, d, "country")),
            ("HAC", fit_with_hac),
            ("HC3", fit_with_robust),
        ]:
            r = fitter(formula, data)
            r["regression"] = label
            r["SE_type"] = se_type
            results.append(r)

    df = pd.DataFrame(results)

    if verbose:
        print("\n=== Japan ダミー：3 種類の SE 比較 ===")
        cols = ["regression", "SE_type", "japan_coef", "japan_se", "japan_p"]
        print(df[cols].round(4).to_string(index=False))

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = PROCESSED_DIR / "japan_stagnation_hac_results.csv"
    df.to_csv(out_csv, index=False)

    # プロット
    fig, ax = plt.subplots(figsize=(11, 6))
    df_pivot = df.pivot(index="regression", columns="SE_type", values="japan_se")
    df_pivot = df_pivot.sort_values("Cluster")
    x = np.arange(len(df_pivot))
    width = 0.27
    for i, col in enumerate(["Cluster", "HAC", "HC3"]):
        if col in df_pivot.columns:
            ax.bar(x + (i - 1) * width, df_pivot[col].values, width,
                    label=col, alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(df_pivot.index, rotation=15, ha="right", fontsize=9)
    ax.set_ylabel("Standard error of Japan dummy")
    ax.set_title("Robustness R-3: SE comparison across estimators",
                  fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()

    p1 = FIG_DIR / "robustness_hac_comparison.png"
    fig.savefig(p1, dpi=150, bbox_inches="tight")
    plt.close(fig)

    if verbose:
        print(f"\n  サマリー: {out_csv}")
        print(f"  図: {p1}")

    return {"results": df}


def main() -> None:
    parser = argparse.ArgumentParser(description="HAC SE ロバストネス")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
