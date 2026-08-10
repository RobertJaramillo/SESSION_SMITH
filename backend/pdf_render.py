"""Markdown -> PDF rendering (reportlab). Source of truth for both the CLI
(scripts/render_markdown_pdf.py) and the API's world-export endpoint. Lives in
the backend package so it is present in the API image (scripts/ is not copied)."""
from __future__ import annotations

import html
import re
from io import BytesIO
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Preformatted,
    Table,
    TableStyle,
)


def esc(s: str) -> str:
    return html.escape(s, quote=False)


def inline_md(s: str) -> str:
    s = esc(s.strip())
    s = re.sub(r"`([^`]+)`", r"<font name='Courier'>\1</font>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    # Avoid broad single-asterisk emphasis parsing because API paths such as /v1/*
    # otherwise become malformed ReportLab XML.
    return s


def split_table_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith('|'):
        line = line[1:]
    if line.endswith('|'):
        line = line[:-1]
    return [cell.strip() for cell in line.split('|')]


def is_table_sep(line: str) -> bool:
    cells = split_table_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", c.strip()) for c in cells)


def add_paragraph(story, para_lines, styles):
    if not para_lines:
        return
    text = ' '.join(x.strip() for x in para_lines).strip()
    if text:
        story.append(Paragraph(inline_md(text), styles['Body']))
        story.append(Spacer(1, 0.07 * inch))
    para_lines.clear()


_DEFAULT_FOOTER = 'AI Campaign Orchestration Platform Architecture'


def build_pdf(md_path: Path, pdf_path: Path):
    """CLI path: render a Markdown file to a PDF file (unchanged behavior)."""
    pdf_path.write_bytes(render_markdown_to_pdf_bytes(md_path.read_text(encoding='utf-8')))


def render_markdown_to_pdf_bytes(md_text: str, *, title: str = _DEFAULT_FOOTER, footer: str = _DEFAULT_FOOTER) -> bytes:
    """Render Markdown text to PDF bytes (used by the API's world-export endpoint)."""
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle('Title2', parent=styles['Title'], fontName='Helvetica-Bold', fontSize=20, leading=24, spaceAfter=14))
    styles.add(ParagraphStyle('H1x', parent=styles['Heading1'], fontName='Helvetica-Bold', fontSize=16, leading=20, spaceBefore=12, spaceAfter=8))
    styles.add(ParagraphStyle('H2x', parent=styles['Heading2'], fontName='Helvetica-Bold', fontSize=13.5, leading=17, spaceBefore=10, spaceAfter=6))
    styles.add(ParagraphStyle('H3x', parent=styles['Heading3'], fontName='Helvetica-Bold', fontSize=11.5, leading=15, spaceBefore=8, spaceAfter=5))
    styles.add(ParagraphStyle('Body', parent=styles['BodyText'], fontName='Helvetica', fontSize=9.5, leading=12.5, spaceAfter=3, alignment=TA_LEFT))
    styles.add(ParagraphStyle('Bulletx', parent=styles['Body'], leftIndent=0.22 * inch, firstLineIndent=-0.12 * inch))
    styles.add(ParagraphStyle('Small', parent=styles['Body'], fontSize=8, leading=10))
    styles.add(ParagraphStyle('TableCell', parent=styles['Body'], fontSize=7.4, leading=9.2, spaceAfter=0))
    styles.add(ParagraphStyle('Codex', fontName='Courier', fontSize=6.7, leading=8.3, leftIndent=0.05 * inch, rightIndent=0.05 * inch, backColor=colors.HexColor('#f5f5f5')))

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=LETTER,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.55 * inch,
        title=title,
        author='Hermes Agent',
    )

    story = []
    lines = md_text.splitlines()
    para: list[str] = []
    i = 0
    in_code = False
    code_lang = ''
    code_lines: list[str] = []

    while i < len(lines):
        line = lines[i]

        if line.strip().startswith('```'):
            if not in_code:
                add_paragraph(story, para, styles)
                in_code = True
                code_lang = line.strip()[3:].strip()
                code_lines = []
            else:
                code_text = '\n'.join(code_lines).rstrip() or ' '
                # Keep long diagram/code blocks readable by using small monospace text.
                label = f"{code_lang} block" if code_lang else "code block"
                story.append(Paragraph(f"<b>{esc(label)}</b>", styles['Small']))
                story.append(Preformatted(code_text, styles['Codex'], maxLineLength=108))
                story.append(Spacer(1, 0.08 * inch))
                in_code = False
                code_lang = ''
                code_lines = []
            i += 1
            continue

        if in_code:
            code_lines.append(line)
            i += 1
            continue

        stripped = line.strip()
        if not stripped:
            add_paragraph(story, para, styles)
            i += 1
            continue

        if stripped == '---':
            add_paragraph(story, para, styles)
            story.append(Spacer(1, 0.08 * inch))
            i += 1
            continue

        if stripped.startswith('#'):
            add_paragraph(story, para, styles)
            level = len(stripped) - len(stripped.lstrip('#'))
            text = stripped[level:].strip()
            if level == 1:
                story.append(Paragraph(inline_md(text), styles['Title2']))
            elif level == 2:
                story.append(Paragraph(inline_md(text), styles['H1x']))
            elif level == 3:
                story.append(Paragraph(inline_md(text), styles['H2x']))
            else:
                story.append(Paragraph(inline_md(text), styles['H3x']))
            i += 1
            continue

        # Markdown table
        if stripped.startswith('|') and i + 1 < len(lines) and is_table_sep(lines[i + 1].strip()):
            add_paragraph(story, para, styles)
            header = split_table_row(stripped)
            i += 2
            rows = [header]
            while i < len(lines) and lines[i].strip().startswith('|'):
                rows.append(split_table_row(lines[i].strip()))
                i += 1
            max_cols = max(len(r) for r in rows)
            norm = [r + [''] * (max_cols - len(r)) for r in rows]
            data = [[Paragraph(inline_md(c), styles['TableCell']) for c in r] for r in norm]
            available = LETTER[0] - 1.1 * inch
            col_widths = [available / max_cols] * max_cols
            tbl = Table(data, colWidths=col_widths, repeatRows=1, hAlign='LEFT')
            tbl.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e9eef7')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.HexColor('#111111')),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('GRID', (0, 0), (-1, -1), 0.25, colors.HexColor('#b8c0cc')),
                ('VALIGN', (0, 0), (-1, -1), 'TOP'),
                ('LEFTPADDING', (0, 0), (-1, -1), 4),
                ('RIGHTPADDING', (0, 0), (-1, -1), 4),
                ('TOPPADDING', (0, 0), (-1, -1), 3),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ]))
            story.append(tbl)
            story.append(Spacer(1, 0.08 * inch))
            continue

        if re.match(r"^[-*]\s+", stripped):
            add_paragraph(story, para, styles)
            text = re.sub(r"^[-*]\s+", "", stripped)
            story.append(Paragraph('• ' + inline_md(text), styles['Bulletx']))
            i += 1
            continue

        if re.match(r"^\d+\.\s+", stripped):
            add_paragraph(story, para, styles)
            story.append(Paragraph(inline_md(stripped), styles['Bulletx']))
            i += 1
            continue

        para.append(line)
        i += 1

    add_paragraph(story, para, styles)

    def page(canvas, doc):
        canvas.saveState()
        canvas.setFont('Helvetica', 7)
        canvas.setFillColor(colors.HexColor('#666666'))
        canvas.drawString(doc.leftMargin, 0.32 * inch, footer)
        canvas.drawRightString(LETTER[0] - doc.rightMargin, 0.32 * inch, f'Page {doc.page}')
        canvas.restoreState()

    doc.build(story, onFirstPage=page, onLaterPages=page)
    return buffer.getvalue()


__all__ = ["build_pdf", "render_markdown_to_pdf_bytes"]
