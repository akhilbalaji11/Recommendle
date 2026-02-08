from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from .db import Base, engine, get_db, SessionLocal
from .models import Product, ProductImage, User, Session as UserSession, Selection, PrefixRating
from .schemas import (
    ProductOut,
    ProductImageOut,
    UserCreate,
    UserOut,
    SessionCreate,
    SessionOut,
    SelectionCreate,
    PrefixRatingCreate,
    RecommendationOut,
)
from .services.recommender import recommender

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"

app = FastAPI(title="Decidio Prototype")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup():
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        recommender.refresh(db)


@app.get("/api/products", response_model=list[ProductOut])
def list_products(
    q: Optional[str] = None,
    vendor: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    query = db.query(Product)
    if q:
        q_like = f"%{q.lower()}%"
        query = query.filter(Product.title.ilike(q_like))
    if vendor:
        query = query.filter(Product.vendor.ilike(f"%{vendor}%"))
    if price_min is not None:
        query = query.filter(Product.price_min >= price_min)
    if price_max is not None:
        query = query.filter(Product.price_max <= price_max)
    products = query.offset(offset).limit(limit).all()
    return [to_product_out(p) for p in products]


@app.get("/api/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return to_product_out(product)


@app.post("/api/users", response_model=UserOut)
def create_user(payload: UserCreate, db: Session = Depends(get_db)):
    user = User(name=payload.name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserOut(id=user.id, name=user.name)


@app.post("/api/sessions", response_model=SessionOut)
def create_session(payload: SessionCreate, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == payload.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    session = UserSession(user_id=user.id)
    db.add(session)
    db.commit()
    db.refresh(session)
    return SessionOut(id=session.id, user_id=session.user_id, created_at=session.created_at)


@app.post("/api/sessions/{session_id}/end")
def end_session(session_id: int, db: Session = Depends(get_db)):
    session = db.query(UserSession).filter(UserSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session.state_json = None
    db.commit()
    return {"status": "ended", "session_id": session_id}


@app.post("/api/sessions/{session_id}/select")
def select_product(session_id: int, payload: SelectionCreate, db: Session = Depends(get_db)):
    session = db.query(UserSession).filter(UserSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    product = db.query(Product).filter(Product.id == payload.product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    selection = Selection(session_id=session.id, product_id=product.id, is_exception=payload.is_exception)
    db.add(selection)
    recommender.update_with_selection(session, product, payload.is_exception)
    db.commit()
    return {"status": "ok"}


@app.post("/api/sessions/{session_id}/rate")
def rate_prefix(session_id: int, payload: PrefixRatingCreate, db: Session = Depends(get_db)):
    session = db.query(UserSession).filter(UserSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    rating = PrefixRating(session_id=session.id, rating=payload.rating, tags_json=json.dumps(payload.tags))
    db.add(rating)
    recommender.update_with_prefix_rating(session, payload.rating)
    db.commit()
    return {"status": "ok"}


@app.get("/api/sessions/{session_id}/recommendations", response_model=RecommendationOut)
def recommend(session_id: int, db: Session = Depends(get_db)):
    session = db.query(UserSession).filter(UserSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    result = recommender.recommend(db, session)
    return RecommendationOut(
        strong=[to_product_out(p) for p in result["strong"]],
        wildcard=to_product_out(result["wildcard"]) if result["wildcard"] else None,
        coherence_score=result["coherence_score"],
        predicted_prefix_rating=result["predicted_prefix_rating"],
    )


@app.get("/api/sessions/{session_id}/selections", response_model=list[ProductOut])
def list_selections(session_id: int, db: Session = Depends(get_db)):
    session = db.query(UserSession).filter(UserSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    product_ids = [s.product_id for s in session.selections]
    if not product_ids:
        return []
    products = db.query(Product).filter(Product.id.in_(product_ids)).all()
    product_map = {p.id: p for p in products}
    ordered = [product_map[pid] for pid in product_ids if pid in product_map]
    return [to_product_out(p) for p in ordered]


@app.get("/api/debug/pbcf")
def pbcf_debug(db: Session = Depends(get_db)):
    stats = recommender.pbcf_stats(db)
    return stats


app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


def to_product_out(product: Product) -> ProductOut:
    return ProductOut(
        id=product.id,
        title=product.title,
        vendor=product.vendor,
        product_type=product.product_type,
        price_min=product.price_min,
        price_max=product.price_max,
        tags=product.tags(),
        options=product.options(),
        description=product.description,
        url=product.url,
        images=[ProductImageOut(url=img.url, alt=img.alt, position=img.position) for img in product.images],
    )
