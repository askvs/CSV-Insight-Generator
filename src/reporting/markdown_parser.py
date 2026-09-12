# Markdown block parser for PDF report generation
import re
from typing import Any
from .pdf_formatting import clean_inline, sanitize_text_for_pdf


# Parse markdown text into structured content blocks for PDF rendering
def format_markdown_for_reportlab(text: str) -> list[tuple[str, Any]]:
    text = sanitize_text_for_pdf(text)
    raw_lines = text.strip().split("\n")
    blocks: list[tuple[str, Any]] = []

    i = 0
    while i < len(raw_lines):
        line = raw_lines[i].strip()
        if not line:
            i += 1
            continue

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

        if line.startswith("|") and line.endswith("|") and line.count("|") >= 2:
            table_raw: list[list[str]] = []
            while i < len(raw_lines) and raw_lines[i].strip().startswith("|"):
                row_str = raw_lines[i].strip()
                if not re.match(r"^\|(\s*:?-+:?\s*\|)+$", row_str):
                    cells = [c.strip() for c in row_str.split("|")[1:-1]]
                    if any(cells):
                        table_raw.append(cells)
                i += 1

            if table_raw:
                blocks.append(("table", table_raw))
            continue

        if line.startswith("#### "):
            clean_text = line[5:].strip()
            blocks.append(("h3", clean_inline(clean_text)))
            i += 1
            continue
        elif line.startswith("### "):
            clean_text = line[4:].strip()
            blocks.append(("h3", clean_inline(clean_text)))
            i += 1
            continue
        elif line.startswith("## "):
            clean_text = line[3:].strip()
            blocks.append(("h2", clean_inline(clean_text)))
            i += 1
            continue
        elif line.startswith("# "):
            clean_text = line[2:].strip()
            blocks.append(("h1", clean_inline(clean_text)))
            i += 1
            continue

        bold_header_match = re.match(
            r"^\*\*([0-9]+\.\s*)?([A-Za-z0-9\s,&/–-]+):?\*\*\s*$", line
        )
        if bold_header_match:
            hdr_text = bold_header_match.group(0).replace("**", "").strip()
            blocks.append(("h2", clean_inline(hdr_text)))
            i += 1
            continue

        if line in ("---", "***", "___"):
            i += 1
            continue

        line_lower = line.lower()

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
            blocks.append(("recommendation", clean_inline(line)))
            i += 1
            continue

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
            blocks.append(("risk", clean_inline(line)))
            i += 1
            continue

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
            blocks.append(("key_insight", clean_inline(line)))
            i += 1
            continue

        bullet_match = re.match(r"^(\*|\-|\•)\s+(.*)$", line)
        if bullet_match:
            item_text = bullet_match.group(2)
            blocks.append(("bullet", clean_inline(item_text)))
            i += 1
            continue

        numbered_match = re.match(r"^(\d+[\.\)])\s+(.*)$", line)
        if numbered_match:
            prefix = numbered_match.group(1)
            item_text = numbered_match.group(2)
            blocks.append(("numbered", f"<b>{prefix}</b> {clean_inline(item_text)}"))
            i += 1
            continue

        blocks.append(("body", clean_inline(line)))
        i += 1

    return blocks
