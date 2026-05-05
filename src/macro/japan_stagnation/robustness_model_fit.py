"""ロバストネス R-4：形式モデルの歴史データ適合性検証.

検証手順:
    1. 各国の年次データから A_T, A_N, ω, k_ICT を時間変化として推定
    2. これらをモデルに入れて Y, w, labor share を予測
    3. 観測値（GDP per WA、実質賃金、労働分配率）と比較
    4. 適合度（RMSE, R²）を報告

仮にモデルが歴史データに良くフィットすれば、
カウンターファクチュアル予測の信頼性が高まる.

簡易検証として、日本とドイツの 2000-2019 年について
モデル予測 vs 観測値の比較を行う.

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - robustness_model_fit.png
    data/processed/
        - japan_stagnation_model_fit.csv
"""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.collectors.pwt_collector import load as load_pwt
from src.collectors.wdi_collector import load_country
from src.collectors.wdi_sector_collector import load_country as load_sector
from src.macro.japan_stagnation.formal_model_extended import (
    ExtendedParams, solve_economy,
)
from src.macro.japan_stagnation.stylized_facts import FIG_DIR, PROCESSED_DIR


def calibrate_country_year(country: str, year: int,
                            ref_country: str = "DEU",
                            ref_year: int = 2019) -> ExtendedParams:
    """各国・年のデータからパラメータをカリブレーション.

    A_T, A_N: 各国の per-WA GDP × 業種シェア（簡易代理）
    ω: PWT labor_share / (1-α)
    """
    alpha = 0.33

    pwt = load_pwt()
    wdi = load_country(country).reset_index()
    sec = load_sector(country).reset_index()

    # 労働分配率 → ω
    pwt_jp = pwt[(pwt["country"] == country) & (pwt["year"] == year)]
    if pwt_jp.empty:
        pwt_jp = pwt[(pwt["country"] == country)]
        if not pwt_jp.empty:
            pwt_jp = pwt_jp.sort_values("year")
            # 補間：最も近い年
            year_diff = (pwt_jp["year"] - year).abs()
            pwt_jp = pwt_jp.loc[year_diff.idxmin():year_diff.idxmin()]
    if not pwt_jp.empty:
        ls = pwt_jp["labor_share"].iloc[0]
        omega = ls / (1 - alpha)
    else:
        omega = 0.85  # default

    # GDP per WA から A の比較
    wdi_y = wdi[wdi["year"] == year]
    sec_y = sec[sec["year"] == year]
    if wdi_y.empty or sec_y.empty:
        return None

    # 参照国の同じ年のデータ
    wdi_ref = load_country(ref_country).reset_index()
    sec_ref = load_sector(ref_country).reset_index()
    wdi_ref_y = wdi_ref[wdi_ref["year"] == year]
    sec_ref_y = sec_ref[sec_ref["year"] == year]

    if wdi_ref_y.empty:
        return None

    # GDP per WA 比
    gdp_per_wa_country = (
        wdi_y["gdp_real"].iloc[0] / wdi_y["population_15_64"].iloc[0]
    )
    gdp_per_wa_ref = (
        wdi_ref_y["gdp_real"].iloc[0] / wdi_ref_y["population_15_64"].iloc[0]
    )
    A_overall = gdp_per_wa_country / gdp_per_wa_ref  # 参照国対比

    # 業種別生産性比（簡易）
    if not sec_ref_y.empty:
        ind_share_country = sec_y["industry_va_pct"].iloc[0] / 100
        ind_share_ref = sec_ref_y["industry_va_pct"].iloc[0] / 100
        srv_share_country = sec_y["services_va_pct"].iloc[0] / 100
        srv_share_ref = sec_ref_y["services_va_pct"].iloc[0] / 100
        # 業種別 A は per-hour productivity 経由（簡易：シェアに反比例）
        A_T = A_overall * (ind_share_country / ind_share_ref) ** (-0.5)
        A_N = A_overall * (srv_share_country / srv_share_ref) ** (-0.5)
        # 上限
        A_T = min(A_T, 1.5)
        A_N = min(A_N, 1.5)
    else:
        A_T = A_overall
        A_N = A_overall

    p = ExtendedParams(
        alpha=alpha,
        A_T=A_T,
        A_N_base=A_N,
        omega=omega,
        L_T_share=ind_share_country if not sec_y.empty else 0.27,
        L_N_share=srv_share_country if not sec_y.empty else 0.69,
    )
    return p


def fit_country_history(country: str, ref_country: str = "DEU",
                          start: int = 2000, end: int = 2019) -> pd.DataFrame:
    rows = []
    pwt = load_pwt()
    wdi = load_country(country).reset_index()
    wdi_ref = load_country(ref_country).reset_index()

    for year in range(start, end + 1, 5):  # 5 年ごと
        p = calibrate_country_year(country, year, ref_country, ref_country)
        if p is None:
            continue
        result = solve_economy(p)

        # 観測値
        wdi_y = wdi[wdi["year"] == year]
        wdi_ref_y = wdi_ref[wdi_ref["year"] == year]
        if wdi_y.empty or wdi_ref_y.empty:
            continue

        gdp_per_wa_country = (
            wdi_y["gdp_real"].iloc[0] / wdi_y["population_15_64"].iloc[0]
        )
        gdp_per_wa_ref = (
            wdi_ref_y["gdp_real"].iloc[0] / wdi_ref_y["population_15_64"].iloc[0]
        )
        observed_ratio = gdp_per_wa_country / gdp_per_wa_ref

        # PWT labor share
        pwt_y = pwt[(pwt["country"] == country) & (pwt["year"] == year)]
        observed_ls = pwt_y["labor_share"].iloc[0] if not pwt_y.empty else np.nan

        rows.append({
            "country":           country,
            "year":              year,
            "observed_gdp_ratio": observed_ratio,
            "model_gdp":         result["Y_total"],
            "observed_ls":       observed_ls,
            "model_ls":          result["labor_share"],
            "calibrated_omega":  p.omega,
            "calibrated_A_T":    p.A_T,
            "calibrated_A_N":    p.A_N_base,
        })
    return pd.DataFrame(rows)


def plot_fit(df: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))

    # 観測 vs モデル GDP 比
    ax = axes[0]
    if not df.empty:
        ax.scatter(df["observed_gdp_ratio"], df["model_gdp"],
                    s=80, alpha=0.7, color="#1f77b4")
        for _, row in df.iterrows():
            ax.annotate(f"{row['country']} {int(row['year'])}",
                          (row["observed_gdp_ratio"], row["model_gdp"]),
                          xytext=(5, 5), textcoords="offset points", fontsize=8)
        # 45° 線
        lim = [min(df["observed_gdp_ratio"].min(), df["model_gdp"].min()) - 0.05,
               max(df["observed_gdp_ratio"].max(), df["model_gdp"].max()) + 0.05]
        ax.plot(lim, lim, color="black", linewidth=0.8, linestyle="--",
                alpha=0.5, label="Perfect fit")
        ax.set_xlabel("Observed GDP per WA (vs Germany)")
        ax.set_ylabel("Model-predicted GDP")
        ax.set_title("Model vs Observed: GDP", fontsize=10, fontweight="bold")
        ax.legend()
        ax.grid(True, alpha=0.3)

    # 観測 vs モデル労働分配率
    ax = axes[1]
    if not df.empty and df["observed_ls"].notna().any():
        sub = df.dropna(subset=["observed_ls"])
        ax.scatter(sub["observed_ls"], sub["model_ls"],
                    s=80, alpha=0.7, color="#ff7f0e")
        for _, row in sub.iterrows():
            ax.annotate(f"{row['country']} {int(row['year'])}",
                          (row["observed_ls"], row["model_ls"]),
                          xytext=(5, 5), textcoords="offset points", fontsize=8)
        lim = [0.5, 0.75]
        ax.plot(lim, lim, color="black", linewidth=0.8, linestyle="--",
                alpha=0.5, label="Perfect fit")
        ax.set_xlim(lim)
        ax.set_ylim(lim)
        ax.set_xlabel("Observed labor share (PWT)")
        ax.set_ylabel("Model-predicted labor share")
        ax.set_title("Model vs Observed: Labor share",
                      fontsize=10, fontweight="bold")
        ax.legend()
        ax.grid(True, alpha=0.3)

    fig.suptitle("Robustness R-4: Model fit to historical data (5-year intervals)",
                 fontsize=11, fontweight="bold", y=1.02)
    fig.tight_layout()

    out = FIG_DIR / "robustness_model_fit.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== R-4: Model Fit to Historical Data ===")

    countries = ["JPN", "USA", "GBR", "FRA", "ITA"]
    all_fits = []
    for c in countries:
        df = fit_country_history(c, ref_country="DEU")
        all_fits.append(df)
    combined = pd.concat(all_fits, ignore_index=True)

    if verbose:
        print("\n=== モデル推定 vs 観測（5 年ごと、対独比） ===")
        cols = ["country", "year", "observed_gdp_ratio", "model_gdp",
                "observed_ls", "model_ls"]
        print(combined[cols].round(3).to_string(index=False))

        # フィット指標
        valid = combined.dropna(subset=["observed_gdp_ratio", "model_gdp"])
        if not valid.empty:
            corr_gdp = np.corrcoef(valid["observed_gdp_ratio"], valid["model_gdp"])[0, 1]
            rmse_gdp = np.sqrt(np.mean(
                (valid["observed_gdp_ratio"] - valid["model_gdp"]) ** 2,
            ))
            print(f"\n  GDP corr (observed vs model): {corr_gdp:.3f}")
            print(f"  GDP RMSE: {rmse_gdp:.3f}")

        valid_ls = combined.dropna(subset=["observed_ls", "model_ls"])
        if not valid_ls.empty:
            corr_ls = np.corrcoef(valid_ls["observed_ls"], valid_ls["model_ls"])[0, 1]
            rmse_ls = np.sqrt(np.mean(
                (valid_ls["observed_ls"] - valid_ls["model_ls"]) ** 2,
            ))
            print(f"\n  LS corr (observed vs model): {corr_ls:.3f}")
            print(f"  LS RMSE: {rmse_ls:.3f}")

    p1 = plot_fit(combined)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = PROCESSED_DIR / "japan_stagnation_model_fit.csv"
    combined.to_csv(out_csv, index=False)

    if verbose:
        print(f"\n  図: {p1}")
        print(f"  サマリー: {out_csv}")

    return {"fit": combined}


def main() -> None:
    parser = argparse.ArgumentParser(description="モデル適合性検証")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
