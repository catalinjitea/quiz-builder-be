from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text
from database import Base


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    question_text = Column(Text, nullable=False)
    option_a = Column(String, nullable=False)
    option_b = Column(String, nullable=False)
    option_c = Column(String, nullable=False)
    option_d = Column(String, nullable=False)
    option_e = Column(String, nullable=True)
    correct_answer = Column(String(1), nullable=False)  # A, B, C, D, or E
    created_at = Column(DateTime, default=datetime.utcnow)


class TestResult(Base):
    __tablename__ = "test_results"

    id = Column(Integer, primary_key=True, index=True)
    total_questions = Column(Integer, nullable=False)
    correct_count = Column(Integer, nullable=False)
    score_percent = Column(Float, nullable=False)
    taken_at = Column(DateTime, default=datetime.utcnow)
    mode = Column(String, nullable=False, default="normal")
    details = Column(Text, nullable=False)  # JSON string
