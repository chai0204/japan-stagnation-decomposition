"""韓国を 'counterfactual Japan' として扱う Oaxaca-Blinder 4 因子分解.

レビュアー指摘（Round 2）への対応：
    > 韓国比較が「説明っぽい列挙」で終わっている
    > 「なぜ韓国は日本と違ったのか（識別可能な差）」が必要
    > Gap = 産業構造 + 輸出比率 + ICT 投資 + 賃金制度

設計：
    Total gap (per-WA growth, JPN-KOR) = sum of contributions over 4 factors:

    1. industrial_structure : manufacturing_va_pct (% of GDP)
                              → 産業構造（製造業比率）
    2. exports_share        : exports_gdp_share (% of GDP)
                              → 輸出依存度
    3. ict_investment       : ICT 投資 / GDP (%, OECD STI Scoreboard 埋込値)
                              → 技術投資集約度
    4. labor_share          : 労働分配率 (PWT 10.01)
                              → 賃金制度・分配メカニズム

被説明変数: 5 年差分の per-WA GDP 成長率（年率%）

Oaxaca-Blinder 分解:
    g_J - g_K = Σ_k (X_J,k - X_K,k) · β_K,k    [characteristics gap, "explained"]
              + Σ_k X_J,k · (β_J,k - β_K,k)    [coefficient gap, "structural"]

参照群（係数推定の基底）: KOR（"counterfactual Japan"）

出力:
    figures/korea_oaxaca_decomposition.png
    data/processed/japan_stagnation_korea_oaxaca.csv
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm

from src.macro.japan_stagnation.stylized_facts import (
    COUNTRY_LABEL, FIG_DIR, PROCESSED_DIR, load_panel,
)

RAW_DIR = Path(__file__).parents[3] / "data" / "raw"

# ── ICT 投資 % of GDP（時間変化を考慮、OECD STI Scoreboard ベースで補間）─
# Source: OECD (various years) STI Scoreboard, "Measuring the Digital Transformation"
# 主要転換点で値を埋め、線形補間で時間パネルを生成
ICT_INVESTMENT_GDP_PANEL = {
    "JPN": {1995: 3.4, 2000: 3.0, 2005: 2.8, 2010: 2.5, 2015: 2.2, 2019: 2.1},
    "KOR": {1995: 2.5, 2000: 2.7, 2005: 3.1, 2010: 3.4, 2015: 3.6, 2019: 3.8},
}


def interp_ict(country: str, year: int) -> float:
    """ICT 投資 % GDP を年次で線形補間."""
    if country not in ICT_INVESTMENT_GDP_PANEL:
        return np.nan
    points = sorted(ICT_INVESTMENT_GDP_PANEL[country].items())
    years_arr = np.array([y for y, _ in points])
    values = np.array([v for _, v in points])
    if year < years_arr.min():
        return values[0]
    if year > years_arr.max():
        return values[-1]
    return float(np.interp(year, years_arr, values))

# ── PWT 10.01 labsh（労働分配率）— pwt_collector から流用 ─
PWT_LABSH = {
    "USA": {1995: 0.626, 2000: 0.633, 2005: 0.628, 2010: 0.605, 2015: 0.596, 2019: 0.601},
    "JPN": {1995: 0.633, 2000: 0.624, 2005: 0.591, 2010: 0.570, 2015: 0.554, 2019: 0.561},
    "DEU": {1995: 0.667, 2000: 0.661, 2005: 0.624, 2010: 0.617, 2015: 0.626, 2019: 0.643},
    "FRA": {1995: 0.683, 2000: 0.661, 2005: 0.661, 2010: 0.659, 2015: 0.667, 2019: 0.670},
    "GBR": {1995: 0.671, 2000: 0.685, 2005: 0.659, 2010: 0.625, 2015: 0.620, 2019: 0.624},
    "ITA": {1995: 0.601, 2000: 0.587, 2005: 0.583, 2010: 0.582, 2015: 0.557, 2019: 0.560},
    "CAN": {1995: 0.609, 2000: 0.601, 2005: 0.580, 2010: 0.585, 2015: 0.581, 2019: 0.580},
    "KOR": {1995: 0.546, 2000: 0.544, 2005: 0.527, 2010: 0.516, 2015: 0.557, 2019: 0.582},
}

PREDICTORS = [
    "manuf_share",
    "exports_share",
    "ict_invest",
    "labor_share",
]
PRED_LABELS = {
    "manuf_share":   "Industrial structure (Manuf %)",
    "exports_share": "Exports / GDP",
    "ict_invest":    "ICT investment / GDP",
    "labor_share":   "Labor share (PWT)",
}


def load_sector_panel() -> pd.DataFrame:
    """WDI sector データを長形式で."""
    frames = []
    for c in ["JPN", "KOR", "USA", "DEU", "FRA", "GBR", "CAN", "ITA"]:
        path = RAW_DIR / f"wdi_sector_{c}.csv"
        if not path.exists():
            continue
        df = pd.read_csv(path)
        df = df.rename(columns={df.columns[0]: "year"})
        df["country"] = c
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def interp_labsh(country: str, year: int) -> float:
    """PWT 労働分配率を線形補間."""
    if country not in PWT_LABSH:
        return np.nan
    points = sorted(PWT_LABSH[country].items())
    years_arr = np.array([y for y, _ in points])
    values = np.array([v for _, v in points])
    if year < years_arr.min():
        return values[0]
    if year > years_arr.max():
        return values[-1]
    return float(np.interp(year, years_arr, values))


def build_decomp_panel(
    interval: int = 5, start: int = 1995, end: int = 2024
) -> pd.DataFrame:
    """Oaxaca 用に統合パネルを構築（年次 → 5年区間平均）."""
    base = load_panel().reset_index()
    sector = load_sector_panel()

    # 派生変数
    base["gdp_per_wa"] = base["gdp_real"] / base["population_15_64"]

    rows = []
    for c in ["JPN", "KOR"]:
        sub_b = base[base["country"] == c].set_index("year").sort_index()
        sub_s = (
            sector[sector["country"] == c].set_index("year").sort_index()
            if not sector.empty else pd.DataFrame()
        )
        for y in sub_b.index:
            y0 = y - interval
            if y0 not in sub_b.index:
                continue
            v0, v1 = sub_b.loc[y0, "gdp_per_wa"], sub_b.loc[y, "gdp_per_wa"]
            if pd.isna(v0) or pd.isna(v1) or v0 <= 0:
                continue
            g_per_wa = ((v1 / v0) ** (1.0 / interval) - 1.0) * 100

            # 期間平均
            window_b = sub_b.loc[y0:y]
            row = {
                "country": c,
                "year_end": y,
                "g_gdp_per_wa": g_per_wa,
                "exports_share": window_b["exports_gdp_share"].mean(),
            }
            if not sub_s.empty:
                window_s = sub_s.loc[
                    (sub_s.index >= y0) & (sub_s.index <= y)
                ]
                row["manuf_share"] = window_s["manufacturing_va_pct"].mean()
            else:
                row["manuf_share"] = np.nan

            # ICT 投資 — 期間平均（年次補間後）
            ict_window = [interp_ict(c, yr) for yr in range(int(y0), int(y) + 1)]
            row["ict_invest"] = float(np.nanmean(ict_window)) if ict_window else np.nan
            row["labor_share"] = interp_labsh(c, y) * 100  # ％ にスケール
            rows.append(row)

    df = pd.DataFrame(rows).dropna(subset=["g_gdp_per_wa"] + PREDICTORS)
    df = df[df["year_end"].between(start, end)]
    return df


def fit_country_model(df_country: pd.DataFrame) -> dict:
    sub = df_country.dropna(subset=PREDICTORS + ["g_gdp_per_wa"]).copy()
    if len(sub) < 6:
        return {"beta": pd.Series(dtype=float), "Xbar": pd.Series(dtype=float)}
    X = sm.add_constant(sub[PREDICTORS])
    y = sub["g_gdp_per_wa"]
    fit = sm.OLS(y, X).fit()
    return {
        "beta":  fit.params,
        "Xbar":  X.mean(),
        "ybar":  y.mean(),
        "fit":   fit,
    }


def fit_pooled_model(panel: pd.DataFrame) -> dict:
    """Japan + Korea のプール回帰（共通係数 + 国 FE）."""
    sub = panel.dropna(subset=PREDICTORS + ["g_gdp_per_wa"]).copy()
    sub["jpn"] = (sub["country"] == "JPN").astype(int)
    X = sm.add_constant(sub[PREDICTORS + ["jpn"]])
    y = sub["g_gdp_per_wa"]
    fit = sm.OLS(y, X).fit()
    return {"beta": fit.params, "fit": fit}


def oaxaca_decompose(panel: pd.DataFrame) -> dict:
    """JPN vs KOR の Oaxaca-Blinder 分解（pooled coefficient ロバスト版を併記）."""
    df_j = panel[panel["country"] == "JPN"]
    df_k = panel[panel["country"] == "KOR"]

    fit_j = fit_country_model(df_j)
    fit_k = fit_country_model(df_k)
    if fit_j["beta"].empty or fit_k["beta"].empty:
        return {}

    Xbar_j, Xbar_k = fit_j["Xbar"], fit_k["Xbar"]
    beta_j, beta_k = fit_j["beta"], fit_k["beta"]
    ybar_j, ybar_k = fit_j["ybar"], fit_k["ybar"]
    total_gap = ybar_j - ybar_k

    # KOR の係数を「規範」として使う（counterfactual Japan）
    char_diff = (Xbar_j - Xbar_k) * beta_k
    coef_diff = Xbar_j * (beta_j - beta_k)

    char_total = char_diff.drop("const", errors="ignore").sum()
    coef_total = coef_diff.sum()  # const も含む

    contrib = pd.DataFrame({
        "predictor":         PREDICTORS,
        "Xbar_japan":        Xbar_j.reindex(PREDICTORS).values,
        "Xbar_korea":        Xbar_k.reindex(PREDICTORS).values,
        "diff":              (Xbar_j - Xbar_k).reindex(PREDICTORS).values,
        "beta_korea":        beta_k.reindex(PREDICTORS).values,
        "beta_japan":        beta_j.reindex(PREDICTORS).values,
        "char_contribution": char_diff.reindex(PREDICTORS).values,
        "coef_contribution": coef_diff.reindex(PREDICTORS).values,
        "total_contribution":(char_diff.reindex(PREDICTORS).values
                              + coef_diff.reindex(PREDICTORS).values),
    })
    contrib["share_of_gap"] = contrib["total_contribution"] / total_gap * 100

    # Pooled-coefficient 分解（係数不安定性を緩和したロバスト版）
    pooled = fit_pooled_model(panel)
    beta_p = pooled["beta"].reindex(PREDICTORS)
    pooled_char = (Xbar_j.reindex(PREDICTORS) - Xbar_k.reindex(PREDICTORS)) * beta_p
    pooled_summary = pd.DataFrame({
        "predictor":           PREDICTORS,
        "diff":                (Xbar_j - Xbar_k).reindex(PREDICTORS).values,
        "beta_pooled":         beta_p.values,
        "char_contribution":   pooled_char.values,
        "share_of_gap":        (pooled_char.values / total_gap * 100),
    })

    return {
        "ybar_japan":     ybar_j,
        "ybar_korea":     ybar_k,
        "total_gap":      total_gap,
        "char_total":     char_total,
        "coef_total":     coef_total,
        "intercept_diff": coef_diff.get("const", 0.0),
        "contributions":  contrib,
        "pooled":         pooled_summary,
        "pooled_char_total": pooled_char.sum(),
        "n_japan":        len(df_j),
        "n_korea":        len(df_k),
    }


def plot_decomposition(res: dict) -> Path:
    contrib = res["contributions"].copy()
    labels = [PRED_LABELS.get(p, p) for p in contrib["predictor"]]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 6))

    # Left panel: characteristics + coefficient contributions per factor
    x = np.arange(len(labels))
    width = 0.4
    ax1.barh(x - width / 2, contrib["char_contribution"], width,
             color="#1f77b4", alpha=0.85, label="Characteristics gap")
    ax1.barh(x + width / 2, contrib["coef_contribution"], width,
             color="#ff7f0e", alpha=0.85, label="Coefficient gap")
    ax1.axvline(0, color="black", linewidth=0.6)
    ax1.set_yticks(x)
    ax1.set_yticklabels(labels)
    ax1.set_xlabel("Contribution to JPN-KOR per-WA growth gap (%/yr)")
    ax1.set_title(
        f"JPN vs KOR (counterfactual Japan)\n"
        f"Total gap = {res['total_gap']:+.2f}%/yr | "
        f"Char {res['char_total']:+.2f}, Coef {res['coef_total']:+.2f}",
        fontsize=10, fontweight="bold",
    )
    ax1.legend(loc="best", fontsize=9, framealpha=0.85)
    ax1.grid(True, axis="x", alpha=0.3)

    # Right panel: total contribution per factor as share of total gap
    total_share = contrib["share_of_gap"].fillna(0).values
    colors = ["#d62728" if s < 0 else "#2ca02c" for s in total_share]
    ax2.barh(x, total_share, color=colors, alpha=0.85)
    ax2.axvline(0, color="black", linewidth=0.6)
    ax2.set_yticks(x)
    ax2.set_yticklabels(labels)
    ax2.set_xlabel("Share of total gap (%)")
    ax2.set_title("Each factor's share of total gap", fontsize=10, fontweight="bold")
    for i, s in enumerate(total_share):
        ax2.text(s + (1 if s >= 0 else -1), i, f"{s:+.1f}%",
                 va="center", ha="left" if s >= 0 else "right", fontsize=9)
    ax2.grid(True, axis="x", alpha=0.3)

    fig.suptitle(
        "Oaxaca-Blinder decomposition: Why did Korea outpace Japan?\n"
        "(Korea as 'counterfactual Japan')",
        fontsize=12, fontweight="bold",
    )
    fig.tight_layout()
    out = FIG_DIR / "korea_oaxaca_decomposition.png"
    fig.savefig(out, dpi=150)
    plt.close(fig)
    return out


def run(verbose: bool = True) -> dict:
    if verbose:
        print("=" * 60)
        print("Korea as counterfactual Japan — Oaxaca 4-factor decomposition")
        print("=" * 60)

    panel = build_decomp_panel(interval=5, start=1995, end=2024)
    if panel.empty:
        print("! データなし — collector を先に実行してください")
        return {}

    if verbose:
        print(f"\nObservations: JPN {(panel['country']=='JPN').sum()}, "
              f"KOR {(panel['country']=='KOR').sum()}")
        print(f"\nMean per-WA growth (%/yr):")
        print(f"  JPN: {panel.loc[panel['country']=='JPN','g_gdp_per_wa'].mean():+.2f}")
        print(f"  KOR: {panel.loc[panel['country']=='KOR','g_gdp_per_wa'].mean():+.2f}")
        print(f"  Gap: {panel.loc[panel['country']=='JPN','g_gdp_per_wa'].mean() - panel.loc[panel['country']=='KOR','g_gdp_per_wa'].mean():+.2f}")

    res = oaxaca_decompose(panel)
    if not res:
        print("! 分解推定失敗")
        return {}

    if verbose:
        print(f"\nTotal gap (JPN - KOR): {res['total_gap']:+.3f} %/yr")
        print(f"  Characteristics:     {res['char_total']:+.3f} (explained by factor levels)")
        print(f"  Coefficients:        {res['coef_total']:+.3f} (structural / unexplained)")
        print(f"  Intercept diff:      {res['intercept_diff']:+.3f}")
        print(f"\nFactor contributions (country-specific coefs, n=30 → unstable):")
        for _, row in res["contributions"].iterrows():
            print(
                f"  {PRED_LABELS[row['predictor']]:35s}  "
                f"diff = {row['diff']:+7.2f}  "
                f"char = {row['char_contribution']:+.3f}  "
                f"coef = {row['coef_contribution']:+.3f}  "
                f"total = {row['total_contribution']:+.3f}  "
                f"({row['share_of_gap']:+5.1f}%)"
            )

        # Pooled-coefficient (ロバスト版)
        print(f"\n[Pooled-coefficient decomposition (n=60, robust)]")
        print(f"Total characteristics gap: {res['pooled_char_total']:+.3f} pp/yr "
              f"({res['pooled_char_total'] / res['total_gap'] * 100:+.1f}% of total)")
        for _, row in res["pooled"].iterrows():
            print(
                f"  {PRED_LABELS[row['predictor']]:35s}  "
                f"diff = {row['diff']:+7.2f}  "
                f"β_pool = {row['beta_pooled']:+.4f}  "
                f"char = {row['char_contribution']:+.3f}  "
                f"({row['share_of_gap']:+5.1f}% of gap)"
            )

    fig = plot_decomposition(res)
    if verbose:
        print(f"\n  → {fig}")

    contrib_csv = res["contributions"].copy()
    contrib_csv["total_gap"] = res["total_gap"]
    out_csv = PROCESSED_DIR / "japan_stagnation_korea_oaxaca.csv"
    contrib_csv.to_csv(out_csv, index=False)
    if verbose:
        print(f"  → {out_csv}")

    return res


if __name__ == "__main__":
    run()
