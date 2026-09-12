# Executive PDF report generator
import hashlib
import html
import io
import os
from datetime import datetime
from typing import Any

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import (
    HRFlowable,
    Image as RLImage,
    KeepTogether,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .chart_generator import generate_fallback_chart
from .markdown_parser import format_markdown_for_reportlab
from .pdf_canvas import NumberedCanvas
from .pdf_formatting import (
    clean_inline,
    format_code_line,
    safe_paragraph,
    sanitize_text_for_pdf,
)


# Generate a complete formatted PDF report from analysis results
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
    pdf_buffer = io.BytesIO()

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

    c_primary = colors.HexColor("#0B2545")
    c_accent = colors.HexColor("#134074")
    c_dark = colors.HexColor("#0F172A")
    c_muted = colors.HexColor("#64748B")
    c_bg_light = colors.HexColor("#F8FAFC")
    c_border = colors.HexColor("#CBD5E1")
    c_insight_bg = colors.HexColor("#EFF6FF")
    c_insight_border = colors.HexColor("#3B82F6")
    c_rec_bg = colors.HexColor("#ECFDF5")
    c_rec_border = colors.HexColor("#10B981")
    c_risk_bg = colors.HexColor("#FFFBEB")
    c_risk_border = colors.HexColor("#F59E0B")

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

    # 1. Header Section
    story.append(safe_paragraph("EXECUTIVE DATA INTELLIGENCE REPORT", kicker_style))
    story.append(Spacer(1, 2))
    story.append(
        safe_paragraph("Strategic Analytics & Cohort Investigation Briefing", title_style)
    )
    story.append(Spacer(1, 3))

    timestamp = datetime.now().strftime("%B %d, %Y • %I:%M %p")
    story.append(
        safe_paragraph(
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

    # 2. Dataset Overview Metrics Table
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
            safe_paragraph(
                f"<b>Data Source:</b><br/>{html.escape(str(dataset_name))}", body_style
            ),
            safe_paragraph(
                f"<b>Total Sample:</b><br/>{rows_disp}",
                body_style,
            ),
            safe_paragraph(f"<b>Tracked Features:</b><br/>{html.escape(str(cols))} columns", body_style),
            safe_paragraph(f"<b>In-Memory Size:</b><br/>{html.escape(str(mem))} MB", body_style),
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

    # 3. User Business Question Box
    query_box_data = [
        [
            safe_paragraph(
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

    # 4. Formatted Markdown Report Sections
    formatted_blocks = format_markdown_for_reportlab(agent_answer)
    for block_type, content in formatted_blocks:
        if block_type == "h1":
            story.append(safe_paragraph(f"<b>{content}</b>", h1_style, raw_fallback=content))
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
            story.append(safe_paragraph(f"<b>{content}</b>", h2_style, raw_fallback=content))
        elif block_type == "h3":
            story.append(safe_paragraph(f"<b>{content}</b>", h3_style, raw_fallback=content))
        elif block_type == "bullet":
            story.append(safe_paragraph(f"• &nbsp; {content}", bullet_style, raw_fallback=content))
        elif block_type == "numbered":
            story.append(safe_paragraph(content, numbered_style, raw_fallback=content))
        elif block_type == "key_insight":
            callout_data = [
                [
                    safe_paragraph(
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
                    safe_paragraph(
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
                    safe_paragraph(
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
            formatted_code = [format_code_line(cl) for cl in content]
            chunk_html = "<br/>".join(formatted_code)
            cb_data = [[safe_paragraph(chunk_html, code_style, raw_fallback="\n".join(content))]]
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
                    esc = clean_inline(cell_text)
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
                    row_cells.append(safe_paragraph(esc, cell_style, raw_fallback=cell_text))
                while len(row_cells) < num_cols:
                    row_cells.append(safe_paragraph("", body_style))
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
            story.append(safe_paragraph(content, body_style, raw_fallback=content))

    # 5. Charts and Visuals Section
    raw_charts = charts if (charts and len(charts) > 0) else []
    effective_charts: list[tuple[bytes, str]] = []
    seen_hashes: set[str] = set()

    for c in raw_charts:
        png_b: bytes | None = None
        title: str = ""

        if isinstance(c, bytes):
            png_b = c
        elif hasattr(c, "_png_bytes") and getattr(c, "_png_bytes"):
            png_b = getattr(c, "_png_bytes")
            if hasattr(c, "layout") and hasattr(c.layout, "title") and c.layout.title and getattr(c.layout.title, "text", None):
                title = str(c.layout.title.text).strip()
        elif hasattr(c, "to_image"):
            if hasattr(c, "layout") and hasattr(c.layout, "title") and c.layout.title and getattr(c.layout.title, "text", None):
                title = str(c.layout.title.text).strip()
            try:
                png_b = c.to_image(format="png", width=900, height=450)
            except Exception:
                pass

        if png_b:
            h = hashlib.md5(png_b).hexdigest()
            if h not in seen_hashes:
                seen_hashes.add(h)
                effective_charts.append((png_b, title))

    if not effective_charts and df is not None:
        fallback = generate_fallback_chart(df)
        if fallback:
            effective_charts.append((fallback, "Empirical Exploratory Distribution"))

    if effective_charts:
        story.append(Spacer(1, 8))
        story.append(safe_paragraph("VISUAL INTELLIGENCE & EMPIRICAL CHARTS", h1_style))
        story.append(
            HRFlowable(
                width="100%", thickness=1, color=c_border, spaceBefore=1, spaceAfter=8
            )
        )

        for i, (chart_bytes, title) in enumerate(effective_charts, 1):
            chart_img_buf = io.BytesIO(chart_bytes)
            chart_rl = RLImage(chart_img_buf, width=490, height=230)

            caption_label = (
                f"<b>Figure {i}:</b> {clean_inline(title)}"
                if title
                else f"<b>Figure {i}:</b> Visual Breakdown Generated via Live Python Sandbox Execution"
            )
            chart_box = [
                [chart_rl],
                [safe_paragraph(caption_label, subtitle_style, raw_fallback=caption_label)],
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

    # 6. Audit Trail and Python Code Appendix
    if executed_code:
        story.append(Spacer(1, 6))
        story.append(
            safe_paragraph("APPENDIX: REPRODUCIBILITY & CODE AUDIT TRAIL", h1_style)
        )
        story.append(
            HRFlowable(
                width="100%", thickness=1, color=c_border, spaceBefore=1, spaceAfter=6
            )
        )
        story.append(
            safe_paragraph(
                "Empirical Python code executed inside the secure sandbox environment:",
                subtitle_style,
            )
        )
        story.append(Spacer(1, 4))

        for idx, code_snippet in enumerate(executed_code, 1):
            raw_lines = code_snippet.strip().split("\n")
            formatted_lines = [format_code_line(ln) for ln in raw_lines]

            CHUNK_SIZE = 12
            chunks = [
                formatted_lines[i : i + CHUNK_SIZE]
                for i in range(0, len(formatted_lines), CHUNK_SIZE)
            ]

            table_rows: list[list[Any]] = [
                [safe_paragraph(f"<b>// Step {idx} Query:</b>", code_style)]
            ]
            for chunk in chunks:
                chunk_html = "<br/>".join(chunk)
                table_rows.append([safe_paragraph(chunk_html, code_style, raw_fallback=code_snippet)])

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


# Backward compatibility aliases
_generate_fallback_chart = generate_fallback_chart
_sanitize_text_for_pdf = sanitize_text_for_pdf
_safe_paragraph = safe_paragraph
_clean_inline = clean_inline
_format_code_line = format_code_line
_format_markdown_for_reportlab = format_markdown_for_reportlab
