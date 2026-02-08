"""
Migration script from SQLite to MongoDB.

This script reads all data from the SQLite database and writes it to MongoDB.
Run with: python -m backend.scripts.migrate_to_mongo
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from motor.motor_asyncio import AsyncIOMotorClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Product, ProductImage, User, Session as UserSession, Selection, PrefixRating
from app.db import DB_PATH, SessionLocal


async def migrate_products(mongo_db, sqlite_session):
    """Migrate products and product images."""
    print("Migrating products...")

    products_collection = mongo_db.products
    products_count = 0

    for product in sqlite_session.query(Product).all():
        # Convert SQLAlchemy product to MongoDB document
        product_doc = {
            "source_id": product.source_id,
            "title": product.title,
            "handle": product.handle,
            "vendor": product.vendor,
            "product_type": product.product_type,
            "price_min": product.price_min,
            "price_max": product.price_max,
            "currency": product.currency,
            "tags": product.tags(),
            "options": product.options(),
            "description": product.description,
            "url": product.url,
            "images": [
                {
                    "url": img.url,
                    "alt": img.alt,
                    "position": img.position,
                }
                for img in product.images
            ],
        }

        result = await products_collection.insert_one(product_doc)
        products_count += 1
        print(f"  Migrated product: {product.title} (id: {result.inserted_id})")

    print(f"Migrated {products_count} products.")
    # Build map from SQLite product ID to MongoDB ObjectId
    product_id_map = {}
    for product in sqlite_session.query(Product).all():
        mongo_product = await products_collection.find_one({"source_id": product.source_id})
        if mongo_product:
            product_id_map[product.id] = str(mongo_product["_id"])
    return product_id_map


async def migrate_users(mongo_db, sqlite_session, product_id_map):
    """Migrate users."""
    print("\nMigrating users...")

    users_collection = mongo_db.users
    users_count = 0

    for user in sqlite_session.query(User).all():
        user_doc = {
            "name": user.name,
            "created_at": user.created_at,
            "sessions": [],  # Will be updated after sessions migration
        }

        result = await users_collection.insert_one(user_doc)
        users_count += 1
        print(f"  Migrated user: {user.name} (id: {result.inserted_id})")

    print(f"Migrated {users_count} users.")
    # Build map from SQLite user ID to MongoDB ObjectId
    user_id_map = {}
    for user in sqlite_session.query(User).all():
        # Find the most recently inserted user with this name
        mongo_user = await users_collection.find_one({"name": user.name}, sort=[("created_at", -1)])
        if mongo_user:
            user_id_map[user.id] = str(mongo_user["_id"])
    return user_id_map


async def migrate_sessions(mongo_db, sqlite_session, user_id_map):
    """Migrate sessions."""
    print("\nMigrating sessions...")

    sessions_collection = mongo_db.sessions
    sessions_count = 0

    session_id_map = {}

    for session in sqlite_session.query(UserSession).all():
        user_id = user_id_map[session.user_id]

        session_doc = {
            "user_id": user_id,
            "created_at": session.created_at,
            "state": {},
            "selections": [],
            "prefix_ratings": [],
        }

        if session.state_json:
            import json
            session_doc["state"] = json.loads(session.state_json)

        result = await sessions_collection.insert_one(session_doc)
        session_id_map[session.id] = str(result.inserted_id)
        sessions_count += 1
        print(f"  Migrated session (id: {result.inserted_id})")

    print(f"Migrated {sessions_count} sessions.")
    return session_id_map


async def migrate_selections(mongo_db, sqlite_session, session_id_map, product_id_map):
    """Migrate selections."""
    print("\nMigrating selections...")

    selections_collection = mongo_db.selections
    selections_count = 0

    for selection in sqlite_session.query(Selection).all():
        session_id = session_id_map[selection.session_id]
        product_id = product_id_map[selection.product_id]

        selection_doc = {
            "session_id": session_id,
            "product_id": product_id,
            "is_exception": selection.is_exception,
            "created_at": selection.created_at,
        }

        result = await selections_collection.insert_one(selection_doc)
        selections_count += 1

        # Add to session's selections array
        await mongo_db.sessions.update_one(
            {"_id": session_id},
            {"$push": {"selections": str(result.inserted_id)}}
        )

    print(f"Migrated {selections_count} selections.")


async def migrate_prefix_ratings(mongo_db, sqlite_session, session_id_map):
    """Migrate prefix ratings."""
    print("\nMigrating prefix ratings...")

    prefix_ratings_collection = mongo_db.prefix_ratings
    ratings_count = 0

    for rating in sqlite_session.query(PrefixRating).all():
        session_id = session_id_map[rating.session_id]

        rating_doc = {
            "session_id": session_id,
            "rating": rating.rating,
            "tags": rating.tags(),
            "created_at": rating.created_at,
        }

        result = await prefix_ratings_collection.insert_one(rating_doc)
        ratings_count += 1

        # Add to session's prefix_ratings array
        await mongo_db.sessions.update_one(
            {"_id": session_id},
            {"$push": {"prefix_ratings": str(result.inserted_id)}}
        )

    print(f"Migrated {ratings_count} prefix ratings.")


async def main():
    """Run the complete migration."""
    print("Starting migration from SQLite to MongoDB...")
    print(f"SQLite DB: {DB_PATH}")

    # Connect to MongoDB
    mongo_client = AsyncIOMotorClient("mongodb://localhost:27017")
    mongo_db = mongo_client["decidio"]

    # Clear existing collections (optional - comment out if you want to preserve data)
    print("\nClearing existing MongoDB collections...")
    for collection_name in ["products", "users", "sessions", "selections", "prefix_ratings"]:
        await mongo_db.drop_collection(collection_name)
        print(f"  Dropped collection: {collection_name}")

    # Create indexes
    print("\nCreating indexes...")
    await mongo_db.products.create_index("source_id", unique=True)
    await mongo_db.products.create_index("title")
    await mongo_db.products.create_index("vendor")
    await mongo_db.users.create_index("name")

    # Connect to SQLite
    sqlite_engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
    SessionSQLite = sessionmaker(bind=sqlite_engine)
    sqlite_session = SessionSQLite()

    try:
        # Run migrations in order
        product_id_map = await migrate_products(mongo_db, sqlite_session)
        user_id_map = await migrate_users(mongo_db, sqlite_session, product_id_map)
        session_id_map = await migrate_sessions(mongo_db, sqlite_session, user_id_map)
        await migrate_selections(mongo_db, sqlite_session, session_id_map, product_id_map)
        await migrate_prefix_ratings(mongo_db, sqlite_session, session_id_map)

        print("\n" + "="*50)
        print("MIGRATION COMPLETE!")
        print("="*50)

        # Print statistics
        products_count = await mongo_db.products.count_documents({})
        users_count = await mongo_db.users.count_documents({})
        sessions_count = await mongo_db.sessions.count_documents({})
        selections_count = await mongo_db.selections.count_documents({})
        ratings_count = await mongo_db.prefix_ratings.count_documents({})

        print("\nFinal Statistics:")
        print(f"  Products: {products_count}")
        print(f"  Users: {users_count}")
        print(f"  Sessions: {sessions_count}")
        print(f"  Selections: {selections_count}")
        print(f"  Prefix Ratings: {ratings_count}")

    except Exception as e:
        print(f"\nError during migration: {e}")
        import traceback
        traceback.print_exc()
    finally:
        sqlite_session.close()
        mongo_client.close()


if __name__ == "__main__":
    asyncio.run(main())
