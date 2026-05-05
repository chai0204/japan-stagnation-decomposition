"""クロスカントリー SVAR：G7 + 韓国の各国で同じ3変数 SVAR を推定し IRF を比較する.

目的:
    日本の SVAR で観察された「GDP→CA、CA↛GDP」のパターンが、
    日本固有か G7 共通かを識別する.
    日本固有なら H6 は強い証拠、G7 共通なら経済学的一般則.

モデル（共通仕様、四半期）:
    y = (Δlog Real GDP, Δ(CA/GDP), Δlog REER)'
    Cholesky 順序: GDP → CA/GDP → REER（メイン）

検証:
    - 各国 Granger 因果検定（CA→GDP、GDP→CA）
    - インパルス応答関数（直交化、12 期）
    - 「日本ダミー比較」: 日本の効果量と他国の分布を対比

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - cross_country_granger_heatmap.png
        - cross_country_irf_ca_to_gdp.png
        - cross_country_japan_anomaly.png
    data/processed/
        - japan_stagnation_cross_country_svar.csv
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import adfuller, grangercausalitytests

from src.collectors.g7_external_collector import COUNTRIES_SERIES, load_country
from src.macro.japan_stagnation.stylized_facts import (
    COLOR, COUNTRY_LABEL, FIG_DIR, PROCESSED_DIR,
)

warnings.filterwarnings("ignore")

VAR_NAMES = ["g_gdp", "d_ca_gdp", "g_reer"]
VAR_LABELS = {
    "g_gdp":    "Δlog(Real GDP)",
    "d_ca_gdp": "Δ(CA/GDP)",
    "g_reer":   "Δlog(REER)",
}


# ── データ準備 ────────────────────────────────────────────────────────────────

def prepare_country_data(country: str) -> pd.DataFrame:
    raw = load_country(country)
    if raw.empty:
        return pd.DataFrame()

    df = raw.copy()
    if "real_gdp" in df.columns:
        df["g_gdp"] = np.log(df["real_gdp"]).diff() * 100
    if "current_account" in df.columns:
        df["d_ca_gdp"] = df["current_account"].diff()
    if "reer" in df.columns:
        df["g_reer"] = np.log(df["reer"]).diff() * 100

    cols = [c for c in VAR_NAMES if c in df.columns]
    if len(cols) < 3:
        return pd.DataFrame()
    return df[cols].dropna()


# ── Granger 因果テスト ────────────────────────────────────────────────────────

def granger_pair(df: pd.DataFrame, x: str, y: str, max_lag: int = 4) -> dict:
    """Y → X (Y is X's predictor)."""
    sub = df[[x, y]].dropna()
    if len(sub) < max_lag + 5:
        return {"min_p": np.nan, "best_lag": np.nan}
    try:
        res = grangercausalitytests(sub, maxlag=max_lag, verbose=False)
        p_values = {l: res[l][0]["ssr_ftest"][1] for l in res}
        return {"min_p": min(p_values.values()),
                "best_lag": min(p_values, key=p_values.get)}
    except Exception:
        return {"min_p": np.nan, "best_lag": np.nan}


# ── SVAR 推定 ────────────────────────────────────────────────────────────────

def fit_country_var(df: pd.DataFrame, max_lag: int = 4):
    """国別 VAR フィット、IRF・Granger 抽出."""
    if len(df) < 20:
        return None
    try:
        model = VAR(df)
        sel = model.select_order(maxlags=max_lag)
        p = sel.bic
        if p is None or p < 1:
            p = 1
        fit = model.fit(p)
        return fit
    except Exception:
        return None


def country_irf(fit, periods: int = 12, ortho: bool = True) -> dict:
    """国別 IRF（点推定のみ、ブートストラップなし、軽量版）."""
    if fit is None:
        return {}
    irf_obj = fit.irf(periods)
    irfs = irf_obj.orth_irfs if ortho else irf_obj.irfs

    out = {}
    names = fit.names
    for i, imp in enumerate(names):
        for j, resp in enumerate(names):
            out[(imp, resp)] = irfs[:, j, i]
    return out


# ── 全国分析 ──────────────────────────────────────────────────────────────────

def run_all_countries(verbose: bool = True) -> dict:
    countries = list(COUNTRIES_SERIES)
    results = {}
    granger_records = []

    for c in countries:
        df = prepare_country_data(c)
        if df.empty or len(df) < 30:
            if verbose:
                print(f"  [{c}] スキップ（データ不足: {len(df)} 期）")
            continue

        if verbose:
            print(f"  [{c}] {len(df)} 期 ({df.index.min().date()} ~ {df.index.max().date()})")

        fit = fit_country_var(df, max_lag=4)
        if fit is None:
            continue

        irfs = country_irf(fit, periods=12)

        # Granger 因果（主要4方向）
        for src, tgt in [
            ("g_gdp",    "d_ca_gdp"),
            ("d_ca_gdp", "g_gdp"),
            ("g_reer",   "g_gdp"),
            ("g_gdp",    "g_reer"),
        ]:
            res = granger_pair(df, x=tgt, y=src, max_lag=4)
            granger_records.append({
                "country":  c,
                "from":     src,
                "to":       tgt,
                "best_lag": res["best_lag"],
                "min_p":    res["min_p"],
                "sig_5pct": res["min_p"] < 0.05 if not np.isnan(res["min_p"]) else None,
            })

        # IRF: CA→GDP、GDP→CA、REER→GDP の点推定
        results[c] = {
            "fit":         fit,
            "n_obs":       int(fit.nobs),
            "lag":         fit.k_ar,
            "irf_ca_to_gdp":   irfs.get(("d_ca_gdp", "g_gdp"), np.array([])),
            "irf_gdp_to_ca":   irfs.get(("g_gdp", "d_ca_gdp"), np.array([])),
            "irf_reer_to_gdp": irfs.get(("g_reer", "g_gdp"), np.array([])),
        }

    granger_df = pd.DataFrame(granger_records)
    return {"results": results, "granger": granger_df}


# ── Granger ヒートマップ（国別） ──────────────────────────────────────────────

def plot_granger_heatmap(granger: pd.DataFrame) -> Path:
    pivot = granger.pivot_table(
        index="country",
        columns=["from", "to"],
        values="min_p",
    )
    # 国の順番（日本を最初に）
    country_order = ["JPN", "USA", "DEU", "FRA", "GBR", "ITA", "CAN", "KOR"]
    pivot = pivot.reindex(country_order)

    # カラム順
    desired_cols = [
        ("d_ca_gdp", "g_gdp"),
        ("g_gdp",    "d_ca_gdp"),
        ("g_reer",   "g_gdp"),
        ("g_gdp",    "g_reer"),
    ]
    pivot = pivot.reindex(columns=desired_cols)

    col_labels = [
        "CA → GDP\n(H6 null)",
        "GDP → CA\n(H6 alt)",
        "REER → GDP",
        "GDP → REER",
    ]

    fig, ax = plt.subplots(figsize=(8, 6))
    im = ax.imshow(pivot.values, cmap="RdYlGn_r", vmin=0, vmax=0.15, aspect="auto")
    ax.set_xticks(range(len(col_labels)))
    ax.set_yticks(range(len(country_order)))
    ax.set_xticklabels(col_labels, fontsize=10)
    ax.set_yticklabels([COUNTRY_LABEL.get(c, c) for c in country_order])
    ax.set_title("Cross-Country Granger Causality: minimum p-value (lags 1-4)",
                 fontsize=11, fontweight="bold")

    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            v = pivot.iloc[i, j]
            if pd.isna(v):
                ax.text(j, i, "—", ha="center", va="center", color="gray", fontsize=9)
                continue
            color = "white" if v < 0.05 else "black"
            ax.text(j, i, f"{v:.3f}", ha="center", va="center",
                    color=color, fontsize=9, fontweight="bold" if v < 0.05 else "normal")

    fig.colorbar(im, ax=ax, label="p-value")
    fig.tight_layout()
    out = FIG_DIR / "cross_country_granger_heatmap.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── IRF: CA→GDP の各国比較 ────────────────────────────────────────────────────

def plot_irf_ca_to_gdp(results: dict) -> Path:
    fig, ax = plt.subplots(figsize=(11, 6))
    horizon = np.arange(0, 13)

    for c, res in results.items():
        irf = res.get("irf_ca_to_gdp", np.array([]))
        if len(irf) == 0:
            continue
        lw = 2.5 if c == "JPN" else 1.2
        alpha = 1.0 if c == "JPN" else 0.65
        ls = "-" if c == "JPN" else "--"
        ax.plot(horizon, irf,
                label=COUNTRY_LABEL.get(c, c),
                color=COLOR.get(c, "gray"),
                linewidth=lw, alpha=alpha, linestyle=ls)

    ax.axhline(0, color="black", linewidth=0.5, linestyle=":")
    ax.set_xlabel("Quarters")
    ax.set_ylabel("Response of Δlog(GDP) to 1 SD shock in Δ(CA/GDP)")
    ax.set_title("IRF: CA/GDP shock → GDP response (Japan vs G7+Korea)",
                 fontsize=11, fontweight="bold")
    ax.grid(True, alpha=0.3)
    ax.legend(ncol=4, loc="upper right", fontsize=9, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / "cross_country_irf_ca_to_gdp.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── 「日本の特異性」散布図 ────────────────────────────────────────────────────

def plot_japan_anomaly(granger: pd.DataFrame) -> Path:
    """各国の (GDP→CA p-value, CA→GDP p-value) 散布図."""
    pivot = granger.pivot_table(
        index="country",
        columns=["from", "to"],
        values="min_p",
    )
    pivot = pivot[[("g_gdp", "d_ca_gdp"), ("d_ca_gdp", "g_gdp")]]
    pivot.columns = ["gdp_to_ca", "ca_to_gdp"]
    pivot = pivot.dropna()

    fig, ax = plt.subplots(figsize=(9, 7))
    for c in pivot.index:
        x = pivot.loc[c, "gdp_to_ca"]
        y = pivot.loc[c, "ca_to_gdp"]
        col = COLOR.get(c, "gray")
        size = 280 if c == "JPN" else 130
        ax.scatter(x, y, color=col, s=size, alpha=0.85,
                   edgecolor="black" if c == "JPN" else "none",
                   linewidth=2.5 if c == "JPN" else 0)
        ax.annotate(COUNTRY_LABEL.get(c, c), (x, y),
                    xytext=(8, 5), textcoords="offset points",
                    fontsize=11 if c == "JPN" else 9,
                    fontweight="bold" if c == "JPN" else "normal")

    # 領域分け
    ax.axhline(0.05, color="red", linewidth=0.8, linestyle=":", alpha=0.6)
    ax.axvline(0.05, color="red", linewidth=0.8, linestyle=":", alpha=0.6)
    ax.text(0.025, 0.01, "Both directions\nsignificant\n(bidirectional)",
            ha="center", fontsize=9, color="darkred", alpha=0.7)
    ax.text(0.025, 0.5, "GDP → CA only\n(H6 supported)",
            ha="center", fontsize=9, color="darkgreen", alpha=0.7)
    ax.text(0.5, 0.01, "CA → GDP only\n(H6 rejected)",
            ha="center", fontsize=9, color="darkred", alpha=0.7)
    ax.text(0.5, 0.5, "Neither\n(uninformative)",
            ha="center", fontsize=9, color="gray", alpha=0.7)

    ax.set_xlim(-0.02, 1.02)
    ax.set_ylim(-0.02, 1.02)
    ax.set_xlabel("p-value: GDP → CA/GDP (smaller = GDP precedes CA)")
    ax.set_ylabel("p-value: CA/GDP → GDP (smaller = CA precedes GDP)")
    ax.set_title("Japan's Position in the GDP-CA Granger Causality Plane",
                 fontsize=11, fontweight="bold")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()

    out = FIG_DIR / "cross_country_japan_anomaly.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── メイン ────────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== Cross-Country SVAR ===")
        print("  各国で同じ 3 変数 VAR を推定し、Granger 因果と IRF を比較")
        print()

    out = run_all_countries(verbose=verbose)

    if not out["results"]:
        print("結果が空です。")
        return out

    # Granger 結果保存
    granger_path = PROCESSED_DIR / "japan_stagnation_cross_country_svar.csv"
    out["granger"].to_csv(granger_path, index=False)

    # 図
    p1 = plot_granger_heatmap(out["granger"])
    p2 = plot_irf_ca_to_gdp(out["results"])
    p3 = plot_japan_anomaly(out["granger"])

    if verbose:
        print("\n=== Granger 因果検定（国別 minimum p-value） ===")
        pivot = out["granger"].pivot_table(
            index="country", columns=["from", "to"], values="min_p"
        )
        country_order = ["JPN", "USA", "DEU", "FRA", "GBR", "ITA", "CAN", "KOR"]
        pivot = pivot.reindex(country_order)
        print(pivot.round(4).to_string())

        print("\n=== H6 の判定（国別） ===")
        print("  H6: 家計対外シフトは GDP の結果（CA→GDP は有意でなく、GDP→CA は有意）")
        h6_check = []
        for c in country_order:
            if c not in out["results"]:
                continue
            ca_to_gdp = out["granger"][
                (out["granger"]["country"] == c) &
                (out["granger"]["from"] == "d_ca_gdp") &
                (out["granger"]["to"] == "g_gdp")
            ]["min_p"].values
            gdp_to_ca = out["granger"][
                (out["granger"]["country"] == c) &
                (out["granger"]["from"] == "g_gdp") &
                (out["granger"]["to"] == "d_ca_gdp")
            ]["min_p"].values
            if len(ca_to_gdp) > 0 and len(gdp_to_ca) > 0:
                p1_v = ca_to_gdp[0]
                p2_v = gdp_to_ca[0]
                if pd.notna(p1_v) and pd.notna(p2_v):
                    h6_supported = (p1_v >= 0.05) and (p2_v < 0.10)
                    bidir = (p1_v < 0.05) and (p2_v < 0.05)
                    h6_check.append({
                        "country":   COUNTRY_LABEL.get(c, c),
                        "ca_to_gdp": p1_v,
                        "gdp_to_ca": p2_v,
                        "H6_pattern": "✓" if h6_supported else "✗",
                        "bidirect":  "✓" if bidir else "",
                    })
        h6_df = pd.DataFrame(h6_check)
        print(h6_df.round(4).to_string(index=False))

        print(f"\n  図1（ヒートマップ）: {p1}")
        print(f"  図2（CA→GDP IRF）: {p2}")
        print(f"  図3（日本の位置）: {p3}")
        print(f"  Granger 結果: {granger_path}")

    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="クロスカントリー SVAR")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
