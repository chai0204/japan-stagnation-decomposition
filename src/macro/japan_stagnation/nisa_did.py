"""NISA 制度変更 DID：2024Q1 新 NISA をシャープな自然実験として活用.

Design:
    Treatment unit: JPN
    Control units : USA, DEU, FRA, GBR, CAN, ITA  (other G7)
    Treatment time: 2024Q1 (NISA expansion: 無期限非課税、年間 360万円拡張)
    Pre-period    : 2010Q1 - 2023Q4 (56 quarters)
    Post-period   : 2024Q1 - 2024Q4 (4 quarters)

Outcomes (capital outflow / exchange rate channel):
    1. current_account_gdp : 経常収支 / GDP (%, FRED)
       → 家計対外シフトが大きければ CA は減少 (流出を相殺する黒字)
    2. reer                : 実質実効為替レート (BIS Broad)
       → 家計対外シフトが大きければ円安圧力 → REER 低下
    3. delta_log_reer      : REER 変化率 (year-over-year %)

Specification:
    Y_{i,t} = α + β · (Treat_i × Post_t) + γ_i + δ_t + ε_{i,t}
    where Treat_i = 1{i = JPN}, Post_t = 1{t >= 2024Q1}
    γ_i = country FE, δ_t = time (quarter) FE
    Cluster-robust SE (clustered by country)

Power caveat:
    Post period is only 4 quarters. Power is limited.
    Placebo tests with fake treatment dates are reported.
    Event study captures dynamic effects.

Outputs:
    figures/nisa_did_main.png        : DID coefficient + event study
    figures/nisa_did_placebo.png     : placebo test distribution
    data/processed/japan_stagnation_nisa_did.csv
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

TREATMENT_DATE = pd.Timestamp("2024-01-01")
SAMPLE_START = pd.Timestamp("2010-01-01")
SAMPLE_END = pd.Timestamp("2024-12-31")


def load_g7_panel() -> pd.DataFrame:
    """G7 各国の四半期外部データを長形式パネル化."""
    frames = []
    for c in ALL_COUNTRIES:
        path = RAW_DIR / f"g7_external_{c}.csv"
        if not path.exists():
            print(f"  ! {path.name} 不在 — スキップ")
            continue
        df = pd.read_csv(path, index_col="date", parse_dates=True)
        df["country"] = c
        df = df.reset_index()
        frames.append(df)
    if not frames:
        return pd.DataFrame()

    panel = pd.concat(frames, ignore_index=True)
    panel = panel.rename(columns={"current_account": "ca_gdp"})
    panel = panel[(panel["date"] >= SAMPLE_START) & (panel["date"] <= SAMPLE_END)]
    return panel.sort_values(["country", "date"]).reset_index(drop=True)


def build_did_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """DID 用変数を付与."""
    df = panel.copy()
    df["treated"] = (df["country"] == TREATED_COUNTRY).astype(int)
    df["post"] = (df["date"] >= TREATMENT_DATE).astype(int)
    df["did"] = df["treated"] * df["post"]
    df["quarter"] = df["date"].dt.to_period("Q").astype(str)

    # REER 年率変化（YoY）
    df = df.sort_values(["country", "date"]).reset_index(drop=True)
    df["reer_yoy"] = (
        df.groupby("country")["reer"]
        .pct_change(periods=4) * 100
    )
    # 実質 GDP 年率変化（YoY） — 「消費・生産」チャネル
    df["gdp_yoy"] = (
        df.groupby("country")["real_gdp"]
        .pct_change(periods=4) * 100
    )
    return df


def estimate_did(df: pd.DataFrame, outcome: str) -> dict:
    """国別 FE + 四半期 FE の DID 推定（クラスタ SE）."""
    sub = df.dropna(subset=[outcome]).copy()
    formula = f"{outcome} ~ did + C(country) + C(quarter)"
    try:
        fit = smf.ols(formula, data=sub).fit(
            cov_type="cluster", cov_kwds={"groups": sub["country"]}
        )
    except Exception as e:
        return {"error": str(e), "outcome": outcome}

    return {
        "outcome": outcome,
        "n": int(fit.nobs),
        "beta": float(fit.params["did"]),
        "se": float(fit.bse["did"]),
        "t": float(fit.tvalues["did"]),
        "p": float(fit.pvalues["did"]),
        "ci_low": float(fit.conf_int().loc["did", 0]),
        "ci_high": float(fit.conf_int().loc["did", 1]),
        "fit": fit,
    }


def event_study(df: pd.DataFrame, outcome: str, lags: int = 8, leads: int = 4) -> pd.DataFrame:
    """イベントスタディ：四半期相対距離別ダミー × 処置を推定."""
    sub = df.dropna(subset=[outcome]).copy()
    sub = sub.sort_values(["country", "date"]).reset_index(drop=True)

    treat_q = pd.Period("2024Q1", freq="Q")
    sub["q"] = sub["date"].dt.to_period("Q")
    sub["rel_q"] = (sub["q"] - treat_q).apply(lambda x: x.n)
    sub["rel_q"] = sub["rel_q"].clip(-lags, leads)

    dummy_cols = []
    for k in range(-lags, leads + 1):
        if k == -1:
            continue
        col = f"D_{'m' if k < 0 else 'p'}{abs(k)}"
        sub[col] = ((sub["rel_q"] == k) & (sub["country"] == TREATED_COUNTRY)).astype(int)
        dummy_cols.append((k, col))

    rhs = " + ".join(c for _, c in dummy_cols) + " + C(country) + C(quarter)"
    formula = f"{outcome} ~ {rhs}"
    try:
        fit = smf.ols(formula, data=sub).fit(
            cov_type="cluster", cov_kwds={"groups": sub["country"]}
        )
    except Exception as e:
        return pd.DataFrame()

    rows = []
    for k, col in dummy_cols:
        rows.append({
            "rel_q": k,
            "beta": float(fit.params.get(col, np.nan)),
            "se": float(fit.bse.get(col, np.nan)),
            "ci_low": float(fit.conf_int().loc[col, 0]) if col in fit.params else np.nan,
            "ci_high": float(fit.conf_int().loc[col, 1]) if col in fit.params else np.nan,
        })
    rows.append({"rel_q": -1, "beta": 0.0, "se": 0.0, "ci_low": 0.0, "ci_high": 0.0})
    return pd.DataFrame(rows).sort_values("rel_q").reset_index(drop=True)


def placebo_test(df: pd.DataFrame, outcome: str, n_placebo: int = 30) -> dict:
    """プラセボ：treatment 日付をランダムに pre-period に動かして DID 係数の分布を見る."""
    sub = df.dropna(subset=[outcome]).copy()
    pre_dates = sub.loc[sub["date"] < TREATMENT_DATE, "date"].unique()
    pre_dates = pre_dates[(pre_dates >= pd.Timestamp("2012-01-01"))
                          & (pre_dates <= pd.Timestamp("2022-12-31"))]
    if len(pre_dates) < n_placebo:
        n_placebo = len(pre_dates)

    rng = np.random.default_rng(42)
    sampled = rng.choice(pre_dates, size=n_placebo, replace=False)

    placebo_betas = []
    for fake_date in sampled:
        d = sub.copy()
        d["post"] = (d["date"] >= fake_date).astype(int)
        d["did"] = d["treated"] * d["post"]
        try:
            fit = smf.ols(
                f"{outcome} ~ did + C(country) + C(quarter)", data=d
            ).fit(cov_type="cluster", cov_kwds={"groups": d["country"]})
            placebo_betas.append(fit.params["did"])
        except Exception:
            continue

    real_beta = estimate_did(df, outcome)["beta"]
    p_emp = float((np.abs(placebo_betas) >= abs(real_beta)).mean())
    return {
        "outcome": outcome,
        "real_beta": real_beta,
        "placebo_betas": placebo_betas,
        "p_empirical": p_emp,
    }


# ── プロット ─────────────────────────────────────────────────────────────────

def plot_main(df: pd.DataFrame, results: list[dict], event_results: dict) -> Path:
    fig, axes = plt.subplots(1, len(results), figsize=(5 * len(results), 6))
    if len(results) == 1:
        axes = [axes]
    for ax, res in zip(axes, results):
        outcome = res["outcome"]
        ev = event_results.get(outcome)
        if ev is None or ev.empty:
            ax.text(0.5, 0.5, "no event-study data",
                    ha="center", va="center", transform=ax.transAxes)
            continue
        ax.errorbar(
            ev["rel_q"], ev["beta"],
            yerr=1.96 * ev["se"],
            fmt="o-", capsize=3, color="#d62728",
        )
        ax.axhline(0, color="k", linewidth=0.6)
        ax.axvline(0, color="gray", linewidth=0.5, linestyle="--",
                   label="2024Q1 NISA expansion")
        ax.set_xlabel("Quarters from treatment")
        ax.set_ylabel(f"{outcome} effect")
        ax.set_title(
            f"{outcome}\n"
            f"β = {res['beta']:+.3f} (SE = {res['se']:.3f}, p = {res['p']:.3f})",
            fontsize=10, fontweight="bold",
        )
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)

    fig.suptitle(
        "NISA 2024Q1 expansion — DID event study (JPN treated, G7 control)",
        fontsize=12, fontweight="bold",
    )
    fig.tight_layout()
    out = FIG_DIR / "nisa_did_main.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def plot_placebo(placebo_results: list[dict]) -> Path:
    fig, axes = plt.subplots(1, len(placebo_results), figsize=(5 * len(placebo_results), 4))
    if len(placebo_results) == 1:
        axes = [axes]
    for ax, p in zip(axes, placebo_results):
        ax.hist(p["placebo_betas"], bins=20, color="#1f77b4",
                alpha=0.7, edgecolor="black")
        ax.axvline(p["real_beta"], color="red", linewidth=2,
                   label=f"Real β = {p['real_beta']:+.3f}")
        ax.set_xlabel("Placebo β")
        ax.set_ylabel("Frequency")
        ax.set_title(
            f"{p['outcome']}\n"
            f"Empirical p = {p['p_empirical']:.3f}",
            fontsize=10, fontweight="bold",
        )
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=9)
    fig.suptitle("NISA DID — Placebo distribution (random pre-treatment dates)",
                 fontsize=12, fontweight="bold")
    fig.tight_layout()
    out = FIG_DIR / "nisa_did_placebo.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def run(verbose: bool = True) -> dict:
    if verbose:
        print("=" * 60)
        print("NISA 2024Q1 expansion — DID natural experiment")
        print("=" * 60)

    panel = load_g7_panel()
    if panel.empty:
        print("! G7 panel データなし — collector を先に実行してください")
        return {}
    df = build_did_panel(panel)

    if verbose:
        print(f"\nSample: {df['date'].min().date()} - {df['date'].max().date()}")
        print(f"Countries: {sorted(df['country'].unique())}")
        print(f"Pre-period N: {(df['date'] < TREATMENT_DATE).sum()} obs")
        print(f"Post-period N: {(df['date'] >= TREATMENT_DATE).sum()} obs")
        for c in df["country"].unique():
            sub = df[df["country"] == c]
            n_pre = (sub["date"] < TREATMENT_DATE).sum()
            n_post = (sub["date"] >= TREATMENT_DATE).sum()
            print(f"  {c}: pre {n_pre}, post {n_post}")

    outcomes = ["ca_gdp", "reer_yoy", "gdp_yoy"]
    results = []
    for o in outcomes:
        res = estimate_did(df, o)
        results.append(res)
        if verbose and "beta" in res:
            star = "***" if res["p"] < 0.01 else "**" if res["p"] < 0.05 else "*" if res["p"] < 0.10 else ""
            print(
                f"\n  [{o}] N = {res['n']:>4}, "
                f"β = {res['beta']:+.4f}, SE = {res['se']:.4f}, "
                f"p = {res['p']:.3f} {star}"
            )

    event_results = {}
    for o in outcomes:
        ev = event_study(df, o, lags=8, leads=4)
        event_results[o] = ev

    placebo_results = []
    for o in outcomes:
        p = placebo_test(df, o, n_placebo=30)
        placebo_results.append(p)
        if verbose:
            print(
                f"\n  [{o}] Placebo: real β = {p['real_beta']:+.4f}, "
                f"empirical p = {p['p_empirical']:.3f}"
            )

    fig_main = plot_main(df, results, event_results)
    fig_placebo = plot_placebo(placebo_results)
    if verbose:
        print(f"\n  → {fig_main}")
        print(f"  → {fig_placebo}")

    rows = []
    for r in results:
        if "beta" not in r:
            continue
        rows.append({
            "outcome":  r["outcome"],
            "n":        r["n"],
            "beta":     r["beta"],
            "se":       r["se"],
            "t":        r["t"],
            "p":        r["p"],
            "ci_low":   r["ci_low"],
            "ci_high":  r["ci_high"],
        })
    out_csv = PROCESSED_DIR / "japan_stagnation_nisa_did.csv"
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    if verbose:
        print(f"  → {out_csv}")

    return {
        "results": results,
        "event_results": event_results,
        "placebo_results": placebo_results,
    }


if __name__ == "__main__":
    run()
