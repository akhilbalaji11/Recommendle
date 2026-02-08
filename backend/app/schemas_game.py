from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProductCard(BaseModel):
    id: str
    title: str
    vendor: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    tags: list[str] = Field(default_factory=list)
    image_url: str | None = None


class MetricsOut(BaseModel):
    coherence_score: float
    predicted_prefix_rating: float


class GameCreate(BaseModel):
    player_name: str = Field(..., min_length=1, max_length=80)


class GameOut(BaseModel):
    id: str
    player_name: str
    status: str
    total_rounds: int
    human_score: int
    ai_score: int
    created_at: datetime


class OnboardingOut(BaseModel):
    game_id: str
    pool_size: int
    products: list[ProductCard]


class OnboardingSubmit(BaseModel):
    selected_product_ids: list[str]
    rating: int = Field(..., ge=1, le=5)


class OnboardingSubmitOut(BaseModel):
    accepted: bool
    coherence_score: float
    predicted_prefix_rating: float
    next_round: int


class RoundStartOut(BaseModel):
    round_number: int
    candidates: list[ProductCard]
    pre_round_metrics: MetricsOut


class RoundPickSubmit(BaseModel):
    product_id: str


class ScoredProductCard(ProductCard):
    score: float


class AIExplanation(BaseModel):
    reason: str
    top_candidates: list[ScoredProductCard]


class RoundResultOut(BaseModel):
    round_number: int
    human_pick: ProductCard
    ai_pick: ScoredProductCard
    ai_correct: bool
    human_points: int
    ai_points: int
    total_human_score: int
    total_ai_score: int
    ai_explanation: AIExplanation
    post_round_metrics: MetricsOut
    game_complete: bool


class GameStatusOut(BaseModel):
    id: str
    player_name: str
    status: str
    current_round: int
    total_rounds: int
    human_score: int
    ai_score: int
    onboarding_complete: bool
    onboarding_selected_count: int
    round_in_progress: int | None = None


class LeaderboardEntry(BaseModel):
    rank: int
    player_name: str
    human_score: int
    ai_score: int
    score_difference: int
    rounds_completed: int
    created_at: datetime
