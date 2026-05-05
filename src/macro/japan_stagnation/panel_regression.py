"""パネル固定効果回帰：人口・国際化指標を統制して日本ダミーを推定する.

仮説 H1 の検証:
    人口要因と国際化指標をコントロールしても日本の成長率は他の G7 諸国と差があるか.

モデル仕様:
    Model 1A:  g_GDP_total ~ Japan_dummy + year_FE
    Model 1B:  g_GDP_per_wa ~ Japan_dummy + year_FE
    Model 1C:  g_GDP_per_wa ~ Japan_dummy + year_FE + aging_share + working_age_growth
    Model 1D:  g_GDP_per_wa ~ Japan_dummy + year_FE + aging + exports_gdp + fdi_outflow
    Model 1E:  g_GDP_per_wa ~ Japan_dummy + country_FE + year_FE  (within transformation)

データ:
    World Bank WDI（8カ国 × 1990-2024）からの 5 年差分パネル.
    成長率は 5 年区間の年率 % として算出（短期循環を除去）.

頑健性:
    - クラスタ標準誤差（国別）
    - サンプル期間サブセット（1995-2024、2000-2019）
    - 韓国除外/含むの両方

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - panel_regression_coefs.png
    data/processed/
        - japan_stagnation_panel_results.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from src.macro.japan_stagnation.stylized_facts import (
    COUNTRY_LABEL, COUNTRY_ORDER, FIG_DIR, PROCESSED_DIR, load_panel,
)


def build_long_panel(
    panel: pd.DataFrame,
    interval: int = 5,
    start: int = 1990,
    end: int = 2024,
) -> pd.DataFrame:
    """5年差分の長形式パネルを構築する.

    Returns:
        DataFrame with columns:
            country, year_end, g_gdp_total, g_gdp_per_wa, g_gdp_per_cap,
            aging_share, exports_gdp_share, fdi_outflows_gdp,
            wa_pop_growth, japan, korea
    """
    df = panel.reset_index().copy()
    df = df[(df["year"] >= start) & (df["year"] <= end)]

    # 派生変数
    df["aging_share"] = 1 - df["population_15_64"] / df["population"]
    df["gdp_per_wa"] = df["gdp_real"] / df["population_15_64"]

    rows = []
    for c in df["country"].unique():
        sub = df[df["country"] == c].set_index("year").sort_index()
        years = sorted(sub.index)
        for y in years:
            y0 = y - interval
            if y0 not in sub.index:
                continue
            row = {
                "country": c,
                "year_end": y,
                "year_start": y0,
            }
            # 年率成長率（%）
            for level, col in [
                ("g_gdp_total",   "gdp_real"),
                ("g_gdp_per_wa",  "gdp_per_wa"),
                ("g_gdp_per_cap", "gdp_per_capita"),
            ]:
                v0, v1 = sub.loc[y0, col], sub.loc[y, col]
                if pd.notna(v0) and pd.notna(v1) and v0 > 0:
                    row[level] = ((v1 / v0) ** (1.0 / interval) - 1.0) * 100
                else:
                    row[level] = np.nan

            # 人口要因
            v0, v1 = sub.loc[y0, "population_15_64"], sub.loc[y, "population_15_64"]
            row["wa_pop_growth"] = (
                ((v1 / v0) ** (1.0 / interval) - 1.0) * 100 if v0 > 0 else np.nan
            )

            # コントロール変数（期間平均）
            window = sub.loc[y0:y]
            row["aging_share"] = window["aging_share"].mean()
            row["exports_gdp_share"] = window["exports_gdp_share"].mean()
            row["fdi_outflows_gdp"] = window["fdi_outflows_gdp"].mean()

            row["japan"] = int(c == "JPN")
            row["korea"] = int(c == "KOR")
            rows.append(row)

    return pd.DataFrame(rows).dropna(subset=["g_gdp_total", "g_gdp_per_wa"])


# ── モデル仕様 ────────────────────────────────────────────────────────────────

MODELS: dict[str, dict] = {
    "1A": {
        "dep": "g_gdp_total",
        "formula": "g_gdp_total ~ japan + C(year_end)",
        "label": "Total GDP — Japan dummy + year FE",
    },
    "1B": {
        "dep": "g_gdp_per_wa",
        "formula": "g_gdp_per_wa ~ japan + C(year_end)",
        "label": "Per-WA GDP — Japan dummy + year FE",
    },
    "1C": {
        "dep": "g_gdp_per_wa",
        "formula": "g_gdp_per_wa ~ japan + aging_share + wa_pop_growth + C(year_end)",
        "label": "Per-WA GDP — + aging + WA growth",
    },
    "1D": {
        "dep": "g_gdp_per_wa",
        "formula": "g_gdp_per_wa ~ japan + aging_share + wa_pop_growth + exports_gdp_share + fdi_outflows_gdp + C(year_end)",
        "label": "Per-WA GDP — + intl indicators",
    },
    "1E": {
        "dep": "g_gdp_per_wa",
        "formula": "g_gdp_per_wa ~ japan + aging_share + wa_pop_growth + exports_gdp_share + fdi_outflows_gdp + C(year_end) + C(country)",
        "label": "Per-WA GDP — + country FE",
    },
}


def fit_model(
    df: pd.DataFrame,
    formula: str,
    cluster_col: str = "country",
) -> dict:
    """OLS with cluster-robust SE (clustered by country)."""
    model = smf.ols(formula, data=df)
    fit = model.fit(
        cov_type="cluster",
        cov_kwds={"groups": df[cluster_col]},
    )
    # japan 係数の抽出
    if "japan" in fit.params.index:
        japan_coef = fit.params["japan"]
        japan_se = fit.bse["japan"]
        japan_t = fit.tvalues["japan"]
        japan_p = fit.pvalues["japan"]
    else:
        japan_coef = japan_se = japan_t = japan_p = np.nan
    return {
        "n_obs": int(fit.nobs),
        "r_squared": fit.rsquared,
        "japan_coef": japan_coef,
        "japan_se": japan_se,
        "japan_t": japan_t,
        "japan_p": japan_p,
        "fit": fit,
    }


def run_all_models(
    df: pd.DataFrame,
    sample_label: str,
) -> pd.DataFrame:
    rows = []
    for mid, spec in MODELS.items():
        try:
            res = fit_model(df, spec["formula"])
            rows.append({
                "model": mid,
                "label": spec["label"],
                "dep_var": spec["dep"],
                "sample": sample_label,
                "n_obs": res["n_obs"],
                "r_squared": res["r_squared"],
                "japan_coef": res["japan_coef"],
                "japan_se": res["japan_se"],
                "japan_t": res["japan_t"],
                "japan_p": res["japan_p"],
                "ci_lo_95": res["japan_coef"] - 1.96 * res["japan_se"],
                "ci_hi_95": res["japan_coef"] + 1.96 * res["japan_se"],
            })
        except Exception as e:
            rows.append({
                "model": mid,
                "label": spec["label"],
                "dep_var": spec["dep"],
                "sample": sample_label,
                "error": str(e),
            })
    return pd.DataFrame(rows)


# ── 図: 日本ダミー係数の比較 ──────────────────────────────────────────────────

def plot_japan_coefficient(results: pd.DataFrame) -> Path:
    df = results.dropna(subset=["japan_coef"]).copy()
    fig, ax = plt.subplots(figsize=(11, 6))

    # サンプル別に色分け、モデル別に位置
    samples = df["sample"].unique()
    n_models = df["model"].nunique()
    n_samples = len(samples)
    width = 0.8 / n_samples

    colors = {"full (1995-2024)": "#1f77b4", "pre-COVID (1995-2019)": "#ff7f0e",
              "ex-Korea (1995-2024)": "#2ca02c"}

    model_ids = sorted(df["model"].unique())
    x_base = np.arange(n_models)

    for i, sample in enumerate(samples):
        sub = df[df["sample"] == sample].set_index("model").reindex(model_ids)
        x = x_base + (i - (n_samples - 1) / 2) * width
        ax.errorbar(
            x, sub["japan_coef"],
            yerr=1.96 * sub["japan_se"],
            fmt="o", capsize=4, capthick=1.2,
            label=sample,
            color=colors.get(sample, "gray"),
            markersize=8, linewidth=1.5,
        )

    ax.axhline(0, color="black", linewidth=0.6, linestyle="-")
    ax.set_xticks(x_base)
    ax.set_xticklabels(model_ids)
    ax.set_xlabel("Model specification")
    ax.set_ylabel("Japan dummy coefficient (% per year)\n[negative = Japan slower]")
    ax.set_title("Japan Dummy Coefficient with 95% CI Across Specifications",
                 fontsize=12, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="best", fontsize=9, framealpha=0.85)

    # モデルラベルのアノテーション
    for i, mid in enumerate(model_ids):
        label = MODELS[mid]["label"]
        ax.annotate(label, (i, ax.get_ylim()[0]),
                    xytext=(0, -22), textcoords="offset points",
                    ha="center", va="top", fontsize=7, alpha=0.7,
                    rotation=15)

    fig.tight_layout()
    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / "panel_regression_coefs.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── メイン ────────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== Phase 1: Panel Regression ===")

    panel = load_panel()

    # 各サブサンプルでパネル構築
    full_panel = build_long_panel(panel, interval=5, start=1990, end=2024)
    pre_covid = build_long_panel(panel, interval=5, start=1990, end=2019)

    # 韓国除外（G7のみ）
    full_no_korea = full_panel[full_panel["country"] != "KOR"]

    if verbose:
        print(f"  Full panel:        {len(full_panel)} obs ({full_panel['country'].nunique()} countries)")
        print(f"  Pre-COVID panel:   {len(pre_covid)} obs")
        print(f"  Ex-Korea panel:    {len(full_no_korea)} obs")

    samples = [
        (full_panel,    "full (1995-2024)"),
        (pre_covid,     "pre-COVID (1995-2019)"),
        (full_no_korea, "ex-Korea (1995-2024)"),
    ]

    all_results = []
    for df, label in samples:
        res = run_all_models(df, label)
        all_results.append(res)
    results = pd.concat(all_results, ignore_index=True)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = PROCESSED_DIR / "japan_stagnation_panel_results.csv"
    # fit オブジェクトは保存しない
    results.to_csv(out_csv, index=False)

    fig_path = plot_japan_coefficient(results)

    if verbose:
        print("\n=== 主要結果（Full sample 1995-2024） ===")
        full = results[results["sample"] == "full (1995-2024)"]
        cols = ["model", "label", "n_obs", "r_squared",
                "japan_coef", "japan_se", "japan_p", "ci_lo_95", "ci_hi_95"]
        print(full[cols].round(4).to_string(index=False))

        print("\n=== Pre-COVID (1995-2019) ===")
        pre = results[results["sample"] == "pre-COVID (1995-2019)"]
        print(pre[cols].round(4).to_string(index=False))

        print("\n=== Ex-Korea (1995-2024) ===")
        ek = results[results["sample"] == "ex-Korea (1995-2024)"]
        print(ek[cols].round(4).to_string(index=False))

        print(f"\n  図: {fig_path}")
        print(f"  結果: {out_csv}")

    return {"results": results, "panel": full_panel}


def main() -> None:
    parser = argparse.ArgumentParser(description="日本停滞 Phase 1 パネル回帰")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
