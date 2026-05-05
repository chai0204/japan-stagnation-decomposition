"""拡張形式モデル：CES 効用 + ICT 内生 + 動的経路.

3 つの拡張:
    1. CES 効用関数 → 厚生（welfare）の計算
       U(C, ℓ) = C^(1-σ)/(1-σ) - χ·ℓ^(1+η)/(1+η)
       消費等価厚生 λ：U(λ·C^base) = U(C^reform)

    2. A_N の内生化（ICT 投資が生産性を駆動）
       A_N = A_N_base × (k_ICT/k_ICT_base)^γ
       Japan ICT/GDP ≈ 1.5%、USA ≈ 4.0% → これを政策レバーに

    3. 動的経路（adjustment dynamics）
       A_N(t+1) = A_N(t) + ρ·(A_N_target - A_N(t))
       ω(t+1)   = ω(t)   + ρ_ω·(ω_target - ω(t))
       30 年シミュレーションで GDP・賃金・厚生の経路を計算

カリブレーション:
    σ = 1.0（log 効用）
    η = 2.0（労働供給弾力性 0.5）
    χ = 1.0
    γ = 0.5（ICT 投資の生産性弾力性）
    ρ = 0.10（改革の収束速度、年率）

シナリオ:
    1. ベースライン継続
    2. ICT 改革（k_ICT を米国水準に 10 年で上げる）
    3. 賃金分配改革（ω を独水準に 5 年で上げる）
    4. 統合改革

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - extended_model_welfare.png
        - extended_model_transition.png
        - extended_model_ict_lever.png
    data/processed/
        - japan_stagnation_extended_model.csv
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.macro.japan_stagnation.stylized_facts import FIG_DIR, PROCESSED_DIR


# ── パラメータ ────────────────────────────────────────────────────────────────

@dataclass
class ExtendedParams:
    # 標準パラメータ
    alpha:        float = 0.33  # 資本シェア

    # 部門別生産性
    A_T:          float = 0.803   # 工業（per-hour Japan/Germany 比）
    A_N_base:     float = 0.686   # サービス業（per-hour Japan/Germany 比、内生化前）
    gamma:        float = 0.50    # ICT 投資の生産性弾力性

    # ICT 資本
    k_ICT:        float = 1.0     # ICT 資本ストック（標準化）
    k_ICT_base:   float = 1.0     # 基準値

    # 賃金分配
    omega:        float = 0.838

    # 部門配分
    L_T_share:    float = 0.27
    L_N_share:    float = 0.69
    L_A_share:    float = 0.04

    # 標準化
    KL_ratio:     float = 1.0
    L_total:      float = 1.0

    # 効用関数パラメータ
    sigma:        float = 1.0     # 消費の異時点間代替弾力性（1=log）
    eta:          float = 2.0     # 労働供給弾力性の逆数
    chi:          float = 1.0     # 労働の効用ウェイト
    ell_baseline: float = 1.0     # 労働供給標準

    # 国際資産
    r_f:          float = 0.04


# ── A_N 内生化 ────────────────────────────────────────────────────────────────

def compute_A_N(p: ExtendedParams) -> float:
    """ICT 投資から A_N を計算."""
    return p.A_N_base * (p.k_ICT / p.k_ICT_base) ** p.gamma


# ── 静学モデル（拡張版）──────────────────────────────────────────────────────

def solve_economy(p: ExtendedParams) -> dict:
    L_T = p.L_total * p.L_T_share
    L_N = p.L_total * p.L_N_share

    K_T = L_T * p.KL_ratio
    K_N = L_N * p.KL_ratio

    A_N = compute_A_N(p)

    Y_T = p.A_T * (L_T ** (1 - p.alpha)) * (K_T ** p.alpha)
    Y_N = A_N    * (L_N ** (1 - p.alpha)) * (K_N ** p.alpha)
    Y_total = Y_T + Y_N

    mpl_T = (1 - p.alpha) * p.A_T * (K_T / L_T) ** p.alpha
    mpl_N = (1 - p.alpha) * A_N    * (K_N / L_N) ** p.alpha
    mpk_T = p.alpha * p.A_T * (L_T / K_T) ** (1 - p.alpha)
    mpk_N = p.alpha * A_N    * (L_N / K_N) ** (1 - p.alpha)

    w_T = p.omega * mpl_T
    w_N = p.omega * mpl_N
    w_avg = (w_T * L_T + w_N * L_N) / (L_T + L_N)

    wage_bill = w_T * L_T + w_N * L_N
    labor_share = wage_bill / Y_total

    K_total = K_T + K_N
    capital_income = mpk_T * K_T + mpk_N * K_N
    r_d = capital_income / K_total

    # 消費 = 賃金所得 + 資本所得（家計と企業帰属を統合した最終消費の代理）
    C = Y_total  # 標準化
    ell = p.ell_baseline  # 単純化

    return {
        "Y_total":     Y_total,
        "Y_T":         Y_T,
        "Y_N":         Y_N,
        "A_N":         A_N,
        "w_avg":       w_avg,
        "wage_bill":   wage_bill,
        "labor_share": labor_share,
        "r_d":         r_d,
        "C":           C,
        "ell":         ell,
    }


# ── 効用と厚生 ────────────────────────────────────────────────────────────────

def utility(C: float, ell: float, p: ExtendedParams) -> float:
    if abs(p.sigma - 1.0) < 1e-6:
        u_c = np.log(C)
    else:
        u_c = (C ** (1 - p.sigma) - 1) / (1 - p.sigma)
    u_ell = p.chi * (ell ** (1 + p.eta)) / (1 + p.eta)
    return u_c - u_ell


def consumption_equivalent_welfare(p_base: ExtendedParams, p_alt: ExtendedParams) -> float:
    """λ such that U(λ·C_base, ell_base) = U(C_alt, ell_alt).

    log 効用の場合: log(λ·C_b) - χℓ_b^(1+η)/(1+η) = log(C_a) - χℓ_a^(1+η)/(1+η)
    => log(λ) = log(C_a/C_b) + χ(ℓ_b^(1+η) - ℓ_a^(1+η))/(1+η)
    => λ = exp(...)
    """
    base = solve_economy(p_base)
    alt = solve_economy(p_alt)

    if abs(p_base.sigma - 1.0) < 1e-6:
        # log 効用
        log_lambda = (
            np.log(alt["C"] / base["C"])
            + p_base.chi
            * (base["ell"] ** (1 + p_base.eta) - alt["ell"] ** (1 + p_base.eta))
            / (1 + p_base.eta)
        )
        return np.exp(log_lambda) - 1  # 「ベースライン消費の何 % 上乗せ相当か」
    else:
        # 一般 CRRA
        u_alt = utility(alt["C"], alt["ell"], p_base)
        # λ について解く（数値）
        from scipy.optimize import brentq
        f = lambda lam: utility(lam * base["C"], base["ell"], p_base) - u_alt
        try:
            lam = brentq(f, 0.1, 10.0)
            return lam - 1
        except Exception:
            return np.nan


# ── 動的経路 ──────────────────────────────────────────────────────────────────

def simulate_transition(
    p_initial: ExtendedParams,
    p_target:  ExtendedParams,
    rho_AN:    float = 0.10,
    rho_omega: float = 0.20,
    rho_ICT:   float = 0.10,
    T:         int   = 30,
) -> pd.DataFrame:
    """初期パラメータから目標パラメータへの線形収束経路."""
    rows = []
    p = replace(p_initial)
    for t in range(T + 1):
        # 各パラメータの遷移
        p.A_N_base = p.A_N_base + rho_AN * (p_target.A_N_base - p.A_N_base)
        p.omega = p.omega + rho_omega * (p_target.omega - p.omega)
        p.k_ICT = p.k_ICT + rho_ICT * (p_target.k_ICT - p.k_ICT)

        result = solve_economy(p)
        # 厚生（ベースライン対比）
        welfare = consumption_equivalent_welfare(p_initial, p)

        rows.append({
            "year":         t,
            "A_N":          compute_A_N(p),
            "omega":        p.omega,
            "k_ICT":        p.k_ICT,
            "Y_total":      result["Y_total"],
            "Y_index":      result["Y_total"] / solve_economy(p_initial)["Y_total"] * 100,
            "w_avg":        result["w_avg"],
            "w_index":      result["w_avg"] / solve_economy(p_initial)["w_avg"] * 100,
            "labor_share":  result["labor_share"],
            "welfare_pct":  welfare * 100,
        })
    return pd.DataFrame(rows)


# ── シナリオ定義 ──────────────────────────────────────────────────────────────

def define_extended_scenarios() -> dict:
    base = ExtendedParams()  # 日本ベースライン

    # ICT 改革（米国水準）：k_ICT を 4/1.5 倍 = 2.67 倍に
    p_ict = replace(base, k_ICT=2.67)

    # 賃金分配改革：omega を 0.96 に
    p_wage = replace(base, omega=0.96)

    # ICT + 賃金統合
    p_combined_partial = replace(base, k_ICT=2.67, omega=0.96)

    # 完全独並み（統合版）
    p_full = replace(base, A_T=1.0, A_N_base=1.0, omega=0.96, k_ICT=1.0)

    return {
        "Japan baseline":        base,
        "ICT investment to USA":  p_ict,
        "Wage share to Germany":  p_wage,
        "ICT + Wage combined":    p_combined_partial,
        "Full reform (Germany)":  p_full,
    }


# ── プロット ─────────────────────────────────────────────────────────────────

def plot_welfare_comparison(scenarios: dict) -> Path:
    base = scenarios["Japan baseline"]
    welfare_results = []
    for name, p in scenarios.items():
        if name == "Japan baseline":
            welfare = 0.0
        else:
            welfare = consumption_equivalent_welfare(base, p) * 100
        result = solve_economy(p)
        welfare_results.append({
            "scenario":   name,
            "welfare_pct": welfare,
            "gdp_index":   result["Y_total"] / solve_economy(base)["Y_total"] * 100,
            "wage_index":  result["w_avg"] / solve_economy(base)["w_avg"] * 100,
        })

    df = pd.DataFrame(welfare_results)

    fig, ax = plt.subplots(figsize=(11, 5.5))
    x = np.arange(len(df))
    width = 0.27
    ax.bar(x - width, df["gdp_index"] - 100, width, label="GDP gain (%)",
           color="#1f77b4", alpha=0.85)
    ax.bar(x, df["wage_index"] - 100, width, label="Wage gain (%)",
           color="#ff7f0e", alpha=0.85)
    ax.bar(x + width, df["welfare_pct"], width, label="Welfare gain (%, CE)",
           color="#2ca02c", alpha=0.85)

    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(df["scenario"], rotation=20, ha="right", fontsize=9)
    ax.set_ylabel("Gain over Japan baseline (%)")
    ax.set_title("Extended Model: GDP, Wage, and Welfare Gains by Scenario\n"
                  "(Welfare = Consumption-equivalent metric)",
                  fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="best", fontsize=9)

    fig.tight_layout()
    out = FIG_DIR / "extended_model_welfare.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_transition(scenarios: dict) -> Path:
    base = scenarios["Japan baseline"]
    target_full = scenarios["Full reform (Germany)"]
    target_combined = scenarios["ICT + Wage combined"]

    path_full = simulate_transition(base, target_full, T=30)
    path_combined = simulate_transition(base, target_combined, T=30)

    fig, axes = plt.subplots(2, 2, figsize=(13, 9), sharex=True)
    axes = axes.flatten()

    # GDP 経路
    ax = axes[0]
    ax.plot(path_full["year"], path_full["Y_index"],
            label="Full reform", linewidth=2, color="#1f77b4")
    ax.plot(path_combined["year"], path_combined["Y_index"],
            label="ICT + Wage", linewidth=2, color="#ff7f0e", linestyle="--")
    ax.axhline(100, color="gray", linewidth=0.8, linestyle=":", alpha=0.5)
    ax.set_title("GDP Path", fontsize=11, fontweight="bold")
    ax.set_ylabel("Index (Japan baseline = 100)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=9)

    # 賃金経路
    ax = axes[1]
    ax.plot(path_full["year"], path_full["w_index"],
            label="Full reform", linewidth=2, color="#1f77b4")
    ax.plot(path_combined["year"], path_combined["w_index"],
            label="ICT + Wage", linewidth=2, color="#ff7f0e", linestyle="--")
    ax.axhline(100, color="gray", linewidth=0.8, linestyle=":", alpha=0.5)
    ax.set_title("Wage Path", fontsize=11, fontweight="bold")
    ax.set_ylabel("Index (Japan baseline = 100)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=9)

    # 労働分配率
    ax = axes[2]
    ax.plot(path_full["year"], path_full["labor_share"],
            label="Full reform", linewidth=2, color="#1f77b4")
    ax.plot(path_combined["year"], path_combined["labor_share"],
            label="ICT + Wage", linewidth=2, color="#ff7f0e", linestyle="--")
    ax.axhline(0.561, color="red", linewidth=0.8, linestyle=":",
                alpha=0.6, label="Japan 2024")
    ax.axhline(0.643, color="green", linewidth=0.8, linestyle=":",
                alpha=0.6, label="Germany 2024")
    ax.set_title("Labor Share Path", fontsize=11, fontweight="bold")
    ax.set_ylabel("Labor share")
    ax.set_xlabel("Years from reform start")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=9)

    # 厚生（消費等価）
    ax = axes[3]
    ax.plot(path_full["year"], path_full["welfare_pct"],
            label="Full reform", linewidth=2, color="#1f77b4")
    ax.plot(path_combined["year"], path_combined["welfare_pct"],
            label="ICT + Wage", linewidth=2, color="#ff7f0e", linestyle="--")
    ax.axhline(0, color="gray", linewidth=0.8, linestyle=":", alpha=0.5)
    ax.set_title("Welfare Path (Consumption Equivalent %)",
                  fontsize=11, fontweight="bold")
    ax.set_ylabel("CE welfare gain (%)")
    ax.set_xlabel("Years from reform start")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=9)

    fig.suptitle("Transition Dynamics: 30-year reform paths",
                 fontsize=12, fontweight="bold", y=1.00)
    fig.tight_layout()

    out = FIG_DIR / "extended_model_transition.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_ict_lever(p_base: ExtendedParams) -> Path:
    """ICT 投資水準と GDP・厚生の関係."""
    ict_levels = np.linspace(0.5, 4.0, 20)
    gdp_idx = []
    welfare = []
    base_Y = solve_economy(p_base)["Y_total"]

    for k in ict_levels:
        p = replace(p_base, k_ICT=k)
        Y = solve_economy(p)["Y_total"]
        w = consumption_equivalent_welfare(p_base, p) * 100
        gdp_idx.append(Y / base_Y * 100)
        welfare.append(w)

    fig, ax1 = plt.subplots(figsize=(10, 5.5))
    ax1.plot(ict_levels, gdp_idx, "o-", color="#1f77b4", linewidth=2,
             markersize=4, label="GDP index")
    ax1.set_xlabel("ICT capital ratio (Japan baseline = 1.0; USA ≈ 2.67)")
    ax1.set_ylabel("GDP index (Japan baseline = 100)", color="#1f77b4")
    ax1.tick_params(axis="y", labelcolor="#1f77b4")
    ax1.grid(True, alpha=0.3)

    ax2 = ax1.twinx()
    ax2.plot(ict_levels, welfare, "s-", color="#2ca02c", linewidth=2,
             markersize=4, label="Welfare (CE %)")
    ax2.set_ylabel("Welfare gain (CE %)", color="#2ca02c")
    ax2.tick_params(axis="y", labelcolor="#2ca02c")

    # USA 水準ライン
    ax1.axvline(2.67, color="red", linewidth=1, linestyle="--",
                  alpha=0.6, label="USA level")
    ax1.legend(loc="upper left")
    ax2.legend(loc="lower right")

    ax1.set_title("ICT Investment Lever: GDP and Welfare Response\n"
                   "(Cross-section: each point is a different long-run k_ICT)",
                   fontsize=11, fontweight="bold")
    fig.tight_layout()

    out = FIG_DIR / "extended_model_ict_lever.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── メイン ────────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== 拡張形式モデル：CES 効用 + ICT 内生 + 動的経路 ===")

    scenarios = define_extended_scenarios()
    base = scenarios["Japan baseline"]

    # 静学比較
    rows = []
    for name, p in scenarios.items():
        result = solve_economy(p)
        if name == "Japan baseline":
            welfare = 0.0
        else:
            welfare = consumption_equivalent_welfare(base, p) * 100
        baseline_result = solve_economy(base)
        rows.append({
            "scenario":      name,
            "Y_total":       result["Y_total"],
            "Y_index":       result["Y_total"] / baseline_result["Y_total"] * 100,
            "A_N":           result["A_N"],
            "w_avg":         result["w_avg"],
            "w_index":       result["w_avg"] / baseline_result["w_avg"] * 100,
            "labor_share":   result["labor_share"],
            "welfare_CE_pct": welfare,
        })
    static_summary = pd.DataFrame(rows)

    # 動的経路
    target_full = scenarios["Full reform (Germany)"]
    target_combined = scenarios["ICT + Wage combined"]
    transition_full = simulate_transition(base, target_full, T=30)
    transition_combined = simulate_transition(base, target_combined, T=30)

    # プロット
    p1 = plot_welfare_comparison(scenarios)
    p2 = plot_transition(scenarios)
    p3 = plot_ict_lever(base)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    static_path = PROCESSED_DIR / "japan_stagnation_extended_model.csv"
    static_summary.to_csv(static_path, index=False)

    transition_path = PROCESSED_DIR / "japan_stagnation_extended_transition.csv"
    transition_combined["scenario"] = "ICT + Wage"
    transition_full["scenario"] = "Full reform"
    pd.concat([transition_combined, transition_full]).to_csv(transition_path, index=False)

    if verbose:
        print("\n=== 静学比較（厚生付き） ===")
        cols = ["scenario", "Y_index", "w_index", "labor_share", "welfare_CE_pct"]
        print(static_summary[cols].round(2).to_string(index=False))

        print("\n=== 動的経路（ICT + Wage 統合改革、選択時点） ===")
        for t in [0, 5, 10, 15, 20, 30]:
            row = transition_combined[transition_combined["year"] == t].iloc[0]
            print(f"  Year {t:2d}: GDP {row['Y_index']:5.1f}, "
                   f"Wage {row['w_index']:5.1f}, "
                   f"Labor share {row['labor_share']:.3f}, "
                   f"Welfare {row['welfare_pct']:+5.1f}%")

        print(f"\n  図1（厚生比較）: {p1}")
        print(f"  図2（動的経路）: {p2}")
        print(f"  図3（ICT レバー）: {p3}")

    return {"static": static_summary, "transition_full": transition_full,
            "transition_combined": transition_combined}


def main() -> None:
    parser = argparse.ArgumentParser(description="拡張形式モデル")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
