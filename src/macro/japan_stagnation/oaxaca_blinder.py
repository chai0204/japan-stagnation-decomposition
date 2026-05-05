"""Oaxaca-Blinder 分解：日独・日米成長率ギャップを「特性差」と「係数差」に分解.

Oaxaca (1973), Blinder (1973) の分解.

目的:
    g_JP - g_X = (X_JP - X_X) β̂_X + X_JP (β̂_JP - β̂_X)
                  ─────── ──────   ─────── ───────────
                  特性差（説明可能） + 係数差（説明できない／構造差）

    パネル回帰では Japan ダミーで「全部含めて」推定したのに対し、
    Oaxaca-Blinder は **どの予測子の差** が説明する/しないかを分解.

説明変数:
    - 高齢化率（aging_share）
    - 生産年齢人口成長率
    - 輸出/GDP 比
    - 対外 FDI フロー/GDP 比

被説明変数: 5 年差分の生産年齢 1人あたり GDP 成長率（年率%）

対比対象:
    - 日本 vs ドイツ
    - 日本 vs 米国
    - 日本 vs 韓国

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - oaxaca_blinder_decomposition.png
    data/processed/
        - japan_stagnation_oaxaca_blinder.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

from src.macro.japan_stagnation.panel_regression import build_long_panel
from src.macro.japan_stagnation.stylized_facts import (
    COUNTRY_LABEL, FIG_DIR, PROCESSED_DIR, load_panel,
)


PREDICTORS = [
    "aging_share",
    "wa_pop_growth",
    "exports_gdp_share",
    "fdi_outflows_gdp",
]
PRED_LABELS = {
    "aging_share":       "Aging share",
    "wa_pop_growth":     "Working-age pop growth",
    "exports_gdp_share": "Exports/GDP",
    "fdi_outflows_gdp":  "Outward FDI/GDP",
}


def fit_country_model(df_country: pd.DataFrame, dep: str = "g_gdp_per_wa") -> dict:
    """国別 OLS（年効果なし、5年差分パネルで）."""
    sub = df_country.dropna(subset=[dep] + PREDICTORS).copy()
    if len(sub) < 6:
        return {"beta": np.array([]), "X": pd.DataFrame(), "y": pd.Series(dtype=float)}
    X = sub[PREDICTORS].copy()
    X = sm.add_constant(X)
    y = sub[dep]
    fit = sm.OLS(y, X).fit()
    return {
        "beta":  fit.params,
        "X":     X,
        "y":     y,
        "fit":   fit,
        "Xbar":  X.mean(),
        "ybar":  y.mean(),
    }


def oaxaca_blinder(
    panel: pd.DataFrame,
    treated: str = "JPN",
    reference: str = "DEU",
    dep: str = "g_gdp_per_wa",
) -> dict:
    """日本 vs 参照国の Oaxaca-Blinder 分解."""
    long = build_long_panel(panel, interval=5, start=1990, end=2024)

    df_t = long[long["country"] == treated]
    df_r = long[long["country"] == reference]

    fit_t = fit_country_model(df_t, dep=dep)
    fit_r = fit_country_model(df_r, dep=dep)

    if fit_t["beta"].empty or fit_r["beta"].empty:
        return {}

    Xbar_t = fit_t["Xbar"]
    Xbar_r = fit_r["Xbar"]
    beta_t = fit_t["beta"]
    beta_r = fit_r["beta"]

    # 平均成長率
    ybar_t = fit_t["ybar"]
    ybar_r = fit_r["ybar"]
    total_gap = ybar_t - ybar_r

    # 特性差（reference の係数を使用）
    char_diff = (Xbar_t - Xbar_r) * beta_r
    # 係数差（treated の特性を使用）
    coef_diff = Xbar_t * (beta_t - beta_r)

    char_total = char_diff.drop("const", errors="ignore").sum()
    coef_total = coef_diff.sum()  # const も含む（切片の差）

    # 各予測子の貢献
    contributions = pd.DataFrame({
        "predictor":         PREDICTORS,
        "Xbar_treated":      Xbar_t.reindex(PREDICTORS).values,
        "Xbar_reference":    Xbar_r.reindex(PREDICTORS).values,
        "beta_reference":    beta_r.reindex(PREDICTORS).values,
        "char_contribution": char_diff.reindex(PREDICTORS).values,
        "coef_contribution": coef_diff.reindex(PREDICTORS).values,
    })

    return {
        "treated":           treated,
        "reference":         reference,
        "ybar_treated":      ybar_t,
        "ybar_reference":    ybar_r,
        "total_gap":         total_gap,
        "char_total":        char_total,
        "coef_total":        coef_total,
        "intercept_diff":    coef_diff.get("const", 0.0),
        "contributions":     contributions,
    }


# ── プロット ─────────────────────────────────────────────────────────────────

def plot_decomposition(results: list) -> Path:
    fig, axes = plt.subplots(1, len(results), figsize=(5.0 * len(results), 6),
                              sharey=True)
    if len(results) == 1:
        axes = [axes]

    for ax, res in zip(axes, results):
        contrib = res["contributions"].copy()
        labels = [PRED_LABELS.get(p, p) for p in contrib["predictor"]]

        x = np.arange(len(labels))
        width = 0.4

        ax.barh(x - width / 2, contrib["char_contribution"], width,
                color="#1f77b4", alpha=0.85, label="Characteristics gap")
        ax.barh(x + width / 2, contrib["coef_contribution"], width,
                color="#ff7f0e", alpha=0.85, label="Coefficient gap")

        ax.set_yticks(x)
        ax.set_yticklabels(labels)
        ax.axvline(0, color="black", linewidth=0.6)

        char_pct = (res["char_total"] / res["total_gap"] * 100
                    if res["total_gap"] != 0 else np.nan)
        ax.set_title(
            f"{COUNTRY_LABEL.get(res['treated'], res['treated'])}"
            f" vs {COUNTRY_LABEL.get(res['reference'], res['reference'])}\n"
            f"Total gap = {res['total_gap']:+.2f}%/yr | "
            f"Char share = {char_pct:.0f}%",
            fontsize=10, fontweight="bold",
        )
        ax.set_xlabel("Contribution (%/yr)")
        ax.grid(True, axis="x", alpha=0.3)
        ax.legend(loc="best", fontsize=8, framealpha=0.85)

    fig.suptitle(
        "Oaxaca-Blinder Decomposition of Per-WA GDP Growth Rate Gap",
        fontsize=12, fontweight="bold", y=1.02,
    )
    fig.tight_layout()
    out = FIG_DIR / "oaxaca_blinder_decomposition.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── メイン ────────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== Oaxaca-Blinder 分解 ===")

    panel = load_panel()

    references = ["DEU", "USA", "KOR"]
    results = []
    for ref in references:
        res = oaxaca_blinder(panel, treated="JPN", reference=ref)
        if res:
            results.append(res)
            if verbose:
                print(f"\n--- 日本 vs {COUNTRY_LABEL.get(ref, ref)} ---")
                print(f"  日本平均成長率:    {res['ybar_treated']:+.3f}%/年")
                print(f"  参照国平均成長率:  {res['ybar_reference']:+.3f}%/年")
                print(f"  総ギャップ:        {res['total_gap']:+.3f}%/年")
                print(f"  特性差合計:        {res['char_total']:+.3f}%/年（{res['char_total']/res['total_gap']*100 if res['total_gap'] else 0:.0f}% 説明）")
                print(f"  係数差合計:        {res['coef_total']:+.3f}%/年（残り）")
                print(f"\n  予測子別貢献:")
                print(res["contributions"].round(4).to_string(index=False))

    p1 = plot_decomposition(results)

    # 結果保存
    summary_rows = []
    for res in results:
        summary_rows.append({
            "reference":       res["reference"],
            "ybar_treated":    res["ybar_treated"],
            "ybar_reference":  res["ybar_reference"],
            "total_gap":       res["total_gap"],
            "char_total":      res["char_total"],
            "coef_total":      res["coef_total"],
        })
    summary = pd.DataFrame(summary_rows)
    out_csv = PROCESSED_DIR / "japan_stagnation_oaxaca_blinder.csv"
    summary.to_csv(out_csv, index=False)

    # 詳細
    detail_rows = []
    for res in results:
        for _, row in res["contributions"].iterrows():
            detail_rows.append({
                "reference":         res["reference"],
                **row.to_dict(),
            })
    detail = pd.DataFrame(detail_rows)
    detail_path = PROCESSED_DIR / "japan_stagnation_oaxaca_blinder_detail.csv"
    detail.to_csv(detail_path, index=False)

    if verbose:
        print(f"\n  図: {p1}")
        print(f"  サマリー: {out_csv}")
        print(f"  詳細: {detail_path}")

    return {"results": results}


def main() -> None:
    parser = argparse.ArgumentParser(description="Oaxaca-Blinder 分解")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
