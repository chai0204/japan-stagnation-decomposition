"""業種別労働生産性分解：日韓・日独の生産性差の源泉を業種別に識別.

仮説（H9 追加）:
    対韓国の生産性差（-2.17%/年）は、製造業ではなくサービス業で支配的.

分析:
    1. 業種別付加価値構成の時系列（製造業・サービス業・農業）
    2. 業種別「相対生産性」 = VA share / employment share
       （>1 ならその業種は平均より生産性高い）
    3. 業種別ドル建て労働生産性の近似
       (sector VA in USD) / (sector emp share × pop_15_64)
    4. 日韓・日独の業種別ギャップ分解

データ:
    - WDI 業種別付加価値・雇用シェア（1995-2024）
    - 既存の WDI パネル（GDP・人口）

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - sector_va_share_time.png
        - sector_relative_productivity.png
        - sector_productivity_jpn_kor_deu.png
    data/processed/
        - japan_stagnation_sector_productivity.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.collectors.wdi_sector_collector import COUNTRIES, load_country
from src.collectors.wdi_labor_collector import load_country as load_labor
from src.collectors.g7_hours_collector import load as load_hours
from src.macro.japan_stagnation.stylized_facts import (
    COLOR, COUNTRY_LABEL, COUNTRY_ORDER, FIG_DIR, PROCESSED_DIR, load_panel,
)


def build_sector_panel() -> pd.DataFrame:
    """業種別データ + WDI パネル + 労働データ + 労働時間を統合."""
    sector_frames = []
    for c in COUNTRIES:
        df = load_country(c)
        if df.empty:
            continue
        df = df.copy()
        df["country"] = c
        sector_frames.append(df.reset_index())
    sector = pd.concat(sector_frames, ignore_index=True)

    # 労働構成（就業率を取得するため）
    lab_frames = []
    for c in COUNTRIES:
        df = load_labor(c)
        if df.empty:
            continue
        df = df.copy()
        df["country"] = c
        lab_frames.append(df.reset_index())
    if lab_frames:
        lab = pd.concat(lab_frames, ignore_index=True)
    else:
        lab = pd.DataFrame()

    # 年間労働時間
    hours = load_hours()

    wdi = load_panel().reset_index()
    panel = pd.merge(wdi, sector, on=["year", "country"], how="inner")
    if not lab.empty:
        panel = pd.merge(panel, lab, on=["year", "country"], how="left")
    if not hours.empty:
        panel = pd.merge(panel, hours, on=["year", "country"], how="left")

    # 派生変数
    # 相対生産性 = VA share / emp share
    panel["industry_rel_prod"] = (
        panel["industry_va_pct"] / panel["industry_emp_pct"]
    )
    panel["services_rel_prod"] = (
        panel["services_va_pct"] / panel["services_emp_pct"]
    )
    panel["agri_rel_prod"] = (
        panel["agri_va_pct"] / panel["agri_emp_pct"]
    )

    # 業種別ドル建て労働生産性（per worker 近似：pop_15_64 を分母）
    panel["industry_prod_usd"] = (
        panel["industry_va_pct"] / 100 * panel["nominal_gdp_usd"]
    ) / (
        panel["industry_emp_pct"] / 100 * panel["population_15_64"]
    )
    panel["services_prod_usd"] = (
        panel["services_va_pct"] / 100 * panel["nominal_gdp_usd"]
    ) / (
        panel["services_emp_pct"] / 100 * panel["population_15_64"]
    )
    panel["overall_prod_usd"] = panel["nominal_gdp_usd"] / panel["population_15_64"]

    # 業種別 per-hour 生産性（時間調整版）
    # 就業者数 = employment_rate × pop_15_64 ÷ 100
    if "employment_rate_total" in panel.columns and "hours_per_worker" in panel.columns:
        panel["employed_estimate"] = (
            panel["employment_rate_total"] / 100 * panel["population_15_64"]
        )
        panel["industry_employed"] = (
            panel["industry_emp_pct"] / 100 * panel["employed_estimate"]
        )
        panel["services_employed"] = (
            panel["services_emp_pct"] / 100 * panel["employed_estimate"]
        )
        panel["industry_total_hours"] = (
            panel["industry_employed"] * panel["hours_per_worker"]
        )
        panel["services_total_hours"] = (
            panel["services_employed"] * panel["hours_per_worker"]
        )
        panel["total_hours_all"] = panel["employed_estimate"] * panel["hours_per_worker"]

        panel["industry_prod_per_hour"] = (
            panel["industry_va_pct"] / 100 * panel["nominal_gdp_usd"]
        ) / panel["industry_total_hours"]
        panel["services_prod_per_hour"] = (
            panel["services_va_pct"] / 100 * panel["nominal_gdp_usd"]
        ) / panel["services_total_hours"]
        panel["overall_prod_per_hour"] = panel["nominal_gdp_usd"] / panel["total_hours_all"]

    return panel


# ── 図1: 業種別付加価値構成の時系列 ─────────────────────────────────────────

def plot_sector_va_time(panel: pd.DataFrame) -> Path:
    fig, axes = plt.subplots(1, 2, figsize=(13, 5.5), sharex=True)

    for ax, var, title in [
        (axes[0], "manufacturing_va_pct", "Manufacturing VA (% of GDP)"),
        (axes[1], "services_va_pct",       "Services VA (% of GDP)"),
    ]:
        for c in COUNTRY_ORDER:
            sub = panel[panel["country"] == c].sort_values("year")
            if sub.empty:
                continue
            lw = 2.5 if c == "JPN" else 1.3
            alpha = 1.0 if c == "JPN" else 0.7
            ax.plot(sub["year"], sub[var],
                     label=COUNTRY_LABEL[c], color=COLOR[c],
                     linewidth=lw, alpha=alpha)
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_xlabel("Year")
        ax.set_ylabel("% of GDP")
        ax.grid(True, alpha=0.3)
    axes[0].legend(ncol=4, loc="best", fontsize=8, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / "sector_va_share_time.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── 図2: 業種別ドル建て労働生産性（日米独韓） ───────────────────────────────

def plot_sector_productivity(panel: pd.DataFrame) -> Path:
    """4 国（日・米・独・韓）の業種別生産性時系列."""
    countries = ["JPN", "USA", "DEU", "KOR"]
    fig, axes = plt.subplots(1, 3, figsize=(16, 5.5), sharex=True)

    for ax, var, title in [
        (axes[0], "industry_prod_usd",  "Industry productivity\n(USD/working-age person)"),
        (axes[1], "services_prod_usd",  "Services productivity\n(USD/working-age person)"),
        (axes[2], "overall_prod_usd",   "Overall productivity\n(GDP/working-age person)"),
    ]:
        for c in countries:
            sub = panel[panel["country"] == c].sort_values("year")
            if sub.empty:
                continue
            lw = 2.5 if c == "JPN" else 1.5
            alpha = 1.0 if c == "JPN" else 0.8
            ax.plot(sub["year"], sub[var] / 1000,
                     label=COUNTRY_LABEL[c], color=COLOR[c],
                     linewidth=lw, alpha=alpha)
        ax.set_title(title, fontsize=11, fontweight="bold")
        ax.set_xlabel("Year")
        ax.set_ylabel("USD thousands per WA person")
        ax.grid(True, alpha=0.3)
        ax.legend(loc="best", fontsize=9, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / "sector_productivity_jpn_kor_deu.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── 図3: 相対生産性（VA share / emp share） ─────────────────────────────────

def plot_relative_productivity(panel: pd.DataFrame) -> Path:
    """近年（2019-2023）平均の業種別相対生産性を国別に."""
    recent = panel[(panel["year"] >= 2019) & (panel["year"] <= 2023)]
    rel = recent.groupby("country").agg(
        industry=("industry_rel_prod", "mean"),
        services=("services_rel_prod", "mean"),
    ).reindex(COUNTRY_ORDER).dropna()

    fig, ax = plt.subplots(figsize=(10, 5.5))
    x = np.arange(len(rel))
    width = 0.35
    ax.bar(x - width / 2, rel["industry"], width, label="Industry",
           color="#1f77b4", alpha=0.85)
    ax.bar(x + width / 2, rel["services"], width, label="Services",
           color="#ff7f0e", alpha=0.85)
    ax.axhline(1.0, color="black", linewidth=0.8, linestyle="--",
                alpha=0.6, label="Average (1.0)")

    ax.set_xticks(x)
    ax.set_xticklabels([COUNTRY_LABEL[c] for c in rel.index])
    ax.set_ylabel("Relative productivity (VA share / employment share)")
    ax.set_title("Sector Relative Productivity, 2019-2023 average\n"
                  "(>1: more productive than economy average)",
                  fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="best", fontsize=9, framealpha=0.85)

    # 日本に強調枠
    if "JPN" in rel.index:
        jp_idx = rel.index.get_loc("JPN")
        ax.axvspan(jp_idx - 0.45, jp_idx + 0.45, alpha=0.08, color="red")

    fig.tight_layout()
    out = FIG_DIR / "sector_relative_productivity.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── 業種別生産性ギャップ分析 ──────────────────────────────────────────────────

def compute_sector_gap_table(panel: pd.DataFrame) -> pd.DataFrame:
    """直近 5 年（2019-2023）の業種別生産性ギャップ（対 USA・対 KOR・対 DEU）."""
    recent = panel[(panel["year"] >= 2019) & (panel["year"] <= 2023)]
    avg = recent.groupby("country").agg(
        ind_prod_usd=("industry_prod_usd", "mean"),
        srv_prod_usd=("services_prod_usd", "mean"),
        all_prod_usd=("overall_prod_usd", "mean"),
        ind_va_pct=("industry_va_pct", "mean"),
        srv_va_pct=("services_va_pct", "mean"),
    )
    if "JPN" not in avg.index:
        return pd.DataFrame()
    jp = avg.loc["JPN"]

    rows = []
    for c in avg.index:
        if c == "JPN":
            continue
        v = avg.loc[c]
        rows.append({
            "vs_country":          COUNTRY_LABEL.get(c, c),
            "industry_prod_jp":    jp["ind_prod_usd"],
            "industry_prod_other": v["ind_prod_usd"],
            "industry_gap_pct":    (jp["ind_prod_usd"] / v["ind_prod_usd"] - 1) * 100,
            "services_prod_jp":    jp["srv_prod_usd"],
            "services_prod_other": v["srv_prod_usd"],
            "services_gap_pct":    (jp["srv_prod_usd"] / v["srv_prod_usd"] - 1) * 100,
            "overall_gap_pct":     (jp["all_prod_usd"] / v["all_prod_usd"] - 1) * 100,
        })
    return pd.DataFrame(rows)


def compute_sector_gap_per_hour(panel: pd.DataFrame) -> pd.DataFrame:
    """直近 5 年（2019-2023）の per-hour 業種別生産性ギャップ."""
    if "industry_prod_per_hour" not in panel.columns:
        return pd.DataFrame()
    recent = panel[(panel["year"] >= 2019) & (panel["year"] <= 2023)]
    avg = recent.groupby("country").agg(
        ind_h=("industry_prod_per_hour", "mean"),
        srv_h=("services_prod_per_hour", "mean"),
        all_h=("overall_prod_per_hour", "mean"),
    ).dropna()
    if "JPN" not in avg.index:
        return pd.DataFrame()
    jp = avg.loc["JPN"]

    rows = []
    for c in avg.index:
        if c == "JPN":
            continue
        v = avg.loc[c]
        rows.append({
            "vs_country":            COUNTRY_LABEL.get(c, c),
            "industry_per_hour_jp":  jp["ind_h"],
            "industry_per_hour_other": v["ind_h"],
            "industry_gap_per_hour_pct": (jp["ind_h"] / v["ind_h"] - 1) * 100,
            "services_per_hour_jp":  jp["srv_h"],
            "services_per_hour_other": v["srv_h"],
            "services_gap_per_hour_pct": (jp["srv_h"] / v["srv_h"] - 1) * 100,
            "overall_gap_per_hour_pct":  (jp["all_h"] / v["all_h"] - 1) * 100,
        })
    return pd.DataFrame(rows)


def plot_sector_per_hour(panel: pd.DataFrame) -> Path:
    """業種別 per-hour 生産性の比較（直近 5 年平均）."""
    if "industry_prod_per_hour" not in panel.columns:
        return None
    recent = panel[(panel["year"] >= 2019) & (panel["year"] <= 2023)]
    avg = recent.groupby("country").agg(
        industry=("industry_prod_per_hour", "mean"),
        services=("services_prod_per_hour", "mean"),
    ).dropna().reindex(COUNTRY_ORDER)

    avg = avg.dropna()
    fig, ax = plt.subplots(figsize=(11, 5.5))
    x = np.arange(len(avg))
    width = 0.35
    ax.bar(x - width / 2, avg["industry"], width, label="Industry per hour",
           color="#1f77b4", alpha=0.85)
    ax.bar(x + width / 2, avg["services"], width, label="Services per hour",
           color="#ff7f0e", alpha=0.85)

    ax.set_xticks(x)
    ax.set_xticklabels([COUNTRY_LABEL[c] for c in avg.index])
    ax.set_ylabel("USD per hour worked")
    ax.set_title("Sector Productivity per Hour Worked (2019-2023 average)\n"
                  "Composition-adjusted productivity",
                  fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="best", fontsize=9, framealpha=0.85)

    if "JPN" in avg.index:
        jp_idx = avg.index.get_loc("JPN")
        ax.axvspan(jp_idx - 0.45, jp_idx + 0.45, alpha=0.08, color="red")

    fig.tight_layout()
    out = FIG_DIR / "sector_productivity_per_hour.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── メイン ────────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== C: 業種別労働生産性分解 ===")

    panel = build_sector_panel()
    if verbose:
        print(f"  パネル: {panel.shape[0]} 行 × {panel.shape[1]} 列")
        print(f"  期間: {panel['year'].min()} - {panel['year'].max()}")
        print(f"  国数: {panel['country'].nunique()}")

    p1 = plot_sector_va_time(panel)
    p2 = plot_sector_productivity(panel)
    p3 = plot_relative_productivity(panel)
    p4 = plot_sector_per_hour(panel)

    gap_table = compute_sector_gap_table(panel)
    if verbose:
        print("\n=== 業種別生産性ギャップ（per-worker：USD/生産年齢1人） ===")
        print(gap_table.round(1).to_string(index=False))

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = PROCESSED_DIR / "japan_stagnation_sector_productivity.csv"
    gap_table.to_csv(out_csv, index=False)

    # per-hour 版（時間調整）
    gap_per_hour = compute_sector_gap_per_hour(panel)
    if not gap_per_hour.empty and verbose:
        print("\n=== 業種別生産性ギャップ（per-hour：USD/時間） ===")
        print(gap_per_hour.round(1).to_string(index=False))
    if not gap_per_hour.empty:
        gap_per_hour.to_csv(
            PROCESSED_DIR / "japan_stagnation_sector_per_hour.csv", index=False
        )

    # 直近 5 年 業種別水準サマリー
    summary = panel[(panel["year"] >= 2019) & (panel["year"] <= 2023)].groupby(
        "country"
    ).agg(
        manufacturing_va_pct=("manufacturing_va_pct", "mean"),
        services_va_pct=("services_va_pct", "mean"),
        industry_prod_usd=("industry_prod_usd", "mean"),
        services_prod_usd=("services_prod_usd", "mean"),
        overall_prod_usd=("overall_prod_usd", "mean"),
    ).reindex(COUNTRY_ORDER)
    summary_path = PROCESSED_DIR / "japan_stagnation_sector_summary.csv"
    summary.to_csv(summary_path)

    if verbose:
        print("\n=== 直近 5 年（2019-2023）業種別水準サマリー ===")
        print(summary.round(2).to_string())

        print(f"\n  図1（業種別 VA シェア時系列）: {p1}")
        print(f"  図2（業種別生産性日米独韓）: {p2}")
        print(f"  図3（相対生産性）: {p3}")

    return {"panel": panel, "gap": gap_table, "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="業種別労働生産性")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
