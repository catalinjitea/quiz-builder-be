from datetime import datetime
from typing import Any
from pydantic import BaseModel


class QuestionCount(BaseModel):
    count: int


class ShuffledQuestion(BaseModel):
    question_id: int
    question_text: str
    options: dict[str, str]        # shuffled label → text, e.g. {"A": "Paris", "B": "Rome", ...}
    shuffled_map: dict[str, str]   # original letter → shuffled label
    correct_shuffled_option: str   # the shuffled label that is correct for this shuffle


class GenerateRequest(BaseModel):
    count: int


class GenerateResponse(BaseModel):
    questions: list[ShuffledQuestion]


class AnswerItem(BaseModel):
    question_id: int
    selected_option: str  # letter in shuffled space (A/B/C/D), or "" if skipped


class SubmitRequest(BaseModel):
    answers: list[AnswerItem]
    shuffled_maps: dict[int, dict[str, str]]  # question_id → shuffled_map
    mode: str = "normal"


class QuestionResult(BaseModel):
    question_id: int
    question_text: str
    selected_option: str
    selected_text: str
    correct_option: str
    correct_text: str
    is_correct: bool


class SubmitResponse(BaseModel):
    total: int
    correct: int
    score_percent: float
    results: list[QuestionResult]
    result_id: int


class TestResultOut(BaseModel):
    id: int
    total_questions: int
    correct_count: int
    score_percent: float
    taken_at: datetime
    mode: str
    details: Any

    class Config:
        from_attributes = True
