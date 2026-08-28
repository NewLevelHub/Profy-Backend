"""Generates scripts/data/jinaq/kz_university_merge_review.json — a review
file for confirming which of the 85 "new" KZ University rows created by
scripts/import_jinaq_universities.py are actually duplicates of an
already-existing curated row under a different name string (abbreviations,
"имени"/"им.", EN/RU name pairs, institution renames, Astana/Nur-Sultan
city naming, spelling variants — checked by hand across all 85, not a
category/keyword heuristic).

This is a DRAFT, not an authoritative merge decision — same discipline as
the specialty->profession mapping: a human confirms each pair (or rejects
it) before scripts/apply_kz_university_merge.py (to be written once this
file is reviewed) touches the database. Getting an identity merge wrong is
much more destructive than a wrong profession tag (it would fold two real,
different universities into one), so `confirmed` defaults to false for
every single entry, including the ones marked high confidence — nothing
merges until a human flips it to true.

Run inside the api container:
  docker-compose exec api python scripts/generate_kz_university_merge_review.py
"""
import asyncio
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import select

from app.database import async_session
from app.models.university import University
from app.models.university_external_ref import UniversityExternalRef

OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "jinaq", "kz_university_merge_review.json"
)

# external_id -> (proposed curated slug or None, confidence, reason)
# confidence: "high" | "medium" | "low" | "none"
DRAFT: dict[str, tuple[str | None, str, str]] = {
    "1003": ("amu", "high", "EN/RU name pair (Astana Medical University / Медицинский университет Астана), city matches"),
    "982": ("mezhdunarodnaya-obrazovatelnaya-korporacziya", "high", "EN/RU translation of the same name, city matches"),
    "981": ("mezhdunarodnyj-inzhenerno-tehnologicheskij-universitet", "high", "EN/RU translation, city matches"),
    "983": ("mezhdunarodnyy-transportno-gumanitarnyy-universitet", "high", "EN/RU translation, city matches"),
    "1062": ("mezhdunarodnyy-kazahsko-turetskiy-universitet-imeni-hodzhi-ahmeda-yasavi", "high", "EN/RU translation, city Туркестан matches both"),
    "1051": ("kyzylordinskiy-universitet-imeni-korkyt-ata", "high", "EN/RU translation + reorder, city matches"),
    "1050": ("bolashak-universitet-kyzylorda", "high", "EN/RU translation, city matches"),
    "1048": ("kyzylordinskiy-otkrytiy-universitet", "high", "EN/RU translation, city matches"),
    "1065": (None, "none", "no candidate found in curated KZ list"),
    "5": (None, "none", "no candidate found in curated KZ list — real, well-known university, likely just genuinely missing from curated set"),
    "1017": ("aktyubinskiy-regionalnyy-universitet", "high", "punctuation-only difference (space after 'К.')"),
    "959": ("almatinskij-gumanitarno-ekonomicheskij-universitet", "high", "curated row just adds the (АГЭУ) abbreviation suffix"),
    "955": ("almatinskij-tehnologicheskij-universitet", "high", "curated row just adds the (АТУ) abbreviation suffix"),
    "985": ("almatinskij-universitet-energetiki-i-svyazi", "high", "curated row just adds the (АУЭС) abbreviation suffix"),
    "958": ("almaty-management-university", "high", "EN/RU name pair, city matches"),
    "1041": ("arkalykskiy-pedagogicheskiy-universitet", "medium", "институт (jinaq) vs университет (curated), same city and namesake"),
    "993": ("astana-it-university", "high", "EN/RU name pair, city matches"),
    "1021": ("atyrauskiy-universitet-dosmuhamedova", "high", "abbreviated vs full first name of same namesake"),
    "1020": ("atyrauskiy-universitet-nefti-i-gaza", "high", "abbreviated vs full first name of same namesake"),
    "1027": ("vostochno-kazakhstanskiy-universitet", "high", "curated drops 'государственный', same namesake and city"),
    "1022": ("vktu-ust-kamenogorsk", "high", "curated drops the 'имени Д. Серикбаева' suffix, same city"),
    "1012": (None, "none", "no candidate found — Кокшетау city not otherwise represented in curated KZ list"),
    "957": ("de-montfort-yuniversiti-kazahstan", "high", "'Университет' vs 'Юниверсити' transliteration variant, same city"),
    "999": ("l-n-gumilyov-eurasian-national-university", "high", "EN/RU name pair, city matches"),
    "961": ("egipetskij-universitet-islamskoj-kultury-nur-mubarak", "high", "curated drops trailing 'в Казахстане', same city"),
    "1055": ("ekibastuzskiy-inzhenerno-tekhnicheskiy-institut-satpaeva", "high", "'Екибастузский'/'Экибастузский' spelling variant only"),
    "995": ("esil-university", "high", "EN/RU name pair, city matches"),
    "1030": (None, "none", "no candidate found — curated's only Zapadno-Kazakhstan entry is the medical university, a different institution"),
    "1018": ("zapadno-kazakhstanskiy-meditsinskiy-universitet", "high", "full vs abbreviated namesake first name"),
    "2": ("al-farabi-kazakh-national-university", "high", "КазНУ abbreviation / EN full name pair, flagship university"),
    "953": ("akademiya-grazhdanskoj-aviaczii", "high", "exact same institution, slug abbreviates the Russian name"),
    "974": ("kazahskaya-akademiya-sporta-i-turizma", "high", "curated just adds the (КАСТ) abbreviation suffix"),
    "967": (None, "none", "no candidate found in curated KZ list"),
    "2341": (
        "mezhdunarodnaya-obrazovatelnaya-korporacziya",
        "low",
        "shares the КазГАСА abbreviation with jinaq entry 982 (International Educational Corporation) — possible "
        "3-way overlap (this row, entry 982, and the curated row might all be the same institution under "
        "different historical names), or this could be a genuinely distinct predecessor institution. Verify "
        "before confirming — do not blindly merge both 982 and 2341 into the same curated row without checking.",
    ),
    "962": ("kazakh-national-academy-of-arts-named-after-t-zhurgenov", "high", "EN/RU name pair, city matches"),
    "963": ("kazahskaya-naczionalnaya-konservatoriya-im-kurmangazy", "high", "'имени' vs 'им.' only"),
    "965": ("kazahskaya-avtomobilno-dorozhnaya-akademiya", "medium", "институт (jinaq) vs академия (curated), same 'автомобильно-дорожный' subject and city"),
    "1002": ("kazatu", "high", "curated adds 'исследовательский' and abbreviates the namesake, same institution"),
    "1011": ("meditsinskiy-universitet-semey", "high", "curated drops the 'Некоммерческое акционерное общество' legal-form prefix, same city"),
    "968": ("kazahskij-naczionalnyj-agrarnyj-issledovatelskij-universitet", "high", "curated just adds the (КазНАИУ) abbreviation suffix"),
    "969": ("kazahskij-gosudarstvennyj-zhenskij-pedagogicheskij-universitet", "medium", "'национальный' (jinaq) vs 'государственный' (curated) — same subject-specific (women's pedagogical) university, verify it wasn't actually renamed to something else"),
    "970": ("kazahskij-naczionalnyj-mediczinskij-universitet-im-s-d-asfendiyarova", "high", "'имени' vs 'им.' + curated adds (КазНМУ) suffix"),
    "972": ("abai-kazakh-national-pedagogical-university", "high", "EN/RU name pair, flagship university"),
    "1067": (None, "none", "no candidate found in curated KZ list"),
    "975": ("kazakh-ablai-khan-university-of-international-relations-and-world-languages", "high", "EN/RU name pair"),
    "1001": ("kazutb", "high", "'имени' vs 'им.' only"),
    "976": ("akademiya-logistiki-i-transporta", "low", "very different name strings (curated: 'ALT UNIVERSITY им. Мухаметжана Тынышпаева'), only the surname reference overlaps — verify carefully before confirming, could be wrong"),
    "988": ("kimep-university", "high", "EN/RU name pair, iconic university"),
    "954": ("kazahstansko-britanskij-tehnicheskij-universitet", "high", "curated just adds the (КБТУ) abbreviation suffix"),
    "978": ("kazahstansko-nemeczkij-universitet", "high", "curated just adds the (КНУ) abbreviation suffix"),
    "979": ("kazahstansko-rossijskij-mediczinskij-universitet", "high", "curated just adds the (КРМУ) abbreviation suffix"),
    "1034": ("bolashaq-akademiya", "high", "curated drops the 'Карагандинская' city-adjective prefix, same city"),
    "1036": ("karagandinskiy-industrialnyy-universitet", "low", "name matches closely but curated row's city is Темиртау, not Караганда (adjacent cities) — verify this is really the same institution before confirming"),
    "1037": ("medical-university-karaganda", "high", "reordered name, same city"),
    "1038": ("kartu-karaganda", "high", "curated drops the 'имени Абылкаса Сагинова' suffix and 'государственный', same city"),
    "1039": ("karsu-buketova", "high", "curated drops 'государственный', same namesake and city"),
    "1040": (None, "none", "no candidate found in curated KZ list"),
    "980": ("kaspijskij-universitet", "medium", "'общественный' (jinaq) vs no modifier (curated) — same city, verify same institution"),
    "1054": ("yessenov-university", "high", "curated's primary name is English with the Russian full name in parens — matches exactly"),
    "1044": ("kostanay-regional-university", "high", "curated drops the 'имени Ахмета Байтурсынова' suffix, same city"),
    "1046": ("kostanaiskiy-sotsialno-tekhnicheskiy-universitet-aldamzhar", "high", "'Зулкарнай'/'Зулхарнай' + 'Алдамжара'/'Алдамжар' spelling variants only"),
    "1057": (None, "none", "no candidate found — distinct from the unrelated МИТУ engineering university"),
    "984": ("mezhdunarodnyj-universitet-informaczionnyh-tehnologij", "high", "curated just adds the (МУИТ) abbreviation suffix"),
    "1061": (None, "none", "no candidate found in curated KZ list"),
    "1": ("nazarbayev-university", "high", "EN/RU name pair, city matches"),
    "1059": ("toraigyrov-university", "medium", "institution was renamed (Pavlodar State University -> Toraighyrov University) — city Павлодар matches exactly, verify it's the same institution and not a genuine separate one"),
    "1047": (None, "none", "no candidate found — distinct from Kostanay Regional University"),
    "1023": (None, "none", "no candidate found in curated KZ list"),
    "1063": (None, "none", "no candidate found in curated KZ list"),
    "1045": ("rudnenskiy-industrialnyy-universitet", "high", "институт (jinaq) vs университет (curated) only, same city"),
    "1029": ("tarazskiy-universitet-dulati", "high", "curated drops 'государственный педагогический', same namesake and city"),
    "1026": ("mezhdunarodnyy-tarazskiy-universitet-murtaza", "medium", "'инновационный' (jinaq) vs 'Международный' (curated) modifier differs, same namesake and city"),
    "1066": (None, "none", "no candidate found in curated KZ list"),
    "987": ("turan-astana", "high", "exact name match — only the city differs (jinaq: Нур-Султан, curated: Астана — same city, renamed over the years)"),
    "1010": ("alikhan-bokeikhan-university", "high", "EN/RU name pair, city matches"),
    "1060": ("universitet-tasheneva", "medium", "middle-name spelling variant ('Жумабека' vs 'Жубанова'), same surname and city"),
    "1008": ("mnu", "medium", "curated ALSO has a separate 'Университет КАЗГЮУ имени М.С. Нарикбаева' (slug kazgyuu) — this looks like a pre-existing duplicate in the curated data itself (KAZGUU renamed to Maqsut Narikbayev University), unrelated to jinaq. Needs a human decision on whether jinaq's row should merge into kazgyuu, mnu, or whether kazgyuu and mnu should first be merged with each other."),
    "986": (None, "none", "no candidate found in curated KZ list"),
    "989": ("universitet-mezhdunarodnogo-biznesa-uib", "high", "curated drops the 'имени Кенжегали Сагадиева' suffix, same city"),
    "1064": (None, "none", "no candidate found in curated KZ list"),
    "1042": (None, "none", "no candidate found in curated KZ list"),
    "1013": ("shakarima-semey-universitet", "high", "reordered name, same namesake and city"),
    "1068": (None, "none", "no candidate found in curated KZ list"),
    "1071": ("yuzhno-kazakhstanskiy-universitet-auezova", "high", "curated drops 'государственный', same namesake and city"),
    "1069": (None, "low", "possible jinaq data-quality duplicate of external_id 1071 with 'медицинский' inserted into the name — no distinct medical-only curated counterpart exists; could be a genuinely separate institution or a source error, needs a human look at the raw jinaq record"),
}


async def main() -> None:
    async with async_session() as db:
        refs_result = await db.execute(
            select(UniversityExternalRef).where(
                UniversityExternalRef.source == "jinaq", UniversityExternalRef.match_method == "new"
            )
        )
        refs = refs_result.scalars().all()

        kz_refs = []
        for ref in refs:
            uni = (await db.execute(select(University).where(University.id == ref.university_id))).scalar_one()
            if uni.country != "Казахстан":
                continue
            kz_refs.append((ref, uni))

        all_slugs = {u.slug for u in (await db.execute(select(University))).scalars().all()}

        entries = []
        unmatched_draft_keys = set(DRAFT.keys())
        for ref, uni in kz_refs:
            proposed_slug, confidence, reason = DRAFT.get(ref.external_id, (None, "none", "not reviewed yet"))
            unmatched_draft_keys.discard(ref.external_id)
            if proposed_slug and proposed_slug not in all_slugs:
                print(f"WARNING: slug {proposed_slug!r} for external_id {ref.external_id} does not exist!")
            candidate = None
            if proposed_slug:
                candidate_uni = (await db.execute(select(University).where(University.slug == proposed_slug))).scalar_one_or_none()
                if candidate_uni:
                    candidate = {"slug": candidate_uni.slug, "name": candidate_uni.name, "city": candidate_uni.city}
            entries.append(
                {
                    "jinaq_external_id": ref.external_id,
                    "jinaq_university_id": str(uni.id),
                    "jinaq_name": uni.name,
                    "jinaq_city": uni.city,
                    "proposed_curated_match": candidate,
                    "confidence": confidence,
                    "reason": reason,
                    "confirmed": False,
                }
            )

        if unmatched_draft_keys:
            print(f"WARNING: {len(unmatched_draft_keys)} draft external_ids never matched a 'new' KZ ref: {unmatched_draft_keys}")

        output = {
            "_readme": (
                "Each entry is a jinaq-created University row suspected of duplicating an already-existing "
                "curated row. Check `proposed_curated_match` against `jinaq_name`/`jinaq_city` — if it's really "
                "the same institution, set `confirmed: true`. If it's wrong, either fix `proposed_curated_match` "
                "to the right slug (look it up among existing universities) or set it to null if this is "
                "genuinely a new, previously-missing university. Nothing merges until `confirmed` is true — "
                "scripts/apply_kz_university_merge.py only acts on confirmed entries."
            ),
            "entries": entries,
        }

        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

        high = sum(1 for e in entries if e["confidence"] == "high")
        medium = sum(1 for e in entries if e["confidence"] == "medium")
        low = sum(1 for e in entries if e["confidence"] == "low")
        none_ = sum(1 for e in entries if e["confidence"] == "none")
        print(f"Wrote {len(entries)} entries to {OUTPUT_PATH}")
        print(f"high={high} medium={medium} low={low} none={none_}")


if __name__ == "__main__":
    asyncio.run(main())
