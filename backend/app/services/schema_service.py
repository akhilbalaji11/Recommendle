from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorDatabase


MIGRATION_COMMAND = "python -m scripts.migrate_multicategory_schema"


async def ensure_multicategory_compatibility(db: AsyncIOMotorDatabase) -> None:
    """Validate startup schema expectations for category-aware gameplay."""
    missing_categories = await db.products.count_documents({"category": {"$exists": False}})
    if missing_categories > 0:
        raise RuntimeError(
            "Detected products without `category` field. "
            f"Run `{MIGRATION_COMMAND}` before starting the API "
            f"(missing documents: {missing_categories})."
        )

    # Ensure required indexes for category-scoped queries.
    await db.products.create_index([("category", 1), ("source_id", 1)], unique=True)
    await db.products.create_index([("category", 1), ("title", 1)])
    await db.products.create_index([("category", 1), ("vendor", 1)])
    await db.products.create_index([("category", 1), ("release_year", 1)])
    await db.games.create_index([("category", 1), ("status", 1), ("created_at", -1)])
    await db.games.create_index([("category", 1), ("player_name", 1), ("created_at", -1)])
