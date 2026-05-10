"""Markdown -> PDF build script (pandoc + lualatex).

Generates high-quality PDFs with proper math equation rendering.

Requirements (Linux):
    sudo apt-get install pandoc texlive-luatex texlive-lang-japanese \\
        texlive-fonts-recommended texlive-fonts-extra texlive-latex-extra

Usage:
    python build_pdf.py             # builds both paper_ja.pdf and paper_en.pdf
    python build_pdf.py --en        # builds paper_en.pdf only
    python build_pdf.py --ja        # builds paper_ja.pdf only
    python build_pdf.py --weasy     # fallback: weasyprint (math NOT rendered)

Notes:
    - Math equations ($$...$$ and $...$) render natively via LaTeX
    - Japanese is handled via ltjsarticle + LuaTeX-ja
    - Special Unicode characters (checkmark, triangle, etc.) are mapped via
      pandoc-header.tex using newunicodechar
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

THIS_DIR = Path(__file__).parent
HEADER_TEX = THIS_DIR / "pandoc-header.tex"


def have_pandoc_lualatex() -> bool:
    return shutil.which("pandoc") is not None and shutil.which("lualatex") is not None


def build_pandoc(md: Path, pdf: Path, lang: str = "en") -> None:
    """High-quality build via pandoc + lualatex."""
    cmd = [
        "pandoc", str(md), "-o", str(pdf),
        "--pdf-engine=lualatex",
        "-V", "geometry:margin=2.5cm",
        "-V", "fontsize=11pt",
        "--toc", "--toc-depth=3",
        "--number-sections",
        f"--include-in-header={HEADER_TEX}",
    ]
    if lang == "ja":
        cmd.extend([
            "-V", "documentclass=ltjsarticle",
        ])
    else:
        cmd.extend([
            "-V", "mainfont=DejaVu Serif",
            "-V", "monofont=DejaVu Sans Mono",
        ])
    print(f"[pandoc] {md.name} -> {pdf.name}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    # Print only warnings/errors
    for line in result.stderr.splitlines():
        if any(k in line for k in ("WARNING", "Error", "error")):
            print(f"  {line}")
    if result.returncode != 0:
        raise RuntimeError(f"pandoc failed: {result.stderr[-500:]}")
    print(f"  Generated: {pdf} ({pdf.stat().st_size // 1024} KB)")


def build_weasyprint(md: Path, pdf: Path) -> None:
    """Fallback: weasyprint (math equations rendered as plain LaTeX source)."""
    try:
        import markdown
        from weasyprint import CSS as WeasyCSS
        from weasyprint import HTML
    except ImportError:
        print("Required packages missing for weasyprint fallback. Install via:")
        print("  uv add markdown weasyprint pygments")
        return

    css = """
    @page { size: A4; margin: 2.5cm 2cm; }
    body { font-family: serif; font-size: 11pt; line-height: 1.5; }
    h1 { font-size: 18pt; border-bottom: 2px solid #333; }
    h2 { font-size: 14pt; }
    table { border-collapse: collapse; margin: 1em 0; font-size: 9.5pt; }
    th, td { border: 1px solid #ccc; padding: 0.3em 0.6em; }
    th { background: #f0f0f0; }
    """
    text = md.read_text(encoding="utf-8")
    html = markdown.markdown(text, extensions=["tables", "fenced_code"])
    full_html = f"<!DOCTYPE html><html><body>{html}</body></html>"
    HTML(string=full_html, base_url=str(md.parent)).write_pdf(
        pdf, stylesheets=[WeasyCSS(string=css)],
    )
    print(f"  Generated (weasyprint, math NOT rendered): {pdf}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Markdown -> PDF build")
    parser.add_argument("--en", action="store_true", help="Build English only")
    parser.add_argument("--ja", action="store_true", help="Build Japanese only")
    parser.add_argument("--weasy", action="store_true",
                          help="Use weasyprint fallback (no math rendering)")
    args = parser.parse_args()

    if args.en:
        targets = [(THIS_DIR / "paper_en_v2.md", THIS_DIR / "paper_en_v2.pdf", "en")]
    elif args.ja:
        targets = [(THIS_DIR / "paper_ja_v2.md", THIS_DIR / "paper_ja_v2.pdf", "ja")]
    else:
        # Default: build both v2
        targets = [
            (THIS_DIR / "paper_ja_v2.md", THIS_DIR / "paper_ja_v2.pdf", "ja"),
            (THIS_DIR / "paper_en_v2.md", THIS_DIR / "paper_en_v2.pdf", "en"),
        ]

    if args.weasy:
        for md, pdf, _ in targets:
            build_weasyprint(md, pdf)
    elif have_pandoc_lualatex():
        for md, pdf, lang in targets:
            build_pandoc(md, pdf, lang)
    else:
        print("Pandoc + LuaLaTeX not found. Install:")
        print("  sudo apt install pandoc texlive-luatex texlive-lang-japanese \\")
        print("    texlive-fonts-recommended texlive-fonts-extra texlive-latex-extra")
        print("Falling back to weasyprint (math equations not rendered).")
        for md, pdf, _ in targets:
            build_weasyprint(md, pdf)


if __name__ == "__main__":
    main()
