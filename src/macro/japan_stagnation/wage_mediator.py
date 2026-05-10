"""H8 wedge の mediator analysis.

レビュー round 4 への対応：
    > 「賃金が弱い」までは示している。なぜ？がまだ薄い。
    > labor share / bargaining power / non-regular employment / ICT complementarity
    > / corporate retained earnings のどれが主要因かを示したい。

# Strategy

ベースライン W1: g_wage ~ g_prod + Japan + year_FE → β_Japan = -2.15

各 mediator を順次追加し、Japan dummy が attenuate するかを観察：

  M1: + Δlabor_share (PWT, primary candidate)
  M2: + Δself_employment_share (WDI)
  M3: + Δvulnerable_employment (WDI, non-regular proxy)
  M4: + Δaging_share, Δexports_gdp (control)
  M5: All

# Interpretation

- Japan dummy がほぼ 0 まで attenuate → 該当 mediator が "the mechanism"
- 部分的に attenuate → 部分的 mechanism
- まったく attenuate しない → 別の mechanism が dominant

# Caveats

- mediator analysis は causal mediation ではなく partial correlations
- 内生性問題：mediator も日本固有の影響を受けている可能性
- proxies の質：vulnerable_employment は WDI ILO 流の compute、日本特有の非正規ではない

# Output

- data/processed/japan_stagnation_wage_mediator.csv
- figures/wage_mediator_attenuation.png
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from src.collectors.wdi_labor_collector import load_country as load_labor
from src.macro.japan_stagnation.pwt_collector_helper import interp_labsh_year
from src.macro.japan_stagnation.stylized_facts import FIG_DIR, PROCESSED_DIR
from src.macro.japan_stagnation.wage_stagnation import (
    build_wage_panel, compute_5yr_diff_panel,
)


# ── データ統合 ───────────────────────────────────────────────────────────────

def load_labor_panel() -> pd.DataFrame:
    countries = ["USA", "JPN", "DEU", "FRA", "GBR", "CAN", "ITA", "KOR"]
    frames = []
    for c in countries:
        df = load_labor(c)
        if df.empty:
            continue
        df = df.copy()
        df["country"] = c
        frames.append(df.reset_index())
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def add_labor_share_to_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """PWT 労働分配率を年次補間して付与."""
    df = panel.copy()
    df["labor_share"] = df.apply(
        lambda r: interp_labsh_year(r["country"], int(r["year"])),
        axis=1,
    )
    return df


def build_extended_5yr_panel(interval: int = 5) -> pd.DataFrame:
    """5 年差分パネル + mediator 変数."""
    base = build_wage_panel()
    labor = load_labor_panel()
    base = pd.merge(
        base, labor[["year", "country", "self_employed_total",
                      "vulnerable_employment"]],
        on=["year", "country"], how="left",
    )
    base = add_labor_share_to_panel(base)
    base["aging_share"] = 1 - base["population_15_64"] / base["population"]
    base["gdp_per_wa"] = base["gdp_real"] / base["population_15_64"]

    rows = []
    for c in base["country"].unique():
        sub = base[base["country"] == c].set_index("year").sort_index()
        for y in sub.index:
            y0 = y - interval
            if y0 not in sub.index:
                continue
            row = {"country": c, "year_end": y, "year_start": y0}

            # 成長率（5 年差分・年率）
            for g_var, col in [
                ("g_real_wage", "real_wage"),
                ("g_gdp_per_wa", "gdp_per_wa"),
            ]:
                v0, v1 = sub.loc[y0, col], sub.loc[y, col]
                if pd.notna(v0) and pd.notna(v1) and v0 > 0:
                    row[g_var] = ((v1 / v0) ** (1.0 / interval) - 1.0) * 100
                else:
                    row[g_var] = np.nan

            # Mediator: 5 年差分絶対変化（mechanical confound あり）
            for d_var, col in [
                ("d_labor_share",      "labor_share"),
                ("d_self_employment",  "self_employed_total"),
                ("d_vulnerable_emp",   "vulnerable_employment"),
                ("d_aging_share",      "aging_share"),
            ]:
                v0, v1 = sub.loc[y0, col], sub.loc[y, col]
                row[d_var] = (v1 - v0) if (pd.notna(v0) and pd.notna(v1)) else np.nan

            # Mediator (LEVEL): t-5 時点の値（lag、より exogenous）
            for lag_var, col in [
                ("lag_labor_share",      "labor_share"),
                ("lag_self_employment",  "self_employed_total"),
                ("lag_vulnerable_emp",   "vulnerable_employment"),
                ("lag_aging_share",      "aging_share"),
            ]:
                v0 = sub.loc[y0, col]
                row[lag_var] = float(v0) if pd.notna(v0) else np.nan

            row["japan"] = int(c == "JPN")
            rows.append(row)

    return pd.DataFrame(rows).dropna(subset=["g_real_wage", "g_gdp_per_wa"])


# ── 推定 ──────────────────────────────────────────────────────────────────────

MODELS = {
    # 5-year change specifications (時間内変動を見る、ただし labor share は mechanical 共変)
    "M0_baseline":    "g_real_wage ~ g_gdp_per_wa + japan + C(year_end)",
    "M1_dlabor":      "g_real_wage ~ g_gdp_per_wa + japan + d_labor_share + C(year_end)",
    "M2_dselfemp":    "g_real_wage ~ g_gdp_per_wa + japan + d_self_employment + C(year_end)",
    "M3_dvuln":       "g_real_wage ~ g_gdp_per_wa + japan + d_vulnerable_emp + C(year_end)",
    "M4_daging":      "g_real_wage ~ g_gdp_per_wa + japan + d_aging_share + C(year_end)",
    "M5_dall":        (
        "g_real_wage ~ g_gdp_per_wa + japan + d_labor_share + d_self_employment "
        "+ d_vulnerable_emp + d_aging_share + C(year_end)"
    ),
    # LEVEL specifications (t-5 lag、より外生的)
    "M6_llabor":      "g_real_wage ~ g_gdp_per_wa + japan + lag_labor_share + C(year_end)",
    "M7_lselfemp":    "g_real_wage ~ g_gdp_per_wa + japan + lag_self_employment + C(year_end)",
    "M8_lvuln":       "g_real_wage ~ g_gdp_per_wa + japan + lag_vulnerable_emp + C(year_end)",
    "M9_laging":      "g_real_wage ~ g_gdp_per_wa + japan + lag_aging_share + C(year_end)",
    "M10_lall":       (
        "g_real_wage ~ g_gdp_per_wa + japan + lag_labor_share + lag_self_employment "
        "+ lag_vulnerable_emp + lag_aging_share + C(year_end)"
    ),
}


def estimate_models(panel: pd.DataFrame) -> dict:
    """各 mediator を順次追加した上で Japan dummy を推定."""
    results = {}
    for name, formula in MODELS.items():
        rhs_vars = formula.split("~")[1].split("+")
        needed = []
        for v in rhs_vars:
            v = v.strip().split("(")[0].strip()
            if v in panel.columns:
                needed.append(v)
        # subset で完全な観測のみ使う（mediator が NaN の行を除外）
        sub = panel.dropna(subset=needed + ["g_real_wage"])
        if len(sub) < 30:
            print(f"  ! {name}: insufficient observations ({len(sub)})")
            continue
        try:
            fit = smf.ols(formula, data=sub).fit(
                cov_type="cluster", cov_kwds={"groups": sub["country"]}
            )
            results[name] = {
                "fit": fit,
                "n": int(fit.nobs),
                "japan_beta": float(fit.params.get("japan", np.nan)),
                "japan_se":   float(fit.bse.get("japan", np.nan)),
                "japan_p":    float(fit.pvalues.get("japan", np.nan)),
                "params":     fit.params,
                "pvalues":    fit.pvalues,
                "r2":         float(fit.rsquared),
            }
        except Exception as e:
            print(f"  ! {name} failed: {e}")
    return results


# ── attenuation 計算 ──────────────────────────────────────────────────────────

def compute_attenuation(results: dict) -> pd.DataFrame:
    """Japan dummy がベースラインから何 % 減ったか."""
    if "M0_baseline" not in results:
        return pd.DataFrame()
    beta_baseline = results["M0_baseline"]["japan_beta"]
    rows = []
    for name, r in results.items():
        attenuation = (1 - r["japan_beta"] / beta_baseline) * 100
        rows.append({
            "model":       name,
            "n":           r["n"],
            "japan_beta":  r["japan_beta"],
            "japan_se":    r["japan_se"],
            "japan_p":     r["japan_p"],
            "attenuation_pct": attenuation,
            "r2":          r["r2"],
        })
    return pd.DataFrame(rows)


def plot_attenuation(att_df: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(10, 5))
    ypos = np.arange(len(att_df))
    colors = ["#1f77b4" if "M0" in m else "#d62728" for m in att_df["model"]]
    ax.barh(ypos, att_df["japan_beta"], color=colors, alpha=0.85)
    for i, row in att_df.iterrows():
        ax.text(row["japan_beta"] - 0.05, i,
                f"β={row['japan_beta']:+.3f} (att={row['attenuation_pct']:+.1f}%)",
                va="center", ha="right", fontsize=9, color="white")
    ax.axvline(0, color="black", linewidth=0.6)
    ax.set_yticks(ypos)
    ax.set_yticklabels(att_df["model"])
    ax.set_xlabel("Japan dummy coefficient (%/yr)")
    ax.set_title(
        "Mediator analysis: Does Japan dummy attenuate when controls added?",
        fontsize=11, fontweight="bold",
    )
    ax.grid(True, axis="x", alpha=0.3)
    ax.invert_yaxis()
    fig.tight_layout()

    out = FIG_DIR / "wage_mediator_attenuation.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── メイン ────────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=" * 60)
        print("Wage panel — Mediator analysis (mechanism identification)")
        print("=" * 60)

    panel = build_extended_5yr_panel(interval=5)
    if verbose:
        print(f"\nExtended panel: {len(panel)} obs, "
              f"{len(panel['country'].unique())} countries")
        # mediator 変数の利用可能性
        for v in ["d_labor_share", "d_self_employment",
                   "d_vulnerable_emp", "d_aging_share"]:
            n_valid = panel[v].notna().sum()
            print(f"  {v}: {n_valid} valid obs")

    results = estimate_models(panel)
    att = compute_attenuation(results)

    if verbose:
        print("\n=== Mediator analysis 結果 ===")
        print(f"\n{'Model':<15} {'N':>5} {'β_Japan':>10} {'SE':>8} {'p':>8} "
              f"{'Atten%':>10} {'R²':>6}")
        print("-" * 70)
        for _, row in att.iterrows():
            print(
                f"{row['model']:<15} {row['n']:>5d} "
                f"{row['japan_beta']:>+10.3f} "
                f"{row['japan_se']:>8.3f} "
                f"{row['japan_p']:>8.4f} "
                f"{row['attenuation_pct']:>+9.1f}% "
                f"{row['r2']:>6.3f}"
            )

        # mediator 自体の係数
        for spec_name, mediators in [
            ("M5_dall (Δ all)",
             ["d_labor_share", "d_self_employment", "d_vulnerable_emp", "d_aging_share"]),
            ("M10_lall (lag levels all)",
             ["lag_labor_share", "lag_self_employment", "lag_vulnerable_emp", "lag_aging_share"]),
        ]:
            key = spec_name.split()[0]
            if key not in results:
                continue
            print(f"\n=== Mediator 自身の係数（{spec_name}） ===")
            params = results[key]["params"]
            pvals = results[key]["pvalues"]
            for v in mediators:
                if v in params:
                    star = ("***" if pvals[v] < 0.01 else
                            "**" if pvals[v] < 0.05 else
                            "*" if pvals[v] < 0.10 else "")
                    print(f"  {v:<22s}  β={params[v]:+8.4f}  "
                          f"p={pvals[v]:.4f} {star}")

    fig = plot_attenuation(att)
    att.to_csv(PROCESSED_DIR / "japan_stagnation_wage_mediator.csv", index=False)

    if verbose:
        print(f"\n  → {fig}")
        print(f"  → {PROCESSED_DIR / 'japan_stagnation_wage_mediator.csv'}")

    return {"results": results, "attenuation": att, "panel": panel}


if __name__ == "__main__":
    run()
