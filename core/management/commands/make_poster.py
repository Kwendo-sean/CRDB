"""Print-ready QR poster in the Learning Week visual language.

Vector throughout — the QR is drawn as rectangles, not a bitmap — so the same
file prints crisply at A4 or blown up to A2 on a stand.
"""

from pathlib import Path

import qrcode
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

# Straight from static/css/app.css so print matches the site.
INK = (7 / 255, 8 / 255, 8 / 255)
PAPER = (241 / 255, 242 / 255, 238 / 255)
RED = (223 / 255, 31 / 255, 38 / 255)
MUTED = (155 / 255, 162 / 255, 158 / 255)
RULE = (42 / 255, 48 / 255, 46 / 255)

SIZES = {"a4": (595.28, 841.89), "a3": (841.89, 1190.55), "a2": (1190.55, 1683.78)}


class Command(BaseCommand):
    help = "Generate a printable A4/A3/A2 QR poster pointing at the participant sign-in page."

    def add_arguments(self, parser):
        parser.add_argument("--url", default="", help="Target URL (default: APP_BASE_URL + /access/)")
        parser.add_argument("--output", default="crdb-learning-week-poster.pdf")
        parser.add_argument("--size", default="a4", choices=sorted(SIZES))
        parser.add_argument("--headline", default="SCAN TO JOIN")
        parser.add_argument("--all-sizes", action="store_true", help="Write one PDF per paper size.")

    def handle(self, *args, **options):
        try:
            from reportlab.lib.utils import simpleSplit
            from reportlab.pdfgen import canvas
        except ImportError as exc:  # pragma: no cover - dev-only dependency
            raise CommandError(
                "reportlab is required for the poster and is a dev dependency.\n"
                "  Install it with: uv sync --extra dev"
            ) from exc

        url = options["url"] or f"{settings.APP_BASE_URL}/access/"
        targets = sorted(SIZES) if options["all_sizes"] else [options["size"]]
        for size in targets:
            out = Path(options["output"])
            if options["all_sizes"]:
                out = out.with_name(f"{out.stem}-{size}{out.suffix}")
            self._draw(canvas, simpleSplit, out, url, SIZES[size], options["headline"])
            self.stdout.write(self.style.SUCCESS(f"  {size.upper():>3}  {out.resolve()}"))
        self.stdout.write(f"\nQR points at: {url}")

    def _draw(self, canvas_module, simpleSplit, path, url, page, headline):
        width, height = page
        unit = width / 595.28  # scale everything off A4 so every size is identical
        pdf = canvas_module.Canvas(str(path), pagesize=page)
        pdf.setTitle("CRDB x PAL Learning Week - Scan to Join")
        pdf.setAuthor("CRDB Bank x Predictive Analytics Lab")

        # Ground
        pdf.setFillColorRGB(*INK)
        pdf.rect(0, 0, width, height, stroke=0, fill=1)

        margin = 48 * unit

        # Masthead
        y = height - margin - 18 * unit
        pdf.setFillColorRGB(*PAPER)
        pdf.setFont("Helvetica-Bold", 20 * unit)
        pdf.drawString(margin, y, "CRDB")
        crdb_w = pdf.stringWidth("CRDB", "Helvetica-Bold", 20 * unit)
        pdf.setFillColorRGB(*RED)
        pdf.drawString(margin + crdb_w + 7 * unit, y, "x")
        x_w = pdf.stringWidth("x", "Helvetica-Bold", 20 * unit)
        pdf.setFillColorRGB(*PAPER)
        pdf.setFont("Helvetica", 20 * unit)
        pdf.drawString(margin + crdb_w + x_w + 14 * unit, y, "PAL")

        pdf.setFillColorRGB(*MUTED)
        pdf.setFont("Courier", 8 * unit)
        pdf.drawRightString(width - margin, y + 4 * unit, "LEARNING WEEK / 2026")
        pdf.drawRightString(width - margin, y - 7 * unit, "07-10 SEP")

        y -= 16 * unit
        pdf.setStrokeColorRGB(*RULE)
        pdf.setLineWidth(0.75 * unit)
        pdf.line(margin, y, width - margin, y)

        # Headline
        y -= 54 * unit
        pdf.setFillColorRGB(*PAPER)
        pdf.setFont("Helvetica-Bold", 46 * unit)
        for line in headline.upper().split("\n"):
            pdf.drawString(margin, y, line)
            y -= 46 * unit
        pdf.setFillColorRGB(*RED)
        pdf.setFont("Helvetica-Bold", 46 * unit)
        pdf.drawString(margin, y, "AND PLAY.")

        y -= 26 * unit
        pdf.setFillColorRGB(*MUTED)
        pdf.setFont("Helvetica", 12 * unit)
        blurb = ("Quizzes, VR games, robot and Arduino assembly. "
                 "Collect points all week and climb the leaderboard.")
        for line in simpleSplit(blurb, "Helvetica", 12 * unit, width - 2 * margin):
            y -= 15 * unit
            pdf.drawString(margin, y, line)

        # QR panel
        panel = width - 2 * margin
        qr_top = y - 30 * unit
        panel_h = panel * 0.78
        panel_y = qr_top - panel_h
        pdf.setFillColorRGB(*PAPER)
        pdf.rect(margin, panel_y, panel, panel_h, stroke=0, fill=1)

        code = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, border=0)
        code.add_data(url)
        code.make(fit=True)
        matrix = code.get_matrix()
        modules = len(matrix)
        quiet = 22 * unit
        qr_side = min(panel, panel_h) - 2 * quiet
        module = qr_side / modules
        origin_x = margin + (panel - qr_side) / 2
        origin_y = panel_y + (panel_h - qr_side) / 2

        pdf.setFillColorRGB(*INK)
        for row_index, row in enumerate(matrix):
            # Draw each run of dark modules as one rectangle: fewer objects, and
            # no hairline seams between neighbouring squares when printed.
            start = None
            for col_index, dark in enumerate(row + [False]):
                if dark and start is None:
                    start = col_index
                elif not dark and start is not None:
                    pdf.rect(origin_x + start * module,
                             origin_y + (modules - row_index - 1) * module,
                             (col_index - start) * module, module, stroke=0, fill=1)
                    start = None

        # Call to action
        y = panel_y - 34 * unit
        pdf.setFillColorRGB(*RED)
        pdf.setFont("Helvetica-Bold", 15 * unit)
        pdf.drawString(margin, y, "1.")
        pdf.drawString(margin + 108 * unit, y, "2.")
        pdf.drawString(margin + 216 * unit, y, "3.")
        pdf.setFillColorRGB(*PAPER)
        pdf.setFont("Helvetica", 10 * unit)
        pdf.drawString(margin + 16 * unit, y, "Scan this code")
        pdf.drawString(margin + 124 * unit, y, "Enter your email")
        pdf.drawString(margin + 232 * unit, y, "Start playing")

        y -= 30 * unit
        pdf.setStrokeColorRGB(*RULE)
        pdf.line(margin, y, width - margin, y)

        # The address, for anyone whose camera will not cooperate
        y -= 22 * unit
        pdf.setFillColorRGB(*MUTED)
        pdf.setFont("Courier", 7.5 * unit)
        pdf.drawString(margin, y, "OR TYPE IT IN")
        y -= 16 * unit
        pdf.setFillColorRGB(*PAPER)
        typed = url.replace("https://", "").replace("http://", "")
        pdf.setFont("Courier-Bold", 11 * unit)
        while pdf.stringWidth(typed, "Courier-Bold", 11 * unit) > width - 2 * margin:
            pdf.setFont("Courier-Bold", 10 * unit)
            break
        pdf.drawString(margin, y, typed)

        pdf.setFillColorRGB(*MUTED)
        pdf.setFont("Courier", 7 * unit)
        footer = margin - 16 * unit
        pdf.drawString(margin, footer, "AI IMPACT ON BANKING & SKILLS")
        pdf.drawRightString(width - margin, footer, "NO PASSWORD NEEDED")

        pdf.showPage()
        pdf.save()
