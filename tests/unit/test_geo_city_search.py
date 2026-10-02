"""PRO-450 — translated city names resolve back to the ru `University.city`
values the catalogue search filters on."""
from app.i18n.geo import source_cities_matching


def test_full_kk_name_resolves_to_the_ru_city():
    assert source_cities_matching("Өскемен") == ["Усть-Каменогорск"]
    assert source_cities_matching("Орал") == ["Уральск"]


def test_match_is_partial_and_case_insensitive():
    assert source_cities_matching("өске") == ["Усть-Каменогорск"]
    assert source_cities_matching("  ҚАРАҒАН ") == ["Караганда"]


def test_one_translation_can_cover_several_ru_spellings():
    assert source_cities_matching("Екібастұз") == ["Екибастуз", "Экибастуз"]


def test_blank_or_unknown_text_matches_nothing():
    assert source_cities_matching("   ") == []
    assert source_cities_matching("Атлантида") == []
