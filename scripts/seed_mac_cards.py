"""
Seed script: upsert `mac_cards` from the JSON manifest (PRO-315).

Run inside Docker:
    docker-compose exec api python scripts/seed_mac_cards.py

Idempotent, self-healing on `image_path`: inserts new rows, updates changed
fields on existing ones. Never deletes — a row missing from the manifest is
set `active=False` instead (so history referencing an old card id stays
valid). Manifest — scripts/data/mac_card_manifest.json; images themselves
live in the frontend static assets (Profy-Frontend/public/mac-cards/), the
backend only stores the relative path.
"""
import asyncio
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import async_session
from app.models.mac import MacCard, MacCardKind

_MANIFEST_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "mac_card_manifest.json"
)


def _load_manifest() -> list[dict]:
    with open(_MANIFEST_PATH, encoding="utf-8") as f:
        return json.load(f)["cards"]


async def main() -> None:
    manifest = _load_manifest()
    manifest_paths = {c["image_path"] for c in manifest}

    async with async_session() as db:
        existing = (await db.execute(select(MacCard))).scalars().all()
        by_path = {c.image_path: c for c in existing}

        inserted = updated = deactivated = 0
        for entry in manifest:
            card = by_path.get(entry["image_path"])
            if card is None:
                db.add(MacCard(
                    image_path=entry["image_path"],
                    kind=MacCardKind(entry["kind"]),
                    active=True,
                    license=entry.get("license"),
                    attribution=entry.get("attribution"),
                ))
                inserted += 1
                continue

            changed = False
            if card.kind.value != entry["kind"]:
                card.kind = MacCardKind(entry["kind"])
                changed = True
            if card.license != entry.get("license"):
                card.license = entry.get("license")
                changed = True
            if card.attribution != entry.get("attribution"):
                card.attribution = entry.get("attribution")
                changed = True
            if not card.active:
                card.active = True
                changed = True
            if changed:
                updated += 1

        for card in existing:
            if card.image_path not in manifest_paths and card.active:
                card.active = False
                deactivated += 1

        await db.commit()

    print(f"mac_cards: {inserted} inserted, {updated} updated, {deactivated} deactivated")


if __name__ == "__main__":
    asyncio.run(main())
