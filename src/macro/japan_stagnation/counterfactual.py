"""政策カウンターファクチュアル：「もし日本が X だったら」の数値シミュレーション.

3 つの主要シナリオ:
    Scenario 1: 労働分配率がドイツ並み（+8.2pp）に回復
        → 賃金水準への直接効果
    Scenario 2: サービス業 per-hour 生産性がドイツ並み（+45%）
        → サービス業の付加価値増 → GDP 増
    Scenario 3: 輸出/GDP が北欧フィンランド並み（+22pp）
        → 輸出主導の追加 GDP

各シナリオで、2024 年の日本 GDP がどう変わるかを推計.
"What-if" 分析として政策議論を定量化.

注意：
    これは構造モデルではなく、観測データに基づく単純な比較統計分析.
    一般均衡効果や動学経路は捕捉しない. あくまで政策議論の出発点.

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - counterfactual_scenarios.png
    data/processed/
        - japan_stagnation_counterfactual.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.collectors.pwt_collector import load as load_pwt
from src.collectors.wdi_collector import load_country
from src.collectors.wdi_sector_collector import load_country as load_sector
from src.macro.japan_stagnation.stylized_facts import FIG_DIR, PROCESSED_DIR


def get_japan_baseline() -> dict:
    """日本の 2019-2023 年平均ベースライン値を取得."""
    wdi = load_country("JPN")
    sector = load_sector("JPN")
    pwt = load_pwt()

    recent_years = [2019, 2020, 2021, 2022, 2023]
    recent_wdi = wdi[wdi.index.isin(recent_years)]
    recent_sector = sector[sector.index.isin(recent_years)]
    recent_pwt = pwt[(pwt["country"] == "JPN") & (pwt["year"] >= 2015)]

    return {
        "gdp_real":              recent_wdi["gdp_real"].mean(),
        "gdp_per_capita":        recent_wdi["gdp_per_capita"].mean(),
        "gdp_per_wa":           (recent_wdi["gdp_real"] / recent_wdi["population_15_64"]).mean(),
        "population":            recent_wdi["population"].mean(),
        "population_15_64":      recent_wdi["population_15_64"].mean(),
        "exports_gdp_share":     recent_wdi["exports_gdp_share"].mean(),
        "fdi_outflows_gdp":      recent_wdi["fdi_outflows_gdp"].mean(),
        "services_va_pct":       recent_sector["services_va_pct"].mean(),
        "industry_va_pct":       recent_sector["industry_va_pct"].mean(),
        "labor_share":           recent_pwt["labor_share"].mean(),
        "nominal_gdp_usd":       recent_sector["nominal_gdp_usd"].mean(),
    }


# ── シナリオ 1: 労働分配率を独並みに ─────────────────────────────────────────

def scenario_labor_share_to_germany(baseline: dict) -> dict:
    """日本の labor_share を独水準に上げると、賃金総額はどれだけ増えるか."""
    pwt = load_pwt()
    deu_ls = pwt[(pwt["country"] == "DEU") & (pwt["year"] == 2019)]["labor_share"].iloc[0]

    jp_ls = baseline["labor_share"]
    delta_pp = (deu_ls - jp_ls) * 100

    # 賃金総額の変化
    gdp_jp = baseline["nominal_gdp_usd"]
    additional_wage_bill_usd = (deu_ls - jp_ls) * gdp_jp

    # 1人あたり賃金増（労働者数で割る）
    workers_proxy = baseline["population_15_64"] * 0.78  # 就業率約78%
    additional_per_worker = additional_wage_bill_usd / workers_proxy

    return {
        "scenario":            "Labor share to Germany (+8.2pp)",
        "baseline_value":      f"LS = {jp_ls:.3f}",
        "counterfactual_value": f"LS = {deu_ls:.3f}",
        "delta_pp":            delta_pp,
        "additional_wage_bill_usd_billion": additional_wage_bill_usd / 1e9,
        "additional_per_worker_usd": additional_per_worker,
        "wage_growth_pct":     (deu_ls / jp_ls - 1) * 100,
    }


# ── シナリオ 2: サービス業生産性を独並みに ────────────────────────────────

def scenario_services_to_germany(baseline: dict) -> dict:
    """サービス業 per-hour 生産性を独水準に上げると GDP がどう増えるか."""
    # 既知: 日本サービス業 per-hour 生産性は独より約 31% 低い
    # 仮に独水準まで追いつくと、サービス業 VA が +31% 増える
    # サービス業 VA share = 69.65% → これが +31% 増えると、新サービス VA は GDP の約 91%
    # しかし他業種との関係で構造再編が起きる
    # 簡略化：サービス業の付加価値が独水準なら、サービス業 VA = 0.6965 × 1.31 = 0.913
    # 全体 GDP 比は: industry (1) + services (1.31) + agri (1.05) で考える

    services_share_jp = baseline["services_va_pct"] / 100
    industry_share_jp = baseline["industry_va_pct"] / 100
    agri_share_jp = 1 - services_share_jp - industry_share_jp

    # 日本サービス業を独水準に押し上げ：サービス業の付加価値が +31% に
    services_uplift_factor = 1.31
    new_services_va = services_share_jp * services_uplift_factor

    # 他業種は変えない（部分均衡）
    new_total_gdp_factor = (industry_share_jp + new_services_va + agri_share_jp)
    additional_gdp_pct = (new_total_gdp_factor - 1) * 100

    return {
        "scenario":           "Services productivity to Germany (+31% per-hour)",
        "baseline_value":     f"Services VA share = {services_share_jp:.2%}",
        "counterfactual_value": f"Services productivity ×1.31",
        "additional_gdp_pct": additional_gdp_pct,
        "additional_gdp_usd_billion": (
            additional_gdp_pct / 100 * baseline["nominal_gdp_usd"] / 1e9
        ),
    }


# ── シナリオ 3: 輸出/GDP をフィンランド並みに ────────────────────────────

def scenario_exports_to_finland(baseline: dict) -> dict:
    """輸出/GDP をフィンランド水準（41%）に上げると GDP 規模がどう増えるか."""
    fin_exports = 41.2  # 直近平均
    jp_exports = baseline["exports_gdp_share"]
    delta_pp = fin_exports - jp_exports

    # 輸出増のうち、GDP への純粋な追加分は輸入の増加で相殺される部分を除く
    # 大まかに: 純輸出 = 輸出 - 輸入。輸出/GDP 上昇のうち、約半分が純 GDP 増と仮定
    additional_gdp_pct = delta_pp * 0.5

    return {
        "scenario":           "Exports/GDP to Finland (+22.3pp)",
        "baseline_value":     f"X/Y = {jp_exports:.1f}%",
        "counterfactual_value": f"X/Y = {fin_exports:.1f}%",
        "delta_pp":           delta_pp,
        "additional_gdp_pct": additional_gdp_pct,
        "additional_gdp_usd_billion": (
            additional_gdp_pct / 100 * baseline["nominal_gdp_usd"] / 1e9
        ),
    }


# ── 統合シナリオ ─────────────────────────────────────────────────────────

def scenario_combined(baseline: dict, ls: dict, srv: dict, exp: dict) -> dict:
    """3 シナリオを同時実現（一部は独立加算、一部は重複）."""
    # 簡略化：労働分配率回復は GDP 増の効果が小さい（再分配のみ）
    # サービス業 + 輸出は GDP に直接効果
    additional_gdp_pct = srv["additional_gdp_pct"] + exp["additional_gdp_pct"]
    additional_wage_pct = ls["wage_growth_pct"] + (additional_gdp_pct * 0.6)  # 賃金の生産性弾力性 0.6

    return {
        "scenario":               "All three combined",
        "additional_gdp_pct":     additional_gdp_pct,
        "additional_wage_pct":    additional_wage_pct,
        "additional_gdp_usd_billion": additional_gdp_pct / 100 * baseline["nominal_gdp_usd"] / 1e9,
    }


# ── プロット ─────────────────────────────────────────────────────────────

def plot_scenarios(scenarios: list[dict]) -> Path:
    fig, ax = plt.subplots(figsize=(11, 5.5))
    labels = [s["scenario"] for s in scenarios]
    gdp_impacts = [s.get("additional_gdp_pct", 0) for s in scenarios]
    wage_impacts = [s.get("wage_growth_pct", s.get("additional_wage_pct", 0)) for s in scenarios]

    x = np.arange(len(labels))
    width = 0.4
    ax.bar(x - width / 2, gdp_impacts, width, label="GDP impact (%)",
           color="#1f77b4", alpha=0.85)
    ax.bar(x + width / 2, wage_impacts, width, label="Wage impact (%)",
           color="#ff7f0e", alpha=0.85)

    ax.axhline(0, color="black", linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=15, ha="right", fontsize=9)
    ax.set_ylabel("Impact (%)")
    ax.set_title("Counterfactual Scenarios: Estimated Impact on Japan's GDP and Wages",
                 fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="best", fontsize=10, framealpha=0.85)
    fig.tight_layout()

    out = FIG_DIR / "counterfactual_scenarios.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── メイン ────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== D-2: 政策カウンターファクチュアル ===")

    baseline = get_japan_baseline()
    if verbose:
        print(f"\n--- 日本ベースライン（2019-2023 平均） ---")
        for k, v in baseline.items():
            if isinstance(v, float):
                print(f"  {k:25s}: {v:,.2f}")

    s1 = scenario_labor_share_to_germany(baseline)
    s2 = scenario_services_to_germany(baseline)
    s3 = scenario_exports_to_finland(baseline)
    s4 = scenario_combined(baseline, s1, s2, s3)

    scenarios = [s1, s2, s3, s4]
    p1 = plot_scenarios(scenarios)

    summary = pd.DataFrame(scenarios)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = PROCESSED_DIR / "japan_stagnation_counterfactual.csv"
    summary.to_csv(out_csv, index=False)

    if verbose:
        print("\n=== シナリオ別影響 ===")
        for s in scenarios:
            print(f"\n[{s['scenario']}]")
            for k, v in s.items():
                if k == "scenario":
                    continue
                if isinstance(v, float):
                    print(f"  {k}: {v:.2f}")
                else:
                    print(f"  {k}: {v}")

        print(f"\n  図: {p1}")
        print(f"  サマリー: {out_csv}")

    return {"scenarios": scenarios, "baseline": baseline}


def main() -> None:
    parser = argparse.ArgumentParser(description="政策カウンターファクチュアル")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
