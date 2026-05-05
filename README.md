# Decomposing Japan's "Stagnation"

**Demographics, Internationalization, and Wage-Productivity Transmission — A Multi-Model Analysis**

[![License: MIT (code) / CC-BY-4.0 (paper)](https://img.shields.io/badge/license-MIT%2FCC--BY--4.0-blue)](LICENSE)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/)
[![Status: Working Paper](https://img.shields.io/badge/status-working%20paper-yellow)](abstract_en.md)

---

## Overview / 概要

This is the working paper and replication package for an empirical analysis of Japan's economic stagnation across the G7, Korea, and Nordic countries (1990–2024).

This work tests 10 hypotheses across 4 theoretical model variants (Static → DSGE → HANK → HANK+DSGE) and arrives at a unified diagnosis: Japan's "stagnation" is largely demographic + measurement, but **wage-productivity transmission failure** and **service-sector low productivity** are the truly Japan-specific challenges.

本リポジトリは、G7・韓国・北欧諸国の 1990-2024 年データを用いた日本経済停滞の実証分析の論文と再現パッケージです。

10 仮説 × 4 階層の理論モデル（Static → DSGE → HANK → HANK+DSGE）で検証し、「日本停滞」の正体は**人口要因と測定問題**で大半説明されるが、**賃金 - 生産性分配の機能不全**と**サービス業生産性の低水準**こそが真の日本固有問題と結論づけます。

---

## Key Findings / 主要な発見

| Finding | Detail |
|---|---|
| **H1**: Per-working-age GDP equality | Japan = G7 average (β=−0.011, p=0.93, ex-Korea) |
| **H8**: Wage stagnation is uniquely Japanese | Japan dummy = −2.35%/yr (per-hour, robust to HAC SE) |
| **H9**: Productivity gap is in services, not manufacturing | −31% vs Germany, −36% vs USA per-hour |
| **H6**: Capital outflow is a consequence, not a cause | Granger: GDP→CA p=0.094, CA→GDP p=0.346 |
| Labor share decline (1995-2019) | Japan −7.2pp (largest in G7); Korea +3.6pp (only positive) |
| Combined reform welfare gain (HANK+DSGE) | +25.8% lifetime CE welfare, 95% of population benefits |

---

## Repository Structure

```
.
├── paper_ja.md          # Full Japanese paper (~2,200 lines, 28 tables, 56 figures)
├── abstract_en.md       # English title, abstract, JEL codes (for SSRN)
├── README.md            # This file
├── LICENSE              # MIT for code + CC-BY-4.0 for paper text
├── CITATION.cff         # Citation metadata
├── REPLICATION.md       # Step-by-step replication instructions
└── figures/             # All 56 figures (PNG)
```

The analysis code is at `src/macro/japan_stagnation/` (within the parent `econ-research` repo) and depends on collectors at `src/collectors/`. See [REPLICATION.md](REPLICATION.md) for end-to-end replication.

---

## Theoretical Model Hierarchy / 理論モデル階層

```
Empirical findings (Phase 0–5)
       ↓
Static counterfactual (Comparative statics)
       ↓
Extended Model (Static + AR1 dynamics)
       ↓
DSGE-light (Perfect-foresight intertemporal optimization)
       ↓
HANK-light (4 heterogeneous household types)
       ↓
HANK+DSGE Full (Dynamics × Heterogeneity)
```

Each tier captures a different aspect of welfare:

| Model | Aggregate welfare gain (Combined reform) | What it captures |
|---|---|---|
| Static | +43.5% | Levels |
| DSGE-light | +8.3% | Transition costs |
| HANK-light | +55.5% | Distribution |
| **HANK+DSGE Full** | **+25.8%** | **Both** (most credible estimate) |

---

## Reproducibility

All data is **publicly accessible**. The collectors fetch from:

- World Bank WDI (REST API)
- FRED (`fredapi`, requires API key in `.env`)
- OECD SDMX (REST API)
- Penn World Tables (embedded values, originally from GGDC)

To replicate:

```bash
# 1. Setup
git clone https://github.com/chai0204/japan-stagnation-decomposition
cd japan-stagnation-decomposition
uv sync

# 2. Get FRED API key (free at https://fred.stlouisfed.org)
echo "FRED_API_KEY=your_key" > .env

# 3. Run analyses (sequential)
uv run python -m src.collectors.wdi_collector
uv run python -m src.macro.japan_stagnation.stylized_facts
uv run python -m src.macro.japan_stagnation.panel_regression
# ... see REPLICATION.md for full sequence
```

Estimated total replication time: 2-4 hours (most of it data fetching from APIs).

---

## Citation

If you use this work, please cite:

```bibtex
@misc{japan_stagnation_2026,
  author       = {Shun Komatsu},
  title        = {Decomposing Japan's Stagnation: Demographics, Internationalization,
                  and Wage-Productivity Transmission},
  year         = {2026},
  howpublished = {Working Paper},
  url          = {https://github.com/chai0204/japan-stagnation-decomposition},
  note         = {Available at SSRN: [ID]}
}
```

See [CITATION.cff](CITATION.cff) for machine-readable citation metadata.

---

## Status & Roadmap

- ✅ **v1.0 (May 2026)**: Japanese version complete. SSRN/GitHub release.
- 🚧 **v1.1 (planned)**: English translation
- 🚧 **v1.2 (planned)**: Submission to *Journal of the Japanese and International Economies*
- 📋 **v2.0 (long-term)**: Extension with continuous-distribution HANK + Bayesian estimation

---

## Acknowledgments

This research was conducted as an independent project. The author is grateful to:
- Authors of the underlying empirical literature (Hayashi-Prescott, Fernández-Villaverde et al., Bahar-Hausmann, Hoshi-Kashyap, Watanabe, Fukao, etc.)
- Public data providers (World Bank, FRED, OECD, IMF, BOJ, Penn World Tables)
- The open-source Python scientific computing community

---

## Contact

For questions, comments, or collaboration:

- GitHub: [https://github.com/chai0204](https://github.com/chai0204)
- Email: junxiaosong508@gmail.com

This work is openly licensed for use, replication, and extension.
