"""PRO-430: the Belbin methodological note in the psychologist report follows
the reader's locale — it used to be a module-level constant resolved once at
import time, i.e. always ru."""

from app.i18n import use_locale
from app.i18n.catalog import tr
from app.services import new_tests_report_service


def test_belbin_note_follows_the_request_locale() -> None:
    for locale in ("ru", "kk"):
        with use_locale(locale):
            note = new_tests_report_service._belbin_methodological_note()
        assert note == tr("report_copy", locale=locale)["belbin_methodological_note"]
