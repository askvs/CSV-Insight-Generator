import html
import io
import os
import re
import textwrap
import unicodedata
from datetime import datetime
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus import (
    Image as RLImage,
)


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to compute total page count and draw running header/footer.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))

        # Running Header (on pages after page 1)
        page_num = getattr(self, "_pageNumber", 1)
        if page_num > 1:
            self.drawString(40, 762, "CSV INSIGHT AGENT — Executive Analytics Briefing")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(40, 756, 612 - 40, 756)

        # Running Footer
        self.drawString(
            40,
            25,
            "Confidential — Automated AI Data Intelligence & Executive Decision Support",
        )
        page_str = f"Page {page_num} of {page_count}"
        self.drawRightString(612 - 40, 25, page_str)

        # Footer divider
        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.75)
        self.line(40, 37, 612 - 40, 37)

        self.restoreState()


def _sanitize_text_for_pdf(text: str) -> str:
    """
    Replaces emojis, non-standard unicode dashes, spaces, and currency symbols
    so standard PDF fonts (Helvetica) render clean text without black square replacement glyphs.
    """
    if not text:
        return ""

    emoji_map = {
        "💡": "[Key Insight] ",
        "📊": "[Chart] ",
        "📈": "[Upward Trend] ",
        "📉": "[Downward Trend] ",
        "⚠️": "[Risk / Alert] ",
        "🔍": "[Finding] ",
        "🎯": "[Target] ",
        "💰": "[Financial] ",
        "🚀": "[Strategic Action] ",
        "•": "-",
        "✅": "[Verified] ",
        "📌": "[Note] ",
        "⭐": "* ",
    }
    for em, replacement in emoji_map.items():
        text = text.replace(em, replacement)

    # Comprehensive mappings for Unicode characters outside Helvetica / WinAnsiEncoding
    unicode_replacements = {
        # Currencies
        "\u20b9": "Rs. ",       # Indian Rupee ₹ -> Rs.
        "\u20bd": "RUB ",       # Russian Ruble
        "\u20ba": "TRY ",       # Turkish Lira
        "\u20a9": "KRW ",       # Won
        "\u20ab": "VND ",       # Dong
        "\u20aa": "ILS ",       # Shekel
        "\u0e3f": "THB ",       # Baht
        # Dashes, hyphens, and bars (which become black squares if unmapped)
        "\u2010": "-",          # Hyphen
        "\u2011": "-",          # Non-breaking hyphen
        "\u2012": "-",          # Figure dash
        "\u2013": "-",          # En dash
        "\u2014": " - ",        # Em dash
        "\u2015": "-",          # Horizontal bar
        "\u2212": "-",          # Minus sign
        "\u00ad": "",           # Soft hyphen
        # Spaces and zero-width characters
        "\u202f": " ",          # Narrow no-break space
        "\u200b": "",           # Zero-width space
        "\u200c": "",           # Zero-width non-joiner
        "\u200d": "",           # Zero-width joiner
        "\u2009": " ",          # Thin space
        "\u200a": " ",          # Hair space
        "\u2002": " ",          # En space
        "\u2003": " ",          # Em space
        "\u2004": " ",          # Three-per-em space
        "\u2005": " ",          # Four-per-em space
        "\u2006": " ",          # Six-per-em space
        "\u3000": " ",          # Ideographic space
        # Math & symbols
        "\u2248": "~",          # Almost equal to ≈
        "\u2260": "!=",         # Not equal to ≠
        "\u2264": "<=",         # Less than or equal ≤
        "\u2265": ">=",         # Greater than or equal ≥
        "\u00d7": "x",          # Multiplication sign ×
        "\u00f7": "/",          # Division sign ÷
        "\u2026": "...",        # Ellipsis …
        "\u2022": "-",          # Bullet •
        "\u25cf": "-",          # Black circle ●
        "\u25a0": "-",          # Black square ■
        "\u25aa": "-",          # Small black square ▪
        "\u25b6": ">",          # Black right triangle ▶
        "\u2714": "[OK]",       # Heavy check mark ✔
        "\u2713": "[OK]",       # Check mark ✓
        "\u2717": "[X]",        # Ballot X ✗
        "\u2718": "[X]",        # Heavy ballot X ✘
        "\u201c": '"',          # Left double quotation mark “
        "\u201d": '"',          # Right double quotation mark ”
        "\u2018": "'",          # Left single quotation mark ‘
        "\u2019": "'",          # Right single quotation mark ’
        "\u00b1": "+/-",        # Plus-minus ±
        "\u221e": "inf",        # Infinity ∞
    }
    for orig, rep in unicode_replacements.items():
        text = text.replace(orig, rep)

    # Strip 4-byte unicode emojis/symbols
    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)

    # Fallback for any remaining characters not encodable in standard PDF Latin-1 font
    safe_chars = []
    for ch in text:
        try:
            ch.encode("latin1")
            safe_chars.append(ch)
        except UnicodeEncodeError:
            # Normalize and convert to closest ASCII equivalent if possible
            norm = (
                unicodedata.normalize("NFKD", ch)
                .encode("ascii", "ignore")
                .decode("ascii")
            )
            safe_chars.append(norm if norm else " ")

    return "".join(safe_chars)


def _safe_paragraph(
    text: str, style: ParagraphStyle, raw_fallback: str | None = None
) -> Paragraph:
    """
    Safely instantiates a ReportLab Paragraph.
    If ReportLab paraparser encounters a syntax error or malformed markup,
    strips invalid tags and falls back to clean, escaped plain text so PDF
    generation never crashes.
    """
    try:
        return Paragraph(text, style)
    except Exception:
        fallback = raw_fallback if raw_fallback is not None else re.sub(r"<[^>]*>", "", str(text))
        return Paragraph(html.escape(str(fallback)), style)


def _clean_inline(s: str) -> str:
    """
    Escapes HTML entities, preserves intentional <br/> breaks, and translates
    markdown bold, italic, and inline code to ReportLab tags.
    """
    esc = html.escape(s)
    # Preserve intentional line-breaks from markdown/table cells (e.g. <br>, <br/>)
    esc = re.sub(r"&lt;br\s*/?&gt;", "<br/>", esc, flags=re.IGNORECASE)
    # Bold-italic (***text***) handled first to prevent mismatched/overlapping tags
    esc = re.sub(r"\*\*\*(.*?)\*\*\*", r"<b><i>\1</i></b>", esc)
    esc = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", esc)
    esc = re.sub(r"\*(.*?)\*", r"<i>\1</i>", esc)
    esc = re.sub(r"`(.*?)`", r"<font face='Courier' size='8'>\1</font>", esc)
    return esc


def _format_code_line(line: str, max_width: int = 90) -> str:
    """
    Formats a single line of code for ReportLab, preserving leading indentation
    and wrapping long lines BEFORE HTML escaping to avoid cutting through entities or tags.
    """
    stripped = line.lstrip(" ")
    leading_spaces = len(line) - len(stripped)
    indent = "&nbsp;" * leading_spaces
    if not stripped:
        return "&nbsp;"
    if len(stripped) > max_width:
        parts = textwrap.wrap(
            stripped,
            width=max_width,
            break_long_words=True,
            break_on_hyphens=False,
        )
        esc_parts = [html.escape(p) for p in parts]
        return f"<br/>{indent}&nbsp;&nbsp;".join(esc_parts)
    return indent + html.escape(stripped)


def _format_markdown_for_reportlab(text: str) -> list[tuple[str, Any]]:
    """
    Converts plain/rich markdown text from LLM into structured blocks
    for ReportLab (headers, subheaders, bullet points, callouts, tables, code blocks, and paragraphs).

    Returns list of (block_type, content):
      - ('h1', str)
      - ('h2', str)
      - ('h3', str)
      - ('bullet', str)
      - ('numbered', str)
      - ('key_insight', str)
      - ('recommendation', str)
      - ('risk', str)
      - ('code_block', list[str])
      - ('table', list[list[str]])
      - ('body', str)
    """
    text = _sanitize_text_for_pdf(text)
    raw_lines = text.strip().split("\n")
    blocks: list[tuple[str, Any]] = []

    i = 0
    while i < len(raw_lines):
        line = raw_lines[i].strip()
        if not line:
            i += 1
            continue

        # Check for fenced code blocks (``` or ```python)
        if line.startswith("```"):
            code_lines: list[str] = []
            i += 1
            while i < len(raw_lines) and not raw_lines[i].strip().startswith("```"):
                code_lines.append(raw_lines[i])
                i += 1
            if i < len(raw_lines) and raw_lines[i].strip().startswith("```"):
                i += 1
            if code_lines:
                blocks.append(("code_block", code_lines))
            continue

        # Check for Markdown Table (starts and ends with '|' or contains multiple '|')
        if line.startswith("|") and line.endswith("|") and line.count("|") >= 2:
            table_raw: list[list[str]] = []
            while i < len(raw_lines) and raw_lines[i].strip().startswith("|"):
                row_str = raw_lines[i].strip()
                # Skip separator lines like |---|---|
                if not re.match(r"^\|(\s*:?-+:?\s*\|)+$", row_str):
                    cells = [c.strip() for c in row_str.split("|")[1:-1]]
                    if any(cells):
                        table_raw.append(cells)
                i += 1

            if table_raw:
                blocks.append(("table", table_raw))
            continue

        # Check for Section Headers (# Header, ## Header, ### Header)
        if line.startswith("#### "):
            clean_text = line[5:].strip()
            blocks.append(("h3", _clean_inline(clean_text)))
            i += 1
            continue
        elif line.startswith("### "):
            clean_text = line[4:].strip()
            blocks.append(("h3", _clean_inline(clean_text)))
            i += 1
            continue
        elif line.startswith("## "):
            clean_text = line[3:].strip()
            blocks.append(("h2", _clean_inline(clean_text)))
            i += 1
            continue
        elif line.startswith("# "):
            clean_text = line[2:].strip()
            blocks.append(("h1", _clean_inline(clean_text)))
            i += 1
            continue

        # Check for bold standalone headers like **1. Executive Summary:** or **Key Findings**
        bold_header_match = re.match(
            r"^\*\*([0-9]+\.\s*)?([A-Za-z0-9\s,&/–-]+):?\*\*\s*$", line
        )
        if bold_header_match:
            hdr_text = bold_header_match.group(0).replace("**", "").strip()
            blocks.append(("h2", _clean_inline(hdr_text)))
            i += 1
            continue

        # Check for horizontal dividers (---, ***, ___)
        if line in ("---", "***", "___"):
            i += 1
            continue

        line_lower = line.lower()

        # Check for Recommendation / Action Plan callouts
        if line_lower.startswith(
            (
                "**strategic recommendation",
                "strategic recommendation:",
                "**recommendation",
                "recommendation:",
                "**action item",
                "action item:",
                "[strategic action]",
                "[recommendation]",
            )
        ):
            blocks.append(("recommendation", _clean_inline(line)))
            i += 1
            continue

        # Check for Risk / Alert callouts
        if line_lower.startswith(
            (
                "**risk",
                "risk:",
                "**caution",
                "caution:",
                "**limitation",
                "limitation:",
                "[risk / alert]",
                "[note]",
            )
        ):
            blocks.append(("risk", _clean_inline(line)))
            i += 1
            continue

        # Check for Key Insight / Finding callouts
        if line_lower.startswith(
            (
                "**key insight",
                "key insight:",
                "**strategic takeaway",
                "strategic takeaway:",
                "**key finding",
                "key finding:",
                "**takeaway:",
                "[key insight]",
                "[finding]",
            )
        ):
            blocks.append(("key_insight", _clean_inline(line)))
            i += 1
            continue

        # Check for bullet points (*, -, •)
        bullet_match = re.match(r"^(\*|\-|\•)\s+(.*)$", line)
        if bullet_match:
            item_text = bullet_match.group(2)
            blocks.append(("bullet", _clean_inline(item_text)))
            i += 1
            continue

        # Check for numbered items (1., 2., etc.)
        numbered_match = re.match(r"^(\d+[\.\)])\s+(.*)$", line)
        if numbered_match:
            prefix = numbered_match.group(1)
            item_text = numbered_match.group(2)
            blocks.append(("numbered", f"<b>{prefix}</b> {_clean_inline(item_text)}"))
            i += 1
            continue

        # Normal paragraph
        blocks.append(("body", _clean_inline(line)))
        i += 1

    return blocks


def _generate_fallback_chart(df: pd.DataFrame | None = None) -> bytes | None:
    """Generates an executive exploratory summary chart if no chart was produced during the turn."""
    if df is None or len(df) == 0:
        return None
    try:
        fig, ax = plt.subplots(figsize=(9, 4.2), dpi=120)
        plt.style.use(
            "seaborn-v0_8-whitegrid"
            if "seaborn-v0_8-whitegrid" in plt.style.available
            else "default"
        )

        # Identify interesting numeric column
        num_cols = df.select_dtypes(include=["number"]).columns.tolist()
        cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()

        if cat_cols and num_cols:
            cat = cat_cols[0]
            num = num_cols[0]
            top_cats = df[cat].value_counts().head(8).index
            sub_df = df[df[cat].isin(top_cats)]  # pyrefly: ignore[bad-argument-type]
            avg_vals = sub_df.groupby(cat)[num].mean().sort_values(ascending=False)  # pyrefly: ignore[missing-argument]

            colors_list = [
                "#1D4ED8",
                "#2563EB",
                "#3B82F6",
                "#60A5FA",
                "#93C5FD",
                "#BFDBFE",
                "#DBEAFE",
                "#EFF6FF",
            ]
            avg_vals.plot(
                kind="bar",
                ax=ax,
                color=colors_list[: len(avg_vals)],
                edgecolor="#0F2942",
                linewidth=0.8,
            )
            ax.set_title(
                f"Empirical Average {num} by {cat}",
                fontsize=12,
                fontweight="bold",
                pad=12,
                color="#0F2942",
            )
            ax.set_ylabel(f"Average {num}", fontsize=10, color="#1E293B")
            ax.set_xlabel(cat, fontsize=10, color="#1E293B")
            ax.tick_params(axis="x", rotation=25)
        elif len(num_cols) >= 2:
            df[num_cols[:5]].mean().plot(
                kind="bar", ax=ax, color="#1D4ED8", edgecolor="#0F2942"
            )
            ax.set_title(
                "Dataset Numeric Baseline Averages",
                fontsize=12,
                fontweight="bold",
                pad=12,
                color="#0F2942",
            )
            ax.set_ylabel("Metric Mean", fontsize=10)
            ax.tick_params(axis="x", rotation=20)
        else:
            return None

        plt.tight_layout()
        buf = io.BytesIO()
        plt.savefig(buf, format="png", bbox_inches="tight", dpi=120)
        plt.close(fig)
        buf.seek(0)
        return buf.getvalue()
    except Exception:
        plt.close("all")
        return None


def generate_pdf_report(
    dataset_name: str,
    profile_dict: dict,
    user_question: str,
    agent_answer: str,
    charts: list[bytes] | None = None,
    executed_code: list[str] | None = None,
    output_path: str | None = None,
    df: pd.DataFrame | None = None,
) -> bytes:
    """
    Generates an executive, world-class PDF intelligence report.

    Parameters:
      dataset_name   — Name of the dataset file (e.g., 'dataset.csv')
      profile_dict   — Profile dictionary from profiler.py
      user_question  — The business query asked by the user
      agent_answer   — The comprehensive plain-English analysis from the agent
      charts         — List of matplotlib chart PNG bytes
      executed_code  — List of executed Python snippets (audit trail)
      output_path    — Optional filepath to save the PDF directly
      df             — Optional loaded dataframe for fallback visualization

    Returns:
      PDF file content as bytes.
    """
    pdf_buffer = io.BytesIO()

    # Document geometry: 40pt (0.55 in) margins
    doc = SimpleDocTemplate(
        pdf_buffer,
        pagesize=letter,
        leftMargin=40,
        rightMargin=40,
        topMargin=40,
        bottomMargin=45,
    )

    story: list[Any] = []
    styles = getSampleStyleSheet()

    # Palette
    c_primary = colors.HexColor("#0B2545")  # Deep Navy
    c_accent = colors.HexColor("#134074")  # Royal Sapphire
    c_dark = colors.HexColor("#0F172A")  # Slate 900
    c_muted = colors.HexColor("#64748B")  # Slate 500
    c_bg_light = colors.HexColor("#F8FAFC")  # Soft Slate 50
    c_border = colors.HexColor("#CBD5E1")  # Border Slate
    c_insight_bg = colors.HexColor("#EFF6FF")  # Blue Tint
    c_insight_border = colors.HexColor("#3B82F6")
    c_rec_bg = colors.HexColor("#ECFDF5")  # Emerald Tint
    c_rec_border = colors.HexColor("#10B981")
    c_risk_bg = colors.HexColor("#FFFBEB")  # Amber Tint
    c_risk_border = colors.HexColor("#F59E0B")

    # Typography Styles
    kicker_style = ParagraphStyle(
        "DocKicker",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8.5,
        leading=11,
        textColor=c_accent,
    )

    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        textColor=c_primary,
    )

    subtitle_style = ParagraphStyle(
        "DocSubTitle",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=c_muted,
    )

    h1_style = ParagraphStyle(
        "H1Section",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=16,
        textColor=c_primary,
        spaceBefore=14,
        spaceAfter=6,
    )

    h2_style = ParagraphStyle(
        "H2Section",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10.5,
        leading=14,
        textColor=c_accent,
        spaceBefore=10,
        spaceAfter=4,
    )

    h3_style = ParagraphStyle(
        "H3Section",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=13,
        textColor=c_dark,
        spaceBefore=6,
        spaceAfter=3,
    )

    body_style = ParagraphStyle(
        "ReportBody",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13.5,
        textColor=c_dark,
        spaceAfter=5,
    )

    bullet_style = ParagraphStyle(
        "ReportBullet",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13.5,
        textColor=c_dark,
        leftIndent=14,
        firstLineIndent=-9,
        spaceAfter=4,
    )

    numbered_style = ParagraphStyle(
        "ReportNumbered",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13.5,
        textColor=c_dark,
        leftIndent=16,
        firstLineIndent=-12,
        spaceAfter=4,
    )

    insight_box_style = ParagraphStyle(
        "InsightBoxText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13.5,
        textColor=colors.HexColor("#1E3A8A"),
    )

    rec_box_style = ParagraphStyle(
        "RecBoxText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13.5,
        textColor=colors.HexColor("#064E3B"),
    )

    risk_box_style = ParagraphStyle(
        "RiskBoxText",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13.5,
        textColor=colors.HexColor("#78350F"),
    )

    query_style = ParagraphStyle(
        "QueryText",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9.5,
        leading=14,
        textColor=c_dark,
    )

    code_style = ParagraphStyle(
        "CodeText",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=7,
        leading=9.5,
        textColor=colors.HexColor("#0F172A"),
    )

    # 1. HEADER SECTION
    story.append(_safe_paragraph("EXECUTIVE DATA INTELLIGENCE REPORT", kicker_style))
    story.append(Spacer(1, 2))
    story.append(
        _safe_paragraph("Strategic Analytics & Cohort Investigation Briefing", title_style)
    )
    story.append(Spacer(1, 3))

    timestamp = datetime.now().strftime("%B %d, %Y • %I:%M %p")
    story.append(
        _safe_paragraph(
            f"Generated: <b>{timestamp}</b> &nbsp;|&nbsp; Source File: <b>{html.escape(str(dataset_name))}</b>",
            subtitle_style,
        )
    )
    story.append(Spacer(1, 6))
    story.append(
        HRFlowable(
            width="100%", thickness=1, color=c_accent, spaceBefore=2, spaceAfter=8
        )
    )

    # 2. DATASET METRICS OVERVIEW CARD
    shape_info = profile_dict.get("shape", {})
    rows = shape_info.get("rows", "N/A")
    cols = shape_info.get("columns", "N/A")
    mem = profile_dict.get("memory_mb", "N/A")

    rows_disp = (
        f"{rows:,} records"
        if isinstance(rows, int)
        else f"{html.escape(str(rows))}"
    )
    meta_table_data = [
        [
            _safe_paragraph(
                f"<b>Data Source:</b><br/>{html.escape(str(dataset_name))}", body_style
            ),
            _safe_paragraph(
                f"<b>Total Sample:</b><br/>{rows_disp}",
                body_style,
            ),
            _safe_paragraph(f"<b>Tracked Features:</b><br/>{html.escape(str(cols))} columns", body_style),
            _safe_paragraph(f"<b>In-Memory Size:</b><br/>{html.escape(str(mem))} MB", body_style),
        ]
    ]
    meta_table = Table(meta_table_data, colWidths=[140, 130, 130, 132])
    meta_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), c_bg_light),
                ("BOX", (0, 0), (-1, -1), 0.75, c_border),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, c_border),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ]
        )
    )
    story.append(meta_table)
    story.append(Spacer(1, 8))

    # 3. STRATEGIC QUESTION INVESTIGATED
    query_box_data = [
        [
            _safe_paragraph(
                f'<b>Primary Business Inquiry:</b><br/>"{html.escape(str(user_question))}"',
                query_style,
            )
        ]
    ]
    query_table = Table(query_box_data, colWidths=[532])
    query_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F1F5F9")),
                ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#94A3B8")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(query_table)
    story.append(Spacer(1, 10))

    # 4. EXECUTIVE FINDINGS & DETAILED ANALYSIS
    formatted_blocks = _format_markdown_for_reportlab(agent_answer)
    for block_type, content in formatted_blocks:
        if block_type == "h1":
            story.append(_safe_paragraph(f"<b>{content}</b>", h1_style, raw_fallback=content))
            story.append(
                HRFlowable(
                    width="100%",
                    thickness=1,
                    color=c_border,
                    spaceBefore=1,
                    spaceAfter=4,
                )
            )
        elif block_type == "h2":
            story.append(_safe_paragraph(f"<b>{content}</b>", h2_style, raw_fallback=content))
        elif block_type == "h3":
            story.append(_safe_paragraph(f"<b>{content}</b>", h3_style, raw_fallback=content))
        elif block_type == "bullet":
            story.append(_safe_paragraph(f"• &nbsp; {content}", bullet_style, raw_fallback=content))
        elif block_type == "numbered":
            story.append(_safe_paragraph(content, numbered_style, raw_fallback=content))
        elif block_type == "key_insight":
            callout_data = [
                [
                    _safe_paragraph(
                        f"<b>KEY STRATEGIC INSIGHT</b><br/>{content}", insight_box_style, raw_fallback=content
                    )
                ]
            ]
            callout_table = Table(callout_data, colWidths=[532])
            callout_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), c_insight_bg),
                        ("BOX", (0, 0), (-1, -1), 1.25, c_insight_border),
                        ("LEFTPADDING", (0, 0), (-1, -1), 10),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.append(Spacer(1, 3))
            story.append(callout_table)
            story.append(Spacer(1, 5))
        elif block_type == "recommendation":
            rec_data = [
                [
                    _safe_paragraph(
                        f"<b>ACTIONABLE RECOMMENDATION</b><br/>{content}", rec_box_style, raw_fallback=content
                    )
                ]
            ]
            rec_table = Table(rec_data, colWidths=[532])
            rec_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), c_rec_bg),
                        ("BOX", (0, 0), (-1, -1), 1.25, c_rec_border),
                        ("LEFTPADDING", (0, 0), (-1, -1), 10),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.append(Spacer(1, 3))
            story.append(rec_table)
            story.append(Spacer(1, 5))
        elif block_type == "risk":
            risk_data = [
                [
                    _safe_paragraph(
                        f"<b>RISK ASSESSMENT & CAVEAT</b><br/>{content}", risk_box_style, raw_fallback=content
                    )
                ]
            ]
            risk_table = Table(risk_data, colWidths=[532])
            risk_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), c_risk_bg),
                        ("BOX", (0, 0), (-1, -1), 1.25, c_risk_border),
                        ("LEFTPADDING", (0, 0), (-1, -1), 10),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.append(Spacer(1, 3))
            story.append(risk_table)
            story.append(Spacer(1, 5))
        elif block_type == "code_block":
            formatted_code = [_format_code_line(cl) for cl in content]
            chunk_html = "<br/>".join(formatted_code)
            cb_data = [[_safe_paragraph(chunk_html, code_style, raw_fallback="\n".join(content))]]
            cb_table = Table(cb_data, colWidths=[532])
            cb_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#CBD5E1")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                    ]
                )
            )
            story.append(Spacer(1, 3))
            story.append(cb_table)
            story.append(Spacer(1, 5))
        elif block_type == "table":
            table_rows_data: list[list[Any]] = []
            num_cols = max(len(row) for row in content) if content else 1
            col_w = 532 / num_cols

            for row_idx, row in enumerate(content):
                row_cells: list[Any] = []
                for cell_text in row:
                    esc = _clean_inline(cell_text)
                    cell_style = (
                        ParagraphStyle(
                            "TableHeadCell",
                            parent=body_style,
                            fontName="Helvetica-Bold",
                            textColor=colors.HexColor("#0B2545"),
                            fontSize=8.5,
                            leading=11,
                        )
                        if row_idx == 0
                        else ParagraphStyle(
                            "TableCell",
                            parent=body_style,
                            fontName="Helvetica",
                            textColor=c_dark,
                            fontSize=8.5,
                            leading=11,
                        )
                    )
                    row_cells.append(_safe_paragraph(esc, cell_style, raw_fallback=cell_text))
                # Pad row if fewer cells
                while len(row_cells) < num_cols:
                    row_cells.append(_safe_paragraph("", body_style))
                table_rows_data.append(row_cells)

            if table_rows_data:
                md_table = Table(
                    table_rows_data, colWidths=[col_w] * num_cols, repeatRows=1
                )
                md_table.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E2E8F0")),
                            (
                                "ROWBACKGROUNDS",
                                (0, 1),
                                (-1, -1),
                                [colors.white, colors.HexColor("#F8FAFC")],
                            ),
                            ("BOX", (0, 0), (-1, -1), 0.75, c_border),
                            ("INNERGRID", (0, 0), (-1, -1), 0.5, c_border),
                            ("TOPPADDING", (0, 0), (-1, -1), 5),
                            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                            ("LEFTPADDING", (0, 0), (-1, -1), 6),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                        ]
                    )
                )
                story.append(Spacer(1, 4))
                story.append(md_table)
                story.append(Spacer(1, 6))
        else:
            story.append(_safe_paragraph(content, body_style, raw_fallback=content))

    # 5. VISUAL ANALYTICS SECTION (Never Empty)
    effective_charts: list[bytes] = charts if (charts and len(charts) > 0) else []
    if not effective_charts and df is not None:
        fallback = _generate_fallback_chart(df)
        if fallback:
            effective_charts.append(fallback)

    if effective_charts:
        story.append(Spacer(1, 8))
        story.append(_safe_paragraph("VISUAL INTELLIGENCE & EMPIRICAL CHARTS", h1_style))
        story.append(
            HRFlowable(
                width="100%", thickness=1, color=c_border, spaceBefore=1, spaceAfter=8
            )
        )

        for i, chart_bytes in enumerate(effective_charts, 1):
            chart_img_buf = io.BytesIO(chart_bytes)
            chart_rl = RLImage(chart_img_buf, width=490, height=230)

            chart_box = [
                [chart_rl],
                [
                    _safe_paragraph(
                        f"<b>Figure {i}:</b> Visual Breakdown Generated via Live Python Sandbox Execution",
                        subtitle_style,
                    )
                ],
            ]
            chart_table = Table(chart_box, colWidths=[532])
            chart_table.setStyle(
                TableStyle(
                    [
                        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                        ("BOX", (0, 0), (-1, -1), 0.75, c_border),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ]
                )
            )
            story.append(KeepTogether([chart_table, Spacer(1, 8)]))

    # 6. AUDIT TRAIL / CODE EXECUTION LOG
    if executed_code:
        story.append(Spacer(1, 6))
        story.append(
            _safe_paragraph("APPENDIX: REPRODUCIBILITY & CODE AUDIT TRAIL", h1_style)
        )
        story.append(
            HRFlowable(
                width="100%", thickness=1, color=c_border, spaceBefore=1, spaceAfter=6
            )
        )
        story.append(
            _safe_paragraph(
                "Empirical Python code executed inside the secure sandbox environment:",
                subtitle_style,
            )
        )
        story.append(Spacer(1, 4))

        for idx, code_snippet in enumerate(executed_code, 1):
            raw_lines = code_snippet.strip().split("\n")
            formatted_lines = [_format_code_line(ln) for ln in raw_lines]

            CHUNK_SIZE = 12
            chunks = [
                formatted_lines[i : i + CHUNK_SIZE]
                for i in range(0, len(formatted_lines), CHUNK_SIZE)
            ]

            table_rows: list[list[Any]] = [
                [_safe_paragraph(f"<b>// Step {idx} Query:</b>", code_style)]
            ]
            for chunk in chunks:
                chunk_html = "<br/>".join(chunk)
                table_rows.append([_safe_paragraph(chunk_html, code_style, raw_fallback=code_snippet)])

            code_box = Table(table_rows, colWidths=[532])
            code_box.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F8FAFC")),
                        ("BOX", (0, 0), (-1, -1), 0.75, colors.HexColor("#CBD5E1")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                        ("TOPPADDING", (0, 0), (-1, 0), 5),
                        ("BOTTOMPADDING", (0, 0), (-1, 0), 2),
                        ("TOPPADDING", (0, 1), (-1, -1), 1),
                        ("BOTTOMPADDING", (0, 1), (-1, -1), 1),
                        ("BOTTOMPADDING", (0, -1), (-1, -1), 5),
                    ]
                )
            )
            story.append(code_box)
            story.append(Spacer(1, 6))

    # Build PDF with two-pass NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)

    pdf_bytes = pdf_buffer.getvalue()
    pdf_buffer.close()

    if output_path:
        out_dir = os.path.dirname(os.path.abspath(output_path))
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)

    return pdf_bytes
