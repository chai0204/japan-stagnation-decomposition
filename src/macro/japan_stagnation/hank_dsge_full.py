"""完全 HANK + DSGE 統合モデル.

DSGE-light の動学（K_ICT, ω 経路）と HANK-light の家計異質性（4 タイプ × MPC）を統合.

各期 t において:
    1. K_ICT(t), ω(t) は DSGE 動学に従って遷移
    2. Y(t) = production(K_ICT(t))、labor_share(t) = ω(t)(1-α)
    3. 各タイプ i の所得 I_i(t)、消費 C_i(t) = MPC_i × I_i(t) / pop_i
    4. 各タイプの瞬間効用 u_i(t) = log(C_i(t))
    5. 各タイプの一生涯効用 V_i = Σ β^t × u_i(t)
    6. CE 厚生 per type, aggregate（utilitarian, pop 加重）

これにより以下が新たに識別可能:
    - 移行期間の各タイプの消費下降の重さ（特に非正規）
    - 一生涯ベースのタイプ別厚生（DSGE-light + HANK-light 両方の視点）
    - 「政治的に持続可能な改革」（全タイプが時系列で常に正の利得を持つ条件）
    - 不平等動学（reform 期間中の inequality 変化）

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - hank_dsge_consumption_paths.png
        - hank_dsge_welfare_decomposition.png
        - hank_dsge_inequality_dynamics.png
    data/processed/
        - japan_stagnation_hank_dsge_full.csv
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.macro.japan_stagnation.dsge_light import DSGEParams, output_total
from src.macro.japan_stagnation.hank_light import (
    HouseholdType, TYPES_JP, HANKParams, compute_aggregate,
)
from src.macro.japan_stagnation.stylized_facts import FIG_DIR, PROCESSED_DIR


# ── 統合モデル ────────────────────────────────────────────────────────────────

@dataclass
class HANKDSGEParams:
    # DSGE 部分
    alpha:        float = 0.33
    beta:         float = 0.96
    delta:        float = 0.08
    gamma:        float = 0.50

    A_T:          float = 0.803
    A_N_base:     float = 0.686

    omega_init:   float = 0.838
    omega_target: float = 0.838
    lambda_w:     float = 0.20

    K_ICT_init:   float = 1.0
    K_ICT_target: float = 1.0
    rho_ICT:      float = 0.067

    L_T_share:    float = 0.27
    L_N_share:    float = 0.69
    L_total:      float = 1.0

    T_horizon:    int   = 50
    types:        list  = None


# ── パス計算 ──────────────────────────────────────────────────────────────────

def compute_path(p: HANKDSGEParams) -> pd.DataFrame:
    """K_ICT, ω, Y, タイプ別 C, 効用の時系列を計算."""
    if p.types is None:
        types = TYPES_JP
    else:
        types = p.types

    K_path = np.zeros(p.T_horizon + 1)
    omega_path = np.zeros(p.T_horizon + 1)
    K_path[0] = p.K_ICT_init
    omega_path[0] = p.omega_init

    for t in range(p.T_horizon):
        K_path[t + 1] = K_path[t] + p.rho_ICT * (p.K_ICT_target - K_path[t])
        omega_path[t + 1] = omega_path[t] + p.lambda_w * (p.omega_target - omega_path[t])

    rows = []
    for t in range(p.T_horizon + 1):
        # 集計生産（DSGE 部分）
        K_ICT_t = K_path[t]
        omega_t = omega_path[t]
        L_T = p.L_total * p.L_T_share
        L_N = p.L_total * p.L_N_share
        K_T = L_T
        K_N = L_N
        A_N_t = p.A_N_base * (K_ICT_t / 1.0) ** p.gamma
        Y_T = p.A_T * (L_T ** (1 - p.alpha)) * (K_T ** p.alpha)
        Y_N = A_N_t * (L_N ** (1 - p.alpha)) * (K_N ** p.alpha)
        Y_t = Y_T + Y_N

        labor_share = omega_t * (1 - p.alpha)
        capital_share = 1 - labor_share

        # 投資コスト（C_aggregate のため）
        if t < p.T_horizon:
            I_t = K_path[t + 1] - (1 - p.delta) * K_path[t]
        else:
            I_t = p.delta * K_path[t]
        I_t = max(I_t, 0)

        # 各タイプの所得と消費
        wage_total = labor_share * Y_t - I_t * 0.0  # 簡略化：賃金所得から投資控除しない
        capital_total = capital_share * Y_t - I_t

        type_results = {}
        for type_obj in types:
            income_i = (
                wage_total * type_obj.wage_income_share
                + capital_total * type_obj.capital_income_share
            )
            income_i = max(income_i, 1e-6)
            income_per_hh = income_i / type_obj.pop_share
            C_per_hh = max(type_obj.MPC * income_per_hh, 1e-6)
            u_i = np.log(C_per_hh)
            type_results[type_obj.name] = {
                "income_per_hh": income_per_hh,
                "C_per_hh":      C_per_hh,
                "utility":       u_i,
            }

        row = {
            "t":           t,
            "K_ICT":       K_ICT_t,
            "omega":       omega_t,
            "Y":           Y_t,
            "I":           I_t,
            "labor_share": labor_share,
            "capital_share": capital_share,
        }
        for type_name, tr in type_results.items():
            row[f"C_{type_name}"]   = tr["C_per_hh"]
            row[f"U_{type_name}"]   = tr["utility"]

        # Gini-like inequality measure
        c_values = np.array([type_results[t.name]["C_per_hh"] for t in types])
        pop_weights = np.array([t.pop_share for t in types])
        c_mean = np.sum(c_values * pop_weights)
        # 簡易 inequality: top 25% / bottom 25% C 比
        # ソート
        sorted_idx = np.argsort(c_values)
        c_sorted = c_values[sorted_idx]
        pop_sorted = pop_weights[sorted_idx]
        # 簡易 Gini
        gini = np.sum(pop_sorted[:, None] * pop_sorted[None, :] * np.abs(c_sorted[:, None] - c_sorted[None, :])) / (2 * c_mean)
        row["gini"] = gini

        rows.append(row)

    return pd.DataFrame(rows)


# ── 厚生計算 ─────────────────────────────────────────────────────────────────

def compute_welfare(path: pd.DataFrame, types: list,
                     beta: float = 0.96, T: int = 50) -> dict:
    """各タイプ別 + 集計の一生涯厚生（割引 PV）."""
    discount = beta ** path["t"].values
    D = np.sum(discount)  # 割引和

    type_V = {}
    for type_obj in types:
        col = f"U_{type_obj.name}"
        if col not in path.columns:
            continue
        V_i = np.sum(discount * path[col].values)
        type_V[type_obj.name] = V_i

    # Aggregate utilitarian welfare
    W = sum(t.pop_share * type_V[t.name] for t in types if t.name in type_V)

    return {
        "type_V":     type_V,
        "aggregate":  W,
        "D":          D,
    }


def consumption_equivalent(welfare_base: dict, welfare_alt: dict,
                              types: list) -> dict:
    """各タイプ別 + 集計 CE 厚生."""
    type_ce = {}
    D = welfare_base["D"]
    for type_obj in types:
        if type_obj.name not in welfare_base["type_V"]:
            continue
        delta_V = welfare_alt["type_V"][type_obj.name] - welfare_base["type_V"][type_obj.name]
        log_lambda = delta_V / D
        type_ce[type_obj.name] = (np.exp(log_lambda) - 1) * 100

    delta_W = welfare_alt["aggregate"] - welfare_base["aggregate"]
    log_lam_agg = delta_W / D
    aggregate_ce = (np.exp(log_lam_agg) - 1) * 100

    return {"type_ce": type_ce, "aggregate_ce": aggregate_ce}


# ── シナリオ ──────────────────────────────────────────────────────────────────

def define_scenarios() -> dict:
    base = HANKDSGEParams(types=TYPES_JP)

    p_ict = replace(base, K_ICT_target=2.67)
    p_wage = replace(base, omega_target=0.96)
    p_combined = replace(base, K_ICT_target=2.67, omega_target=0.96)

    return {
        "Japan baseline": base,
        "ICT reform":      p_ict,
        "Wage reform":     p_wage,
        "Combined":        p_combined,
    }


# ── プロット ─────────────────────────────────────────────────────────────────

def plot_consumption_paths(scenarios: dict, paths: dict) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(13, 9))
    axes = axes.flatten()

    type_names = [t.name for t in TYPES_JP]
    for ax, type_name in zip(axes, type_names):
        col = f"C_{type_name}"
        for sc_name, path in paths.items():
            base_C = paths["Japan baseline"][col].iloc[0]
            ax.plot(path["t"], path[col] / base_C * 100,
                    label=sc_name, linewidth=2, alpha=0.85)
        ax.axhline(100, color="black", linewidth=0.5, linestyle="--", alpha=0.5)
        ax.set_title(type_name, fontsize=11, fontweight="bold")
        ax.set_xlabel("Years")
        ax.set_ylabel("Consumption (baseline = 100)")
        ax.grid(True, alpha=0.3)
        if type_name == type_names[0]:
            ax.legend(loc="best", fontsize=9)

    fig.suptitle("HANK+DSGE Full: Consumption paths by household type",
                 fontsize=12, fontweight="bold", y=1.00)
    fig.tight_layout()

    out = FIG_DIR / "hank_dsge_consumption_paths.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_welfare_decomposition(welfare_results: dict) -> Path:
    """各シナリオの厚生（タイプ別 + 集計）."""
    scenarios = ["ICT reform", "Wage reform", "Combined"]
    type_names = [t.name for t in TYPES_JP] + ["AGGREGATE"]

    fig, ax = plt.subplots(figsize=(13, 6))
    x = np.arange(len(type_names))
    width = 0.27
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c"]

    for i, (sc, color) in enumerate(zip(scenarios, colors)):
        if sc not in welfare_results:
            continue
        ce_dict = welfare_results[sc]
        values = [ce_dict["type_ce"].get(name, 0) for name in type_names[:-1]]
        values.append(ce_dict["aggregate_ce"])
        offset = (i - 1) * width
        bars = ax.bar(x + offset, values, width, label=sc,
                       color=color, alpha=0.85)
        for j, v in enumerate(values):
            ax.text(x[j] + offset, v + (0.5 if v >= 0 else -1.5),
                    f"{v:+.1f}", ha="center", fontsize=8)

    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(type_names, rotation=15, ha="right", fontsize=9)
    ax.set_ylabel("Lifetime CE welfare (%)")
    ax.set_title("HANK+DSGE Full: Lifetime welfare by household type and reform",
                  fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="best", fontsize=9)
    fig.tight_layout()

    out = FIG_DIR / "hank_dsge_welfare_decomposition.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_inequality_dynamics(paths: dict) -> Path:
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for sc_name, path in paths.items():
        ax.plot(path["t"], path["gini"],
                label=sc_name, linewidth=2, alpha=0.85)
    ax.set_xlabel("Years from reform")
    ax.set_ylabel("Inequality (simplified Gini-like)")
    ax.set_title("HANK+DSGE Full: Inequality dynamics during reform",
                  fontsize=11, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=10)
    fig.tight_layout()

    out = FIG_DIR / "hank_dsge_inequality_dynamics.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── メイン ────────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== HANK + DSGE 完全統合モデル ===")
        print("\n--- 4 タイプ家計（再掲） ---")
        for t in TYPES_JP:
            print(f"  {t.name:25s}: pop {t.pop_share:.2f}, MPC {t.MPC:.2f}")

    scenarios = define_scenarios()
    paths = {}
    for sc_name, p in scenarios.items():
        paths[sc_name] = compute_path(p)

    # 厚生計算（vs baseline）
    base_path = paths["Japan baseline"]
    base_welfare = compute_welfare(base_path, TYPES_JP, T=50)

    welfare_results = {}
    for sc_name, path in paths.items():
        if sc_name == "Japan baseline":
            continue
        alt_welfare = compute_welfare(path, TYPES_JP, T=50)
        ce = consumption_equivalent(base_welfare, alt_welfare, TYPES_JP)
        welfare_results[sc_name] = ce

    # 図
    p1 = plot_consumption_paths(scenarios, paths)
    p2 = plot_welfare_decomposition(welfare_results)
    p3 = plot_inequality_dynamics(paths)

    # サマリー
    rows = []
    for sc_name, ce in welfare_results.items():
        for type_name, v in ce["type_ce"].items():
            rows.append({"scenario": sc_name, "type": type_name, "CE_pct": v})
        rows.append({"scenario": sc_name, "type": "AGGREGATE",
                       "CE_pct": ce["aggregate_ce"]})
    summary = pd.DataFrame(rows)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(PROCESSED_DIR / "japan_stagnation_hank_dsge_full.csv", index=False)

    if verbose:
        print("\n=== 一生涯 CE 厚生（タイプ別 + 集計、HANK+DSGE 完全） ===")
        for sc_name, ce in welfare_results.items():
            print(f"\n[{sc_name}]")
            print(f"  Aggregate: {ce['aggregate_ce']:+.2f}%")
            for type_name, v in ce["type_ce"].items():
                print(f"    {type_name:25s}: {v:+.2f}%")

        print("\n=== 移行期間の不平等（Gini-like、選択時点） ===")
        for sc_name, path in paths.items():
            t_show = [0, 5, 10, 20, 30, 50]
            ginis = [path[path["t"] == t]["gini"].iloc[0] for t in t_show
                      if t in path["t"].values]
            print(f"  {sc_name:18s}: " +
                   ", ".join(f"y{t}: {g:.3f}" for t, g in zip(t_show, ginis)))

        print(f"\n  図1 (消費経路): {p1}")
        print(f"  図2 (厚生分解): {p2}")
        print(f"  図3 (不平等動学): {p3}")

    return {"paths": paths, "welfare": welfare_results, "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="完全 HANK+DSGE モデル")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
