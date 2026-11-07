"""Shared fixtures: tiny PDFs generated on the fly, so the repository holds no binaries."""

from __future__ import annotations

from pathlib import Path

import pytest


def make_text_pdf(path: Path, pages: int = 5) -> None:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    for n in range(1, pages + 1):
        c.setFont("Helvetica", 9)
        c.drawString(72, 800, "FAST Academic Rules Handbook 2026")          # running header
        c.drawString(72, 30, f"Page {n} of {pages}")                         # running footer
        c.setFont("Helvetica-Bold", 12)
        c.drawString(72, 740, f"{n}. Section number {n}")
        c.setFont("Helvetica", 10)
        c.drawString(72, 715, f"{n}.1 Students must attend lectures regularly in section {n}.")
        if n == 2:                                                           # a real table
            rows = [["Grade", "Points"], ["A", "4.00"], ["B", "3.00"], ["C", "2.00"]]
            y = 650
            for row in rows:
                c.drawString(100, y, row[0])
                c.drawString(300, y, row[1])
                c.line(90, y - 4, 400, y - 4)
                y -= 20
            c.line(90, 650 + 14, 400, 650 + 14)
            c.line(90, 650 + 14, 90, y + 16)
            c.line(250, 650 + 14, 250, y + 16)
            c.line(400, 650 + 14, 400, y + 16)
        c.showPage()
    c.save()


def make_scanned_pdf(path: Path) -> None:
    """An image-only PDF: no fonts, no text layer. Needs Pillow and reportlab."""
    from PIL import Image, ImageDraw, ImageFont
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas

    img = Image.new("RGB", (1600, 500), "white")
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=56)
    draw.text((40, 60), "Faculty start-up policy", fill="black", font=font)
    draw.text((40, 180), "Approval required from ORIC", fill="black", font=font)
    c = canvas.Canvas(str(path), pagesize=A4)
    c.drawImage(ImageReader(img), 40, 400, width=500, height=156)
    c.showPage()
    c.save()


@pytest.fixture()
def text_pdf(tmp_path: Path) -> Path:
    p = tmp_path / "rules.pdf"
    make_text_pdf(p)
    return p


@pytest.fixture()
def scanned_pdf(tmp_path: Path) -> Path:
    p = tmp_path / "scan.pdf"
    make_scanned_pdf(p)
    return p
