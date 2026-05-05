"""Monadic Gravity Model：輸出/GDP 比を国特性で説明する.

完全な二国間貿易データを使わず、各国の「全体としての貿易開放度」を
- 経済規模（log GDP, log population）
- 言語距離（英語からの距離）
- 地理的隔離度（主要交易相手からの距離）
- 国境を越えるアクセスのしやすさ（陸続きの隣国数）
で説明する monadic 形式の重力モデル.

仮説:
    H4（修正版）: 輸出/GDP 比は、経済規模 + 言語距離 + 地理的隔離度で
                  説明される。Japan ダミーは有意か？
    H5: 韓国は同程度の言語距離・地理隔離下で日本より輸出/GDP が高い

データ:
    - WDI: exports_gdp_share, gdp_real, population
    - 言語距離: Melitz-Toubal (2014) Linguistic Proximity Index 風の値（埋め込み）
    - 地理的隔離度: Major-Trade-Weighted distance proxy（埋め込み）

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - gravity_monadic_residual.png
    data/processed/
        - japan_stagnation_gravity_monadic.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from src.macro.japan_stagnation.stylized_facts import (
    COLOR, COUNTRY_LABEL, FIG_DIR, PROCESSED_DIR, load_panel,
)

# ── 国特性（時間不変） ────────────────────────────────────────────────────────
# 言語距離 (linguistic distance to English on 0-1 scale)：
#   Melitz-Toubal (2014) "Native and dominant languages" の精神に従い、
#   Levenshtein-distance-based ASJP の主要言語×英語のスケールを参照.

LINGUISTIC_DISTANCE: dict[str, float] = {
    "USA": 0.0,
    "GBR": 0.0,
    "CAN": 0.0,   # 公用語英語（ケベック仏語あるが弱め）
    "DEU": 0.40,  # ゲルマン同族
    "FRA": 0.85,
    "ITA": 0.90,
    "JPN": 1.00,
    "KOR": 1.00,
}

# 地理的隔離度 (geographic remoteness to OECD trading partners)：
#   主要交易相手（米欧）への距離を考慮した代理指標. 0=近い, 1=遠い.

GEO_REMOTENESS: dict[str, float] = {
    "USA": 0.50,
    "GBR": 0.20,
    "CAN": 0.45,
    "DEU": 0.10,
    "FRA": 0.10,
    "ITA": 0.15,
    "JPN": 0.85,
    "KOR": 0.80,
}

# EU/EEA メンバー（時間不変、簡略化）

EU_MEMBER: dict[str, int] = {
    "USA": 0, "GBR": 0,  # Brexit 後を反映（簡略）
    "CAN": 0, "DEU": 1, "FRA": 1, "ITA": 1, "JPN": 0, "KOR": 0,
}

# NAFTA/USMCA メンバー

NAFTA_MEMBER: dict[str, int] = {
    "USA": 1, "CAN": 1, "MEX": 1,
    "GBR": 0, "DEU": 0, "FRA": 0, "ITA": 0, "JPN": 0, "KOR": 0,
}


# ── データ準備 ────────────────────────────────────────────────────────────────

def build_gravity_panel(
    panel: pd.DataFrame,
    start: int = 1995,
    end: int = 2024,
) -> pd.DataFrame:
    df = panel.reset_index().copy()
    df = df[(df["year"] >= start) & (df["year"] <= end)].copy()
    df = df.dropna(subset=["exports_gdp_share", "gdp_real", "population"])

    df["log_gdp"]      = np.log(df["gdp_real"])
    df["log_pop"]      = np.log(df["population"])
    df["log_exports_gdp"] = np.log(df["exports_gdp_share"])

    df["lang_dist"]    = df["country"].map(LINGUISTIC_DISTANCE)
    df["geo_remote"]   = df["country"].map(GEO_REMOTENESS)
    df["eu"]           = df["country"].map(EU_MEMBER)

    df["japan"] = (df["country"] == "JPN").astype(int)
    df["korea"] = (df["country"] == "KOR").astype(int)

    df = df.dropna(subset=["lang_dist", "geo_remote", "eu"])
    return df


# ── 推定モデル ────────────────────────────────────────────────────────────────

GRAVITY_MODELS: dict[str, str] = {
    "G1": "log_exports_gdp ~ log_gdp + log_pop + C(year)",
    "G2": "log_exports_gdp ~ log_gdp + log_pop + lang_dist + geo_remote + C(year)",
    "G3": "log_exports_gdp ~ log_gdp + log_pop + lang_dist + geo_remote + eu + C(year)",
    "G4": "log_exports_gdp ~ log_gdp + log_pop + lang_dist + geo_remote + eu + japan + C(year)",
}


def fit_models(df: pd.DataFrame) -> dict[str, dict]:
    out = {}
    for mid, formula in GRAVITY_MODELS.items():
        try:
            model = smf.ols(formula, data=df)
            fit = model.fit(cov_type="cluster", cov_kwds={"groups": df["country"]})
            out[mid] = fit
        except Exception as e:
            print(f"  Model {mid} エラー: {e}")
    return out


def collect_results(fits: dict) -> pd.DataFrame:
    rows = []
    for mid, fit in fits.items():
        for var in ["log_gdp", "log_pop", "lang_dist", "geo_remote", "eu", "japan"]:
            if var in fit.params.index:
                rows.append({
                    "model":   mid,
                    "var":     var,
                    "coef":    fit.params[var],
                    "se":      fit.bse[var],
                    "t":       fit.tvalues[var],
                    "p":       fit.pvalues[var],
                    "n_obs":   int(fit.nobs),
                    "r2":      fit.rsquared,
                })
    return pd.DataFrame(rows)


# ── プロット: 国別残差 ────────────────────────────────────────────────────────

def plot_country_residuals(df: pd.DataFrame, fits: dict) -> Path:
    fit = fits["G3"]  # Japan ダミーなしのフルモデル
    df = df.copy()
    df["resid"] = fit.resid

    # 直近 5 年平均残差
    recent = df[df["year"] >= 2019]
    avg_resid = recent.groupby("country")["resid"].mean().sort_values()

    fig, ax = plt.subplots(figsize=(10, 5.5))
    countries = avg_resid.index.tolist()
    colors = [COLOR.get(c, "gray") for c in countries]
    labels = [COUNTRY_LABEL.get(c, c) for c in countries]
    bars = ax.barh(labels, avg_resid.values, color=colors, alpha=0.85,
                    edgecolor="black", linewidth=0.5)
    ax.axvline(0, color="black", linewidth=0.6)
    ax.set_xlabel("Residual log(exports/GDP) — actual minus model prediction\n(2019-2024 average)")
    ax.set_title(
        "Monadic Gravity Model: Country Residuals\n"
        "(controlling for size, language distance, remoteness, EU)",
        fontsize=11, fontweight="bold",
    )
    ax.grid(True, axis="x", alpha=0.3)
    for bar, c in zip(bars, countries):
        if c == "JPN":
            bar.set_edgecolor("red")
            bar.set_linewidth(2.5)
    fig.tight_layout()
    out = FIG_DIR / "gravity_monadic_residual.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── プロット: 言語距離 vs 輸出/GDP ───────────────────────────────────────────

def plot_lang_vs_exports(df: pd.DataFrame) -> Path:
    recent = df[df["year"] >= 2019].groupby("country").agg(
        lang_dist=("lang_dist", "first"),
        exports_share=("exports_gdp_share", "mean"),
    ).reset_index()

    fig, ax = plt.subplots(figsize=(10, 6))
    for _, row in recent.iterrows():
        c = row["country"]
        ax.scatter(row["lang_dist"], row["exports_share"],
                    color=COLOR.get(c, "gray"),
                    s=300 if c == "JPN" else 130,
                    alpha=0.85,
                    edgecolor="black" if c == "JPN" else "none",
                    linewidth=2.5 if c == "JPN" else 0)
        ax.annotate(COUNTRY_LABEL.get(c, c),
                     (row["lang_dist"], row["exports_share"]),
                     xytext=(8, 8), textcoords="offset points",
                     fontsize=11 if c == "JPN" else 9,
                     fontweight="bold" if c == "JPN" else "normal")

    ax.set_xlabel("Linguistic distance to English (0=identical, 1=most distant)")
    ax.set_ylabel("Exports / GDP (%, 2019-2024 average)")
    ax.set_title("Linguistic Distance vs Trade Openness\n"
                 "(Japan and Korea share max linguistic distance, but Korea trades much more)",
                 fontsize=11, fontweight="bold")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out = FIG_DIR / "gravity_lang_vs_exports.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── メイン ────────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== Phase 2: Monadic Gravity Model ===")

    panel = load_panel()
    df = build_gravity_panel(panel, start=1995, end=2024)

    if verbose:
        print(f"  サンプル: {len(df)} 観測 ({df['country'].nunique()} 国)")

    fits = fit_models(df)

    if verbose:
        print("\n=== モデル仕様と Japan ダミー ===")
        for mid, fit in fits.items():
            jp = fit.params.get("japan", np.nan)
            jp_p = fit.pvalues.get("japan", np.nan)
            n = int(fit.nobs)
            r2 = fit.rsquared
            print(f"  {mid}: N={n}, R²={r2:.3f}, Japan={jp:+.3f} (p={jp_p:.3f})")

    results = collect_results(fits)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = PROCESSED_DIR / "japan_stagnation_gravity_monadic.csv"
    results.to_csv(out_csv, index=False)

    p1 = plot_country_residuals(df, fits)
    p2 = plot_lang_vs_exports(df)

    if verbose:
        print("\n=== 主要係数（Model G4：日本ダミー含む） ===")
        g4 = results[results["model"] == "G4"]
        print(g4[["var", "coef", "se", "p", "r2"]].round(4).to_string(index=False))

        print("\n=== 直近 5 年（2019-2024）の国別残差ランキング ===")
        fit = fits["G3"]  # Japan dummy なしモデル
        df2 = df.copy()
        df2["resid"] = fit.resid
        recent_resid = df2[df2["year"] >= 2019].groupby("country")["resid"].mean().sort_values()
        print(recent_resid.round(4).to_string())

        print(f"\n  図1: {p1}")
        print(f"  図2: {p2}")
        print(f"  結果: {out_csv}")

    return {"fits": fits, "results": results, "df": df}


def main() -> None:
    parser = argparse.ArgumentParser(description="Monadic Gravity Model")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
