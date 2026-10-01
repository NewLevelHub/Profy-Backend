"""Expanded "what this means / what follows from it" copy for the RIASEC
interest map — pure content, no logic.

Shaped after how a career counsellor explains an interest level to a family
(see PRO-336): the level alone ("ведущий") is not an explanation, so every
type × level pair carries two short paragraphs — `means` (how the interest
shows up in everyday life) and `follows` (what it implies for choosing a
field). Addressed to the student ("ты"), gender-neutral wording.
"""


from typing import Literal

from app.i18n.catalog import key as i18n_key

Level = Literal["low", "medium", "high"]

# code -> level -> (means, follows)
TYPE_EXPLANATIONS: dict[str, dict[Level, tuple[str, str]]] = {
    "R": {
        "high": (
            i18n_key("riasec_explanations", "r_high_means", locale="ru"),
            i18n_key("riasec_explanations", "r_high_follows", locale="ru"),
        ),
        "medium": (
            i18n_key("riasec_explanations", "r_medium_means", locale="ru"),
            i18n_key("riasec_explanations", "r_medium_follows", locale="ru"),
        ),
        "low": (
            i18n_key("riasec_explanations", "r_low_means", locale="ru"),
            i18n_key("riasec_explanations", "r_low_follows", locale="ru"),
        ),
    },
    "I": {
        "high": (
            i18n_key("riasec_explanations", "i_high_means", locale="ru"),
            i18n_key("riasec_explanations", "i_high_follows", locale="ru"),
        ),
        "medium": (
            i18n_key("riasec_explanations", "i_medium_means", locale="ru"),
            i18n_key("riasec_explanations", "i_medium_follows", locale="ru"),
        ),
        "low": (
            i18n_key("riasec_explanations", "i_low_means", locale="ru"),
            i18n_key("riasec_explanations", "i_low_follows", locale="ru"),
        ),
    },
    "A": {
        "high": (
            i18n_key("riasec_explanations", "a_high_means", locale="ru"),
            i18n_key("riasec_explanations", "a_high_follows", locale="ru"),
        ),
        "medium": (
            i18n_key("riasec_explanations", "a_medium_means", locale="ru"),
            i18n_key("riasec_explanations", "a_medium_follows", locale="ru"),
        ),
        "low": (
            i18n_key("riasec_explanations", "a_low_means", locale="ru"),
            i18n_key("riasec_explanations", "a_low_follows", locale="ru"),
        ),
    },
    "S": {
        "high": (
            i18n_key("riasec_explanations", "s_high_means", locale="ru"),
            i18n_key("riasec_explanations", "s_high_follows", locale="ru"),
        ),
        "medium": (
            i18n_key("riasec_explanations", "s_medium_means", locale="ru"),
            i18n_key("riasec_explanations", "s_medium_follows", locale="ru"),
        ),
        "low": (
            i18n_key("riasec_explanations", "s_low_means", locale="ru"),
            i18n_key("riasec_explanations", "s_low_follows", locale="ru"),
        ),
    },
    "E": {
        "high": (
            i18n_key("riasec_explanations", "e_high_means", locale="ru"),
            i18n_key("riasec_explanations", "e_high_follows", locale="ru"),
        ),
        "medium": (
            i18n_key("riasec_explanations", "e_medium_means", locale="ru"),
            i18n_key("riasec_explanations", "e_medium_follows", locale="ru"),
        ),
        "low": (
            i18n_key("riasec_explanations", "e_low_means", locale="ru"),
            i18n_key("riasec_explanations", "e_low_follows", locale="ru"),
        ),
    },
    "C": {
        "high": (
            i18n_key("riasec_explanations", "c_high_means", locale="ru"),
            i18n_key("riasec_explanations", "c_high_follows", locale="ru"),
        ),
        "medium": (
            i18n_key("riasec_explanations", "c_medium_means", locale="ru"),
            i18n_key("riasec_explanations", "c_medium_follows", locale="ru"),
        ),
        "low": (
            i18n_key("riasec_explanations", "c_low_means", locale="ru"),
            i18n_key("riasec_explanations", "c_low_follows", locale="ru"),
        ),
    },
}

# riasec_service.consistency() of the top-2 pair -> hexagon relation + copy.
# {a}/{b} are nominative type labels (RIASEC_LABELS).
COMBINATION_TEXTS: dict[str, tuple[Literal["adjacent", "alternate", "opposite"], str]] = {
    "high": (
        "adjacent",
        i18n_key("riasec_explanations", "combination_high", locale="ru"),
    ),
    "medium": (
        "alternate",
        i18n_key("riasec_explanations", "combination_medium", locale="ru"),
    ),
    "low": (
        "opposite",
        i18n_key("riasec_explanations", "combination_low", locale="ru"),
    ),
}


def localized_type_explanation(code: str, level: Level) -> tuple[str, str]:
    """Resolve explanation copy at request time, after the locale context is set."""
    return (
        i18n_key("riasec_explanations", f"{code.lower()}_{level}_means"),
        i18n_key("riasec_explanations", f"{code.lower()}_{level}_follows"),
    )


def localized_combination_text(kind: str) -> tuple[Literal["adjacent", "alternate", "opposite"], str]:
    relation = {"high": "combination_high", "medium": "combination_medium", "low": "combination_low"}[kind]
    return COMBINATION_TEXTS[kind][0], i18n_key("riasec_explanations", relation)

# How many of the student's own answers to quote per level: (liked, disliked).
# A leading type is mostly explained by what was liked, an absent one by what
# was rejected — the mix mirrors which side actually moved the score.
QUOTE_MIX: dict[Level, tuple[int, int]] = {
    "high": (3, 1),
    "medium": (2, 2),
    "low": (1, 3),
}
