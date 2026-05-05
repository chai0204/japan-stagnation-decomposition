"""論文 Markdown → PDF 変換スクリプト（weasyprint 経由）.

依存:
    uv add markdown weasyprint pygments

実行:
    uv run python docs/papers/japan-stagnation-decomposition/build_pdf.py

代替（pandoc が利用可能な場合）:
    pandoc paper_ja.md -o paper_ja.pdf \\
        --pdf-engine=lualatex \\
        -V documentclass=ltjsarticle \\
        --toc --toc-depth=3 --number-sections
"""

from __future__ import annotations

import argparse
from pathlib import Path

THIS_DIR = Path(__file__).parent
DEFAULT_INPUT = THIS_DIR / "paper_ja.md"
DEFAULT_OUTPUT = THIS_DIR / "paper_ja.pdf"


CSS = """
@page {
    size: A4;
    margin: 2.5cm 2cm;
    @top-right {
        content: "Decomposing Japan's Stagnation — Working Paper";
        font-size: 9pt;
        color: #666;
    }
    @bottom-right {
        content: counter(page) " / " counter(pages);
        font-size: 9pt;
        color: #666;
    }
}

body {
    font-family: "Hiragino Mincho Pro", "Yu Mincho", "MS Mincho", serif;
    font-size: 10.5pt;
    line-height: 1.55;
    color: #222;
    text-align: justify;
}

h1 { font-size: 18pt; margin-top: 1.5em; margin-bottom: 0.6em;
     border-bottom: 2px solid #333; padding-bottom: 0.3em; }
h2 { font-size: 14pt; margin-top: 1.4em; margin-bottom: 0.5em;
     color: #1a1a1a; page-break-after: avoid; }
h3 { font-size: 12pt; margin-top: 1.2em; margin-bottom: 0.4em;
     page-break-after: avoid; }
h4 { font-size: 11pt; margin-top: 1em; margin-bottom: 0.3em;
     page-break-after: avoid; font-weight: bold; }

p { margin: 0.4em 0; }

table {
    border-collapse: collapse;
    margin: 1em 0;
    font-size: 9.5pt;
    width: 100%;
    page-break-inside: avoid;
}
th, td {
    border: 1px solid #ccc;
    padding: 0.3em 0.6em;
    text-align: left;
}
th {
    background-color: #f0f0f0;
    font-weight: bold;
}

code {
    font-family: "DejaVu Sans Mono", "Consolas", monospace;
    font-size: 9pt;
    background-color: #f5f5f5;
    padding: 0.1em 0.3em;
    border-radius: 2px;
}
pre {
    background-color: #f5f5f5;
    padding: 0.6em;
    border-radius: 4px;
    font-size: 9pt;
    overflow-x: auto;
    page-break-inside: avoid;
}

blockquote {
    border-left: 3px solid #888;
    padding-left: 1em;
    margin-left: 0;
    color: #555;
}

img { max-width: 100%; height: auto; }

a { color: #0366d6; text-decoration: none; }
a:hover { text-decoration: underline; }

ul, ol { margin: 0.4em 0; padding-left: 1.5em; }
li { margin: 0.15em 0; }

hr { border: none; border-top: 1px solid #ccc; margin: 1.5em 0; }
"""


def build_pdf_weasyprint(
    md_path: Path = DEFAULT_INPUT,
    pdf_path: Path = DEFAULT_OUTPUT,
) -> None:
    try:
        import markdown
        from weasyprint import HTML, CSS as WeasyCSS
    except ImportError:
        print("Required packages missing. Install via:")
        print("  uv add markdown weasyprint pygments")
        return

    text = md_path.read_text(encoding="utf-8")
    html_body = markdown.markdown(
        text,
        extensions=["tables", "fenced_code", "toc", "footnotes"],
    )
    html = f"""<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="utf-8">
    <title>Decomposing Japan's Stagnation</title>
</head>
<body>
{html_body}
</body>
</html>"""

    HTML(string=html, base_url=str(md_path.parent)).write_pdf(
        pdf_path,
        stylesheets=[WeasyCSS(string=CSS)],
    )
    print(f"Generated: {pdf_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="論文 Markdown → PDF")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--all", action="store_true",
                          help="Build both paper_ja.pdf and paper_en.pdf")
    args = parser.parse_args()

    if args.all:
        build_pdf_weasyprint(THIS_DIR / "paper_ja.md", THIS_DIR / "paper_ja.pdf")
        build_pdf_weasyprint(THIS_DIR / "paper_en.md", THIS_DIR / "paper_en.pdf")
    else:
        build_pdf_weasyprint(args.input, args.output)


if __name__ == "__main__":
    main()
