"""ロバストネス R-1：サブサンプル安定性検証.

主要パネル回帰（H1, H8）を以下のサブサンプルで再推定:
    - Pre-Lehman      : 1995-2007
    - Post-Lehman     : 2009-2019
    - Pre-Abenomics   : 1995-2012
    - Post-Abenomics  : 2014-2024
    - Pre-COVID       : 1995-2019
    - Post-COVID      : 2021-2024

各サブサンプルで Japan dummy が頑健に有意か確認.

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - robustness_subsample_h1.png
        - robustness_subsample_h8.png
    data/processed/
        - japan_stagnation_subsample_results.csv
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


SUBSAMPLES = [
    ("Full (1995-2024)",     1995, 2024),
    ("Pre-Lehman (1995-2007)",  1995, 2007),
    ("Post-Lehman (2009-2019)", 2009, 2019),
    ("Pre-Abenomics (1995-2012)", 1995, 2012),
    ("Post-Abenomics (2014-2024)", 2014, 2024),
    ("Pre-COVID (1995-2019)",  1995, 2019),
    ("Post-COVID (2021-2024)", 2021, 2024),
]


# ── H1 サブサンプル安定性 ────────────────────────────────────────────────────

def run_h1_subsample() -> pd.DataFrame:
    panel_full = load_panel()

    rows = []
    for label, start, end in SUBSAMPLES:
        # 5 年差分が十分取れない期間はスキップ
        if end - start < 7:
            rows.append({"subsample": label, "n_obs": 0, "skip": True})
            continue
        try:
            diff_panel = build_long_panel(panel_full, interval=5, start=start, end=end)
        except KeyError:
            rows.append({"subsample": label, "n_obs": 0, "skip": True})
            continue
        if diff_panel.empty or len(diff_panel) < 30:
            rows.append({
                "subsample": label, "n_obs": len(diff_panel), "skip": True,
            })
            continue

        # ex-Korea サンプル（最も頑健）
        sub = diff_panel[diff_panel["country"] != "KOR"]
        try:
            # Model 1B（Per-WA + year FE のみ）
            fit_b = smf.ols(
                "g_gdp_per_wa ~ japan + C(year_end)", data=sub,
            ).fit(cov_type="cluster", cov_kwds={"groups": sub["country"]})
            # Model 1C（+ controls）
            fit_c = smf.ols(
                "g_gdp_per_wa ~ japan + aging_share + wa_pop_growth + C(year_end)",
                data=sub,
            ).fit(cov_type="cluster", cov_kwds={"groups": sub["country"]})

            rows.append({
                "subsample":      label,
                "n_obs":          int(fit_b.nobs),
                "M1B_coef":       fit_b.params.get("japan", np.nan),
                "M1B_se":         fit_b.bse.get("japan", np.nan),
                "M1B_p":          fit_b.pvalues.get("japan", np.nan),
                "M1C_coef":       fit_c.params.get("japan", np.nan),
                "M1C_se":         fit_c.bse.get("japan", np.nan),
                "M1C_p":          fit_c.pvalues.get("japan", np.nan),
            })
        except Exception as e:
            rows.append({"subsample": label, "error": str(e)})

    return pd.DataFrame(rows)


# ── H8 サブサンプル安定性 ────────────────────────────────────────────────────

def run_h8_subsample() -> pd.DataFrame:
    wage_panel = build_wage_panel()

    rows = []
    for label, start, end in SUBSAMPLES:
        if end - start < 7:
            rows.append({"subsample": label, "n_obs": 0, "skip": True})
            continue
        sub_panel = wage_panel[(wage_panel["year"] >= start) & (wage_panel["year"] <= end)]
        try:
            diff = compute_5yr_diff_panel(sub_panel, interval=5)
        except (KeyError, ValueError):
            rows.append({"subsample": label, "n_obs": 0, "skip": True})
            continue
        if diff.empty or len(diff) < 30:
            rows.append({"subsample": label, "n_obs": len(diff), "skip": True})
            continue
        try:
            # W1: 賃金 ~ 生産性 + Japan + 年 FE
            fit_w1 = smf.ols(
                "g_real_wage ~ g_gdp_per_wa + japan + C(year_end)", data=diff,
            ).fit(cov_type="cluster", cov_kwds={"groups": diff["country"]})
            # W3: + 国 FE
            fit_w3 = smf.ols(
                "g_real_wage ~ g_gdp_per_wa + aging_share + japan + C(year_end) + C(country)",
                data=diff,
            ).fit(cov_type="cluster", cov_kwds={"groups": diff["country"]})

            rows.append({
                "subsample":   label,
                "n_obs":       int(fit_w1.nobs),
                "W1_coef":     fit_w1.params.get("japan", np.nan),
                "W1_se":       fit_w1.bse.get("japan", np.nan),
                "W1_p":        fit_w1.pvalues.get("japan", np.nan),
                "W3_coef":     fit_w3.params.get("japan", np.nan),
                "W3_se":       fit_w3.bse.get("japan", np.nan),
                "W3_p":        fit_w3.pvalues.get("japan", np.nan),
            })
        except Exception as e:
            rows.append({"subsample": label, "error": str(e)})

    return pd.DataFrame(rows)


# ── プロット ─────────────────────────────────────────────────────────────────

def plot_subsample(df: pd.DataFrame, coef_col: str, se_col: str,
                    title: str, suffix: str) -> Path:
    df = df.dropna(subset=[coef_col]).copy()
    fig, ax = plt.subplots(figsize=(11, 5.5))
    x = np.arange(len(df))
    ax.errorbar(
        x, df[coef_col],
        yerr=1.96 * df[se_col],
        fmt="o", capsize=5, capthick=1.5,
        color="#d62728", markersize=10, linewidth=1.8,
    )
    ax.axhline(0, color="black", linewidth=0.6, linestyle="-")
    ax.set_xticks(x)
    ax.set_xticklabels(df["subsample"], rotation=20, ha="right", fontsize=9)
    ax.set_ylabel("Japan dummy coefficient (95% CI)")
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)

    for i, (coef, p) in enumerate(zip(df[coef_col], df[coef_col.replace("coef", "p")])):
        sig = ""
        if p < 0.01:
            sig = "***"
        elif p < 0.05:
            sig = "**"
        elif p < 0.10:
            sig = "*"
        ax.text(i, coef + (0.15 if coef > 0 else -0.15),
                f"{coef:+.2f}{sig}", ha="center", fontsize=9)

    fig.tight_layout()
    out = FIG_DIR / f"robustness_subsample_{suffix}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── メイン ────────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== R-1: Subsample Stability ===")

    h1 = run_h1_subsample()
    h8 = run_h8_subsample()

    if verbose:
        print("\n=== H1（per-WA, ex-Korea）サブサンプル ===")
        cols = ["subsample", "n_obs", "M1B_coef", "M1B_p", "M1C_coef", "M1C_p"]
        print(h1[cols].round(3).to_string(index=False))

        print("\n=== H8（賃金停滞）サブサンプル ===")
        cols = ["subsample", "n_obs", "W1_coef", "W1_p", "W3_coef", "W3_p"]
        print(h8[cols].round(3).to_string(index=False))

    p1 = plot_subsample(h1, "M1B_coef", "M1B_se",
                          "H1: Japan dummy across subsamples (Model 1B, ex-Korea)",
                          "h1")
    p2 = plot_subsample(h8, "W1_coef", "W1_se",
                          "H8: Japan dummy in wage equation across subsamples",
                          "h8")

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    h1.to_csv(PROCESSED_DIR / "japan_stagnation_subsample_h1.csv", index=False)
    h8.to_csv(PROCESSED_DIR / "japan_stagnation_subsample_h8.csv", index=False)

    if verbose:
        print(f"\n  図1 (H1): {p1}")
        print(f"  図2 (H8): {p2}")

    return {"h1": h1, "h8": h8}


def main() -> None:
    parser = argparse.ArgumentParser(description="サブサンプル安定性")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
