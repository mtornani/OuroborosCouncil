#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Regenerate the Scouting & Match Analysis outreach portfolio as a PDF, with
a single parametrized field: who it's prepared for.

The content (OB1 Global Radar, OB1 Serie C Scout, Sentinel, Match Analysis
Pro) is fixed and lives in portfolio/content.py. Only the cover page's
"Prepared for: {recipient}" changes between exports — no more hand-patching
the PDF per recipient.

Usage:
    python generate_portfolio.py --recipient "Analytics FC"
    python generate_portfolio.py --recipient "Driblab" --output outputs/portfolio_driblab.pdf
    python generate_portfolio.py --recipient "Analytics FC" --html-only   # skip PDF, just write the HTML
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parent
TEMPLATE_DIR = REPO_ROOT / "templates"
TEMPLATE_NAME = "portfolio.html"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "outputs"


def slugify(value: str) -> str:
    """'Analytics FC' -> 'analytics_fc' — used for the default output filename."""
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE).strip().lower()
    return re.sub(r"[\s-]+", "_", value) or "recipient"


def render_html(recipient: str) -> str:
    """Render the portfolio template with the fixed content + the given recipient."""
    from portfolio.content import COVER, SYSTEMS, CONTACT

    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)
    template = env.get_template(TEMPLATE_NAME)
    return template.render(
        cover=COVER,
        systems=SYSTEMS,
        contact=CONTACT,
        recipient=recipient,
        generated_at=datetime.now().strftime("%Y-%m-%d"),
    )


def html_to_pdf(html: str, output_path: Path) -> None:
    """HTML -> PDF via WeasyPrint (this ecosystem's standard PDF pipeline —
    see the mirko-report-export skill: HTML -> weasyprint/pdfkit when a PDF
    is specifically requested). No headless browser, no build step."""
    from weasyprint import HTML

    output_path.parent.mkdir(parents=True, exist_ok=True)
    HTML(string=html, base_url=str(REPO_ROOT)).write_pdf(str(output_path))


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate the scouting/match-analysis portfolio PDF for a recipient."
    )
    parser.add_argument(
        "--recipient",
        required=True,
        help='Who the portfolio is prepared for, e.g. "Analytics FC" or "Driblab".',
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output PDF path. Defaults to outputs/portfolio_<recipient-slug>.pdf",
    )
    parser.add_argument(
        "--html-only",
        action="store_true",
        help="Write the rendered HTML next to the PDF path instead of building a PDF "
        "(useful to preview the page in a browser, or if WeasyPrint isn't installed).",
    )
    args = parser.parse_args()

    recipient = args.recipient.strip()
    if not recipient:
        parser.error("--recipient cannot be empty")

    output_path = args.output or (DEFAULT_OUTPUT_DIR / f"portfolio_{slugify(recipient)}.pdf")

    html = render_html(recipient)

    if args.html_only:
        html_path = output_path.with_suffix(".html")
        html_path.parent.mkdir(parents=True, exist_ok=True)
        html_path.write_text(html, encoding="utf-8")
        print(f"HTML → {html_path}")
        return 0

    html_to_pdf(html, output_path)
    print(f"PDF → {output_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
