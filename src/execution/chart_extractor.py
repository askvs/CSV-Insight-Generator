# Chart extractor for sandbox matplotlib figures
import io
import matplotlib.pyplot as plt


# Save all active matplotlib figures as PNG bytes and close them
def extract_all_chart_pngs() -> list[bytes]:
    fig_nums = list(plt.get_fignums())
    if not fig_nums:
        return []

    pngs = []
    for num in fig_nums:
        try:
            fig = plt.figure(num)
            buf = io.BytesIO()
            fig.savefig(buf, format="png", bbox_inches="tight", dpi=100)
            buf.seek(0)
            pngs.append(buf.getvalue())
        except Exception:
            pass
    plt.close("all")
    return pngs


# Save the first active matplotlib figure as PNG bytes
def extract_chart_png() -> bytes | None:
    all_pngs = extract_all_chart_pngs()
    return all_pngs[0] if all_pngs else None


# Aliases for backward compatibility
_extract_all_chart_pngs = extract_all_chart_pngs
_extract_chart_png = extract_chart_png
