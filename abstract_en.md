# Decomposing Japan's "Stagnation": Demographics, Internationalization, and Wage-Productivity Transmission — A Multi-Model Analysis

## Working Paper Metadata (for SSRN/arXiv submission)

**Title (English)**:
*Decomposing Japan's Stagnation: Demographics, Internationalization, and Wage-Productivity Transmission — Empirical Analysis with Formal, DSGE, HANK, and HANK+DSGE Models*

**Title (Japanese)**:
日本の「停滞」再考：人口・国際化・家計対外シフトによる G7 比較分析

**Author**: Shun Komatsu
**Affiliation**: Independent Researcher, Tokyo, Japan
**Date**: May 2026
**Version**: 1.0

**JEL Classifications**: E21, E24, F21, F44, J11, J31, O47, O53

**Keywords**: economic stagnation, demographics, per-hour productivity, wage-productivity transmission, labor share, international comparison, household financial assets, HANK, DSGE, formal economic model, Japan, G7

---

## Abstract (English, ~ 350 words)

Japan's long-term stagnation has traditionally been explained by aging demographics and TFP slowdown (Hayashi & Prescott, 2002; Yoshikawa, 2016). However, recent international comparisons challenge this account. Fernández-Villaverde, Ventura, and Yao (2024) show that Japan's per-working-age GDP grew faster than the U.S. during 1998–2019. Bahar, Arcay, Daboin Pacheco, and Hausmann (2024) document that Japan retains the world's highest economic complexity index since 1981, with firms increasingly earning abroad as the GNI–GDP gap widens. These findings reopen the fundamental question: *is Japan actually stagnating?*

This paper systematically tests this question using a panel of G7 countries plus South Korea and Nordic economies (1990–2024) drawn from World Bank WDI, FRED, OECD SDMX, Penn World Tables, and OECD STAN, and develops a four-tier hierarchy of theoretical models to interpret the findings.

**Empirical findings (24 in total)**: (1) Per-working-age GDP growth in Japan is statistically indistinguishable from the G7 average (β = −0.011, p = 0.93, ex-Korea sample); 78–106% of the headline GDP growth gap is demographic. (2) Per-hour productivity growth in Japan is +67% (1995–2024), comparable to the U.S. and exceeding Germany. (3) Yet, Japan's wage growth is uniquely depressed: real wage gains lag productivity by an annualized −2.15% (W1) and −2.35% under per-hour adjustment (WC2), robust to subsamples and HAC standard errors. The labor share fell by 7.2 percentage points (1995–2019), the largest decline in the G7. (4) Service-sector per-hour productivity is 31–36% below Germany and the U.S. — concentrated in professional services and finance, not manufacturing. (5) Cross-country SVAR shows household capital outflow is a *consequence*, not a cause, of stagnation, sharing patterns with Korea and France (net creditor non-financial-center economies).

**Theoretical contributions**: We develop and integrate (i) a formal two-sector small open economy model, (ii) a DSGE-light model with capital adjustment costs and dynamic transitions, (iii) a HANK-light model with four heterogeneous household types, and (iv) a fully integrated HANK+DSGE model. The combined ICT-investment-plus-wage-share reform yields lifetime CE welfare gains of +25.8% (95% of population gains; 5% — self-employed/owners — face transition losses requiring policy compensation), with inequality (Gini-like) declining 44%.

**Policy implications**: Service-sector productivity reform paired with wage-share restoration, supported by transitional compensation for capital owners, can plausibly reverse the visible "Lost 30 Years" pattern over a 10–20 year horizon.

---

## Replication Materials

- **Repository**: https://github.com/chai0204/japan-stagnation-decomposition
- **Programming language**: Python 3.12+
- **Dependencies**: pandas, numpy, statsmodels, scipy, matplotlib
- **Data sources**: All publicly available; collectors fetch from World Bank, FRED, OECD SDMX
- **Reproducibility**: Full pipeline runnable via `make all` (or sequential `uv run python -m ...` commands)

## Citation

Please cite this work as:

```
Komatsu, Shun. (2026). Decomposing Japan's Stagnation: Demographics,
Internationalization, and Wage-Productivity Transmission. Working Paper.
https://github.com/chai0204/japan-stagnation-decomposition
SSRN: [SSRN ID once posted]
```

BibTeX:

```bibtex
@misc{japan_stagnation_2026,
  author       = {Komatsu, Shun},
  title        = {Decomposing Japan's Stagnation: Demographics,
                  Internationalization, and Wage-Productivity Transmission},
  year         = {2026},
  howpublished = {Working Paper},
  url          = {https://github.com/chai0204/japan-stagnation-decomposition}
}
```
