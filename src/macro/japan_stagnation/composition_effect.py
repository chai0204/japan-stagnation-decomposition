"""労働構成効果分析：女性・パート労働拡大が日本の生産性・賃金指標に与える影響.

ユーザーの仮説:
    日本では女性・高齢者・学生のパートタイム労働者が大幅に拡大したため、
    雇用者ベースの生産性・賃金指標が「構成変化」で見かけ上低くなる.
    この変化が日本固有なら、per-employee 指標は信頼できない.

検証する3つの問い:
    Q1: 女性労働参加率の変化は日本固有か、G7 共通か？
    Q2: 1人あたり労働時間の変化は日本固有か？
    Q3: per-WA GDP（構成効果非依存）と per-hour GDP（時間調整）と
        賃金（雇用者ベース、構成効果あり）でどう結論が変わるか？

データ:
    - WDI 労働参加率（性別別、15-64）
    - FRED 年間労働時間（OECD MEI）
    - 既存の WDI パネル

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - lfp_female_g7.png
        - hours_per_worker_g7.png
        - composition_adjusted_productivity.png
        - composition_adjusted_wages.png
    data/processed/
        - japan_stagnation_composition_effect.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.collectors.wdi_labor_collector import COUNTRIES, load_country as load_labor
from src.collectors.g7_hours_collector import load as load_hours
from src.collectors.g7_wage_collector import load_country as load_wage_country
from src.macro.japan_stagnation.stylized_facts import (
    COLOR, COUNTRY_LABEL, COUNTRY_ORDER, FIG_DIR, PROCESSED_DIR, load_panel,
)


# ── データ統合 ────────────────────────────────────────────────────────────────

def build_composition_panel() -> pd.DataFrame:
    """WDI 労働構成 + WDI 経済 + FRED 労働時間 + FRED 賃金 を統合."""
    # 労働構成
    lab_frames = []
    for c in COUNTRIES:
        df = load_labor(c)
        if df.empty:
            continue
        df = df.copy()
        df["country"] = c
        lab_frames.append(df.reset_index())
    lab = pd.concat(lab_frames, ignore_index=True)

    # 労働時間
    hours = load_hours()

    # 賃金
    wage_frames = []
    for c in COUNTRIES:
        df = load_wage_country(c)
        if df.empty:
            continue
        df = df.copy()
        df["country"] = c
        wage_frames.append(df.reset_index())
    wage = pd.concat(wage_frames, ignore_index=True)

    # WDI 経済
    wdi = load_panel().reset_index()

    # 結合
    panel = pd.merge(wdi, lab, on=["year", "country"], how="left")
    panel = pd.merge(panel, hours, on=["year", "country"], how="left")
    panel = pd.merge(panel, wage, on=["year", "country"], how="left")

    return panel


# ── 派生指標 ──────────────────────────────────────────────────────────────────

def add_derived(panel: pd.DataFrame) -> pd.DataFrame:
    df = panel.copy()
    # employment estimate（就業率 × 15+ 人口の代理として 15-64 を使用）
    df["employed_estimate"] = df["employment_rate_total"] / 100 * df["population_15_64"]
    # GDP per employee（構成効果あり）
    df["gdp_per_employee"] = df["gdp_real"] / df["employed_estimate"]
    # 総労働時間
    df["total_hours"] = df["employed_estimate"] * df["hours_per_worker"]
    # GDP per hour（最も構成効果に頑健）
    df["gdp_per_hour"] = df["gdp_real"] / df["total_hours"]
    # GDP per WA（再確認）
    df["gdp_per_wa"] = df["gdp_real"] / df["population_15_64"]
    # 賃金 per hour（時間調整賃金）
    df["wage_per_hour"] = df["real_wage"] / df["hours_per_worker"]
    return df


# ── Q1: 女性労働参加率の比較 ──────────────────────────────────────────────────

def plot_female_lfp(panel: pd.DataFrame) -> Path:
    df = panel.dropna(subset=["lfp_female_15_64"])
    fig, ax = plt.subplots(figsize=(11, 6))
    for c in COUNTRY_ORDER:
        sub = df[df["country"] == c].sort_values("year")
        if sub.empty:
            continue
        lw = 2.5 if c == "JPN" else 1.3
        alpha = 1.0 if c == "JPN" else 0.7
        ax.plot(sub["year"], sub["lfp_female_15_64"],
                label=COUNTRY_LABEL[c], color=COLOR[c],
                linewidth=lw, alpha=alpha)
    ax.set_title("Female Labor Force Participation Rate (15-64) — G7 + Korea",
                  fontsize=11, fontweight="bold")
    ax.set_xlabel("Year")
    ax.set_ylabel("% of women aged 15-64")
    ax.grid(True, alpha=0.3)
    ax.legend(ncol=4, loc="best", fontsize=9, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / "lfp_female_g7.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── Q2: 1人あたり労働時間の比較 ─────────────────────────────────────────────

def plot_hours_per_worker(panel: pd.DataFrame) -> Path:
    df = panel.dropna(subset=["hours_per_worker"])
    fig, ax = plt.subplots(figsize=(11, 6))
    for c in COUNTRY_ORDER:
        sub = df[df["country"] == c].sort_values("year")
        if sub.empty:
            continue
        lw = 2.5 if c == "JPN" else 1.3
        alpha = 1.0 if c == "JPN" else 0.7
        ax.plot(sub["year"], sub["hours_per_worker"],
                label=COUNTRY_LABEL[c], color=COLOR[c],
                linewidth=lw, alpha=alpha)
    ax.set_title("Average Annual Hours Worked per Worker — G7 + Korea",
                  fontsize=11, fontweight="bold")
    ax.set_xlabel("Year")
    ax.set_ylabel("Hours / year")
    ax.grid(True, alpha=0.3)
    ax.legend(ncol=4, loc="best", fontsize=9, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / "hours_per_worker_g7.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── Q3: 4 指標の累積成長比較 ────────────────────────────────────────────────

def cumulative_idx(panel: pd.DataFrame, var: str, base_year: int = 1995) -> pd.DataFrame:
    rows = []
    for c in panel["country"].unique():
        sub = panel[panel["country"] == c].sort_values("year").dropna(subset=[var])
        if base_year not in sub["year"].values:
            continue
        base = sub.loc[sub["year"] == base_year, var].iloc[0]
        if base == 0 or pd.isna(base):
            continue
        for _, row in sub.iterrows():
            rows.append({
                "year": row["year"],
                "country": c,
                "var": var,
                "index": row[var] / base * 100,
            })
    return pd.DataFrame(rows)


def plot_4indicators(panel: pd.DataFrame, base_year: int = 1995) -> Path:
    indicators = [
        ("gdp_per_wa",       "GDP per Working-Age (no composition bias)"),
        ("gdp_per_employee", "GDP per Employee (composition affected)"),
        ("gdp_per_hour",     "GDP per Hour (most composition-robust)"),
        ("real_wage",        "Real Wage per Worker (composition affected)"),
    ]
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharex=True)
    axes = axes.flatten()

    for ax, (var, title) in zip(axes, indicators):
        ci = cumulative_idx(panel, var, base_year)
        for c in COUNTRY_ORDER:
            sub = ci[ci["country"] == c].sort_values("year")
            if sub.empty:
                continue
            lw = 2.5 if c == "JPN" else 1.2
            alpha = 1.0 if c == "JPN" else 0.6
            ax.plot(sub["year"], sub["index"],
                    label=COUNTRY_LABEL[c], color=COLOR[c],
                    linewidth=lw, alpha=alpha)
        ax.axhline(100, color="black", linewidth=0.5, linestyle=":", alpha=0.5)
        ax.set_title(title, fontsize=10)
        ax.grid(True, alpha=0.3)
        ax.set_ylabel(f"Index ({base_year}=100)")

    axes[0].legend(ncol=2, loc="upper left", fontsize=8, framealpha=0.85)
    for ax in axes[2:]:
        ax.set_xlabel("Year")

    fig.suptitle("Four Productivity/Wage Indicators: Composition Effect Comparison",
                 fontsize=12, fontweight="bold", y=1.00)
    fig.tight_layout()

    out = FIG_DIR / "composition_adjusted_productivity.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── サマリー表：4 指標の 1995-2023 累積成長率 ───────────────────────────────

def compute_summary(panel: pd.DataFrame, base: int = 1995, end: int = 2023) -> pd.DataFrame:
    rows = []
    for c in COUNTRY_ORDER:
        row = {"country": COUNTRY_LABEL[c]}
        for var, label in [
            ("gdp_per_wa",       "per_WA"),
            ("gdp_per_employee", "per_employee"),
            ("gdp_per_hour",     "per_hour"),
            ("real_wage",        "real_wage"),
            ("wage_per_hour",    "wage_per_hour"),
            ("lfp_female_15_64", "female_lfp"),
            ("hours_per_worker", "hours_per_worker"),
        ]:
            sub = panel[(panel["country"] == c) &
                         (panel["year"].isin([base, end]))].dropna(subset=[var])
            if len(sub) < 2:
                row[f"{label}_growth_pct"] = np.nan
                continue
            v0 = sub.loc[sub["year"] == base, var].iloc[0]
            v1 = sub.loc[sub["year"] == end, var].iloc[0]
            if v0 == 0 or pd.isna(v0):
                row[f"{label}_growth_pct"] = np.nan
                continue
            row[f"{label}_growth_pct"] = (v1 / v0 - 1) * 100
        rows.append(row)
    return pd.DataFrame(rows)


# ── メイン ────────────────────────────────────────────────────────────────────

def fit_time_adjusted_panel(panel: pd.DataFrame) -> pd.DataFrame:
    """時間調整 + 雇用者ベースの両方で Japan ダミー回帰.

    5 年差分の年率成長率を計算し、複数の被説明変数で日本ダミーを推定.
    """
    import statsmodels.formula.api as smf

    df = panel.copy()
    rows = []
    for c in df["country"].unique():
        sub = df[df["country"] == c].set_index("year").sort_index()
        years = sub.index.tolist()
        for y in years:
            y0 = y - 5
            if y0 not in sub.index:
                continue
            row = {"country": c, "year_end": y, "japan": int(c == "JPN")}
            for g, col in [
                ("g_real_wage",        "real_wage"),
                ("g_wage_per_hour",    "wage_per_hour"),
                ("g_gdp_per_wa",       "gdp_per_wa"),
                ("g_gdp_per_employee", "gdp_per_employee"),
                ("g_gdp_per_hour",     "gdp_per_hour"),
            ]:
                v0 = sub.loc[y0, col] if col in sub.columns else np.nan
                v1 = sub.loc[y, col] if col in sub.columns else np.nan
                if pd.notna(v0) and pd.notna(v1) and v0 > 0:
                    row[g] = ((v1 / v0) ** (1.0 / 5) - 1.0) * 100
                else:
                    row[g] = np.nan
            rows.append(row)
    diff = pd.DataFrame(rows)

    # 各 specification
    specs = [
        ("WC1", "g_real_wage ~ g_gdp_per_wa + japan + C(year_end)",
                "Wage/worker ~ GDP/WA + Japan"),
        ("WC2", "g_wage_per_hour ~ g_gdp_per_hour + japan + C(year_end)",
                "Wage/hour ~ GDP/hour + Japan (composition-adjusted)"),
        ("WC3", "g_wage_per_hour ~ g_gdp_per_hour + japan + C(year_end) + C(country)",
                "Wage/hour + country FE"),
    ]

    results = []
    for mid, formula, label in specs:
        # 必要な変数を抽出して dropna
        dep = formula.split("~")[0].strip()
        rhs = formula.split("~")[1]
        # シンプルに必要列を抽出
        needed = [dep, "japan", "year_end", "country"]
        if "g_gdp_per_wa" in rhs:
            needed.append("g_gdp_per_wa")
        if "g_gdp_per_hour" in rhs:
            needed.append("g_gdp_per_hour")
        sub_df = diff[needed].dropna()
        try:
            model = smf.ols(formula, data=sub_df)
            fit = model.fit(cov_type="cluster", cov_kwds={"groups": sub_df["country"]})
            results.append({
                "model":     mid,
                "label":     label,
                "n_obs":     int(fit.nobs),
                "r_squared": fit.rsquared,
                "japan_coef": fit.params.get("japan", np.nan),
                "japan_se":   fit.bse.get("japan", np.nan),
                "japan_p":    fit.pvalues.get("japan", np.nan),
            })
        except Exception as e:
            results.append({"model": mid, "label": label, "error": str(e)})
    return pd.DataFrame(results), diff


def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== 構成効果分析：女性・パート労働拡大の影響 ===")

    panel = build_composition_panel()
    panel = add_derived(panel)

    if verbose:
        print(f"  パネル: {panel.shape[0]} 行")

    p1 = plot_female_lfp(panel)
    p2 = plot_hours_per_worker(panel)
    p3 = plot_4indicators(panel)

    summary = compute_summary(panel, base=1995, end=2023)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = PROCESSED_DIR / "japan_stagnation_composition_effect.csv"
    summary.to_csv(out_csv, index=False)

    # 追加: 時間調整パネル回帰
    if verbose:
        print("\n--- 時間調整パネル回帰 ---")
    reg_results, _ = fit_time_adjusted_panel(panel)
    reg_path = PROCESSED_DIR / "japan_stagnation_composition_panel.csv"
    reg_results.to_csv(reg_path, index=False)
    if verbose:
        print(reg_results.round(4).to_string(index=False))

    if verbose:
        print("\n=== 1995-2023 累積成長率（%） ===")
        cols = ["country", "per_WA_growth_pct", "per_employee_growth_pct",
                "per_hour_growth_pct", "real_wage_growth_pct", "wage_per_hour_growth_pct"]
        print(summary[cols].round(1).to_string(index=False))

        print("\n=== 構成変化 1995-2023（%ポイントの絶対変化） ===")
        for c in COUNTRY_ORDER:
            sub = panel[(panel["country"] == c) &
                         (panel["year"].isin([1995, 2023]))]
            if len(sub) < 2:
                continue
            ff = sub.loc[sub["year"] == 1995, "lfp_female_15_64"]
            fl = sub.loc[sub["year"] == 2023, "lfp_female_15_64"]
            hf = sub.loc[sub["year"] == 1995, "hours_per_worker"]
            hl = sub.loc[sub["year"] == 2023, "hours_per_worker"]
            if len(ff) and len(fl):
                d_lfp = fl.iloc[0] - ff.iloc[0]
            else:
                d_lfp = np.nan
            if len(hf) and len(hl):
                d_hours_pct = (hl.iloc[0] / hf.iloc[0] - 1) * 100
            else:
                d_hours_pct = np.nan
            print(f"  {COUNTRY_LABEL[c]:10s}: 女性LFP {d_lfp:+.1f} pp, "
                  f"労働時間 {d_hours_pct:+.1f}%")

        print(f"\n  図1 (女性LFP): {p1}")
        print(f"  図2 (労働時間): {p2}")
        print(f"  図3 (4指標): {p3}")
        print(f"  サマリー: {out_csv}")

    return {"panel": panel, "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="構成効果分析")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
