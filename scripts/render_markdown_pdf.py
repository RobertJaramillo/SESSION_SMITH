#!/usr/bin/env python3
"""CLI: render a Markdown file to a PDF.

The rendering logic lives in ``backend.pdf_render`` so the API can reuse it (the
API image does not include scripts/). This wrapper keeps the original
command-line interface working:

    python scripts/render_markdown_pdf.py input.md output.pdf
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the repo root importable regardless of the current working directory.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.pdf_render import build_pdf  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("usage: render_markdown_pdf.py input.md output.pdf", file=sys.stderr)
        raise SystemExit(2)
    build_pdf(Path(sys.argv[1]), Path(sys.argv[2]))
