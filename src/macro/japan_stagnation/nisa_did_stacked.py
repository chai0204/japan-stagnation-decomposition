"""旧 NISA (2014Q1) + 新 NISA (2024Q1) の stacked DID.

レビュー round 5 の指摘：
    > New NISA 単独だと時系列が短い。旧NISA + 新NISA の stacked DID か、
    > Abenomics financial liberalization の方が現実的。

# Background

NISA (Nippon Individual Savings Account) は税制優遇付きの少額投資制度：
- 2014Q1: 旧 NISA 開始（年 100 万円、5 年間、累計 500 万円、20% 課税免除）
- 2018Q1: つみたて NISA 追加（年 40 万円、20 年間、800 万円累計）
- 2024Q1: 新 NISA 開始（年 360 万円、無期限、累計 1800 万円）

両者ともに「家計の対外資産シフト」を促進する政策ショックの可能性。

# Stacked DID design (Cengiz et al. 2019, Callaway-Sant'Anna 2021 流)

各 cohort g（g = 2014Q1, 2024Q1）について：
- treated unit: JPN
- control units: USA, DEU, FRA, GBR, CAN, ITA
- pre-period: g - K quarters
- post-period: g + L quarters

各 cohort dataset を stack し、cohort × country × rel_q FE で DID 推定。

# Models

DID:
    Y_{g,c,t} = α + β · DID_{g,c,t} + γ_{g,c} + δ_{g,t} + ε_{g,c,t}

    where DID_{g,c,t} = 1{c=JPN} × 1{t ≥ g}
    γ_{g,c}: cohort-country FE
    δ_{g,t}: cohort-rel_q FE

Parallel trends test:
    Joint F test of pre-treatment dummies = 0

# Outputs

- figures/nisa_did_stacked_main.png
- figures/nisa_did_stacked_event_study.png
- data/processed/japan_stagnation_nisa_did_stacked.csv
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from src.macro.japan_stagnation.stylized_facts import FIG_DIR, PROCESSED_DIR

RAW_DIR = Path(__file__).parents[3] / "data" / "raw"

CONTROL_COUNTRIES = ["USA", "DEU", "FRA", "GBR", "CAN", "ITA"]
TREATED_COUNTRY = "JPN"
ALL_COUNTRIES = [TREATED_COUNTRY] + CONTROL_COUNTRIES

# Treatment events
EVENTS = {
    "old_NISA_2014Q1": pd.Period("2014Q1", freq="Q"),
    "new_NISA_2024Q1": pd.Period("2024Q1", freq="Q"),
}

# Cohort window sizes (quarters)
K_PRE = 20   # 5 years
L_POST_OLD = 16  # 4 years (avoid 2018Q1 つみたて NISA contamination would be 2014+16=2018)
L_POST_NEW = 4   # 1 year (data limit)

SAMPLE_START = pd.Timestamp("2008-01-01")  # earliest needed for 2014 - 5y
SAMPLE_END = pd.Timestamp("2024-12-31")


def load_g7_panel() -> pd.DataFrame:
    frames = []
    for c in ALL_COUNTRIES:
        path = RAW_DIR / f"g7_external_{c}.csv"
        if not path.exists():
            print(f"  ! {path.name} 不在")
            continue
        df = pd.read_csv(path, index_col="date", parse_dates=True)
        df["country"] = c
        df = df.reset_index()
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    panel = pd.concat(frames, ignore_index=True)
    panel = panel.rename(columns={"current_account": "ca_gdp"})
    panel = panel[
        (panel["date"] >= SAMPLE_START) & (panel["date"] <= SAMPLE_END)
    ]
    # YoY transformations
    panel = panel.sort_values(["country", "date"]).reset_index(drop=True)
    panel["reer_yoy"] = panel.groupby("country")["reer"].pct_change(periods=4) * 100
    panel["gdp_yoy"] = panel.groupby("country")["real_gdp"].pct_change(periods=4) * 100
    return panel


def build_cohort_data(
    panel: pd.DataFrame, event_q: pd.Period, cohort_id: str,
    k_pre: int, l_post: int,
) -> pd.DataFrame:
    """1 つの treatment event 用 cohort データを構築."""
    df = panel.copy()
    df["q"] = df["date"].dt.to_period("Q")
    df["rel_q"] = (df["q"] - event_q).apply(lambda p: p.n)
    df = df[(df["rel_q"] >= -k_pre) & (df["rel_q"] < l_post)]
    df["cohort_id"] = cohort_id
    df["is_treated"] = (df["country"] == TREATED_COUNTRY).astype(int)
    df["post"] = (df["rel_q"] >= 0).astype(int)
    df["did"] = df["is_treated"] * df["post"]
    return df


def stack_cohorts(
    panel: pd.DataFrame, k_pre: int, l_post_old: int, l_post_new: int,
) -> pd.DataFrame:
    """両 cohort を stack."""
    cohorts = []
    cohorts.append(build_cohort_data(
        panel, EVENTS["old_NISA_2014Q1"], "old_2014",
        k_pre=k_pre, l_post=l_post_old,
    ))
    cohorts.append(build_cohort_data(
        panel, EVENTS["new_NISA_2024Q1"], "new_2024",
        k_pre=k_pre, l_post=l_post_new,
    ))
    return pd.concat(cohorts, ignore_index=True)


def estimate_stacked_did(stacked: pd.DataFrame, outcome: str) -> dict:
    """Stacked DID（cohort-country FE + cohort-rel_q FE）."""
    sub = stacked.dropna(subset=[outcome]).copy()
    formula = (
        f"{outcome} ~ did "
        f"+ C(cohort_id):C(country) "
        f"+ C(cohort_id):C(rel_q)"
    )
    try:
        fit = smf.ols(formula, data=sub).fit(
            cov_type="cluster", cov_kwds={"groups": sub["country"]}
        )
    except Exception as e:
        return {"error": str(e), "outcome": outcome}
    return {
        "outcome": outcome,
        "n":       int(fit.nobs),
        "beta":    float(fit.params["did"]),
        "se":      float(fit.bse["did"]),
        "t":       float(fit.tvalues["did"]),
        "p":       float(fit.pvalues["did"]),
        "ci_low":  float(fit.conf_int().loc["did", 0]),
        "ci_high": float(fit.conf_int().loc["did", 1]),
        "fit":     fit,
    }


def estimate_separate_did(
    panel: pd.DataFrame, event_q: pd.Period, cohort_id: str,
    k_pre: int, l_post: int, outcome: str,
) -> dict:
    """各 cohort 単独の DID（比較用）."""
    cohort = build_cohort_data(panel, event_q, cohort_id, k_pre, l_post)
    sub = cohort.dropna(subset=[outcome]).copy()
    formula = f"{outcome} ~ did + C(country) + C(rel_q)"
    try:
        fit = smf.ols(formula, data=sub).fit(
            cov_type="cluster", cov_kwds={"groups": sub["country"]}
        )
    except Exception as e:
        return {"error": str(e), "outcome": outcome, "cohort": cohort_id}
    return {
        "outcome": outcome,
        "cohort":  cohort_id,
        "n":       int(fit.nobs),
        "beta":    float(fit.params["did"]),
        "se":      float(fit.bse["did"]),
        "p":       float(fit.pvalues["did"]),
        "ci_low":  float(fit.conf_int().loc["did", 0]),
        "ci_high": float(fit.conf_int().loc["did", 1]),
        "fit":     fit,
    }


def event_study_stacked(stacked: pd.DataFrame, outcome: str,
                         lags: int = 12, leads: int = 12) -> dict:
    """Stacked event study with parallel trends test."""
    sub = stacked.dropna(subset=[outcome]).copy()
    sub["rel_q_capped"] = sub["rel_q"].clip(-lags, leads)

    dummy_cols = []
    pre_cols = []
    for k in range(-lags, leads + 1):
        if k == -1:
            continue
        col = f"D_{'m' if k < 0 else 'p'}{abs(k)}"
        sub[col] = (
            (sub["rel_q_capped"] == k) & (sub["country"] == TREATED_COUNTRY)
        ).astype(int)
        dummy_cols.append((k, col))
        if k < -1:
            pre_cols.append(col)

    rhs = (
        " + ".join(c for _, c in dummy_cols)
        + " + C(cohort_id):C(country) + C(cohort_id):C(rel_q)"
    )
    formula = f"{outcome} ~ {rhs}"
    try:
        fit = smf.ols(formula, data=sub).fit(
            cov_type="cluster", cov_kwds={"groups": sub["country"]}
        )
    except Exception:
        return {}

    rows = []
    for k, col in dummy_cols:
        rows.append({
            "rel_q":   k,
            "beta":    float(fit.params.get(col, np.nan)),
            "se":      float(fit.bse.get(col, np.nan)),
            "ci_low":  float(fit.conf_int().loc[col, 0]) if col in fit.params else np.nan,
            "ci_high": float(fit.conf_int().loc[col, 1]) if col in fit.params else np.nan,
        })
    rows.append({"rel_q": -1, "beta": 0.0, "se": 0.0, "ci_low": 0.0, "ci_high": 0.0})
    events = pd.DataFrame(rows).sort_values("rel_q").reset_index(drop=True)

    # Parallel trends test: joint F test of pre dummies = 0
    pretrend_p, pretrend_F = np.nan, np.nan
    if pre_cols:
        try:
            hyp = ", ".join(f"{c} = 0" for c in pre_cols)
            f_test = fit.f_test(hyp)
            pretrend_F = float(f_test.fvalue)
            pretrend_p = float(f_test.pvalue)
        except Exception:
            pass

    return {"events": events, "pretrend_F": pretrend_F, "pretrend_p": pretrend_p}


def plot_stacked_event_study(events_dict: dict) -> Path:
    fig, axes = plt.subplots(1, len(events_dict), figsize=(5 * len(events_dict), 5))
    if len(events_dict) == 1:
        axes = [axes]
    for ax, (outcome, ev) in zip(axes, events_dict.items()):
        df = ev["events"]
        if df.empty:
            continue
        ax.errorbar(
            df["rel_q"], df["beta"],
            yerr=1.96 * df["se"],
            fmt="o-", capsize=2, color="#d62728", markersize=4,
        )
        ax.axhline(0, color="k", linewidth=0.5)
        ax.axvline(0, color="gray", linewidth=0.5, linestyle="--")
        ax.set_xlabel("Quarters from treatment")
        ax.set_ylabel(f"{outcome}")
        title = f"{outcome}\nParallel trends F={ev.get('pretrend_F', np.nan):.2f}, p={ev.get('pretrend_p', np.nan):.3f}"
        ax.set_title(title, fontsize=10)
        ax.grid(True, alpha=0.3)
    fig.suptitle(
        "Stacked DID event study: 旧 NISA 2014Q1 + 新 NISA 2024Q1",
        fontsize=12, fontweight="bold",
    )
    fig.tight_layout()
    out = FIG_DIR / "nisa_did_stacked_event_study.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def run(verbose: bool = True) -> dict:
    if verbose:
        print("=" * 60)
        print("Stacked DID: 旧 NISA 2014Q1 + 新 NISA 2024Q1")
        print("=" * 60)

    panel = load_g7_panel()
    if panel.empty:
        print("! データなし")
        return {}

    if verbose:
        print(f"\n基本パネル: {len(panel)} obs, "
              f"{panel['date'].min().date()} - {panel['date'].max().date()}")

    stacked = stack_cohorts(panel, K_PRE, L_POST_OLD, L_POST_NEW)
    if verbose:
        print(f"\nStacked dataset:")
        for cid in stacked["cohort_id"].unique():
            sub = stacked[stacked["cohort_id"] == cid]
            print(f"  {cid}: {len(sub)} obs, "
                  f"rel_q range [{sub['rel_q'].min()}, {sub['rel_q'].max()}]")

    outcomes = ["ca_gdp", "reer_yoy", "gdp_yoy"]

    # Stacked DID
    if verbose:
        print(f"\n=== Stacked DID（両 cohort 統合） ===")
    stacked_results = {}
    for o in outcomes:
        r = estimate_stacked_did(stacked, o)
        stacked_results[o] = r
        if verbose and "beta" in r:
            star = ("***" if r["p"] < 0.01 else
                    "**" if r["p"] < 0.05 else
                    "*" if r["p"] < 0.10 else "")
            print(
                f"  [{o}] N={r['n']:>4}, "
                f"β={r['beta']:+.4f}, SE={r['se']:.4f}, "
                f"p={r['p']:.4f} {star}, 95% CI=[{r['ci_low']:+.3f}, {r['ci_high']:+.3f}]"
            )

    # Cohort 別 DID（比較用）
    if verbose:
        print(f"\n=== 各 cohort 個別 DID（比較） ===")
    sep_results = {}
    for cohort_name, event_q, l_post in [
        ("old_2014", EVENTS["old_NISA_2014Q1"], L_POST_OLD),
        ("new_2024", EVENTS["new_NISA_2024Q1"], L_POST_NEW),
    ]:
        for o in outcomes:
            r = estimate_separate_did(panel, event_q, cohort_name, K_PRE, l_post, o)
            sep_results[(cohort_name, o)] = r
            if verbose and "beta" in r:
                star = ("***" if r["p"] < 0.01 else
                        "**" if r["p"] < 0.05 else
                        "*" if r["p"] < 0.10 else "")
                print(
                    f"  [{cohort_name}] [{o}] N={r['n']:>4}, "
                    f"β={r['beta']:+.4f}, SE={r['se']:.4f}, "
                    f"p={r['p']:.4f} {star}"
                )

    # Event study (stacked)
    if verbose:
        print(f"\n=== Stacked Event study + parallel trends test ===")
    es_results = {}
    for o in outcomes:
        es = event_study_stacked(stacked, o, lags=12, leads=12)
        es_results[o] = es
        if verbose and es:
            verdict = ("PASS" if es.get("pretrend_p", np.nan) > 0.10
                       else "VIOLATED")
            print(
                f"  [{o}] Parallel trends: F={es.get('pretrend_F', np.nan):.3f}, "
                f"p={es.get('pretrend_p', np.nan):.3f} → {verdict}"
            )

    # Plot
    fig = plot_stacked_event_study(es_results)

    # CSV output
    rows = []
    for o, r in stacked_results.items():
        if "beta" in r:
            rows.append({
                "spec": "stacked", "outcome": o,
                "n": r["n"], "beta": r["beta"], "se": r["se"], "p": r["p"],
                "ci_low": r["ci_low"], "ci_high": r["ci_high"],
                "pretrend_p": es_results.get(o, {}).get("pretrend_p", np.nan),
            })
    for (cohort, o), r in sep_results.items():
        if "beta" in r:
            rows.append({
                "spec": cohort, "outcome": o,
                "n": r["n"], "beta": r["beta"], "se": r["se"], "p": r["p"],
                "ci_low": r["ci_low"], "ci_high": r["ci_high"],
                "pretrend_p": np.nan,
            })
    df_out = pd.DataFrame(rows)
    out_csv = PROCESSED_DIR / "japan_stagnation_nisa_did_stacked.csv"
    df_out.to_csv(out_csv, index=False)

    if verbose:
        print(f"\n  → {fig}")
        print(f"  → {out_csv}")

    return {
        "stacked": stacked_results,
        "separate": sep_results,
        "event_study": es_results,
        "summary_df": df_out,
    }


if __name__ == "__main__":
    run()
