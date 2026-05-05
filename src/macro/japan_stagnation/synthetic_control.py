"""シンセティック・コントロール法：合成日本を構築し実際の日本との乖離を識別.

Abadie & Gardeazabal (2003), Abadie, Diamond & Hainmueller (2010) の手法.

目的:
    G7 + 韓国の他国の重み付け平均で「合成日本」を構築し、
    本物の日本との成長率乖離を「日本固有要因」として識別する.
    Phase 1 のパネル回帰を補強する非パラメトリック識別.

方法:
    1. プレ介入期間（仮置き：1995-2000）における観測指標の重み付け平均が
       日本の値を再現するように、他国の重みを最適化（quadratic programming）
    2. 同じ重みでポスト期間（2001-2024）の合成日本を計算
    3. 実際の日本との差分を時系列でプロット

対象アウトカム:
    1人あたり実質 GDP（年次、1995=100 指数）

予測子（マッチング変数）:
    - 1人あたり GDP（プレ期間平均）
    - 1人あたり GDP 成長率（プレ期間 5 年）
    - 高齢化率
    - 輸出/GDP
    - 人口成長率

制約:
    - 重み w_i ∈ [0, 1]
    - Σw_i = 1
    - 日本自身は除外

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - synthetic_japan_gdp_pc.png
        - synthetic_japan_gdp_per_wa.png
    data/processed/
        - japan_stagnation_synthetic_control.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import minimize

from src.macro.japan_stagnation.stylized_facts import (
    COUNTRY_LABEL, FIG_DIR, PROCESSED_DIR, load_panel,
)


def _objective(w: np.ndarray, X_treated: np.ndarray, X_donors: np.ndarray) -> float:
    """加重平均と被介入の差を最小化."""
    synth = X_donors @ w
    return float(np.sum((X_treated - synth) ** 2))


def fit_synthetic_weights(
    X_treated: np.ndarray,
    X_donors: np.ndarray,
    seed: int = 42,
) -> np.ndarray:
    """単純な逐次2次計画法で重みを推定.

    制約: w >= 0, sum(w) = 1.
    """
    n = X_donors.shape[1]
    rng = np.random.default_rng(seed)

    # 複数のスタートから最適化
    best_obj = np.inf
    best_w = None
    for trial in range(10):
        w0 = rng.dirichlet(np.ones(n))
        cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
        bounds = [(0.0, 1.0)] * n
        try:
            result = minimize(
                _objective, w0, args=(X_treated, X_donors),
                method="SLSQP", bounds=bounds, constraints=cons,
                options={"maxiter": 500, "ftol": 1e-10},
            )
            if result.success and result.fun < best_obj:
                best_obj = result.fun
                best_w = result.x
        except Exception:
            continue
    if best_w is None:
        # フォールバック: 均等重み
        best_w = np.ones(n) / n
    return best_w


# ── データ準備 ────────────────────────────────────────────────────────────────

def build_predictors_panel(
    panel: pd.DataFrame,
    pre_start: int = 1995,
    pre_end: int = 2000,
) -> pd.DataFrame:
    """予測子を国別に集約."""
    df = panel.reset_index().copy()
    df["aging_share"] = 1 - df["population_15_64"] / df["population"]
    df["gdp_per_wa"] = df["gdp_real"] / df["population_15_64"]

    pre = df[(df["year"] >= pre_start) & (df["year"] <= pre_end)]

    rows = []
    for c in df["country"].unique():
        sub_pre = pre[pre["country"] == c]
        if len(sub_pre) < 3:
            continue
        rec = {
            "country": c,
            "gdp_per_capita_pre":     sub_pre["gdp_per_capita"].mean(),
            "gdp_per_wa_pre":         sub_pre["gdp_per_wa"].mean(),
            "aging_share_pre":        sub_pre["aging_share"].mean(),
            "exports_gdp_share_pre":  sub_pre["exports_gdp_share"].mean(),
            "fdi_outflows_gdp_pre":   sub_pre["fdi_outflows_gdp"].mean(),
        }
        rows.append(rec)
    return pd.DataFrame(rows).set_index("country")


def get_outcome_series(panel: pd.DataFrame, var: str = "gdp_per_capita") -> pd.DataFrame:
    """国別アウトカム時系列（年次）."""
    df = panel.reset_index().copy()
    if var == "gdp_per_wa":
        df[var] = df["gdp_real"] / df["population_15_64"]
    pivot = df.pivot(index="year", columns="country", values=var)
    return pivot


def normalize_to_base(series: pd.DataFrame, base_year: int = 1995) -> pd.DataFrame:
    """基準年 = 100 に指数化."""
    if base_year not in series.index:
        return series
    return series.div(series.loc[base_year]).mul(100)


# ── 合成日本構築 ──────────────────────────────────────────────────────────────

def build_synthetic_japan(
    panel: pd.DataFrame,
    outcome_var: str = "gdp_per_capita",
    pre_start: int = 1995,
    pre_end: int = 2000,
    treated: str = "JPN",
    verbose: bool = True,
) -> dict:
    predictors = build_predictors_panel(panel, pre_start, pre_end)
    if treated not in predictors.index:
        raise ValueError(f"{treated} データなし")

    donors = [c for c in predictors.index if c != treated]
    pred_cols = [c for c in predictors.columns if not predictors[c].isna().any()]

    X_treated = predictors.loc[treated, pred_cols].values.astype(float)
    X_donors = predictors.loc[donors, pred_cols].T.values.astype(float)

    # 標準化
    means = X_donors.mean(axis=1, keepdims=True)
    stds = X_donors.std(axis=1, keepdims=True) + 1e-9
    X_treated_z = (X_treated.reshape(-1, 1) - means).flatten() / stds.flatten()
    X_donors_z = (X_donors - means) / stds

    w = fit_synthetic_weights(X_treated_z, X_donors_z)

    if verbose:
        print(f"\n  合成 {treated} の重み:")
        for d, wi in sorted(zip(donors, w), key=lambda x: -x[1]):
            if wi > 0.01:
                print(f"    {COUNTRY_LABEL.get(d, d):10s}: {wi:.3f}")

    # アウトカムを構築（基準年=100に指数化）
    outcome = get_outcome_series(panel, var=outcome_var)
    outcome_idx = normalize_to_base(outcome, base_year=pre_start)

    treated_series = outcome_idx[treated]
    donor_series = outcome_idx[donors]
    synthetic = donor_series.values @ w

    df_result = pd.DataFrame({
        "actual": treated_series,
        "synthetic": pd.Series(synthetic, index=outcome_idx.index),
    })
    df_result["gap"] = df_result["actual"] - df_result["synthetic"]

    return {
        "weights":   pd.Series(w, index=donors).sort_values(ascending=False),
        "result":    df_result,
        "predictor_fit": predictors,
        "outcome_var": outcome_var,
    }


# ── プロット ─────────────────────────────────────────────────────────────────

def plot_synthetic(result: dict, var_label: str, suffix: str) -> Path:
    df = result["result"]
    weights = result["weights"]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5.5),
                              gridspec_kw={"width_ratios": [2.4, 1.0]})

    ax = axes[0]
    ax.plot(df.index, df["actual"], color="#d62728", linewidth=2.5,
            label="Actual Japan", marker="o", markersize=3)
    ax.plot(df.index, df["synthetic"], color="#1f77b4", linewidth=2.0,
            linestyle="--", label="Synthetic Japan",
            marker="s", markersize=3)
    ax.fill_between(df.index, df["actual"], df["synthetic"],
                    where=df["actual"] < df["synthetic"],
                    alpha=0.15, color="#d62728", label="Underperformance")
    ax.fill_between(df.index, df["actual"], df["synthetic"],
                    where=df["actual"] >= df["synthetic"],
                    alpha=0.15, color="#2ca02c")
    ax.axhline(100, color="black", linewidth=0.6, linestyle=":", alpha=0.5)
    ax.set_title(f"Synthetic Control: Japan vs Synthetic Japan ({var_label})",
                 fontsize=11, fontweight="bold")
    ax.set_xlabel("Year")
    ax.set_ylabel("Index (1995=100)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="upper left", fontsize=9)

    # 重み棒グラフ
    ax = axes[1]
    top = weights[weights > 0.01].sort_values(ascending=True)
    labels = [COUNTRY_LABEL.get(c, c) for c in top.index]
    colors_list = ["#1f77b4"] * len(top)
    ax.barh(labels, top.values, color=colors_list, alpha=0.85, edgecolor="black", linewidth=0.5)
    ax.set_title("Donor weights", fontsize=11, fontweight="bold")
    ax.set_xlabel("Weight")
    ax.grid(True, axis="x", alpha=0.3)
    for i, (lbl, v) in enumerate(zip(labels, top.values)):
        ax.text(v + 0.005, i, f"{v:.2f}", va="center", fontsize=9)

    fig.tight_layout()

    out = FIG_DIR / f"synthetic_japan_{suffix}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── メイン ────────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== Synthetic Control: Synthetic Japan ===")

    panel = load_panel()

    # 1. 1人あたり GDP
    if verbose:
        print("\n--- アウトカム: 1 人あたり実質 GDP ---")
    res_pc = build_synthetic_japan(
        panel, outcome_var="gdp_per_capita",
        pre_start=1995, pre_end=2000, verbose=verbose,
    )
    p1 = plot_synthetic(res_pc, "GDP per capita", "gdp_pc")

    # 2. 生産年齢 1人あたり GDP
    if verbose:
        print("\n--- アウトカム: 生産年齢 1 人あたり実質 GDP ---")
    res_wa = build_synthetic_japan(
        panel, outcome_var="gdp_per_wa",
        pre_start=1995, pre_end=2000, verbose=verbose,
    )
    p2 = plot_synthetic(res_wa, "GDP per Working-Age Adult", "gdp_per_wa")

    # 結果保存
    combined = pd.DataFrame({
        "year":              res_pc["result"].index,
        "actual_pc":         res_pc["result"]["actual"].values,
        "synthetic_pc":      res_pc["result"]["synthetic"].values,
        "gap_pc":            res_pc["result"]["gap"].values,
        "actual_per_wa":     res_wa["result"]["actual"].values,
        "synthetic_per_wa":  res_wa["result"]["synthetic"].values,
        "gap_per_wa":        res_wa["result"]["gap"].values,
    })
    out_csv = PROCESSED_DIR / "japan_stagnation_synthetic_control.csv"
    combined.to_csv(out_csv, index=False)

    if verbose:
        print("\n=== 結果サマリー ===")
        print(f"\n  最新（2024）の合成日本との乖離:")
        last_pc = res_pc["result"].iloc[-1]
        last_wa = res_wa["result"].iloc[-1]
        print(f"    1 人あたり GDP:")
        print(f"      Actual = {last_pc['actual']:.1f}, Synthetic = {last_pc['synthetic']:.1f}")
        print(f"      Gap = {last_pc['gap']:+.1f} ポイント")
        print(f"    生産年齢 1 人あたり GDP:")
        print(f"      Actual = {last_wa['actual']:.1f}, Synthetic = {last_wa['synthetic']:.1f}")
        print(f"      Gap = {last_wa['gap']:+.1f} ポイント")

        print(f"\n  図1: {p1}")
        print(f"  図2: {p2}")
        print(f"  結果: {out_csv}")

    return {"per_capita": res_pc, "per_wa": res_wa, "combined": combined}


def main() -> None:
    parser = argparse.ArgumentParser(description="シンセティック・コントロール")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
