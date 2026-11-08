from __future__ import annotations

import re
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication

from ims.ui.labels import Label, qr_payload, write_label_sheet


def page_count(pdf: Path) -> int:
    return len(re.findall(rb"/Type\s*/Page[^s]", pdf.read_bytes()))


def test_qr_payload_identifies_the_asset() -> None:
    assert qr_payload("DRN-0001") == "IMS:DRN-0001"


def test_sheets_hold_21_labels_and_start_position_skips_used_ones(
    qapp: QApplication, tmp_path: Path
) -> None:
    labels = [Label(f"MOT-{i:04d}", "Motor", f"M-{i}") for i in range(21)]
    one = tmp_path / "one.pdf"
    assert write_label_sheet(labels, one) == 1
    assert one.read_bytes().startswith(b"%PDF") and page_count(one) == 1
    two = tmp_path / "two.pdf"
    assert write_label_sheet(labels, two, start_position=1) == 2
    assert page_count(two) == 2


def test_long_tags_and_titles_still_write(qapp: QApplication, tmp_path: Path) -> None:
    label = Label("DGPS-ROVER-000001-SPARE", "DGPS receiver (base / rover) · Trimble R12i", "")
    assert write_label_sheet([label], tmp_path / "long.pdf", start_position=20) == 1


@pytest.mark.parametrize("start", [-1, 21])
def test_bad_input_is_refused(qapp: QApplication, tmp_path: Path, start: int) -> None:
    with pytest.raises(ValueError, match="no labels"):
        write_label_sheet([], tmp_path / "x.pdf")
    with pytest.raises(ValueError, match="start position"):
        write_label_sheet([Label("A-1", "A")], tmp_path / "x.pdf", start_position=start)
