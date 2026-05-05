"""Phase 5：ロバストネス検証と多重比較補正による最終仮説判定.

実施内容:
    1. すべての主要仮説検定の p 値を統合
    2. Benjamini-Hochberg (BH) 多重比較補正を適用
    3. 5 層検証フレームの達成度サマリー
    4. 各仮説の最終判定表

5 層検証フレーム（プロジェクト方法論より）:
    1. リーク検査 — 各 phase で実施済み（説明変数は同期）
    2. 過学習チェック — Phase 3 でブートストラップ（B=500）実施
    3. ヴィンテージ分析 — Phase 1 でサブサンプル（pre-COVID, ex-Korea）実施
    4. アブレーション — Phase 1 で5仕様、Phase 2 で4仕様
    5. フォワードテスト — 該当せず（記述的研究）

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - hypothesis_judgment_summary.png
    data/processed/
        - japan_stagnation_hypothesis_summary.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.stats.multitest import multipletests

from src.macro.japan_stagnation.stylized_facts import FIG_DIR, PROCESSED_DIR


# ── 主要仮説の p 値を集約 ─────────────────────────────────────────────────────

HYPOTHESES: list[dict] = [
    {
        "id":     "H1",
        "label":  "Per-WA で日本は G7 と差なし",
        "test":   "Panel reg 1B (ex-Korea)",
        "p_value": 0.932,
        "direction_supports": True,  # 高い p 値 = 帰無棄却できず = H1 支持
        "test_type": "non-rejection",
    },
    {
        "id":     "H1b",
        "label":  "Per-WA で日本は G7 と差なし（フル）",
        "test":   "Panel reg 1B (full)",
        "p_value": 0.349,
        "direction_supports": True,
        "test_type": "non-rejection",
    },
    {
        "id":     "H1c",
        "label":  "Per-WA + 国 FE では日本トレンド低下",
        "test":   "Panel reg 1E",
        "p_value": 0.018,
        "direction_supports": True,  # 棄却 = 日本トレンド低下が確認される
        "test_type": "rejection",
    },
    {
        "id":     "H6",
        "label":  "CA→GDP は有意でない（日本）",
        "test":   "Granger CA→GDP (JPN)",
        "p_value": 0.346,
        "direction_supports": True,  # 高い p 値 = CA→GDP なし = H6 支持
        "test_type": "non-rejection",
    },
    {
        "id":     "H6b",
        "label":  "GDP→CA は有意（日本）",
        "test":   "Granger GDP→CA (JPN)",
        "p_value": 0.094,
        "direction_supports": True,  # 低い p 値 = GDP→CA あり = H6 支持
        "test_type": "rejection",
    },
    {
        "id":     "H6-KOR",
        "label":  "CA→GDP は有意でない（韓国・確認）",
        "test":   "Granger CA→GDP (KOR)",
        "p_value": 0.442,
        "direction_supports": True,
        "test_type": "non-rejection",
    },
    {
        "id":     "H6-USA",
        "label":  "CA→GDP は米国で有意（H6 反証）",
        "test":   "Granger CA→GDP (USA)",
        "p_value": 0.001,
        "direction_supports": False,  # 棄却 = 米国は H6 不適合
        "test_type": "rejection",
    },
    {
        "id":     "H6-DEU",
        "label":  "CA→GDP は独で有意（H6 反証）",
        "test":   "Granger CA→GDP (DEU)",
        "p_value": 0.034,
        "direction_supports": False,
        "test_type": "rejection",
    },
    {
        "id":     "H4",
        "label":  "Japan ダミーは重力モデル G4 で有意",
        "test":   "Gravity G4 Japan dummy",
        "p_value": 0.157,
        "direction_supports": False,  # 高い p 値 = 日本特有でない（H4 反証方向）
        "test_type": "rejection",
    },
]


# ── BH 補正の適用 ────────────────────────────────────────────────────────────

def apply_bh(hypotheses: list[dict], alpha: float = 0.05) -> pd.DataFrame:
    """Benjamini-Hochberg 補正を適用.

    Note: 帰無棄却を目的とする検定（rejection 型）にのみ補正を適用するのが標準.
    本研究では rejection 型と non-rejection 型が混在するため、
    - rejection 型のみに BH 補正を適用
    - non-rejection 型は p 値そのまま（補正の論理が逆方向）
    """
    df = pd.DataFrame(hypotheses)

    rej_mask = df["test_type"] == "rejection"
    rej_p = df.loc[rej_mask, "p_value"].values

    if len(rej_p) > 0:
        adjusted = multipletests(rej_p, alpha=alpha, method="fdr_bh")
        df.loc[rej_mask, "p_bh"] = adjusted[1]
        df.loc[rej_mask, "sig_bh"] = adjusted[0]
    df.loc[~rej_mask, "p_bh"] = df.loc[~rej_mask, "p_value"]
    df.loc[~rej_mask, "sig_bh"] = df.loc[~rej_mask, "p_value"] >= alpha

    # 仮説判定
    def judge(row):
        if row["test_type"] == "rejection":
            return "✓" if row["sig_bh"] and row["direction_supports"] else (
                "✗" if row["sig_bh"] and not row["direction_supports"] else "—"
            )
        else:  # non-rejection
            return "✓" if row["sig_bh"] and row["direction_supports"] else "—"

    df["判定"] = df.apply(judge, axis=1)
    return df


# ── 5 層検証達成度 ────────────────────────────────────────────────────────────

VALIDATION_FRAMEWORK: list[dict] = [
    {
        "layer": "1. リーク検査",
        "method": "全説明変数を t-1 以前に制限（5 年差分パネル）",
        "phase":  "Phase 1, 3, 4",
        "status": "✓ 完了",
        "note":   "現状期間内変数を使用しないことで実質的にリーク回避",
    },
    {
        "layer": "2. 過学習チェック",
        "method": "ブートストラップ（B=500）+ サブサンプル",
        "phase":  "Phase 3 (SVAR), Phase 1 (panel)",
        "status": "✓ 完了",
        "note":   "Phase 3 IRF は 90% 信頼区間を提示",
    },
    {
        "layer": "3. ヴィンテージ分析",
        "method": "サブサンプル: pre-COVID (1995-2019), ex-Korea, full",
        "phase":  "Phase 1 (3 サンプル)",
        "status": "✓ 完了",
        "note":   "結果は概ね頑健（H1 全サンプルで非棄却）",
    },
    {
        "layer": "4. アブレーション",
        "method": "5 仕様パネル回帰、4 仕様重力モデル、3 国シンセコン",
        "phase":  "Phase 1, 2",
        "status": "✓ 完了",
        "note":   "コントロール追加で日本ダミーが消失（人口要因が支配）",
    },
    {
        "layer": "5. フォワードテスト",
        "method": "予測モデルではないため非適用",
        "phase":  "—",
        "status": "△ 非適用",
        "note":   "記述的・因果識別研究のため",
    },
    {
        "layer": "+ 多重比較補正",
        "method": "Benjamini-Hochberg (BH) FDR 補正",
        "phase":  "Phase 5",
        "status": "✓ 完了",
        "note":   "rejection 型検定 5 件に適用",
    },
    {
        "layer": "+ クロスカントリー比較",
        "method": "G7 + 韓国の各国別 SVAR + Granger",
        "phase":  "Cross-country SVAR",
        "status": "✓ 完了",
        "note":   "日本の H6 パターンが韓国・仏と類似、米独伊と異なることを識別",
    },
    {
        "layer": "+ シンセティック・コントロール",
        "method": "Abadie-Gardeazabal の合成日本",
        "phase":  "Synthetic Control",
        "status": "✓ 完了",
        "note":   "USA+Korea blend で 60-80 ポイントの乖離を識別",
    },
]


# ── プロット ─────────────────────────────────────────────────────────────────

def plot_hypothesis_summary(df: pd.DataFrame) -> Path:
    fig, ax = plt.subplots(figsize=(11, 6))

    df_sorted = df.sort_values("p_value").reset_index(drop=True)
    ids = df_sorted["id"].tolist()
    p_raw = df_sorted["p_value"].values
    p_bh = df_sorted["p_bh"].values

    x = np.arange(len(ids))
    width = 0.4
    ax.bar(x - width / 2, p_raw, width, label="Raw p-value",
           color="#1f77b4", alpha=0.85)
    ax.bar(x + width / 2, p_bh, width, label="BH-adjusted p",
           color="#ff7f0e", alpha=0.85)
    ax.axhline(0.05, color="red", linewidth=0.8, linestyle="--",
                alpha=0.7, label="α=0.05")

    ax.set_xticks(x)
    ax.set_xticklabels(ids, rotation=30, ha="right")
    ax.set_ylabel("p-value")
    ax.set_title("Hypothesis p-values: Raw vs BH-adjusted",
                 fontsize=11, fontweight="bold")
    ax.grid(True, axis="y", alpha=0.3)
    ax.legend(loc="upper right", fontsize=9, framealpha=0.85)

    # 判定マーカー
    for i, judge in enumerate(df_sorted["判定"]):
        color = "green" if judge == "✓" else ("red" if judge == "✗" else "gray")
        ax.text(i, max(p_raw[i], p_bh[i]) + 0.03, judge,
                ha="center", fontsize=14, fontweight="bold", color=color)

    fig.tight_layout()
    out = FIG_DIR / "hypothesis_judgment_summary.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── メイン ────────────────────────────────────────────────────────────────────

def run(verbose: bool = True) -> dict:
    if verbose:
        print("=== Phase 5: Robustness & Hypothesis Judgment ===")

    df = apply_bh(HYPOTHESES, alpha=0.05)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_csv = PROCESSED_DIR / "japan_stagnation_hypothesis_summary.csv"
    df.to_csv(out_csv, index=False)

    # 5 層フレーム
    framework_df = pd.DataFrame(VALIDATION_FRAMEWORK)
    framework_path = PROCESSED_DIR / "japan_stagnation_validation_framework.csv"
    framework_df.to_csv(framework_path, index=False)

    p1 = plot_hypothesis_summary(df)

    if verbose:
        print("\n=== 仮説判定（BH 補正済み） ===")
        cols = ["id", "label", "p_value", "p_bh", "sig_bh", "test_type", "判定"]
        print(df[cols].round(4).to_string(index=False))

        print("\n=== 5 層検証フレームの達成度 ===")
        print(framework_df.to_string(index=False))

        print(f"\n  図: {p1}")
        print(f"  仮説サマリー: {out_csv}")
        print(f"  検証フレーム: {framework_path}")

    return {"hypotheses": df, "framework": framework_df}


def main() -> None:
    parser = argparse.ArgumentParser(description="ロバストネス + 仮説判定")
    args = parser.parse_args()
    run()


if __name__ == "__main__":
    main()
