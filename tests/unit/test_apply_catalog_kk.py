"""Guards for scripts/apply_catalog_descriptions_kk.py — the offline authoring
script that writes `*_i18n['kk']` overlays (run from start.sh / CD).

Regression cover for the review of 2026-09-08:
  * is_kazakh() must not silently reject valid kk values (all-Latin terms,
    short strings, Latin abbreviations with attached punctuation);
  * _sort_catalog() must not IndexError on an entry with an empty ref list.
"""
import importlib

apply_kk = importlib.import_module("scripts.apply_catalog_descriptions_kk")


class TestIsKazakh:
    def test_accepts_all_latin_and_abbreviations(self):
        for v in ("Data Science, AI.", "IT, MBA", "MBA", "IT,, MBA. 2026)"):
            assert apply_kk.is_kazakh(v) is True, v

    def test_accepts_short_or_empty(self):
        for v in ("", "  ", "abc", "AI"):
            assert apply_kk.is_kazakh(v) is True, v

    def test_latin_abbreviations_do_not_sink_a_real_kk_sentence(self):
        # "IT," / "HR," must be treated as Latin despite the comma, so the two
        # Kazakh words still carry the ratio.
        assert apply_kk.is_kazakh("IT, HR, MBA — Нархоз университеті") is True

    def test_still_rejects_untranslated_russian(self):
        assert apply_kk.is_kazakh(
            "Русское описание программы для специалистов которые очень нужны"
        ) is False
        assert apply_kk.is_kazakh(
            "который чтобы нужно тебе если когда только уже потому"
        ) is False

    def test_accepts_real_kazakh_prose(self):
        assert apply_kk.is_kazakh(
            "Бағдарламалық қамтамасыз етуді әзірлеуге баулитын бағдарлама"
        ) is True


class TestIsKazakhName:
    def test_accepts_identical_international_term(self):
        assert apply_kk.is_kazakh_name("Биология", "Биология") is True

    def test_accepts_latin_name(self):
        assert apply_kk.is_kazakh_name("Satbayev University", "Satbayev University") is True

    def test_rejects_blank(self):
        assert apply_kk.is_kazakh_name("", "X") is False
        assert apply_kk.is_kazakh_name("  -  ", "X") is False


def test_sort_catalog_tolerates_empty_ref_lists():
    data = {
        "universities": [{"slugs": [], "ru": "a", "kk": "а"},
                         {"slugs": ["nu"], "ru": "b", "kk": "б"}],
        "programs": [{"rows": [], "ru": "p", "kk": "п"}],
        "university_names": [{"slug": "", "ru": "x", "kk": "х"}],
        "program_names": [{"ru": "n", "kk": "н", "slugs": []}],
    }
    # must not raise
    apply_kk._sort_catalog(data)
    assert [e["ru"] for e in data["universities"]] == ["a", "b"]
