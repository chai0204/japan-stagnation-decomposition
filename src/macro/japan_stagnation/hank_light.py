"""HANK-light：異質的家計新ケインジアンモデル.

DSGE-light（§6.14）は代表的家計だったため、賃金分配（ω 改革）の厚生効果が
0% になる構造的限界があった. HANK-light では家計を 4 タイプに分割し、
分配が厚生に与える効果を識別する.

家計タイプ（日本 2024 年カリブレーション）:
    Type A: 大企業正社員（Pop 20%, Wage 30%, Capital 5%, MPC 0.55）
    Type B: SME 正社員（Pop 38%, Wage 40%, Capital 10%, MPC 0.70）
    Type C: 非正規労働者（Pop 37%, Wage 25%, Capital 5%, MPC 0.92）
    Type D: 自営業・役員（Pop 5%, Wage 5%, Capital 80%, MPC 0.50）

ロジック:
    各タイプの所得 I_i = Y × (labor_share × wage_share_i + capital_share × cap_share_i)
    各タイプの消費 C_i = MPC_i × I_i
    各タイプの厚生 U_i = log(C_i / pop_share_i)（per-household）
    集計厚生 W = Σ pop_share_i × U_i

賃金改革（ω → ω*）の効果:
    - labor_share = ω × (1-α) が上昇 → 賃金所得が増える
    - capital_share = α × ω + (1-ω)(1-α) が減少
    - Type A, B, C は wage 比率が高いので利益
    - Type D は capital 比率が高いので損失
    - 集計厚生：高 MPC タイプ（C 非正規）への再分配で正の効果

ICT 改革（A_N 上昇）:
    - Y 全体が上昇 → 全タイプ均一に利得
    - ただし Type D（capital 多）が比例的に利得大

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - hank_consumption_by_type.png
        - hank_welfare_by_type.png
        - hank_vs_dsge.png
    data/processed/
        - japan_stagnation_hank_results.csv
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace, field
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.macro.japan_stagnation.stylized_facts import FIG_DIR, PROCESSED_DIR


@dataclass
class HouseholdType:
    name:                  str
    pop_share:             float  # 人口（家計数）シェア
    wage_income_share:     float  # 全賃金所得に占めるシェア
    capital_income_share:  float  # 全資本所得に占めるシェア
    MPC:                   float  # 限界消費性向
    color:                 str = "gray"


# ── 日本のカリブレーション ────────────────────────────────────────────────────
# 内閣府「国民経済計算」+ 厚生労働省「賃金構造基本統計」+ Cabinet Office HANK
# レポートに基づく approximate 値

TYPES_JP = [
    HouseholdType("Large-firm regular",
                   pop_share=0.20, wage_income_share=0.30,
                   capital_income_share=0.05, MPC=0.55, color="#1f77b4"),
    HouseholdType("SME regular",
                   pop_share=0.38, wage_income_share=0.40,
                   capital_income_share=0.10, MPC=0.70, color="#2ca02c"),
    HouseholdType("Non-regular",
                   pop_share=0.37, wage_income_share=0.25,
                   capital_income_share=0.05, MPC=0.92, color="#d62728"),
    HouseholdType("Self-employed/owner",
                   pop_share=0.05, wage_income_share=0.05,
                   capital_income_share=0.80, MPC=0.50, color="#ff7f0e"),
]

# ── 経済全体パラメータ ────────────────────────────────────────────────────────

@dataclass
class HANKParams:
    alpha:        float = 0.33  # 資本シェア
    Y_baseline:   float = 1.0   # 基準 GDP
    omega:        float = 0.838 # 賃金分配パラメータ
    A_N_base:     float = 0.686
    A_T:          float = 0.803
    gamma:        float = 0.50  # ICT 弾力性
    K_ICT:        float = 1.0   # ICT 資本（ベースライン）
    K_ICT_ss:     float = 1.0   # 標準化定数
    types:        list = field(default_factory=lambda: TYPES_JP)


# ── 集計と分配計算 ────────────────────────────────────────────────────────────

def compute_aggregate(p: HANKParams) -> dict:
    """集計 GDP・労働所得・資本所得."""
    A_N = p.A_N_base * (p.K_ICT / p.K_ICT_ss) ** p.gamma
    L_T_share = 0.27
    L_N_share = 0.69
    Y_T = p.A_T * (L_T_share ** (1 - p.alpha)) * ((L_T_share) ** p.alpha)
    Y_N = A_N    * (L_N_share ** (1 - p.alpha)) * ((L_N_share) ** p.alpha)
    Y = Y_T + Y_N

    labor_share = p.omega * (1 - p.alpha)
    capital_share = 1 - labor_share

    wage_total = labor_share * Y
    capital_total = capital_share * Y

    return {
        "Y":            Y,
        "labor_share":  labor_share,
        "capital_share": capital_share,
        "wage_total":   wage_total,
        "capital_total": capital_total,
    }


def compute_household_outcomes(p: HANKParams) -> pd.DataFrame:
    """各タイプの所得・消費・厚生."""
    agg = compute_aggregate(p)
    rows = []
    for t in p.types:
        income = (
            agg["wage_total"] * t.wage_income_share
            + agg["capital_total"] * t.capital_income_share
        )
        # per household
        income_per_hh = income / t.pop_share
        consumption_per_hh = t.MPC * income_per_hh
        # 厚生（log 効用）
        utility = np.log(max(consumption_per_hh, 1e-6))
        rows.append({
            "type":         t.name,
            "pop_share":    t.pop_share,
            "MPC":          t.MPC,
            "income_total": income,
            "income_per_hh": income_per_hh,
            "C_per_hh":     consumption_per_hh,
            "utility_per_hh": utility,
            "weighted_utility": t.pop_share * utility,
        })
    return pd.DataFrame(rows)


def aggregate_welfare(p: HANKParams) -> float:
    """utilitarian 集計厚生（pop_share 加重）."""
    df = compute_household_outcomes(p)
    return df["weighted_utility"].sum()


def consumption_equivalent_welfare_hank(
    p_base: HANKParams, p_alt: HANKParams,
) -> dict:
    """HANK 消費等価厚生.

    各タイプ別と集計の両方を計算.
    """
    df_base = compute_household_outcomes(p_base)
    df_alt = compute_household_outcomes(p_alt)

    # 集計
    welfare_base = df_base["weighted_utility"].sum()
    welfare_alt = df_alt["weighted_utility"].sum()
    # 集計 CE 厚生
    log_lambda = welfare_alt - welfare_base
    ce_aggregate = np.exp(log_lambda) - 1

    # タイプ別 CE 厚生
    type_ce = []
    for i, t in enumerate(p_base.types):
        u_base = df_base.iloc[i]["utility_per_hh"]
        u_alt = df_alt.iloc[i]["utility_per_hh"]
        log_lam_i = u_alt - u_base
        ce_i = np.exp(log_lam_i) - 1
        type_ce.append({
            "type":    t.name,
            "CE_pct":  ce_i * 100,
            "C_base":  df_base.iloc[i]["C_per_hh"],
            "C_alt":   df_alt.iloc[i]["C_per_hh"],
        })

    return {
        "ce_aggregate_pct":  ce_aggregate * 100,
        "type_ce":           pd.DataFrame(type_ce),
    }


# ── シナリオ ──────────────────────────────────────────────────────────────────

def define_hank_scenarios() -> dict:
    base = HANKParams()  # 日本ベースライン

    # ICT 改革：K_ICT を 2.67 倍
    p_ict = replace(base, K_ICT=2.67)

    # 賃金改革：omega を 0.96
    p_wage = replace(base, omega=0.96)

    # 統合改革
    p_combined = replace(base, K_ICT=2.67, omega=0.96)

    return {
        "Japan baseline":   base,
        "ICT reform":       p_ict,
        "Wage reform":      p_wage,
        "Combined reform":  p_combined,
    }


# ── プロット ─────────────────────────────────────────────────────────────────

def plot_consumption_by_type(scenarios_results: dict) -> Path:
    fig, ax = plt.subplots(figsize=(11, 6))
    types = [t.name for t in TYPES_JP]
    x = np.arange(len(types))
    width = 0.2

    base_df = scenarios_results["Japan baseline"]
    base_C = base_df["C_per_hh"].values

    for i, (name, df) in enumerate(scenarios_results.items()):
        ratio = df["C_per_hh"].values / base_C * 100
        offset = (i - 1.5) * width
        ax.bar(x + offset, ratio, width, label=name, alpha=0.85)

    ax.axhline(100, color="black", linewidth=0.5, linestyle="--", alpha=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(types, rotation=15, ha="right", fontsize=9)
    ax.set_ylabel("Consumption per household (Japan baseline = 100)")
    ax.set_title("HANK: Consumption by household type and reform scenario",
                  fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="best", fontsize=9, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / "hank_consumption_by_type.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_welfare_by_type(welfare_results: dict) -> Path:
    fig, ax = plt.subplots(figsize=(11, 6))
    types = [t.name for t in TYPES_JP]
    x = np.arange(len(types))
    width = 0.27

    scenarios = ["ICT reform", "Wage reform", "Combined reform"]
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c"]

    for i, (sc, color) in enumerate(zip(scenarios, colors)):
        if sc not in welfare_results:
            continue
        type_ce = welfare_results[sc]["type_ce"]
        ce_values = type_ce["CE_pct"].values
        offset = (i - 1) * width
        ax.bar(x + offset, ce_values, width, label=sc,
                color=color, alpha=0.85)

    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(types, rotation=15, ha="right", fontsize=9)
    ax.set_ylabel("CE welfare gain (%)")
    ax.set_title("HANK: Welfare gain by household type and reform scenario",
                  fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="best", fontsize=9)
    fig.tight_layout()

    out = FIG_DIR / "hank_welfare_by_type.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_hank_vs_dsge(welfare_results: dict) -> Path:
    """HANK と DSGE-light の集計厚生比較."""
    scenarios = ["ICT reform", "Wage reform", "Combined reform"]
    hank_welfare = [welfare_results[s]["ce_aggregate_pct"] for s in scenarios]
    # DSGE-light 値（前回計算）
    dsge_welfare = [8.34, 0.0, 8.34]
    # Static counterfactual (Extended model)
    static_welfare = [43.5, 0.0, 43.5]

    x = np.arange(len(scenarios))
    width = 0.27

    fig, ax = plt.subplots(figsize=(11, 6))
    ax.bar(x - width, static_welfare, width, label="Extended (static)",
           color="#1f77b4", alpha=0.85)
    ax.bar(x, dsge_welfare, width, label="DSGE-light (intertemporal)",
           color="#ff7f0e", alpha=0.85)
    ax.bar(x + width, hank_welfare, width, label="HANK-light (heterogeneous)",
           color="#2ca02c", alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels(scenarios, rotation=10, ha="right", fontsize=10)
    ax.set_ylabel("Welfare gain (CE %)")
    ax.set_title("Model comparison: Aggregate welfare gains across model variants",
                  fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="best", fontsize=10)

    for i, (s, d, h) in enumerate(zip(static_welfare, dsge_welfare, hank_welfare)):
        ax.text(i - width, s + 1, f"{s:.1f}", ha="center", fontsize=9)
        ax.text(i, d + 1, f"{d:.1f}", ha="center", fontsize=9)
        ax.text(i + width, h + 1, f"{h:.1f}", ha="center", fontsize=9)

    fig.tight_layout()
    out = FIG_DIR / "hank_vs_dsge.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── メイン ────────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== HANK-light：異質的家計新ケインジアンモデル ===")
        print("\n--- 日本家計タイプ・カリブレーション ---")
        for t in TYPES_JP:
            print(f"  {t.name:25s}: pop {t.pop_share:.2f}, "
                   f"wage {t.wage_income_share:.2f}, "
                   f"capital {t.capital_income_share:.2f}, MPC {t.MPC:.2f}")

    scenarios = define_hank_scenarios()
    base = scenarios["Japan baseline"]

    # 各シナリオでタイプ別結果
    scenarios_results = {}
    for name, p in scenarios.items():
        df = compute_household_outcomes(p)
        scenarios_results[name] = df

    # 厚生計算
    welfare_results = {}
    for name, p in scenarios.items():
        if name == "Japan baseline":
            continue
        welfare_results[name] = consumption_equivalent_welfare_hank(base, p)

    # 図
    p1 = plot_consumption_by_type(scenarios_results)
    p2 = plot_welfare_by_type(welfare_results)
    p3 = plot_hank_vs_dsge(welfare_results)

    # サマリー保存
    summary_rows = []
    for name, w in welfare_results.items():
        for _, r in w["type_ce"].iterrows():
            summary_rows.append({
                "scenario": name,
                "type":     r["type"],
                "CE_pct":   r["CE_pct"],
                "C_base":   r["C_base"],
                "C_alt":    r["C_alt"],
            })
        summary_rows.append({
            "scenario": name,
            "type":     "AGGREGATE",
            "CE_pct":   w["ce_aggregate_pct"],
            "C_base":   np.nan,
            "C_alt":    np.nan,
        })
    summary = pd.DataFrame(summary_rows)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(PROCESSED_DIR / "japan_stagnation_hank_results.csv", index=False)

    if verbose:
        print("\n=== タイプ別 + 集計 CE 厚生 ===")
        for name, w in welfare_results.items():
            print(f"\n[{name}]")
            print(f"  Aggregate CE welfare: {w['ce_aggregate_pct']:+.2f}%")
            print(f"  Type-specific:")
            for _, r in w["type_ce"].iterrows():
                print(f"    {r['type']:25s}: {r['CE_pct']:+.2f}%")

        print(f"\n  図1 (消費): {p1}")
        print(f"  図2 (厚生): {p2}")
        print(f"  図3 (vs DSGE): {p3}")

    return {"results": scenarios_results, "welfare": welfare_results,
            "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="HANK-light モデル")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
