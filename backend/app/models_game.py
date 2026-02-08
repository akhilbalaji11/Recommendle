from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field
from bson import ObjectId


class PyObjectId(ObjectId):
    """Pydantic validator for MongoDB ObjectId."""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        from pydantic_core import core_schema
        return core_schema.with_info_plain_validator_function(
            cls.validate,
            serialization=core_schema.plain_serializer_function_ser_schema(str),
        )

    @classmethod
    def validate(cls, v, _info):
        if not isinstance(v, ObjectId):
            if isinstance(v, str) and ObjectId.is_valid(v):
                return ObjectId(v)
            raise ValueError("Invalid ObjectId")
        return v


class MongoModel(BaseModel):
    """Base model for MongoDB documents."""

    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }


class GameSession(MongoModel):
    """A complete game session with multiple rounds."""
    player_name: str
    status: str = "waiting"  # waiting, playing, completed
    current_round: int = 0
    total_rounds: int = 5
    human_score: int = 0
    ai_score: int = 0
    rounds: list[PyObjectId] = Field(default_factory=list)


class GameRound(MongoModel):
    """A single round in the game."""
    game_session_id: PyObjectId
    round_number: int
    mystery_user_id: str  # The user from the dataset we're predicting
    clue_pen_ids: list[str]  # 4 pens shown to players
    target_pen_id: str  # The 5th pen (actual answer)
    human_prediction_id: Optional[str] = None
    ai_prediction_id: Optional[str] = None
    human_correct: Optional[bool] = None
    ai_correct: Optional[bool] = None
    ai_confidence: Optional[float] = None  # AI's confidence in its prediction
    completed: bool = False


class UserSelection(MongoModel):
    """Track a user's selections for training the model."""
    user_id: str  # Can be "dataset_user_{original_id}" for migrated users
    product_id: str
    rating: Optional[int] = None  # 1-5 if explicitly rated
    is_exception: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
