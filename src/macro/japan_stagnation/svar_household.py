"""SVAR による家計対外シフトと GDP・賃金の因果方向識別.

仮説 H6 の検証:
    家計対外シフト（経常収支変動を代理）は GDP 成長率の低下の **結果** であり、
    GDP 停滞を引き起こす **原因** ではない可能性が高い.

モデル:
    変数（4 次元、四半期）:
        y1 = Δlog(real GDP)        — 実質 GDP 成長率
        y2 = Δlog(real wage)       — 実質賃金変化率
        y3 = Δ(CA / nominal GDP)   — 経常収支対 GDP 比の変化
        y4 = Δlog(REER)            — 実質実効為替レート変化率

    Cholesky 識別順序:
        Order A（メイン）: GDP → Wage → CA/GDP → REER
            （GDP ショックが賃金 → 対外フロー → 為替の順に伝播）
        Order B（頑健性）: CA/GDP → GDP → Wage → REER
            （対外フローを最も外生として扱う）

検証:
    - Granger 因果検定（CA→GDP / GDP→CA の双方向）
    - インパルス応答関数（直交化、24 期 = 6 年）
    - 分散分解
    - ブートストラップ 90% 信頼区間（B=500）

出力:
    docs/papers/japan-stagnation-decomposition/figures/
        - svar_irf_main.png
        - svar_granger.png
        - svar_variance_decomp.png
    data/processed/
        - japan_stagnation_svar_irf.csv
        - japan_stagnation_svar_granger.csv
"""

from __future__ import annotations

import argparse
import warnings
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from statsmodels.tsa.api import VAR
from statsmodels.tsa.stattools import adfuller, grangercausalitytests

from src.collectors.japan_external_collector import load as load_japan_external
from src.macro.japan_stagnation.stylized_facts import FIG_DIR, PROCESSED_DIR

warnings.filterwarnings("ignore")

VAR_NAMES_MAIN = ["g_gdp", "g_wage", "d_ca_gdp", "g_reer"]
VAR_LABELS = {
    "g_gdp":    "Δlog(Real GDP)",
    "g_wage":   "Δlog(Real Wage)",
    "d_ca_gdp": "Δ(CA / Nominal GDP)",
    "g_reer":   "Δlog(REER)",
}


# ── データ準備 ────────────────────────────────────────────────────────────────

def prepare_data(verbose: bool = True) -> pd.DataFrame:
    raw = load_japan_external()
    if raw.empty:
        raise FileNotFoundError("data/raw/japan_external_quarterly.csv が見つかりません")

    df = raw.copy()
    # Δlog（前期比対数差分 × 100, 単位: %）
    df["g_gdp"]   = np.log(df["real_gdp"]).diff() * 100
    df["g_wage"]  = np.log(df["wage_real_idx"]).diff() * 100
    df["g_reer"]  = np.log(df["reer"]).diff() * 100

    # CA/GDP の差分（CA はすでに % of GDP に近い、ratio として扱い、差分で定常化）
    df["ca_gdp_pct"] = df["current_account"]
    df["d_ca_gdp"] = df["ca_gdp_pct"].diff()

    cols = VAR_NAMES_MAIN
    out = df[cols].dropna().copy()

    if verbose:
        print(f"  サンプル: {len(out)} 期 ({out.index.min().date()} ~ {out.index.max().date()})")
        print(f"  変数: {cols}")
        print(f"  記述統計:")
        print(out.describe().round(4).to_string())
    return out


# ── 単位根検定 ────────────────────────────────────────────────────────────────

def adf_table(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for c in df.columns:
        s = df[c].dropna()
        try:
            stat, p, *_ = adfuller(s, autolag="BIC")
        except Exception:
            stat, p = np.nan, np.nan
        rows.append({"variable": c, "adf_stat": stat, "p_value": p,
                     "stationary_5pct": p < 0.05 if not np.isnan(p) else None})
    return pd.DataFrame(rows)


# ── Granger 因果 ──────────────────────────────────────────────────────────────

def granger_table(df: pd.DataFrame, max_lag: int = 4) -> pd.DataFrame:
    """全ペアの Granger 因果検定（Y → X: X の予測に Y が役立つか）."""
    rows = []
    for x in df.columns:
        for y in df.columns:
            if x == y:
                continue
            sub = df[[x, y]].dropna()
            try:
                res = grangercausalitytests(sub, maxlag=max_lag, verbose=False)
                # 各ラグの F 検定 p 値
                p_values = {l: res[l][0]["ssr_ftest"][1] for l in res}
                min_p = min(p_values.values())
                best_lag = min(p_values, key=p_values.get)
            except Exception:
                p_values = {}
                min_p = np.nan
                best_lag = np.nan
            rows.append({
                "from (Y)": y,
                "to (X)":   x,
                "best_lag": best_lag,
                "min_p":    min_p,
                "sig_5pct": min_p < 0.05 if not np.isnan(min_p) else None,
            })
    return pd.DataFrame(rows)


# ── SVAR 推定 + IRF ──────────────────────────────────────────────────────────

def fit_var(df: pd.DataFrame, max_lag: int = 8, ic: str = "bic"):
    model = VAR(df)
    sel = model.select_order(maxlags=max_lag)
    p = getattr(sel, ic)
    if p is None or p < 1:
        p = 1
    fit = model.fit(p)
    return fit, p, sel


def compute_irf_with_ci(
    fit, periods: int = 24, ortho: bool = True,
    n_boot: int = 500, alpha: float = 0.10, seed: int = 42,
):
    """ブートストラップ信頼区間付き IRF.

    Returns:
        dict[(impulse, response)] = {"point": np.array, "lo": np.array, "hi": np.array}
    """
    rng = np.random.default_rng(seed)
    irf_obj = fit.irf(periods)
    irfs_point = irf_obj.orth_irfs if ortho else irf_obj.irfs

    # ブートストラップ
    n_obs = fit.nobs
    n_vars = len(fit.names)
    boot_irfs = np.zeros((n_boot, periods + 1, n_vars, n_vars))

    resid = fit.resid.values
    coefs = fit.coefs  # shape (k_ar, n_vars, n_vars)
    intercept = fit.intercept
    p = fit.k_ar
    Y = fit.endog  # shape (n_obs + p, n_vars)（lag 含む）

    for b in range(n_boot):
        idx = rng.integers(0, n_obs, size=n_obs)
        boot_resid = resid[idx]
        Y_boot = np.zeros_like(Y)
        Y_boot[:p] = Y[:p]
        for t in range(p, n_obs + p):
            y_t = intercept.copy()
            for k in range(p):
                y_t = y_t + coefs[k] @ Y_boot[t - k - 1]
            y_t = y_t + boot_resid[t - p]
            Y_boot[t] = y_t
        try:
            boot_model = VAR(pd.DataFrame(Y_boot, columns=fit.names))
            boot_fit = boot_model.fit(p)
            boot_irf_obj = boot_fit.irf(periods)
            boot_irfs[b] = boot_irf_obj.orth_irfs if ortho else boot_irf_obj.irfs
        except Exception:
            boot_irfs[b] = irfs_point

    lo = np.quantile(boot_irfs, alpha / 2, axis=0)
    hi = np.quantile(boot_irfs, 1 - alpha / 2, axis=0)

    out: dict[tuple[str, str], dict] = {}
    for i, imp in enumerate(fit.names):
        for j, resp in enumerate(fit.names):
            out[(imp, resp)] = {
                "point": irfs_point[:, j, i],
                "lo":    lo[:, j, i],
                "hi":    hi[:, j, i],
            }
    return out


# ── プロット ─────────────────────────────────────────────────────────────────

def plot_irf_grid(irf_dict: dict, var_names: list[str], periods: int = 24) -> Path:
    n = len(var_names)
    fig, axes = plt.subplots(n, n, figsize=(13, 11), sharex=True)
    horizon = np.arange(periods + 1)

    for i, imp in enumerate(var_names):
        for j, resp in enumerate(var_names):
            ax = axes[j, i]
            d = irf_dict[(imp, resp)]
            ax.plot(horizon, d["point"], color="#1f77b4", linewidth=1.8)
            ax.fill_between(horizon, d["lo"], d["hi"], color="#1f77b4", alpha=0.18)
            ax.axhline(0, color="black", linewidth=0.5, linestyle=":")
            ax.grid(True, alpha=0.25)
            if j == 0:
                ax.set_title(f"Shock: {VAR_LABELS[imp]}", fontsize=10)
            if i == 0:
                ax.set_ylabel(f"Resp: {VAR_LABELS[resp]}", fontsize=9)
            if j == n - 1:
                ax.set_xlabel("Quarters")

    fig.suptitle("Orthogonalized Impulse Response Functions (90% bootstrap CI)",
                 fontsize=12, fontweight="bold", y=1.00)
    fig.tight_layout()

    FIG_DIR.mkdir(parents=True, exist_ok=True)
    out = FIG_DIR / "svar_irf_main.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_granger_heatmap(granger: pd.DataFrame) -> Path:
    pivot = granger.pivot(index="from (Y)", columns="to (X)", values="min_p")
    pivot = pivot.reindex(index=VAR_NAMES_MAIN, columns=VAR_NAMES_MAIN)

    fig, ax = plt.subplots(figsize=(7, 5.5))
    im = ax.imshow(pivot.values, cmap="RdYlGn_r", vmin=0, vmax=0.15, aspect="auto")
    ax.set_xticks(range(len(VAR_NAMES_MAIN)))
    ax.set_yticks(range(len(VAR_NAMES_MAIN)))
    ax.set_xticklabels([VAR_LABELS[v] for v in VAR_NAMES_MAIN], rotation=30, ha="right")
    ax.set_yticklabels([VAR_LABELS[v] for v in VAR_NAMES_MAIN])
    ax.set_xlabel("To (predicted variable)")
    ax.set_ylabel("From (predictor variable)")
    ax.set_title("Granger Causality: minimum p-value across lags 1-4",
                 fontsize=11, fontweight="bold")

    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            v = pivot.values[i, j]
            if pd.isna(v):
                continue
            color = "white" if v < 0.05 else "black"
            ax.text(j, i, f"{v:.3f}", ha="center", va="center", color=color, fontsize=9)
    fig.colorbar(im, ax=ax, label="p-value")
    fig.tight_layout()

    out = FIG_DIR / "svar_granger.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


def plot_variance_decomp(fit, periods: int = 24) -> Path:
    fevd = fit.fevd(periods)
    decomp_array = fevd.decomp  # shape (n_vars, periods, n_vars)
    var_names = fit.names

    n = len(var_names)
    fig, axes = plt.subplots(2, 2, figsize=(12, 8))
    axes = axes.flatten()

    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    horizon = np.arange(1, periods + 1)

    for j, resp in enumerate(var_names):
        ax = axes[j]
        bottom = np.zeros(periods)
        for i, imp in enumerate(var_names):
            v = decomp_array[j, :, i] * 100
            ax.fill_between(horizon, bottom, bottom + v,
                             label=f"Shock: {VAR_LABELS[imp]}",
                             color=colors[i], alpha=0.85)
            bottom += v
        ax.set_title(f"FEVD of {VAR_LABELS[resp]}", fontsize=10)
        ax.set_xlabel("Quarters ahead")
        ax.set_ylabel("Share (%)")
        ax.set_ylim(0, 100)
        ax.grid(True, alpha=0.3)
        if j == 0:
            ax.legend(loc="upper right", fontsize=7, framealpha=0.85)

    fig.suptitle("Forecast Error Variance Decomposition (Cholesky)",
                 fontsize=12, fontweight="bold", y=1.00)
    fig.tight_layout()

    out = FIG_DIR / "svar_variance_decomp.png"
    fig.savefig(out, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return out


# ── メイン ────────────────────────────────────────────────────────────────────

def run(periods: int = 24, n_boot: int = 500, verbose: bool = True) -> dict:
    if verbose:
        print("=== Phase 3: SVAR Household Outward Shift ===")

    df = prepare_data(verbose=verbose)

    # 単位根
    if verbose:
        print("\n--- ADF 単位根検定 ---")
    adf = adf_table(df)
    if verbose:
        print(adf.round(4).to_string(index=False))

    # Granger 因果（記述的）
    if verbose:
        print("\n--- Granger 因果検定（max_lag=4） ---")
    granger = granger_table(df, max_lag=4)
    if verbose:
        print(granger.round(4).to_string(index=False))

    # SVAR フィット
    if verbose:
        print("\n--- VAR ラグ次数選択 ---")
    fit, p, sel = fit_var(df, max_lag=8, ic="bic")
    if verbose:
        print(f"  選択されたラグ: BIC = {p}")
        print(f"  推定: {fit.k_ar} ラグ, {fit.nobs} 観測")

    # IRF（メインの順序）
    if verbose:
        print(f"\n--- IRF 計算（ブートストラップ B={n_boot}） ---")
    irfs = compute_irf_with_ci(fit, periods=periods, ortho=True,
                               n_boot=n_boot, alpha=0.10)

    # IRF を CSV に
    irf_records = []
    for (imp, resp), d in irfs.items():
        for h in range(len(d["point"])):
            irf_records.append({
                "shock": imp, "response": resp, "horizon": h,
                "point": d["point"][h], "lo90": d["lo"][h], "hi90": d["hi"][h],
            })
    irf_df = pd.DataFrame(irf_records)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    irf_path = PROCESSED_DIR / "japan_stagnation_svar_irf.csv"
    irf_df.to_csv(irf_path, index=False)

    granger_path = PROCESSED_DIR / "japan_stagnation_svar_granger.csv"
    granger.to_csv(granger_path, index=False)

    # 図
    p1 = plot_irf_grid(irfs, list(df.columns), periods=periods)
    p2 = plot_granger_heatmap(granger)
    p3 = plot_variance_decomp(fit, periods=periods)

    if verbose:
        print(f"\n=== 出力 ===")
        print(f"  IRF: {p1}")
        print(f"  Granger: {p2}")
        print(f"  分散分解: {p3}")
        print(f"  IRF データ: {irf_path}")
        print(f"  Granger データ: {granger_path}")

        # H6 の検証サマリー
        print("\n=== H6 検証サマリー ===")
        ca_to_gdp = granger[(granger["from (Y)"] == "d_ca_gdp") & (granger["to (X)"] == "g_gdp")]
        gdp_to_ca = granger[(granger["from (Y)"] == "g_gdp") & (granger["to (X)"] == "d_ca_gdp")]
        print(f"  CA → GDP（外生説）: p = {ca_to_gdp['min_p'].iloc[0]:.4f}")
        print(f"  GDP → CA（内生説）: p = {gdp_to_ca['min_p'].iloc[0]:.4f}")

    return {"fit": fit, "granger": granger, "irf": irfs, "lag_selected": p}


def main() -> None:
    parser = argparse.ArgumentParser(description="日本停滞 Phase 3 SVAR")
    parser.add_argument("--periods", type=int, default=24)
    parser.add_argument("--n-boot", type=int, default=500)
    args = parser.parse_args()
    run(periods=args.periods, n_boot=args.n_boot)


if __name__ == "__main__":
    main()
