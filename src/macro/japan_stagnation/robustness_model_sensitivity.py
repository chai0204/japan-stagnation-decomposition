"""ロバストネス R-2：形式モデルパラメータ感度分析.

検証項目:
    1. 資本シェア α ∈ [0.25, 0.40] での結果安定性
    2. ICT 弾力性 γ ∈ [0.30, 0.70] での結果
    3. 改革収束速度 ρ_ICT, ρ_omega ∈ [0.05, 0.30] での経路
    4. CES の σ（リスク回避度）∈ [0.5, 2.0] での厚生

各パラメータを変動させ、政策含意（GDP 増加、賃金増加、厚生）が
頑健に成立するかを確認.

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - robustness_model_alpha.png
        - robustness_model_gamma.png
        - robustness_model_rho.png
    data/processed/
        - japan_stagnation_model_sensitivity.csv
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.macro.japan_stagnation.formal_model_extended import (
    ExtendedParams, solve_economy, consumption_equivalent_welfare,
    simulate_transition,
)
from src.macro.japan_stagnation.stylized_facts import FIG_DIR, PROCESSED_DIR


def sensitivity_alpha() -> pd.DataFrame:
    """資本シェア α への感度."""
    rows = []
    for alpha in np.linspace(0.25, 0.40, 7):
        base = ExtendedParams(alpha=alpha)
        # ICT + Wage 統合改革
        target = replace(base, k_ICT=2.67, omega=0.96)
        Y_base = solve_economy(base)["Y_total"]
        result = solve_economy(target)
        welfare = consumption_equivalent_welfare(base, target) * 100
        rows.append({
            "alpha":          alpha,
            "Y_index":        result["Y_total"] / Y_base * 100,
            "w_index":        result["w_avg"] / solve_economy(base)["w_avg"] * 100,
            "labor_share":    result["labor_share"],
            "welfare_pct":    welfare,
        })
    return pd.DataFrame(rows)


def sensitivity_gamma() -> pd.DataFrame:
    """ICT 弾力性 γ への感度."""
    rows = []
    for gamma in np.linspace(0.30, 0.70, 9):
        base = ExtendedParams(gamma=gamma)
        target = replace(base, k_ICT=2.67, omega=0.96)
        Y_base = solve_economy(base)["Y_total"]
        result = solve_economy(target)
        welfare = consumption_equivalent_welfare(base, target) * 100
        rows.append({
            "gamma":         gamma,
            "Y_index":       result["Y_total"] / Y_base * 100,
            "w_index":       result["w_avg"] / solve_economy(base)["w_avg"] * 100,
            "welfare_pct":   welfare,
        })
    return pd.DataFrame(rows)


def sensitivity_rho() -> pd.DataFrame:
    """改革速度 ρ への感度（10 年後の状態）."""
    rows = []
    for rho_ict in np.linspace(0.05, 0.25, 5):
        for rho_om in np.linspace(0.05, 0.30, 6):
            base = ExtendedParams()
            target = replace(base, k_ICT=2.67, omega=0.96)
            path = simulate_transition(
                base, target, rho_ICT=rho_ict, rho_omega=rho_om, T=30,
            )
            row_10 = path[path["year"] == 10].iloc[0]
            row_30 = path[path["year"] == 30].iloc[0]
            rows.append({
                "rho_ict":         rho_ict,
                "rho_omega":       rho_om,
                "Y_at_year10":     row_10["Y_index"],
                "Y_at_year30":     row_30["Y_index"],
                "welfare_at_10":   row_10["welfare_pct"],
                "welfare_at_30":   row_30["welfare_pct"],
            })
    return pd.DataFrame(rows)


# ── プロット ─────────────────────────────────────────────────────────────────

def plot_alpha(df: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    axes[0].plot(df["alpha"], df["Y_index"], "o-", color="#1f77b4", linewidth=2)
    axes[0].plot(df["alpha"], df["w_index"], "s-", color="#ff7f0e", linewidth=2,
                  label="Wage")
    axes[0].plot(df["alpha"], df["Y_index"], "o-", color="#1f77b4", linewidth=2,
                  label="GDP")
    axes[0].axvline(0.33, color="red", linewidth=0.8, linestyle="--",
                     alpha=0.6, label="Standard α=0.33")
    axes[0].set_xlabel("Capital share α")
    axes[0].set_ylabel("Index (Japan baseline = 100)")
    axes[0].set_title("Sensitivity to α: GDP and Wage Gain", fontsize=10, fontweight="bold")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend(loc="best")

    axes[1].plot(df["alpha"], df["welfare_pct"], "D-", color="#2ca02c", linewidth=2)
    axes[1].axvline(0.33, color="red", linewidth=0.8, linestyle="--", alpha=0.6)
    axes[1].set_xlabel("Capital share α")
    axes[1].set_ylabel("Welfare gain (CE %)")
    axes[1].set_title("Sensitivity to α: Welfare", fontsize=10, fontweight="bold")
    axes[1].grid(True, alpha=0.3)

    fig.suptitle("Robustness R-2a: Capital share α sensitivity",
                 fontsize=11, fontweight="bold", y=1.02)
    fig.tight_layout()
    out = FIG_DIR / "robustness_model_alpha.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_gamma(df: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(df["gamma"], df["Y_index"], "o-", color="#1f77b4", linewidth=2,
            label="GDP")
    ax.plot(df["gamma"], df["w_index"], "s-", color="#ff7f0e", linewidth=2,
            label="Wage")
    ax.plot(df["gamma"], df["welfare_pct"] + 100, "D-", color="#2ca02c", linewidth=2,
            label="Welfare (CE % + 100)")
    ax.axvline(0.50, color="red", linewidth=0.8, linestyle="--",
                alpha=0.6, label="Baseline γ=0.5")
    ax.set_xlabel("ICT productivity elasticity γ")
    ax.set_ylabel("Index (Japan baseline = 100)")
    ax.set_title("Sensitivity to ICT elasticity γ\n"
                  "(higher γ = more responsive to ICT investment)",
                  fontsize=11, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best")
    fig.tight_layout()

    out = FIG_DIR / "robustness_model_gamma.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_rho(df: pd.DataFrame) -> Path:
    pivot10 = df.pivot(index="rho_ict", columns="rho_omega", values="Y_at_year10")

    fig, axes = plt.subplots(1, 2, figsize=(12, 5))
    im = axes[0].imshow(pivot10.values, cmap="RdYlGn", aspect="auto",
                          origin="lower")
    axes[0].set_xticks(range(len(pivot10.columns)))
    axes[0].set_xticklabels([f"{x:.2f}" for x in pivot10.columns], fontsize=9)
    axes[0].set_yticks(range(len(pivot10.index)))
    axes[0].set_yticklabels([f"{x:.2f}" for x in pivot10.index], fontsize=9)
    axes[0].set_xlabel("ρ_omega (wage reform speed)")
    axes[0].set_ylabel("ρ_ict (ICT reform speed)")
    axes[0].set_title("GDP at year 10 (Japan baseline = 100)",
                       fontsize=10, fontweight="bold")
    plt.colorbar(im, ax=axes[0])

    for i in range(pivot10.shape[0]):
        for j in range(pivot10.shape[1]):
            axes[0].text(j, i, f"{pivot10.iloc[i, j]:.0f}",
                          ha="center", va="center", fontsize=8)

    pivot30 = df.pivot(index="rho_ict", columns="rho_omega", values="Y_at_year30")
    im2 = axes[1].imshow(pivot30.values, cmap="RdYlGn", aspect="auto",
                           origin="lower")
    axes[1].set_xticks(range(len(pivot30.columns)))
    axes[1].set_xticklabels([f"{x:.2f}" for x in pivot30.columns], fontsize=9)
    axes[1].set_yticks(range(len(pivot30.index)))
    axes[1].set_yticklabels([f"{x:.2f}" for x in pivot30.index], fontsize=9)
    axes[1].set_xlabel("ρ_omega")
    axes[1].set_ylabel("ρ_ict")
    axes[1].set_title("GDP at year 30 (long-run)",
                       fontsize=10, fontweight="bold")
    plt.colorbar(im2, ax=axes[1])

    for i in range(pivot30.shape[0]):
        for j in range(pivot30.shape[1]):
            axes[1].text(j, i, f"{pivot30.iloc[i, j]:.0f}",
                          ha="center", va="center", fontsize=8)

    fig.suptitle("Robustness R-2c: Reform speed sensitivity (ρ_ict × ρ_omega)",
                 fontsize=11, fontweight="bold", y=1.02)
    fig.tight_layout()
    out = FIG_DIR / "robustness_model_rho.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── メイン ────────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== R-2: Formal Model Sensitivity ===")

    df_a = sensitivity_alpha()
    df_g = sensitivity_gamma()
    df_r = sensitivity_rho()

    if verbose:
        print("\n--- α 感度（資本シェア） ---")
        print(df_a.round(2).to_string(index=False))

        print("\n--- γ 感度（ICT 弾力性） ---")
        print(df_g.round(2).to_string(index=False))

        print("\n--- ρ 感度（改革速度の組み合わせ） ---")
        # 主要点だけ
        sub = df_r[df_r["rho_ict"].isin([0.05, 0.10, 0.20])]
        sub = sub[sub["rho_omega"].isin([0.10, 0.20, 0.30])]
        print(sub.round(2).to_string(index=False))

    p1 = plot_alpha(df_a)
    p2 = plot_gamma(df_g)
    p3 = plot_rho(df_r)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    df_a.to_csv(PROCESSED_DIR / "japan_stagnation_sensitivity_alpha.csv", index=False)
    df_g.to_csv(PROCESSED_DIR / "japan_stagnation_sensitivity_gamma.csv", index=False)
    df_r.to_csv(PROCESSED_DIR / "japan_stagnation_sensitivity_rho.csv", index=False)

    if verbose:
        print(f"\n  図1 (α): {p1}")
        print(f"  図2 (γ): {p2}")
        print(f"  図3 (ρ): {p3}")

    return {"alpha": df_a, "gamma": df_g, "rho": df_r}


def main() -> None:
    parser = argparse.ArgumentParser(description="形式モデル感度分析")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
