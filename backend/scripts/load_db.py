import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from sqlalchemy.orm import Session

from app.db import Base, engine, SessionLocal
from app.models import Product, ProductImage

DATA_DIR = ROOT_DIR / "data"
PRODUCTS_JSON = DATA_DIR / "products.json"


def load_products(db: Session):
    if not PRODUCTS_JSON.exists():
        raise SystemExit("products.json not found. Run scrape_gouletpens.py first.")

    data = json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))

    db.query(ProductImage).delete()
    db.query(Product).delete()
    db.commit()

    for item in data:
        product = Product(
            source_id=item.get("source_id"),
            title=item.get("title"),
            handle=item.get("handle"),
            vendor=item.get("vendor"),
            product_type=item.get("product_type"),
            price_min=item.get("price_min"),
            price_max=item.get("price_max"),
            currency=item.get("currency"),
            tags_json=json.dumps(item.get("tags", [])),
            options_json=json.dumps(item.get("options", {})),
            description=item.get("description"),
            url=item.get("url"),
        )
        db.add(product)
        db.flush()
        for img in item.get("images", []):
            db.add(
                ProductImage(
                    product_id=product.id,
                    url=img.get("url"),
                    alt=img.get("alt"),
                    position=img.get("position"),
                )
            )
    db.commit()


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        load_products(db)
    print("Loaded products into database")
