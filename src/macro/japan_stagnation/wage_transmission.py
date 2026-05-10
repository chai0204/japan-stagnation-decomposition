"""賃金 - 生産性 transmission failure の interaction model 検証.

レビュー round 3 の指摘に対応：
    > 査読者は「Japan dummy = -2.15」では満足しない
    > "Is the productivity-to-wage transmission slope WEAKER in Japan?"
    > = slope failure として identify すべき

本モジュールは、H8 を「level wedge」だけでなく「**slope failure**」として
直接 identify する interaction model を実装する。

# Models

T1 (Baseline, level only — W1 と同じ):
    g_wage = α + β1·g_prod + β2·Japan + year_FE + ε
    - β2 = -2.15: Japan の wage level が低い（intercept shift）

T2 (Japan slope test):
    g_wage = α + β1·g_prod + β2·Japan + β3·(g_prod × Japan) + year_FE + ε
    - β3 < 0 → Japan の transmission slope が弱い（slope failure）
    - β3 = 0 → Japan は同じ slope、ただ level だけ shift
    - β3 が有意ならば、H8 は "slope failure" として強く identify

T3 (Korea slope test):
    g_wage = α + β1·g_prod + β2·Korea + β3·(g_prod × Korea) + year_FE + ε
    - β3 > 0 → Korea の transmission slope が強い

T4 (Both Japan and Korea):
    g_wage = α + β1·g_prod + β2·Japan + β3·(g_prod × Japan)
                + β4·Korea + β5·(g_prod × Korea) + year_FE + ε

# 解釈

- T1 で β_Japan = -2.15: "Japan は productivity を所与として 2.15pp/yr 低い賃金"
- T2 で β3_Japan < 0 が有意: "Japan は productivity 1pp 増 → 賃金 X pp 増（X < global slope）"
  → これは H8 の structural interpretation を強化（単なる level shift ではない）

# Output

- figures/wage_transmission_interaction.png: scatter + 国別 fit lines
- data/processed/japan_stagnation_wage_transmission.csv: 4 modelの coefficients
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from src.macro.japan_stagnation.stylized_facts import (
    COLOR, COUNTRY_LABEL, FIG_DIR, PROCESSED_DIR,
)
from src.macro.japan_stagnation.wage_stagnation import (
    build_wage_panel, compute_5yr_diff_panel,
)


# ── interaction 変数の付与 ───────────────────────────────────────────────────

def add_interaction_vars(panel: pd.DataFrame) -> pd.DataFrame:
    df = panel.copy()
    df["japan"] = (df["country"] == "JPN").astype(int)
    df["korea"] = (df["country"] == "KOR").astype(int)
    df["prod_x_japan"] = df["g_gdp_per_wa"] * df["japan"]
    df["prod_x_korea"] = df["g_gdp_per_wa"] * df["korea"]
    return df


# ── 推定 ──────────────────────────────────────────────────────────────────────

def fit_one(formula: str, df: pd.DataFrame) -> dict:
    fit = smf.ols(formula, data=df).fit(
        cov_type="cluster", cov_kwds={"groups": df["country"]}
    )
    return {
        "formula":  formula,
        "n":        int(fit.nobs),
        "r2":       float(fit.rsquared),
        "params":   fit.params,
        "bse":      fit.bse,
        "pvalues":  fit.pvalues,
        "ci_low":   fit.conf_int()[0],
        "ci_high":  fit.conf_int()[1],
        "fit":      fit,
    }


def estimate_models(panel: pd.DataFrame) -> dict:
    df = add_interaction_vars(panel).dropna(
        subset=["g_real_wage", "g_gdp_per_wa"]
    ).copy()

    results = {}

    # T1: Baseline (level only)
    results["T1"] = fit_one(
        "g_real_wage ~ g_gdp_per_wa + japan + C(year_end)", df
    )

    # T2: Japan slope test
    results["T2"] = fit_one(
        "g_real_wage ~ g_gdp_per_wa + japan + prod_x_japan + C(year_end)", df
    )

    # T3: Korea slope test (no Japan dummy)
    results["T3"] = fit_one(
        "g_real_wage ~ g_gdp_per_wa + korea + prod_x_korea + C(year_end)", df
    )

    # T4: Both
    results["T4"] = fit_one(
        "g_real_wage ~ g_gdp_per_wa + japan + prod_x_japan "
        "+ korea + prod_x_korea + C(year_end)", df
    )

    return results


# ── 表 ─────────────────────────────────────────────────────────────────────────

def summarize(results: dict) -> pd.DataFrame:
    rows = []
    for name, r in results.items():
        for var in ["g_gdp_per_wa", "japan", "prod_x_japan",
                     "korea", "prod_x_korea"]:
            if var not in r["params"]:
                continue
            rows.append({
                "model":  name,
                "var":    var,
                "n":      r["n"],
                "r2":     r["r2"],
                "beta":   float(r["params"][var]),
                "se":     float(r["bse"][var]),
                "p":      float(r["pvalues"][var]),
                "ci_low": float(r["ci_low"][var]),
                "ci_high":float(r["ci_high"][var]),
            })
    return pd.DataFrame(rows)


# ── 図：transmission slope の比較 ─────────────────────────────────────────────

def plot_country_slopes(panel: pd.DataFrame) -> Path:
    """国別 wage-productivity scatter + fit line (個別 OLS)."""
    df = panel.dropna(subset=["g_real_wage", "g_gdp_per_wa"]).copy()

    fig, ax = plt.subplots(figsize=(11, 7))

    countries = sorted(df["country"].unique())
    for c in countries:
        sub = df[df["country"] == c]
        if len(sub) < 4:
            continue
        x, y = sub["g_gdp_per_wa"], sub["g_real_wage"]
        # 個別 OLS slope
        try:
            slope, intercept = np.polyfit(x, y, 1)
        except Exception:
            continue
        x_line = np.array([x.min() - 0.5, x.max() + 0.5])
        y_line = intercept + slope * x_line

        is_japan = c == "JPN"
        is_korea = c == "KOR"
        color = COLOR.get(c, "gray")
        lw = 2.8 if (is_japan or is_korea) else 1.0
        alpha = 1.0 if (is_japan or is_korea) else 0.5

        ax.scatter(x, y, color=color, alpha=alpha * 0.8, s=30,
                   label=f"{COUNTRY_LABEL[c]} (slope={slope:.2f})")
        ax.plot(x_line, y_line, color=color, linewidth=lw, alpha=alpha)

    # 45 度線
    lo, hi = -3, 8
    ax.plot([lo, hi], [lo, hi], color="black", linewidth=0.5,
            linestyle="--", alpha=0.4, label="Wage = Productivity")
    ax.axhline(0, color="black", linewidth=0.4, alpha=0.4)
    ax.axvline(0, color="black", linewidth=0.4, alpha=0.4)

    ax.set_xlabel("Per-WA GDP growth (%/yr, 5yr-diff)")
    ax.set_ylabel("Real wage growth (%/yr, 5yr-diff)")
    ax.set_title(
        "Wage-productivity transmission slopes — country-by-country OLS\n"
        "Steeper slope = stronger productivity-to-wage transmission",
        fontsize=11, fontweight="bold",
    )
    ax.legend(ncol=2, loc="lower right", fontsize=8, framealpha=0.85)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()

    out = FIG_DIR / "wage_transmission_slopes.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_interaction_coef(results: dict) -> Path:
    """T2/T3/T4 の interaction 係数を forest plot で可視化."""
    rows = []
    for name in ["T2", "T3", "T4"]:
        r = results[name]
        for var in ["prod_x_japan", "prod_x_korea"]:
            if var in r["params"]:
                rows.append({
                    "model": name,
                    "var": var,
                    "beta": float(r["params"][var]),
                    "lo":   float(r["ci_low"][var]),
                    "hi":   float(r["ci_high"][var]),
                    "p":    float(r["pvalues"][var]),
                })
    df = pd.DataFrame(rows)

    fig, ax = plt.subplots(figsize=(10, 5))
    ypos = np.arange(len(df))
    colors = ["#d62728" if "japan" in v else "#2ca02c" for v in df["var"]]
    ax.errorbar(
        df["beta"], ypos,
        xerr=[df["beta"] - df["lo"], df["hi"] - df["beta"]],
        fmt="o", capsize=4, markersize=8,
        ecolor="gray", color="black",
    )
    for i, (beta, color) in enumerate(zip(df["beta"], colors)):
        ax.scatter(beta, i, color=color, s=80, zorder=3)
    ax.axvline(0, color="black", linewidth=0.6, linestyle="--")
    ax.set_yticks(ypos)
    ax.set_yticklabels([
        f"{r['model']}: {r['var']} (β={r['beta']:+.3f}, p={r['p']:.3f})"
        for _, r in df.iterrows()
    ])
    ax.set_xlabel("Interaction coefficient (slope shifter)")
    ax.set_title(
        "Wage-productivity transmission slope shifters\n"
        "Negative = WEAKER transmission for that country",
        fontsize=11, fontweight="bold",
    )
    ax.grid(True, axis="x", alpha=0.3)
    fig.tight_layout()

    out = FIG_DIR / "wage_transmission_interaction.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── 国別個別 OLS（参考） ──────────────────────────────────────────────────────

def country_by_country_slopes(panel: pd.DataFrame) -> pd.DataFrame:
    """各国の wage-productivity slope を個別 OLS で推定."""
    df = panel.dropna(subset=["g_real_wage", "g_gdp_per_wa"]).copy()
    rows = []
    for c in sorted(df["country"].unique()):
        sub = df[df["country"] == c]
        if len(sub) < 4:
            continue
        try:
            fit = smf.ols("g_real_wage ~ g_gdp_per_wa", data=sub).fit()
            rows.append({
                "country": c,
                "n":       int(fit.nobs),
                "slope":   float(fit.params["g_gdp_per_wa"]),
                "se":      float(fit.bse["g_gdp_per_wa"]),
                "p":       float(fit.pvalues["g_gdp_per_wa"]),
                "intercept": float(fit.params["Intercept"]),
                "r2":      float(fit.rsquared),
            })
        except Exception:
            continue
    return pd.DataFrame(rows).sort_values("slope")


# ── メイン ────────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=" * 60)
        print("Wage-productivity transmission failure — Interaction models")
        print("=" * 60)

    panel = build_wage_panel()
    diff = compute_5yr_diff_panel(panel)
    if verbose:
        print(f"\nSample: {len(diff)} obs, "
              f"{len(diff['country'].unique())} countries")

    results = estimate_models(diff)
    summary = summarize(results)

    if verbose:
        print("\n=== 4 model 推定結果 ===")
        for name in ["T1", "T2", "T3", "T4"]:
            r = results[name]
            print(f"\n[{name}] N={r['n']}, R²={r['r2']:.3f}")
            sub = summary[summary["model"] == name]
            for _, row in sub.iterrows():
                star = ("***" if row["p"] < 0.01 else
                        "**" if row["p"] < 0.05 else
                        "*"  if row["p"] < 0.10 else "")
                print(
                    f"  {row['var']:18s}  "
                    f"β = {row['beta']:+7.3f}  "
                    f"SE = {row['se']:.3f}  "
                    f"p = {row['p']:.4f} {star}  "
                    f"95% CI = [{row['ci_low']:+.3f}, {row['ci_high']:+.3f}]"
                )

    # 国別個別 OLS
    by_country = country_by_country_slopes(diff)
    if verbose:
        print(f"\n=== 国別 OLS slope (g_real_wage ~ g_gdp_per_wa) ===")
        for _, row in by_country.iterrows():
            star = ("***" if row["p"] < 0.01 else
                    "**" if row["p"] < 0.05 else
                    "*"  if row["p"] < 0.10 else "")
            print(
                f"  {row['country']}  N={row['n']:2d}  "
                f"slope={row['slope']:+.3f} (SE={row['se']:.3f}, p={row['p']:.3f}){star}"
            )

    # 図
    fig1 = plot_country_slopes(diff)
    fig2 = plot_interaction_coef(results)

    # CSV
    summary.to_csv(PROCESSED_DIR / "japan_stagnation_wage_transmission.csv",
                   index=False)
    by_country.to_csv(PROCESSED_DIR / "japan_stagnation_wage_transmission_by_country.csv",
                       index=False)

    if verbose:
        print(f"\n  → {fig1}")
        print(f"  → {fig2}")
        print(f"  → {PROCESSED_DIR / 'japan_stagnation_wage_transmission.csv'}")

    return {
        "results": results,
        "summary": summary,
        "by_country": by_country,
    }


if __name__ == "__main__":
    run()
