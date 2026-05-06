# Replication Instructions

This document provides step-by-step instructions to replicate all results in the paper *"Decomposing Japan's Stagnation: Demographics, Internationalization, and Wage-Productivity Transmission"*.

---

## Prerequisites

### Exact environment used (for full bit-level reproducibility)

This is the exact environment used to produce all results in the paper:

- **OS**: Linux (Ubuntu 24.04 / WSL2 on Windows 11). Also tested on macOS.
- **Python**: 3.12.3 (specified in `.python-version`)
- **uv**: 0.10.7 or later (recommended package manager)
- **Disk space**: ~5 GB (data + figures)
- **RAM**: 2 GB minimum, 4 GB recommended (SVAR bootstrap with B=500)
- **Internet**: required for API data fetching (~1 GB total)

Library versions are pinned in `uv.lock` (46 transitive dependencies). Key direct dependencies:

| Library | Pinned version |
|---|---|
| pandas | >=2.0 (lock: 2.x) |
| numpy | >=1.26 (lock: 1.26.x) |
| scipy | >=1.11 (lock: 1.x) |
| statsmodels | >=0.14.6 (lock: 0.14.x) |
| linearmodels | >=7.0 (lock: 7.x) |
| matplotlib | >=3.8 (lock: 3.x) |
| fredapi | >=0.5 (lock: 0.5.x) |
| requests | >=2.31 (lock: 2.x) |
| python-dotenv | >=1.0 (lock: 1.x) |

The `uv.lock` file pins exact versions for full reproducibility. Use `uv sync` to install the exact pinned versions.

### Compatibility notes

- Python 3.13: Should work but not extensively tested.
- Python 3.11 or earlier: NOT supported (some modules use 3.12+ syntax).
- Cross-OS reproducibility: Numerical results should match across Linux/macOS/Windows. Original paper results were produced on Linux (WSL2).

### API Keys (free, public)

Create `.env` in the repository root:

```bash
FRED_API_KEY=your_key_here  # https://fred.stlouisfed.org/docs/api/api_key.html
```

OECD SDMX, World Bank WDI, and Penn World Tables require **no API key**.

---

## Setup (exact reproduction)

### Recommended: using uv (fastest, most reproducible)

```bash
# 1. Install uv (one time)
curl -LsSf https://astral.sh/uv/install.sh | sh   # Linux/macOS
# Or: pip install uv

# 2. Clone and sync
git clone https://github.com/chai0204/japan-stagnation-decomposition.git
cd japan-stagnation-decomposition

# 3. Install exact pinned versions from uv.lock
uv sync   # Reads .python-version + uv.lock for full reproducibility

# 4. Set up FRED API key
echo "FRED_API_KEY=your_key" > .env
```

### Alternative: using pip

```bash
git clone https://github.com/chai0204/japan-stagnation-decomposition.git
cd japan-stagnation-decomposition

# Use Python 3.12 specifically
python3.12 -m venv .venv
source .venv/bin/activate

# Install based on pyproject.toml (minimum versions)
pip install -e .

echo "FRED_API_KEY=your_key" > .env
```

**Note**: `pip install -e .` uses minimum-version constraints (`>=`). For exact bit-level reproducibility (matching paper figures and tables exactly), use `uv sync` which reads `uv.lock`. Otherwise, results should still match within numerical precision.

---

## Replication Sequence

The full replication takes **2-4 hours**, mostly waiting for API fetches.

### Phase 0: Data Collection

```bash
# G7 + Korea + Nordic — annual macro panel (World Bank WDI)
uv run python -m src.collectors.wdi_collector

# G7 + Korea quarterly external data (FRED)
uv run python -m src.collectors.g7_external_collector
uv run python -m src.collectors.japan_external_collector

# Wages, hours, labor force composition
uv run python -m src.collectors.g7_wage_collector
uv run python -m src.collectors.g7_hours_collector
uv run python -m src.collectors.wdi_labor_collector

# Sectoral data
uv run python -m src.collectors.wdi_sector_collector

# Services balance (digital deficit)
uv run python -m src.collectors.wdi_services_collector

# Labor share (Penn World Tables, embedded)
uv run python -m src.collectors.pwt_collector

# Service sub-sector (OECD STAN, embedded)
uv run python -m src.collectors.oecd_stan_collector

# OECD SDMX household financial assets
uv run python -m src.collectors.oecd_household_collector
```

Estimated time: 30-60 minutes.

### Phase 1: Stylized Facts (§5)

```bash
uv run python -m src.macro.japan_stagnation.stylized_facts
uv run python -m src.macro.japan_stagnation.growth_accounting
uv run python -m src.macro.japan_stagnation.composition_effect
```

Outputs:
- `figures/cumulative_growth_4levels.png` (Figure 1)
- `figures/growth_decomposition_bars.png` (Figure 5)
- `figures/composition_adjusted_productivity.png`
- Table 1, 2, 3

### Phase 2: Hypothesis Testing (§6.1-6.10)

```bash
# H1: Per-WA equality
uv run python -m src.macro.japan_stagnation.panel_regression

# H6: Capital outflow SVAR
uv run python -m src.macro.japan_stagnation.svar_household
uv run python -m src.macro.japan_stagnation.cross_country_svar
uv run python -m src.macro.japan_stagnation.svar_robustness

# Synthetic control
uv run python -m src.macro.japan_stagnation.synthetic_control
uv run python -m src.macro.japan_stagnation.synthetic_control_permutation

# Oaxaca-Blinder
uv run python -m src.macro.japan_stagnation.oaxaca_blinder

# H4-H5: Gravity (monadic)
uv run python -m src.macro.japan_stagnation.gravity_monadic

# H7: Digital deficit
uv run python -m src.macro.japan_stagnation.digital_deficit

# H8: Wage stagnation
uv run python -m src.macro.japan_stagnation.wage_stagnation

# H9: Sectoral productivity
uv run python -m src.macro.japan_stagnation.sector_productivity

# Final BH-corrected hypothesis verdicts
uv run python -m src.macro.japan_stagnation.robustness
```

Estimated time: 30 minutes.

### Phase 3: Extensions (§6.11)

```bash
uv run python -m src.macro.japan_stagnation.labor_share
uv run python -m src.macro.japan_stagnation.services_subsector
uv run python -m src.macro.japan_stagnation.nordic_comparison
uv run python -m src.macro.japan_stagnation.counterfactual
```

### Phase 4: Cross-country Household Composition (§6.13)

```bash
uv run python -m src.macro.japan_stagnation.household_cross_country
```

### Phase 5: Theoretical Models (§6.12, 6.14, 6.15, 6.16)

```bash
# Static formal model + extended model
uv run python -m src.macro.japan_stagnation.formal_model
uv run python -m src.macro.japan_stagnation.formal_model_extended

# DSGE-light
uv run python -m src.macro.japan_stagnation.dsge_light

# HANK-light
uv run python -m src.macro.japan_stagnation.hank_light

# Full HANK+DSGE integration
uv run python -m src.macro.japan_stagnation.hank_dsge_full
```

### PDF generation (optional)

To regenerate `paper_ja.pdf` and `paper_en.pdf` from the Markdown sources with proper LaTeX math rendering:

```bash
# Install pandoc and LaTeX (Linux)
sudo apt-get install pandoc texlive-luatex texlive-lang-japanese \
    texlive-fonts-recommended texlive-fonts-extra texlive-latex-extra

# Generate both PDFs
python3 build_pdf.py            # builds paper_ja.pdf and paper_en.pdf
python3 build_pdf.py --en       # English only
python3 build_pdf.py --ja       # Japanese only
```

If pandoc/LuaLaTeX is not available, a weasyprint-based fallback is provided (`python3 build_pdf.py --weasy`), but **math equations will appear as raw LaTeX source** with this fallback.

### Phase 6: Robustness (§7)

```bash
uv run python -m src.macro.japan_stagnation.robustness_subsample
uv run python -m src.macro.japan_stagnation.robustness_model_sensitivity
uv run python -m src.macro.japan_stagnation.robustness_hac
uv run python -m src.macro.japan_stagnation.robustness_model_fit
```

---

## One-shot Replication (using Make or shell script)

For convenience:

```bash
make all  # if Makefile is provided
# or
bash scripts/replicate.sh
```

This executes all of the above in correct sequence and writes:
- All raw data to `data/raw/`
- All processed data to `data/processed/`
- All figures to `docs/papers/japan-stagnation-decomposition/figures/`
- Console output (numerical tables) to stdout

---

## Verifying Results

After replication, verify by comparing:

1. **CSV outputs** in `data/processed/japan_stagnation_*.csv`
2. **Figure files** in `docs/papers/japan-stagnation-decomposition/figures/`
3. **Numerical tables** printed to stdout

Key reproducible numbers to check:

| Section | Number | Expected value |
|---|---|---|
| §5.1 Table 1 | Japan per-WA growth (1995-2024) | +46.0% |
| §5.3 Table 2 | Japan total GDP growth (1995-2024) | 0.679%/yr |
| §6.1 Table 4 | Japan dummy (Model 1B, ex-Korea) | β=−0.011, p=0.93 |
| §6.4 Table 5 | Granger CA→GDP (Japan) | p=0.346 |
| §6.8 Table 11 | Wage panel W1 Japan dummy | β=−2.15, p<0.001 |
| §6.11.1 Table 15 | Labor share decline (1995-2019) | Japan −7.2pp |
| §6.13 Table 20 | Japan household risk asset share | 15.7% |
| §6.16 Table 27 | HANK+DSGE combined CE welfare | +25.8% |

If any of these deviate substantially, debug:
- Data fetched correctly? (`data/raw/wdi_JPN.csv` should have 35 rows × 9 columns)
- All collectors completed without errors?
- Python version 3.12+? (Some functions use match-case)
- Random seed set? (Bootstrap uses seed=42 by default)

---

## Common Issues

### FRED API rate limiting

If you encounter 429 errors, wait 60 seconds and retry. The collectors include automatic backoff.

### OECD SDMX timeout

OECD's API can be slow. If the household collector fails, retry. The collector has 3-attempt retry built-in.

### Memory usage

Peak memory usage is ~1.5 GB during the SVAR bootstrap (B=500). On systems with <2GB RAM, reduce `--n-boot 100`.

---

## Citing the Replication Package

If you use this code or data, please cite:

```bibtex
@misc{japan_stagnation_replication_2026,
  author       = {Komatsu, Shun},
  title        = {Replication Package for "Decomposing Japan's Stagnation"},
  year         = {2026},
  url          = {https://github.com/chai0204/japan-stagnation-decomposition},
  note         = {MIT License (code) / CC-BY-4.0 (paper)}
}
```

---

## Contact

For replication issues:
- Open a GitHub issue: https://github.com/chai0204/japan-stagnation-decomposition/issues
- Email: junxiaosong508@gmail.com
