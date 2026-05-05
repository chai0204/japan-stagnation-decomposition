"""シンセコン Permutation Test：日本の乖離は統計的に有意か.

Abadie, Diamond & Hainmueller (2010) の placebo test を実装.

手順:
    1. 各国 c を順番に「treated」とし、他の国を donor pool として合成 c を構築
    2. 各 c の actual - synthetic gap を計算
    3. 日本の gap を他国の gap 分布と比較
    4. permutation p-value: |gap_jp| が他国の |gap| 分布の何位か

期待:
    日本の gap が permutation 分布の極端側にあれば、
    シンセコン結果は統計的に有意（H1 強い反証）

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - synthetic_control_permutation.png
    data/processed/
        - japan_stagnation_synth_permutation.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.macro.japan_stagnation.synthetic_control import (
    build_synthetic_japan,
    get_outcome_series,
    normalize_to_base,
    build_predictors_panel,
    fit_synthetic_weights,
)
from src.macro.japan_stagnation.stylized_facts import (
    COLOR, COUNTRY_LABEL, FIG_DIR, PROCESSED_DIR, load_panel,
)


def run_placebo_for_country(
    panel: pd.DataFrame,
    treated: str,
    outcome_var: str = "gdp_per_capita",
    pre_start: int = 1995,
    pre_end: int = 2000,
) -> dict:
    """1 つの placebo（treated として 1 国を指定）."""
    predictors = build_predictors_panel(panel, pre_start, pre_end)
    if treated not in predictors.index:
        return {}

    donors = [c for c in predictors.index if c != treated]
    pred_cols = [c for c in predictors.columns if not predictors[c].isna().any()]

    X_treated = predictors.loc[treated, pred_cols].values.astype(float)
    X_donors = predictors.loc[donors, pred_cols].T.values.astype(float)

    means = X_donors.mean(axis=1, keepdims=True)
    stds = X_donors.std(axis=1, keepdims=True) + 1e-9
    X_treated_z = (X_treated.reshape(-1, 1) - means).flatten() / stds.flatten()
    X_donors_z = (X_donors - means) / stds

    w = fit_synthetic_weights(X_treated_z, X_donors_z)

    outcome = get_outcome_series(panel, var=outcome_var)
    outcome_idx = normalize_to_base(outcome, base_year=pre_start)

    if treated not in outcome_idx.columns:
        return {}
    treated_series = outcome_idx[treated]

    valid_donors = [d for d in donors if d in outcome_idx.columns]
    donor_series = outcome_idx[valid_donors]
    # weights を donors の有効な部分集合に合わせる
    w_dict = dict(zip(donors, w))
    w_valid = np.array([w_dict[d] for d in valid_donors])
    if w_valid.sum() > 0:
        w_valid = w_valid / w_valid.sum()
    synthetic = donor_series.values @ w_valid

    gap = treated_series - pd.Series(synthetic, index=outcome_idx.index)

    return {
        "treated":   treated,
        "actual":    treated_series,
        "synthetic": pd.Series(synthetic, index=outcome_idx.index),
        "gap":       gap,
        "weights":   w_dict,
    }


def run_all_placebos(
    panel: pd.DataFrame,
    outcome_var: str = "gdp_per_capita",
    pre_start: int = 1995,
    pre_end: int = 2000,
) -> dict[str, dict]:
    countries = panel.reset_index()["country"].unique()
    out = {}
    for c in countries:
        try:
            res = run_placebo_for_country(
                panel, c, outcome_var, pre_start, pre_end,
            )
            if res:
                out[c] = res
        except Exception as e:
            print(f"  [{c}] failed: {e}")
    return out


def compute_permutation_p(placebos: dict, end_year: int = 2024) -> dict:
    """日本の gap が他国の gap 分布で何位か."""
    gaps_at_end = {}
    for c, res in placebos.items():
        if end_year in res["gap"].index:
            gaps_at_end[c] = res["gap"].loc[end_year]
    if "JPN" not in gaps_at_end:
        return {}

    jp_gap = gaps_at_end["JPN"]
    other_gaps = {c: g for c, g in gaps_at_end.items() if c != "JPN"}

    # 片側検定（日本は負の方向に大きいか）
    abs_jp = abs(jp_gap)
    abs_others = [abs(g) for g in other_gaps.values()]
    rank_abs = sum(1 for g in abs_others if g >= abs_jp) + 1
    p_abs = rank_abs / (len(abs_others) + 1)

    # signed test
    rank_neg = sum(1 for g in other_gaps.values() if g <= jp_gap) + 1
    p_neg = rank_neg / (len(other_gaps) + 1)

    return {
        "jp_gap":           jp_gap,
        "other_gaps":       other_gaps,
        "permutation_p_abs": p_abs,
        "permutation_p_neg": p_neg,
        "n_countries":       len(other_gaps) + 1,
    }


# ── プロット ─────────────────────────────────────────────────────────────────

def plot_placebo_gaps(placebos: dict, outcome_label: str, suffix: str) -> Path:
    fig, ax = plt.subplots(figsize=(11, 6))

    for c, res in placebos.items():
        gap = res["gap"]
        is_jp = c == "JPN"
        lw = 3.0 if is_jp else 1.0
        alpha = 1.0 if is_jp else 0.4
        color = "#d62728" if is_jp else "gray"
        ax.plot(gap.index, gap.values,
                color=color, linewidth=lw, alpha=alpha,
                label="Japan" if is_jp else None)

    ax.axhline(0, color="black", linewidth=0.6, linestyle=":")
    ax.set_title(f"Placebo Test: Synth Control Gap for {outcome_label}\n"
                  "Each gray line = one country treated as 'treated' (placebo)\n"
                  "Red = Japan (actual)",
                  fontsize=11, fontweight="bold")
    ax.set_xlabel("Year")
    ax.set_ylabel("Actual − Synthetic gap (index points)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=10)
    fig.tight_layout()

    out = FIG_DIR / f"synthetic_control_permutation_{suffix}.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== C-4: Synthetic Control Permutation Test ===")

    panel = load_panel()

    # 1人あたり GDP
    if verbose:
        print("\n--- アウトカム: 1 人あたり GDP ---")
    placebos_pc = run_all_placebos(
        panel, outcome_var="gdp_per_capita",
        pre_start=1995, pre_end=2000,
    )
    perm_pc = compute_permutation_p(placebos_pc, end_year=2024)
    p1 = plot_placebo_gaps(placebos_pc, "GDP per capita", "gdp_pc")

    if verbose and perm_pc:
        print(f"  Japan の 2024 gap: {perm_pc['jp_gap']:+.1f} pt")
        print(f"  他国の gap 分布:")
        for c, g in sorted(perm_pc["other_gaps"].items(), key=lambda x: x[1]):
            print(f"    {COUNTRY_LABEL.get(c, c):10s}: {g:+.1f} pt")
        print(f"  Permutation p-value (片側、絶対値): {perm_pc['permutation_p_abs']:.3f}")
        print(f"  Permutation p-value (片側、負方向): {perm_pc['permutation_p_neg']:.3f}")

    # 生産年齢 1人あたり
    panel_temp = panel.reset_index().copy()
    panel_temp["gdp_per_wa"] = panel_temp["gdp_real"] / panel_temp["population_15_64"]
    panel_per_wa = panel_temp.set_index(["year", "country"])

    if verbose:
        print("\n--- アウトカム: 生産年齢 1 人あたり GDP ---")
    placebos_wa = run_all_placebos(
        panel_per_wa, outcome_var="gdp_per_wa",
        pre_start=1995, pre_end=2000,
    )
    perm_wa = compute_permutation_p(placebos_wa, end_year=2024)
    p2 = plot_placebo_gaps(placebos_wa, "GDP per Working-Age", "gdp_per_wa")

    if verbose and perm_wa:
        print(f"  Japan の 2024 gap: {perm_wa['jp_gap']:+.1f} pt")
        print(f"  Permutation p-value (片側、絶対値): {perm_wa['permutation_p_abs']:.3f}")
        print(f"  Permutation p-value (片側、負方向): {perm_wa['permutation_p_neg']:.3f}")

    # 結果保存
    rows = []
    for label, perm in [("per_capita", perm_pc), ("per_wa", perm_wa)]:
        if perm:
            rows.append({
                "outcome":           label,
                "japan_gap_2024":    perm["jp_gap"],
                "p_value_abs":       perm["permutation_p_abs"],
                "p_value_neg":       perm["permutation_p_neg"],
                "n_countries":       perm["n_countries"],
            })
    summary = pd.DataFrame(rows)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = PROCESSED_DIR / "japan_stagnation_synth_permutation.csv"
    summary.to_csv(out_csv, index=False)

    if verbose:
        print(f"\n  図1: {p1}")
        print(f"  図2: {p2}")
        print(f"  サマリー: {out_csv}")

    return {"per_capita": perm_pc, "per_wa": perm_wa, "summary": summary}


def main() -> None:
    parser = argparse.ArgumentParser(description="Synth Control Permutation Test")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
