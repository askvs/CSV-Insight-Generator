# Text sanitization and formatting helpers for PDF reports
import html
import re
import textwrap
import unicodedata
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import Paragraph


# Replace emojis and unsupported unicode symbols with clean text
def sanitize_text_for_pdf(text: str) -> str:
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

    unicode_replacements = {
        "\u20b9": "Rs. ",
        "\u20bd": "RUB ",
        "\u20ba": "TRY ",
        "\u20a9": "KRW ",
        "\u20ab": "VND ",
        "\u20aa": "ILS ",
        "\u0e3f": "THB ",
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": " - ",
        "\u2015": "-",
        "\u2212": "-",
        "\u00ad": "",
        "\u202f": " ",
        "\u200b": "",
        "\u200c": "",
        "\u200d": "",
        "\u2009": " ",
        "\u200a": " ",
        "\u2002": " ",
        "\u2003": " ",
        "\u2004": " ",
        "\u2005": " ",
        "\u2006": " ",
        "\u3000": " ",
        "\u2248": "~",
        "\u2260": "!=",
        "\u2264": "<=",
        "\u2265": ">=",
        "\u00d7": "x",
        "\u00f7": "/",
        "\u2026": "...",
        "\u2022": "-",
        "\u25cf": "-",
        "\u25a0": "-",
        "\u25aa": "-",
        "\u25b6": ">",
        "\u2714": "[OK]",
        "\u2713": "[OK]",
        "\u2717": "[X]",
        "\u2718": "[X]",
        "\u201c": '"',
        "\u201d": '"',
        "\u2018": "'",
        "\u2019": "'",
        "\u00b1": "+/-",
        "\u221e": "inf",
    }
    for orig, rep in unicode_replacements.items():
        text = text.replace(orig, rep)

    text = re.sub(r"[\U00010000-\U0010ffff]", "", text)

    safe_chars = []
    for ch in text:
        try:
            ch.encode("latin1")
            safe_chars.append(ch)
        except UnicodeEncodeError:
            norm = (
                unicodedata.normalize("NFKD", ch)
                .encode("ascii", "ignore")
                .decode("ascii")
            )
            safe_chars.append(norm if norm else " ")

    return "".join(safe_chars)


# Safely create a ReportLab paragraph without breaking on formatting errors
def safe_paragraph(text: str, style: ParagraphStyle, raw_fallback: str | None = None) -> Paragraph:
    try:
        return Paragraph(text, style)
    except Exception:
        fallback = raw_fallback if raw_fallback is not None else re.sub(r"<[^>]*>", "", str(text))
        return Paragraph(html.escape(str(fallback)), style)


# Convert inline markdown formatting to ReportLab HTML tags
def clean_inline(s: str) -> str:
    esc = html.escape(s)
    esc = re.sub(r"&lt;br\s*/?&gt;", "<br/>", esc, flags=re.IGNORECASE)
    esc = re.sub(r"\*\*\*(.*?)\*\*\*", r"<b><i>\1</i></b>", esc)
    esc = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", esc)
    esc = re.sub(r"\*(.*?)\*", r"<i>\1</i>", esc)
    esc = re.sub(r"`(.*?)`", r"<font face='Courier' size='8'>\1</font>", esc)
    return esc


# Format a single line of python code for ReportLab display
def format_code_line(line: str, max_width: int = 90) -> str:
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
