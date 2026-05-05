"""形式モデル：2 部門小国開放経済の比較静学.

本研究の実証発見（H1, H6, H8, H9）を統合的に生成する最小モデル.

経済構造:
    - 2 部門：T（貿易財/工業）・N（非貿易財/サービス業）
    - 各部門 Cobb-Douglas 生産関数: Y_i = A_i × L_i^(1-α) × K_i^α
    - 賃金設定: w_i = ω × MPL_i（ω = 賃金分配パラメータ）
    - 家計：消費 + 国内資産 + 外国資産（対外シフト = r_d < r_f の結果）

外生変数:
    A_T : 貿易財生産性
    A_N : 非貿易財生産性
    ω   : 賃金分配パラメータ（0 < ω ≤ 1）
    L_T, L_N : 各部門雇用
    K_T, K_N : 各部門資本

内生変数（本モデルでは部門配分は所与とした簡略版）:
    Y, w, 労働分配率, 対外資産比率（r_d 経由）

カリブレーション:
    日本の実データに合わせる
        α = 0.33（標準値）
        per-hour 生産性比から A_T_jp/A_T_deu, A_N_jp/A_N_deu
        労働分配率から ω

シナリオ:
    1. Baseline (Japan as is)
    2. + 工業生産性を独並みに（A_T_jp → A_T_deu）
    3. + サービス業生産性を独並みに（A_N_jp → A_N_deu）
    4. + 賃金分配を独並みに（ω_jp → ω_deu）
    5. すべて同時実現

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - formal_model_scenarios.png
        - formal_model_capital_outflow.png
    data/processed/
        - japan_stagnation_formal_model.csv
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.macro.japan_stagnation.stylized_facts import FIG_DIR, PROCESSED_DIR


# ── パラメータ定義 ────────────────────────────────────────────────────────────

@dataclass
class ModelParams:
    """モデルパラメータ（カリブレーション値）."""
    # 標準パラメータ
    alpha: float = 0.33  # 資本シェア（Cobb-Douglas）

    # 部門別生産性（標準化、比較用）
    A_T: float = 0.81   # 貿易財/工業（per-hour, Japan/Germany 比 ≈ 0.81）
    A_N: float = 0.685  # 非貿易財/サービス（per-hour, Japan/Germany 比 ≈ 0.685）

    # 賃金分配パラメータ
    omega: float = 0.838  # 日本（labor share 0.561 / (1-α) = 0.838）

    # 部門配分（観測値）
    L_T_share: float = 0.27  # 工業雇用シェア
    L_N_share: float = 0.69  # サービス業雇用シェア
    L_A_share: float = 0.04  # 農業（簡略化のため無視）

    # 資本ストック（K/L 比、簡略化のため部門間同一とする）
    KL_ratio: float = 1.0  # 標準化（K/L = 1）

    # 国際金融
    r_f: float = 0.04  # 外国資産期待リターン
    foreign_share_base: float = 0.10  # baseline 対外資産比率
    elasticity_foreign: float = 5.0   # r_d - r_f に対する弾力性

    # 労働力
    L_total: float = 1.0  # 標準化


# ── モデル方程式 ──────────────────────────────────────────────────────────────

def production(A: float, L: float, K: float, alpha: float) -> float:
    """Cobb-Douglas 生産関数."""
    return A * (L ** (1 - alpha)) * (K ** alpha)


def MPL(A: float, L: float, K: float, alpha: float) -> float:
    """労働の限界生産力."""
    return (1 - alpha) * A * (K / L) ** alpha


def MPK(A: float, L: float, K: float, alpha: float) -> float:
    """資本の限界生産力."""
    return alpha * A * (L / K) ** (1 - alpha)


def solve_economy(p: ModelParams) -> dict:
    """与えられたパラメータで経済を解く."""
    # 部門別労働
    L_T = p.L_total * p.L_T_share
    L_N = p.L_total * p.L_N_share
    # 部門別資本
    K_T = L_T * p.KL_ratio
    K_N = L_N * p.KL_ratio
    # 部門別 GDP
    Y_T = production(p.A_T, L_T, K_T, p.alpha)
    Y_N = production(p.A_N, L_N, K_N, p.alpha)
    Y_total = Y_T + Y_N
    # 限界生産力
    mpl_T = MPL(p.A_T, L_T, K_T, p.alpha)
    mpl_N = MPL(p.A_N, L_N, K_N, p.alpha)
    mpk_T = MPK(p.A_T, L_T, K_T, p.alpha)
    mpk_N = MPK(p.A_N, L_N, K_N, p.alpha)
    # 集計賃金（労働者数加重平均）
    w_T = p.omega * mpl_T
    w_N = p.omega * mpl_N
    w_avg = (w_T * L_T + w_N * L_N) / (L_T + L_N)
    # 賃金総額
    wage_bill = w_T * L_T + w_N * L_N
    # 労働分配率
    labor_share = wage_bill / Y_total
    # 国内資本リターン（加重）
    K_total = K_T + K_N
    capital_income = mpk_T * K_T + mpk_N * K_N
    r_d = capital_income / K_total
    # 対外資産シフト：r_d < r_f なら家計が外貨に流れる
    return_diff = p.r_f - r_d
    foreign_share = p.foreign_share_base + p.elasticity_foreign * max(0, return_diff)
    foreign_share = min(foreign_share, 0.5)  # 上限

    return {
        "Y_T":          Y_T,
        "Y_N":          Y_N,
        "Y_total":      Y_total,
        "w_T":          w_T,
        "w_N":          w_N,
        "w_avg":        w_avg,
        "wage_bill":    wage_bill,
        "labor_share":  labor_share,
        "r_d":          r_d,
        "r_f":          p.r_f,
        "return_diff":  return_diff,
        "foreign_share": foreign_share,
    }


# ── カリブレーション ──────────────────────────────────────────────────────────

# 観測値からカリブレートしたパラメータ（per-hour ベース）
# 日本は per-hour で工業 76.7、サービス業 60.8（USD 千ドル）
# ドイツは per-hour で工業 95.5、サービス業 88.7
# 日本/ドイツ比: 工業 0.803、サービス 0.686

JAPAN_PARAMS = ModelParams(
    A_T=0.803,
    A_N=0.686,
    omega=0.838,  # labor share 0.561 / (1-α) = 0.838
    L_T_share=0.27,
    L_N_share=0.69,
    L_A_share=0.04,
)

GERMANY_PARAMS = ModelParams(
    A_T=1.000,
    A_N=1.000,
    omega=0.960,  # labor share 0.643 / (1-α) = 0.960
    L_T_share=0.30,
    L_N_share=0.66,
    L_A_share=0.04,
)


# ── シナリオ定義 ──────────────────────────────────────────────────────────────

def define_scenarios() -> dict[str, ModelParams]:
    base = JAPAN_PARAMS

    s1 = ModelParams(
        A_T=GERMANY_PARAMS.A_T, A_N=base.A_N, omega=base.omega,
        L_T_share=base.L_T_share, L_N_share=base.L_N_share,
        L_A_share=base.L_A_share,
    )
    s2 = ModelParams(
        A_T=base.A_T, A_N=GERMANY_PARAMS.A_N, omega=base.omega,
        L_T_share=base.L_T_share, L_N_share=base.L_N_share,
        L_A_share=base.L_A_share,
    )
    s3 = ModelParams(
        A_T=base.A_T, A_N=base.A_N, omega=GERMANY_PARAMS.omega,
        L_T_share=base.L_T_share, L_N_share=base.L_N_share,
        L_A_share=base.L_A_share,
    )
    s4 = ModelParams(
        A_T=GERMANY_PARAMS.A_T, A_N=GERMANY_PARAMS.A_N,
        omega=GERMANY_PARAMS.omega,
        L_T_share=base.L_T_share, L_N_share=base.L_N_share,
        L_A_share=base.L_A_share,
    )

    return {
        "Japan baseline":           base,
        "+Industry to Germany":     s1,
        "+Services to Germany":     s2,
        "+Labor share to Germany":  s3,
        "All three combined":       s4,
        "Germany reference":        GERMANY_PARAMS,
    }


# ── プロット ─────────────────────────────────────────────────────────────────

def plot_scenarios(results: dict) -> Path:
    fig, axes = plt.subplots(1, 3, figsize=(15, 5))

    labels = list(results.keys())
    base_y = results["Japan baseline"]["Y_total"]
    base_w = results["Japan baseline"]["w_avg"]

    # 図1: GDP（日本ベース対比）
    ax = axes[0]
    gdp_idx = [r["Y_total"] / base_y * 100 for r in results.values()]
    colors = ["#d62728"] + ["#1f77b4"] * 4 + ["#2ca02c"]
    ax.bar(range(len(labels)), gdp_idx, color=colors, alpha=0.85,
           edgecolor="black", linewidth=0.5)
    ax.axhline(100, color="black", linewidth=0.5, linestyle="--", alpha=0.5)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("GDP (Japan baseline = 100)")
    ax.set_title("GDP under each scenario", fontsize=10, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    for i, v in enumerate(gdp_idx):
        ax.text(i, v + 1, f"{v:.0f}", ha="center", fontsize=9)

    # 図2: 平均賃金（日本ベース対比）
    ax = axes[1]
    wage_idx = [r["w_avg"] / base_w * 100 for r in results.values()]
    ax.bar(range(len(labels)), wage_idx, color=colors, alpha=0.85,
           edgecolor="black", linewidth=0.5)
    ax.axhline(100, color="black", linewidth=0.5, linestyle="--", alpha=0.5)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("Wage (Japan baseline = 100)")
    ax.set_title("Average wage under each scenario", fontsize=10, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    for i, v in enumerate(wage_idx):
        ax.text(i, v + 2, f"{v:.0f}", ha="center", fontsize=9)

    # 図3: 労働分配率
    ax = axes[2]
    ls = [r["labor_share"] for r in results.values()]
    ax.bar(range(len(labels)), ls, color=colors, alpha=0.85,
           edgecolor="black", linewidth=0.5)
    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("Labor share")
    ax.set_title("Labor share", fontsize=10, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    for i, v in enumerate(ls):
        ax.text(i, v + 0.005, f"{v:.3f}", ha="center", fontsize=9)

    fig.suptitle("Formal Model: Counterfactual Scenarios for Japan",
                 fontsize=12, fontweight="bold", y=1.02)
    fig.tight_layout()

    out = FIG_DIR / "formal_model_scenarios.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_capital_outflow(results: dict) -> Path:
    """対外資産シフトと国内リターンの関係を可視化."""
    fig, ax = plt.subplots(figsize=(10, 5.5))

    labels = list(results.keys())
    r_d = [r["r_d"] for r in results.values()]
    r_f = results["Japan baseline"]["r_f"]
    foreign_shares = [r["foreign_share"] for r in results.values()]

    x = np.arange(len(labels))
    width = 0.4

    # 国内リターンと外国リターン
    ax.bar(x - width / 2, r_d, width, label="Domestic return r_d",
           color="#1f77b4", alpha=0.85)
    ax.bar(x + width / 2, [r_f] * len(labels), width, label=f"Foreign return r_f={r_f}",
           color="#ff7f0e", alpha=0.85)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=20, ha="right", fontsize=8)
    ax.set_ylabel("Return")
    ax.set_title("Domestic vs foreign returns under each scenario\n"
                  "(when r_d < r_f, households shift to foreign assets)",
                  fontsize=11, fontweight="bold")
    ax.legend(loc="best")
    ax.grid(True, axis="y", alpha=0.3)

    # 第2軸：対外資産シェア
    ax2 = ax.twinx()
    ax2.plot(x, foreign_shares, "o-", color="#d62728", linewidth=2,
             markersize=8, label="Foreign asset share")
    ax2.set_ylabel("Foreign asset share", color="#d62728")
    ax2.legend(loc="upper right")

    fig.tight_layout()
    out = FIG_DIR / "formal_model_capital_outflow.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── メイン ────────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== 形式モデル：2 部門小国開放経済 ===")
        print("\nカリブレーション:")
        print(f"  日本: A_T={JAPAN_PARAMS.A_T}, A_N={JAPAN_PARAMS.A_N}, ω={JAPAN_PARAMS.omega}")
        print(f"  独 :  A_T={GERMANY_PARAMS.A_T}, A_N={GERMANY_PARAMS.A_N}, ω={GERMANY_PARAMS.omega}")

    scenarios = define_scenarios()
    results = {name: solve_economy(p) for name, p in scenarios.items()}

    # 集計表
    rows = []
    base = results["Japan baseline"]
    for name, r in results.items():
        rows.append({
            "scenario":      name,
            "Y_total":       r["Y_total"],
            "Y_index":       r["Y_total"] / base["Y_total"] * 100,
            "w_avg":         r["w_avg"],
            "w_index":       r["w_avg"] / base["w_avg"] * 100,
            "labor_share":   r["labor_share"],
            "r_d":           r["r_d"],
            "return_diff":   r["return_diff"],
            "foreign_share": r["foreign_share"],
        })
    summary = pd.DataFrame(rows)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = PROCESSED_DIR / "japan_stagnation_formal_model.csv"
    summary.to_csv(out_csv, index=False)

    p1 = plot_scenarios(results)
    p2 = plot_capital_outflow(results)

    if verbose:
        print("\n=== シナリオ別結果 ===")
        cols_disp = ["scenario", "Y_index", "w_index", "labor_share", "r_d", "foreign_share"]
        print(summary[cols_disp].round(3).to_string(index=False))

        print(f"\n  図1: {p1}")
        print(f"  図2: {p2}")
        print(f"  サマリー: {out_csv}")

    return {"results": results, "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="形式モデル比較静学")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
