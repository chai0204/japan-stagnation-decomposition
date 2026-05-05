"""日本経済停滞の記述的事実：4 水準 GDP 比較と国際化指標.

分析内容（Phase 0）:
    - 4 水準の累積成長率比較（総 GDP / 1人あたり / 生産年齢1人あたり / GNI）
    - 輸出/GDP 比の G7 + 韓国比較
    - 対外直接投資フロー/GDP 比の比較
    - GNI - GDP ギャップ（対 GDP %）の比較

入力:
    data/raw/wdi_<country>.csv （8カ国 × 9指標 × 1990-2024）

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - cumulative_growth_4levels.png
        - export_gdp_share.png
        - fdi_outflow_share.png
        - gni_gdp_gap.png
    data/processed/
        - japan_stagnation_stylized_facts.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.collectors.wdi_collector import COUNTRIES, load_country

REPO_ROOT = Path(__file__).parents[3]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
# Auto-detect repo structure: standalone repo (figures/ at root) or
# original econ-research repo (docs/papers/japan-stagnation-decomposition/figures/)
_STANDALONE_FIG = REPO_ROOT / "figures"
_ORIGINAL_FIG = REPO_ROOT / "docs" / "papers" / "japan-stagnation-decomposition" / "figures"
FIG_DIR = _STANDALONE_FIG if _STANDALONE_FIG.exists() else _ORIGINAL_FIG

COUNTRY_ORDER = ["JPN", "USA", "DEU", "FRA", "GBR", "ITA", "CAN", "KOR"]
COUNTRY_LABEL = {
    "JPN": "Japan", "USA": "USA", "DEU": "Germany", "FRA": "France",
    "GBR": "UK", "ITA": "Italy", "CAN": "Canada", "KOR": "Korea",
}

COLOR = {
    "JPN": "#d62728",
    "USA": "#1f77b4",
    "DEU": "#2ca02c",
    "FRA": "#9467bd",
    "GBR": "#8c564b",
    "ITA": "#e377c2",
    "CAN": "#7f7f7f",
    "KOR": "#ff7f0e",
}


# ── データロード ──────────────────────────────────────────────────────────────

def load_panel() -> pd.DataFrame:
    """8 カ国の WDI データを長形式パネルに統合する."""
    frames = []
    for c in COUNTRY_ORDER:
        df = load_country(c)
        if df.empty:
            continue
        df = df.copy()
        df["country"] = c
        frames.append(df.reset_index())
    panel = pd.concat(frames, ignore_index=True)
    return panel.set_index(["year", "country"]).sort_index()


# ── 4 水準累積成長率の計算 ────────────────────────────────────────────────────

def compute_4level_growth(panel: pd.DataFrame, base_year: int = 1995) -> pd.DataFrame:
    """4 水準の指数化累積成長率（基準年 = 100）.

    Levels:
        - total_gdp:        実質 GDP（合計）
        - gdp_per_capita:   1 人あたり実質 GDP
        - gdp_per_wa:       生産年齢 1 人あたり実質 GDP
        - gni_per_capita:   1 人あたり実質 GNI
    """
    df = panel.reset_index().copy()
    # 生産年齢 1人あたり GDP
    df["gdp_per_wa"] = df["gdp_real"] / df["population_15_64"]
    df["gni_per_capita_calc"] = df["gni_real"] / df["population"]

    levels = {
        "total_gdp":        "gdp_real",
        "gdp_per_capita":   "gdp_per_capita",
        "gdp_per_wa":       "gdp_per_wa",
        "gni_per_capita":   "gni_per_capita",
    }

    rows = []
    for level, col in levels.items():
        for c in df["country"].unique():
            sub = df[df["country"] == c].set_index("year")[col].dropna()
            if base_year not in sub.index:
                continue
            base = sub.loc[base_year]
            if base == 0 or pd.isna(base):
                continue
            idx = sub / base * 100
            for y, v in idx.items():
                rows.append({"year": y, "country": c, "level": level, "index": v})
    return pd.DataFrame(rows)


# ── 図1: 4水準の累積成長率 ────────────────────────────────────────────────────

def plot_cumulative_growth_4levels(growth_df: pd.DataFrame, base_year: int = 1995) -> Path:
    fig, axes = plt.subplots(2, 2, figsize=(14, 10), sharex=True)
    axes = axes.flatten()

    titles = {
        "total_gdp":        f"(a) Total Real GDP ({base_year}=100)",
        "gdp_per_capita":   f"(b) Real GDP per Capita ({base_year}=100)",
        "gdp_per_wa":       f"(c) Real GDP per Working-Age Adult ({base_year}=100)",
        "gni_per_capita":   f"(d) Real GNI per Capita ({base_year}=100)",
    }

    for ax, (level, title) in zip(axes, titles.items()):
        sub = growth_df[growth_df["level"] == level]
        for c in COUNTRY_ORDER:
            cs = sub[sub["country"] == c].sort_values("year")
            if cs.empty:
                continue
            lw = 2.5 if c == "JPN" else 1.3
            alpha = 1.0 if c == "JPN" else 0.75
            ax.plot(cs["year"], cs["index"],
                    label=COUNTRY_LABEL[c], color=COLOR[c],
                    linewidth=lw, alpha=alpha)
        ax.axhline(100, color="black", linestyle=":", linewidth=0.8, alpha=0.5)
        ax.set_title(title, fontsize=11)
        ax.grid(True, alpha=0.3)
        ax.set_ylabel("Index")

    axes[0].legend(loc="upper left", ncol=2, fontsize=9, framealpha=0.85)
    for ax in axes[2:]:
        ax.set_xlabel("Year")

    fig.suptitle("Japan vs G7 + Korea: Four Aggregation Levels of Economic Growth",
                 fontsize=13, fontweight="bold", y=1.00)
    fig.tight_layout()

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / "cumulative_growth_4levels.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── 図2: 輸出 / GDP 比 ────────────────────────────────────────────────────────

def plot_export_share(panel: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(11, 6))
    df = panel.reset_index()
    for c in COUNTRY_ORDER:
        sub = df[df["country"] == c].sort_values("year")
        lw = 2.5 if c == "JPN" else 1.3
        alpha = 1.0 if c == "JPN" else 0.75
        ax.plot(sub["year"], sub["exports_gdp_share"],
                label=COUNTRY_LABEL[c], color=COLOR[c],
                linewidth=lw, alpha=alpha)
    ax.set_title("Exports of Goods and Services (% of GDP) — G7 + Korea",
                 fontsize=12, fontweight="bold")
    ax.set_xlabel("Year")
    ax.set_ylabel("% of GDP")
    ax.grid(True, alpha=0.3)
    ax.legend(ncol=4, loc="upper left", fontsize=9, framealpha=0.85)
    fig.tight_layout()

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / "export_gdp_share.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── 図3: 対外 FDI フロー / GDP 比 ─────────────────────────────────────────────

def plot_fdi_outflow(panel: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(11, 6))
    df = panel.reset_index()
    # 5年移動平均（FDIフローはノイズが大きい）
    df = df.sort_values(["country", "year"])
    df["fdi_ma5"] = df.groupby("country")["fdi_outflows_gdp"].transform(
        lambda x: x.rolling(5, min_periods=1).mean()
    )
    for c in COUNTRY_ORDER:
        sub = df[df["country"] == c].sort_values("year")
        lw = 2.5 if c == "JPN" else 1.3
        alpha = 1.0 if c == "JPN" else 0.75
        ax.plot(sub["year"], sub["fdi_ma5"],
                label=COUNTRY_LABEL[c], color=COLOR[c],
                linewidth=lw, alpha=alpha)
    ax.axhline(0, color="black", linestyle=":", linewidth=0.8, alpha=0.5)
    ax.set_title("Outward FDI Flows (% of GDP, 5-year MA) — G7 + Korea",
                 fontsize=12, fontweight="bold")
    ax.set_xlabel("Year")
    ax.set_ylabel("% of GDP")
    ax.grid(True, alpha=0.3)
    ax.legend(ncol=4, loc="upper left", fontsize=9, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / "fdi_outflow_share.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── 図4: GNI - GDP ギャップ（対 GDP %） ───────────────────────────────────────

def compute_gni_gdp_gap(panel: pd.DataFrame) -> pd.DataFrame:
    df = panel.reset_index().copy()
    df["gni_gdp_gap_pct"] = (df["gni_real"] - df["gdp_real"]) / df["gdp_real"] * 100
    return df[["year", "country", "gni_gdp_gap_pct"]].dropna()


def plot_gni_gdp_gap(gap_df: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(11, 6))
    for c in COUNTRY_ORDER:
        sub = gap_df[gap_df["country"] == c].sort_values("year")
        lw = 2.5 if c == "JPN" else 1.3
        alpha = 1.0 if c == "JPN" else 0.75
        ax.plot(sub["year"], sub["gni_gdp_gap_pct"],
                label=COUNTRY_LABEL[c], color=COLOR[c],
                linewidth=lw, alpha=alpha)
    ax.axhline(0, color="black", linestyle=":", linewidth=0.8, alpha=0.5)
    ax.set_title("GNI − GDP Gap (% of GDP) — G7 + Korea",
                 fontsize=12, fontweight="bold")
    ax.set_xlabel("Year")
    ax.set_ylabel("(GNI − GDP) / GDP (%)")
    ax.grid(True, alpha=0.3)
    ax.legend(ncol=4, loc="upper left", fontsize=9, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / "gni_gdp_gap.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── サマリー統計表 ────────────────────────────────────────────────────────────

def compute_summary_table(
    growth_df: pd.DataFrame,
    panel: pd.DataFrame,
    gap_df: pd.DataFrame,
    base_year: int = 1995,
    end_year: int = 2024,
) -> pd.DataFrame:
    """主要指標の最終年値・累積成長率を国別にまとめる."""
    rows = []
    for c in COUNTRY_ORDER:
        row: dict = {"country": COUNTRY_LABEL[c]}
        for level in ["total_gdp", "gdp_per_capita", "gdp_per_wa", "gni_per_capita"]:
            sub = growth_df[(growth_df["country"] == c) & (growth_df["level"] == level)]
            if sub.empty:
                row[f"{level}_pct"] = np.nan
                continue
            sub = sub.sort_values("year")
            last = sub[sub["year"] <= end_year].iloc[-1]
            # 累積成長率 = (index - 100)
            row[f"{level}_pct"] = last["index"] - 100

        # 輸出/GDP（最終年）
        ex = panel.loc[(slice(None), c), "exports_gdp_share"].dropna()
        if len(ex) > 0:
            last_year = ex.index.get_level_values("year").max()
            row["exports_gdp_share_last"] = ex.loc[(last_year, c)]
            row["exports_gdp_share_year"] = int(last_year)

        # 対外FDIフロー（直近10年平均）
        fdi = panel.loc[(slice(None), c), "fdi_outflows_gdp"].dropna()
        if len(fdi) > 0:
            recent = fdi[fdi.index.get_level_values("year") >= 2014]
            row["fdi_outflows_gdp_avg"] = recent.mean()

        # GNI-GDPギャップ（直近5年平均）
        gap = gap_df[(gap_df["country"] == c) & (gap_df["year"] >= 2019)]
        if len(gap) > 0:
            row["gni_gdp_gap_pct_recent"] = gap["gni_gdp_gap_pct"].mean()

        rows.append(row)

    return pd.DataFrame(rows)


# ── メイン ────────────────────────────────────────────────────────────────────

def run_phase0(base_year: int = 1995, end_year: int = 2024, verbose: bool = True) -> dict:
    """Phase 0 全分析を実行する."""
    if verbose:
        print("=== Phase 0: Stylized Facts ===")
        print(f"  基準年: {base_year}, 終了年: {end_year}")

    panel = load_panel()
    if verbose:
        print(f"  パネルデータ: {panel.shape[0]} 行 × {panel.shape[1]} 列")
        print(f"  国数: {panel.index.get_level_values('country').nunique()}")

    growth_df = compute_4level_growth(panel, base_year=base_year)
    gap_df = compute_gni_gdp_gap(panel)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

    # 図表生成
    p1 = plot_cumulative_growth_4levels(growth_df, base_year)
    p2 = plot_export_share(panel)
    p3 = plot_fdi_outflow(panel)
    p4 = plot_gni_gdp_gap(gap_df)

    # サマリー表
    summary = compute_summary_table(growth_df, panel, gap_df, base_year, end_year)
    summary_path = PROCESSED_DIR / "japan_stagnation_stylized_facts.csv"
    summary.to_csv(summary_path, index=False)

    growth_path = PROCESSED_DIR / "japan_stagnation_4level_growth.csv"
    growth_df.to_csv(growth_path, index=False)

    if verbose:
        print("\n=== 出力 ===")
        print(f"  図1: {p1}")
        print(f"  図2: {p2}")
        print(f"  図3: {p3}")
        print(f"  図4: {p4}")
        print(f"  サマリー: {summary_path}")
        print(f"  4水準成長率: {growth_path}")
        print("\n=== サマリー表（基準年 1995=100） ===")
        cols = ["country", "total_gdp_pct", "gdp_per_capita_pct",
                "gdp_per_wa_pct", "gni_per_capita_pct",
                "exports_gdp_share_last", "fdi_outflows_gdp_avg",
                "gni_gdp_gap_pct_recent"]
        for col in cols:
            if col not in summary.columns:
                summary[col] = np.nan
        print(summary[cols].round(2).to_string(index=False))

    return {"summary": summary, "growth": growth_df, "panel": panel, "gap": gap_df}


def main() -> None:
    parser = argparse.ArgumentParser(description="日本停滞 Phase 0 記述的事実分析")
    parser.add_argument("--base-year", type=int, default=1995)
    parser.add_argument("--end-year", type=int, default=2024)
    args = parser.parse_args()
    run_phase0(args.base_year, args.end_year)


if __name__ == "__main__":
    main()
