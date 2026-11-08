"""Profile pictures and uploaded images for QML (``image://files/<ref>``), and picture prep."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt
from PySide6.QtGui import QImage, QPainter, QPainterPath
from PySide6.QtQuick import QQuickImageProvider

from ims.domain.common.errors import RuleViolation

PICTURE_SIZE = 512


class FileImageProvider(QQuickImageProvider):
    def __init__(self, read: Callable[[str], bytes | None]) -> None:
        super().__init__(QQuickImageProvider.ImageType.Image)
        self._read = read

    def requestImage(self, ref: str, size: QSize, requested_size: QSize) -> QImage:  # noqa: N802
        """``<ref>`` returns the image; ``<ref>?round`` returns it cropped to a circle."""
        name, _, options = ref.partition("?")
        data = self._read(name)
        image = QImage.fromData(data) if data else QImage()
        if image.isNull():
            image = QImage(QSize(1, 1), QImage.Format.Format_ARGB32_Premultiplied)
            image.fill(Qt.GlobalColor.transparent)
        elif requested_size.isValid() and not requested_size.isEmpty():
            image = image.scaled(
                requested_size,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
        if "round" in options.split("&") and not image.isNull() and image.width() > 1:
            image = _circle(image)
        size.setWidth(image.width())
        size.setHeight(image.height())
        return image


def _circle(image: QImage) -> QImage:
    """Square-crops ``image`` and masks it to a circle (no GPU effects needed)."""
    side = min(image.width(), image.height())
    out = QImage(side, side, QImage.Format.Format_ARGB32_Premultiplied)
    out.fill(Qt.GlobalColor.transparent)
    painter = QPainter(out)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addEllipse(0, 0, side, side)
    painter.setClipPath(path)
    painter.drawImage(0, 0, image, (image.width() - side) // 2, (image.height() - side) // 2)
    painter.end()
    return out


def prepare_picture(path: str) -> bytes:
    """Loads an image file, crops it to a centred square and saves a 512 px PNG."""
    image = QImage(path)
    if image.isNull():
        raise RuleViolation("That file is not a picture this app can read (use PNG or JPEG).")
    side = min(image.width(), image.height())
    square = image.copy((image.width() - side) // 2, (image.height() - side) // 2, side, side)
    scaled = square.scaled(
        PICTURE_SIZE,
        PICTURE_SIZE,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    # PySide accepts the format as str at runtime; its type stubs wrongly say bytes.
    scaled.save(buffer, "PNG")  # type: ignore[call-overload]
    buffer.close()
    return bytes(data.data())
