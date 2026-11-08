"""Printable asset labels: A4 sheets of 21 labels (63.5 x 38.1 mm, 3 x 7) with a QR code.

The QR code holds ``IMS:<asset tag>`` so a phone or scanner can identify the asset later.
QR modules are drawn as vector rectangles, so labels print sharp at any printer resolution.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import segno
from PySide6.QtCore import QMarginsF, QRectF, QSizeF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetricsF,
    QPageLayout,
    QPageSize,
    QPainter,
    QPdfWriter,
)

COLUMNS, ROWS = 3, 7
LABEL_W_MM, LABEL_H_MM = 63.5, 38.1
LEFT_MM, TOP_MM = 7.2, 15.1  # standard 21-up sheet margins
GAP_X_MM = 2.5


@dataclass(frozen=True, slots=True)
class Label:
    tag: str
    title: str
    serial: str = ""


def qr_payload(tag: str) -> str:
    return f"IMS:{tag}"


def write_label_sheet(labels: Sequence[Label], path: Path, *, start_position: int = 0) -> int:
    """Writes a PDF of label sheets; ``start_position`` skips used labels on the first sheet.

    Returns the number of pages written.
    """
    if not labels:
        raise ValueError("no labels to print")
    if not 0 <= start_position < COLUMNS * ROWS:
        raise ValueError("start position must be within the first sheet")
    writer = QPdfWriter(str(path))
    writer.setPageLayout(
        QPageLayout(
            QPageSize(QPageSize.PageSizeId.A4), QPageLayout.Orientation.Portrait, QMarginsF()
        )
    )
    writer.setResolution(600)
    writer.setTitle("Asset labels")
    writer.setCreator("Inventory Management")
    dots_per_mm = writer.resolution() / 25.4

    painter = QPainter(writer)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
    pages = 1
    slot = start_position
    for label in labels:
        if slot == COLUMNS * ROWS:
            writer.newPage()
            pages += 1
            slot = 0
        column, row = slot % COLUMNS, slot // COLUMNS
        x = (LEFT_MM + column * (LABEL_W_MM + GAP_X_MM)) * dots_per_mm
        y = (TOP_MM + row * LABEL_H_MM) * dots_per_mm
        _draw_label(
            painter,
            label,
            QRectF(x, y, LABEL_W_MM * dots_per_mm, LABEL_H_MM * dots_per_mm),
            dots_per_mm,
        )
        slot += 1
    painter.end()
    return pages


def _draw_label(painter: QPainter, label: Label, box: QRectF, mm: float) -> None:
    padding = 3 * mm
    qr_size = box.height() - 2 * padding
    _draw_qr(
        painter,
        qr_payload(label.tag),
        QRectF(box.x() + padding, box.y() + padding, qr_size, qr_size),
    )
    text_x = box.x() + padding * 2 + qr_size
    text_w = box.right() - padding - text_x
    painter.setPen(QColor("#000000"))

    tag_font = QFont("Segoe UI", 1)
    tag_font.setWeight(QFont.Weight.Bold)
    size = round(5.2 * mm)
    while True:  # shrink long tags until they fit beside the QR code
        tag_font.setPixelSize(size)
        if QFontMetricsF(tag_font).horizontalAdvance(label.tag) <= text_w or size <= 2 * mm:
            break
        size = round(size * 0.92)
    painter.setFont(tag_font)
    painter.drawText(
        QRectF(text_x, box.y() + padding, text_w, 7 * mm),
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        label.tag,
    )

    small = QFont("Segoe UI", 1)
    small.setPixelSize(round(2.6 * mm))
    painter.setFont(small)
    painter.drawText(
        QRectF(text_x, box.y() + padding + 8 * mm, text_w, 12 * mm),
        int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop) | int(Qt.TextFlag.TextWordWrap),
        label.title,
    )
    if label.serial:
        painter.drawText(
            QRectF(text_x, box.bottom() - padding - 4 * mm, text_w, 4 * mm),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignBottom,
            f"S/N {label.serial}",
        )


def _draw_qr(painter: QPainter, payload: str, area: QRectF) -> None:
    code = segno.make(payload, error="m")
    matrix = list(code.matrix)
    quiet = 2  # modules of white border around the code
    count = len(matrix) + quiet * 2
    module = min(area.width(), area.height()) / count
    painter.fillRect(area, QColor("#ffffff"))
    black = QColor("#000000")
    for r, row in enumerate(matrix):
        for c, cell in enumerate(row):
            if cell:
                painter.fillRect(
                    QRectF(
                        area.x() + (c + quiet) * module,
                        area.y() + (r + quiet) * module,
                        module + 0.5,
                        module + 0.5,
                    ),
                    black,
                )


def page_size_mm() -> QSizeF:
    return QPageSize(QPageSize.PageSizeId.A4).size(QPageSize.Unit.Millimeter)
