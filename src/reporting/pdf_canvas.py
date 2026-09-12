# Custom PDF canvas for page numbering and running headers and footers
from reportlab.lib import colors
from reportlab.pdfgen import canvas


# Two-pass canvas to count total pages and add page headers and footers
class NumberedCanvas(canvas.Canvas):

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

    # Draw header and footer lines and page numbers
    def draw_page_decorations(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#64748B"))

        page_num = getattr(self, "_pageNumber", 1)
        if page_num > 1:
            self.drawString(40, 762, "CSV INSIGHT AGENT — Executive Analytics Briefing")
            self.setStrokeColor(colors.HexColor("#CBD5E1"))
            self.setLineWidth(0.5)
            self.line(40, 756, 612 - 40, 756)

        self.drawString(
            40,
            25,
            "Confidential — Automated AI Data Intelligence & Executive Decision Support",
        )
        page_str = f"Page {page_num} of {page_count}"
        self.drawRightString(612 - 40, 25, page_str)

        self.setStrokeColor(colors.HexColor("#E2E8F0"))
        self.setLineWidth(0.75)
        self.line(40, 37, 612 - 40, 37)

        self.restoreState()
