"""Theme-tinted SVG icons for QML: ``image://icon/<name>?color=%23rrggbb``.

Icons are stroke SVGs drawn with ``currentColor``; the provider substitutes the colour
and renders at the exact pixel size QML requests, so they stay crisp at any scale.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtQuick import QQuickImageProvider
from PySide6.QtSvg import QSvgRenderer

ICON_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"
_SAFE_NAME = re.compile(r"^[a-z0-9-]+$")
DEFAULT_SIZE = 20


@lru_cache(maxsize=256)
def _svg_source(name: str) -> str:
    if not _SAFE_NAME.match(name):
        raise ValueError(f"invalid icon name: {name!r}")
    path = ICON_DIR / f"{name}.svg"
    if not path.is_file():
        raise FileNotFoundError(f"unknown icon: {name}")
    return path.read_text(encoding="utf-8")


def available_icons() -> list[str]:
    return sorted(p.stem for p in ICON_DIR.glob("*.svg"))


def render_icon(name: str, color: str, size: QSize) -> QImage:
    svg = _svg_source(name).replace("currentColor", color)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    image = QImage(size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size.width(), size.height()))
    painter.end()
    return image


class IconProvider(QQuickImageProvider):
    def __init__(self) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)

    def requestImage(self, icon_id: str, size: QSize, requested_size: QSize) -> QImage:  # noqa: N802
        parts = urlsplit(icon_id)
        name = parts.path.strip("/")
        color = parse_qs(parts.query).get("color", ["#000000"])[0]
        if not QColor.isValidColorName(color):
            color = "#000000"
        width = requested_size.width() if requested_size.width() > 0 else DEFAULT_SIZE
        height = requested_size.height() if requested_size.height() > 0 else width
        try:
            image = render_icon(name, color, QSize(width, height))
        except (ValueError, FileNotFoundError):
            image = QImage(QSize(width, height), QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image
