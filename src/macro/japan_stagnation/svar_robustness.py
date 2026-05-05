"""SVAR 頑健性検証：Cholesky 識別順序の入れ替えに対する結果の安定性.

既存の SVAR 結果（svar_household.py、cross_country_svar.py）の Cholesky 順序が
H6 の判定にどの程度影響するかを定量的に確認する.

Cholesky 識別順序の理論的意味:
    最も外生的（同期的に他変数に影響、自身は同期的に影響受けない）と仮定する変数を最初に置く.
    順序を入れ替えると、各変数が「同期に他にどれだけ影響するか」の仮定が変わる.
    H6 の核心（CA→GDP の有無）が順序に依存しないなら、結果は頑健.

実施する4つの順序:
    Order A（メイン）: GDP → CA/GDP → REER
        ・GDP は最も外生（実質経済が動かす）
    Order B: REER → GDP → CA/GDP
        ・為替が最も外生（金融市場で同期的に決まる）
    Order C: CA/GDP → GDP → REER
        ・対外フローが最も外生（H6 帰無に有利な順序）
    Order D: REER → CA/GDP → GDP
        ・GDP を最も内生に置く（H6 帰無に最も不利）

各順序で:
    - 直交化 IRF（CA→GDP, GDP→CA, REER→GDP）
    - 分散分解 24 期先

頑健性の判定:
    H6 主張（CA→GDP の効果が小さい）が全 4 順序で同様なら頑健.

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - svar_ordering_robustness_ca_to_gdp.png
        - svar_ordering_robustness_fevd.png
    data/processed/
        - japan_stagnation_svar_ordering.csv
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.tsa.api import VAR

from src.collectors.japan_external_collector import load as load_japan_external
from src.macro.japan_stagnation.stylized_facts import FIG_DIR, PROCESSED_DIR

warnings.filterwarnings("ignore")


VAR_LABELS = {
    "g_gdp":    "Δlog(Real GDP)",
    "d_ca_gdp": "Δ(CA/GDP)",
    "g_reer":   "Δlog(REER)",
}

ORDERINGS: dict[str, list[str]] = {
    "A: GDP→CA→REER (main)":  ["g_gdp", "d_ca_gdp", "g_reer"],
    "B: REER→GDP→CA":         ["g_reer", "g_gdp", "d_ca_gdp"],
    "C: CA→GDP→REER":         ["d_ca_gdp", "g_gdp", "g_reer"],
    "D: REER→CA→GDP":         ["g_reer", "d_ca_gdp", "g_gdp"],
}


def prepare_data() -> pd.DataFrame:
    raw = load_japan_external()
    if raw.empty:
        raise FileNotFoundError("data/raw/japan_external_quarterly.csv が見つかりません")
    df = raw.copy()
    df["g_gdp"] = np.log(df["real_gdp"]).diff() * 100
    df["g_reer"] = np.log(df["reer"]).diff() * 100
    df["d_ca_gdp"] = df["current_account"].diff()
    return df[["g_gdp", "d_ca_gdp", "g_reer"]].dropna()


def fit_var_with_ordering(df: pd.DataFrame, order: list[str]):
    sub = df[order].copy()
    model = VAR(sub)
    sel = model.select_order(maxlags=8)
    p = sel.bic
    if p is None or p < 1:
        p = 1
    return model.fit(p), p


def compute_irf_table(fit, periods: int = 16, ortho: bool = True) -> pd.DataFrame:
    irf_obj = fit.irf(periods)
    irfs = irf_obj.orth_irfs if ortho else irf_obj.irfs
    names = fit.names
    rows = []
    for i, imp in enumerate(names):
        for j, resp in enumerate(names):
            for h in range(periods + 1):
                rows.append({
                    "shock":    imp,
                    "response": resp,
                    "horizon":  h,
                    "irf":      irfs[h, j, i],
                })
    return pd.DataFrame(rows)


def compute_fevd_table(fit, periods: int = 16) -> pd.DataFrame:
    fevd = fit.fevd(periods)
    decomp = fevd.decomp  # (n_vars, periods, n_vars)
    names = fit.names
    rows = []
    for j, resp in enumerate(names):
        for h in range(periods):
            for i, imp in enumerate(names):
                rows.append({
                    "response": resp,
                    "horizon":  h + 1,
                    "shock":    imp,
                    "share":    decomp[j, h, i] * 100,
                })
    return pd.DataFrame(rows)


# ── プロット: CA→GDP の IRF を 4 順序で比較 ─────────────────────────────────

def plot_ordering_irf(all_irfs: dict, focus_pair: tuple[str, str]) -> Path:
    imp, resp = focus_pair
    fig, ax = plt.subplots(figsize=(11, 6))

    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    for (label, df), color in zip(all_irfs.items(), colors):
        sub = df[(df["shock"] == imp) & (df["response"] == resp)]
        if sub.empty:
            continue
        ax.plot(sub["horizon"], sub["irf"], label=label,
                color=color, linewidth=2.0, alpha=0.85,
                marker="o", markersize=4)

    ax.axhline(0, color="black", linewidth=0.6, linestyle=":")
    ax.set_title(f"IRF Robustness: {VAR_LABELS[imp]} shock → {VAR_LABELS[resp]} response\n"
                  f"(4 Cholesky orderings)",
                  fontsize=11, fontweight="bold")
    ax.set_xlabel("Quarters")
    ax.set_ylabel("Response (orthogonalized)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=9, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / f"svar_ordering_robustness_{imp}_to_{resp}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── FEVD の 24 期先寄与（CA から GDP へ）の比較 ─────────────────────────────

def plot_ordering_fevd(all_fevds: dict) -> Path:
    """各順序で「GDP の予測誤差分散に CA ショックがどれだけ寄与するか」を比較."""
    fig, ax = plt.subplots(figsize=(10, 5.5))

    horizons = []
    rows = []
    for label, df in all_fevds.items():
        sub = df[(df["response"] == "g_gdp") & (df["shock"] == "d_ca_gdp")]
        rows.append((label, sub["horizon"].values, sub["share"].values))

    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    for (label, h, s), color in zip(rows, colors):
        ax.plot(h, s, label=label, color=color, linewidth=2.0, alpha=0.85,
                marker="o", markersize=3)

    ax.set_title("FEVD Robustness: CA shock contribution to GDP variance\n"
                  "(small contribution = H6 supported)",
                  fontsize=11, fontweight="bold")
    ax.set_xlabel("Quarters ahead")
    ax.set_ylabel("Share of GDP variance from CA shock (%)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=9, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / "svar_ordering_robustness_fevd.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── メイン ────────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== SVAR 頑健性：Cholesky 順序の入れ替え ===")
        print(f"  4 順序を比較: {list(ORDERINGS.keys())}")

    df = prepare_data()
    if verbose:
        print(f"  サンプル: {len(df)} 期 ({df.index.min().date()} ~ {df.index.max().date()})")

    all_irfs = {}
    all_fevds = {}
    summary_rows = []

    for label, order in ORDERINGS.items():
        if verbose:
            print(f"\n--- {label} ---")
        fit, p = fit_var_with_ordering(df, order)
        if verbose:
            print(f"  Selected lag: {p}")
            print(f"  Log-Likelihood: {fit.llf:.2f}")

        irfs = compute_irf_table(fit, periods=16)
        fevds = compute_fevd_table(fit, periods=16)
        all_irfs[label] = irfs
        all_fevds[label] = fevds

        # H6 関連の主要数値を抽出
        ca_to_gdp_h4 = irfs[(irfs["shock"] == "d_ca_gdp") &
                              (irfs["response"] == "g_gdp") &
                              (irfs["horizon"] == 4)]["irf"].iloc[0]
        gdp_to_ca_h4 = irfs[(irfs["shock"] == "g_gdp") &
                              (irfs["response"] == "d_ca_gdp") &
                              (irfs["horizon"] == 4)]["irf"].iloc[0]
        ca_to_gdp_share_24 = fevds[(fevds["response"] == "g_gdp") &
                                      (fevds["shock"] == "d_ca_gdp") &
                                      (fevds["horizon"] == 16)]["share"].iloc[0]
        gdp_to_ca_share_24 = fevds[(fevds["response"] == "d_ca_gdp") &
                                      (fevds["shock"] == "g_gdp") &
                                      (fevds["horizon"] == 16)]["share"].iloc[0]

        summary_rows.append({
            "ordering":              label,
            "lag":                   p,
            "irf_ca_to_gdp_h4":      ca_to_gdp_h4,
            "irf_gdp_to_ca_h4":      gdp_to_ca_h4,
            "fevd_ca_to_gdp_pct":    ca_to_gdp_share_24,
            "fevd_gdp_to_ca_pct":    gdp_to_ca_share_24,
        })

    summary = pd.DataFrame(summary_rows)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = PROCESSED_DIR / "japan_stagnation_svar_ordering.csv"
    summary.to_csv(out_csv, index=False)

    # 主要図
    p1 = plot_ordering_irf(all_irfs, ("d_ca_gdp", "g_gdp"))
    p2 = plot_ordering_irf(all_irfs, ("g_gdp", "d_ca_gdp"))
    p3 = plot_ordering_fevd(all_fevds)

    if verbose:
        print("\n=== H6 関連数値の頑健性サマリー ===")
        print("  IRF h=4: CA→GDP（H6 帰無：小さければ支持）, GDP→CA（H6 対立：正なら支持）")
        print("  FEVD h=16: CA shock の GDP 分散寄与率（小さければ H6 支持）")
        print()
        print(summary.round(4).to_string(index=False))

        print(f"\n  図1（CA→GDP IRF）: {p1}")
        print(f"  図2（GDP→CA IRF）: {p2}")
        print(f"  図3（FEVD CA→GDP 寄与）: {p3}")
        print(f"  サマリー: {out_csv}")

    return {"summary": summary, "irfs": all_irfs, "fevds": all_fevds}


def main() -> None:
    parser = argparse.ArgumentParser(description="SVAR 順序頑健性")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
