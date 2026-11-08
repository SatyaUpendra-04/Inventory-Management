from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from PySide6.QtCore import QSize
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication

from ims.domain.common.errors import NotFound, RuleViolation
from ims.domain.identity.roles import Role
from ims.domain.identity.user import PilotLicence
from ims.ui.images import FileImageProvider, prepare_picture
from ims.ui.models.dict_list import DictListModel
from ims.ui.tasks import TaskQueue
from ims.ui.viewmodels import forms

pytestmark = pytest.mark.ui


class TestTaskQueue:
    def test_runs_off_thread_and_delivers_on_the_ui_thread(self, qapp: QApplication) -> None:
        import threading

        queue = TaskQueue()
        main = threading.get_ident()
        seen: dict[str, object] = {}
        busy_changes: list[bool] = []
        queue.busyChanged.connect(lambda: busy_changes.append(queue.busy))
        queue.submit(
            lambda: threading.get_ident(),
            lambda worker: seen.update(worker=worker, callback=threading.get_ident()),
        )
        queue.wait_until_idle()
        assert seen["worker"] != main and seen["callback"] == main
        assert busy_changes == [True, False]

    def test_errors_go_to_the_error_callback(self, qapp: QApplication) -> None:
        for synchronous in (False, True):
            queue = TaskQueue(synchronous=synchronous)
            errors: list[BaseException] = []

            def boom() -> None:
                raise NotFound("gone")

            queue.submit(boom, on_error=errors.append)
            queue.submit(boom)  # no handler: logged, not raised
            queue.wait_until_idle()
            assert [str(e) for e in errors] == ["gone"]
            assert not queue.busy

    def test_tasks_run_in_order(self, qapp: QApplication) -> None:
        queue = TaskQueue()
        order: list[int] = []
        for n in range(10):
            queue.submit(lambda n=n: n, order.append)
        queue.wait_until_idle()
        assert order == list(range(10))


class TestImages:
    def test_prepare_picture_crops_square_png(self, qapp: QApplication, tmp_path: Path) -> None:
        image = QImage(800, 400, QImage.Format.Format_RGB32)
        image.fill(QColor("#ff0000"))
        path = tmp_path / "wide.jpg"
        image.save(str(path))
        png = prepare_picture(str(path))
        assert png.startswith(b"\x89PNG")
        result = QImage.fromData(png)
        assert (result.width(), result.height()) == (512, 512)

    def test_prepare_picture_rejects_non_images(self, qapp: QApplication, tmp_path: Path) -> None:
        path = tmp_path / "fake.png"
        path.write_bytes(b"not an image")
        with pytest.raises(RuleViolation, match="not a picture"):
            prepare_picture(str(path))

    def test_provider_scales_and_rounds(self, qapp: QApplication, tmp_path: Path) -> None:
        image = QImage(100, 100, QImage.Format.Format_RGB32)
        image.fill(QColor("#00ff00"))
        path = tmp_path / "p.png"
        image.save(str(path))
        data = path.read_bytes()
        provider = FileImageProvider(lambda ref: data if ref == "x.png" else None)
        size = QSize()
        square = provider.requestImage("x.png", size, QSize(40, 40))
        assert (square.width(), size.width()) == (40, 40)
        assert square.pixelColor(0, 0).alpha() == 255
        round_ = provider.requestImage("x.png?round", QSize(), QSize(40, 40))
        assert round_.pixelColor(0, 0).alpha() == 0 and round_.pixelColor(20, 20).alpha() == 255
        missing = provider.requestImage("nope.png?round", QSize(), QSize(40, 40))
        assert missing.width() == 1


class TestForms:
    def test_errors_read_as_sentences(self) -> None:
        assert forms.describe_error(RuleViolation(["email: email address is not valid"])) == (
            "Email address is not valid."
        )
        assert forms.describe_error(NotFound("User not found.")) == "User not found."
        assert "log file" in forms.describe_error(ZeroDivisionError())

    def test_values(self) -> None:
        assert forms.text({"a": "  x "}, "a") == "x" and forms.text({}, "a") == ""
        assert forms.optional_date({"d": "2026-11-08T00:00"}, "d") == date(2026, 11, 8)
        assert forms.optional_date({"d": ""}, "d") is None
        assert forms.optional_decimal({"n": "1,250.5"}, "n", "Area") == Decimal("1250.5")
        with pytest.raises(RuleViolation, match="Area must be a number"):
            forms.optional_decimal({"n": "lots"}, "n", "Area")

    def test_licence_parsing_keeps_document_for_same_number(self) -> None:
        existing = PilotLicence(number="RPC-1", expires_on=date(2027, 1, 1), document="a.pdf")
        same = forms.licence_from(
            {"licenceNumber": "rpc-1", "licenceExpiry": "2028-01-01"}, existing
        )
        assert same is not None and same.document == "a.pdf" and same.expires_on.year == 2028
        new = forms.licence_from(
            {"licenceNumber": "RPC-2", "licenceExpiry": "2028-01-01"}, existing
        )
        assert new is not None and new.document is None
        assert forms.licence_from({}) is None
        with pytest.raises(RuleViolation, match="both the licence number"):
            forms.licence_from({"licenceNumber": "RPC-2"})

    def test_user_fields_and_helpers(self) -> None:
        fields = forms.user_fields(
            {"fullName": "A B", "role": "pilot", "licenceNumber": "", "licenceExpiry": ""}
        )
        assert fields["role"] is Role.PILOT and fields["licence"] is None
        assert forms.initials("Ravi Kumar Das") == "RD" and forms.initials("Ravi") == "RA"
        assert forms.initials("") == "?"
        assert (
            forms.local_path("file:///C:/pics/me.png").replace("\\", "/").endswith("C:/pics/me.png")
        )
        assert forms.local_path("C:/pics/me.png") == "C:/pics/me.png"


def test_dict_list_model_checks_rows(qapp: QApplication) -> None:
    model = DictListModel(["a", "b"])
    model.reset([{"a": 1, "b": 2}])
    assert model.rowCount() == 1 and model.find("a", 1) == {"a": 1, "b": 2}
    assert model.find("a", 9) == {}
    with pytest.raises(KeyError, match="missing roles"):
        model.reset([{"a": 1}])
