import csv
import io
import json
import os
import random
from datetime import datetime

from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

import models
import schemas
from database import Base, engine, get_db

Base.metadata.create_all(bind=engine)

# Auto-migrate: add option_e if upgrading from an older DB
with engine.connect() as _conn:
    _cols = [c["name"] for c in inspect(engine).get_columns("questions")]
    if "option_e" not in _cols:
        _conn.execute(text("ALTER TABLE questions ADD COLUMN option_e TEXT"))
        _conn.commit()

with engine.connect() as _conn:
    _cols = [c["name"] for c in inspect(engine).get_columns("test_results")]
    if "mode" not in _cols:
        _conn.execute(text("ALTER TABLE test_results ADD COLUMN mode TEXT NOT NULL DEFAULT 'normal'"))
        _conn.commit()

app = FastAPI(title="Quiz Builder")

_origins = ["http://localhost:5173"]
if _frontend_url := os.getenv("FRONTEND_URL"):
    _origins.append(_frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

REQUIRED_COLUMNS = {"question", "option_a", "option_b", "option_c", "option_d", "correct_answer"}
VALID_ANSWERS = {"A", "B", "C", "D", "E"}


@app.post("/questions/upload")
def upload_questions(file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = file.file.read().decode("utf-8-sig")  # handle BOM
    reader = csv.DictReader(io.StringIO(content))

    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV file is empty or has no header row.")

    missing = REQUIRED_COLUMNS - {f.strip().lower() for f in reader.fieldnames}
    if missing:
        raise HTTPException(status_code=400, detail=f"CSV missing columns: {', '.join(sorted(missing))}")

    rows = []
    for i, row in enumerate(reader, start=2):
        answer = row.get("correct_answer", "").strip().upper()
        option_e = row.get("option_e", "").strip() or None
        if answer not in VALID_ANSWERS:
            raise HTTPException(
                status_code=400,
                detail=f"Row {i}: correct_answer must be A–E (got '{answer}').",
            )
        if answer == "E" and not option_e:
            raise HTTPException(
                status_code=400,
                detail=f"Row {i}: correct_answer is E but option_e is empty.",
            )
        rows.append(
            models.Question(
                question_text=row["question"].strip(),
                option_a=row["option_a"].strip(),
                option_b=row["option_b"].strip(),
                option_c=row["option_c"].strip(),
                option_d=row["option_d"].strip(),
                option_e=option_e,
                correct_answer=answer,
            )
        )

    if not rows:
        raise HTTPException(status_code=400, detail="CSV has no data rows.")

    db.query(models.Question).delete()
    db.add_all(rows)
    db.commit()
    return {"imported": len(rows)}


@app.get("/questions/count", response_model=schemas.QuestionCount)
def question_count(db: Session = Depends(get_db)):
    return {"count": db.query(models.Question).count()}


@app.post("/tests/generate", response_model=schemas.GenerateResponse)
def generate_test(body: schemas.GenerateRequest, db: Session = Depends(get_db)):
    total = db.query(models.Question).count()
    if total == 0:
        raise HTTPException(status_code=400, detail="No questions loaded. Upload a CSV first.")
    count = min(body.count, total)

    questions = db.query(models.Question).all()
    sample = random.sample(questions, count)

    shuffled_questions = []
    for q in sample:
        originals = {"A": q.option_a, "B": q.option_b, "C": q.option_c, "D": q.option_d}
        if q.option_e:
            originals["E"] = q.option_e
        labels = list(originals.keys())
        shuffled_labels = labels[:]
        random.shuffle(shuffled_labels)

        # shuffled_map: original letter → new shuffled label
        shuffled_map = {orig: shuf for orig, shuf in zip(labels, shuffled_labels)}

        # options in shuffled order: shuffled_label → original text
        options = {shuffled_labels[i]: originals[labels[i]] for i in range(len(labels))}

        shuffled_questions.append(
            schemas.ShuffledQuestion(
                question_id=q.id,
                question_text=q.question_text,
                options=options,
                shuffled_map=shuffled_map,
                correct_shuffled_option=shuffled_map[q.correct_answer],
            )
        )

    return {"questions": shuffled_questions}


@app.post("/tests/submit", response_model=schemas.SubmitResponse)
def submit_test(body: schemas.SubmitRequest, db: Session = Depends(get_db)):
    results = []
    correct_count = 0

    for answer in body.answers:
        q = db.get(models.Question, answer.question_id)
        if not q:
            raise HTTPException(status_code=404, detail=f"Question {answer.question_id} not found.")

        smap = body.shuffled_maps.get(answer.question_id, {})
        # Invert map: shuffled label → original letter
        inv_map = {v: k for k, v in smap.items()}

        original_selected = inv_map.get(answer.selected_option, answer.selected_option)
        original_correct = q.correct_answer

        is_correct = original_selected == original_correct

        option_texts = {"A": q.option_a, "B": q.option_b, "C": q.option_c, "D": q.option_d}
        if q.option_e:
            option_texts["E"] = q.option_e
        shuffled_correct_label = smap.get(original_correct, original_correct)

        results.append(
            schemas.QuestionResult(
                question_id=q.id,
                question_text=q.question_text,
                selected_option=answer.selected_option,
                selected_text=option_texts.get(original_selected, ""),
                correct_option=shuffled_correct_label,
                correct_text=option_texts[original_correct],
                is_correct=is_correct,
            )
        )
        if is_correct:
            correct_count += 1

    total = len(results)
    score_percent = round((correct_count / total) * 100, 1) if total else 0.0

    db_result = models.TestResult(
        total_questions=total,
        correct_count=correct_count,
        score_percent=score_percent,
        taken_at=datetime.utcnow(),
        mode=body.mode,
        details=json.dumps([r.model_dump() for r in results]),
    )
    db.add(db_result)
    db.commit()
    db.refresh(db_result)

    return schemas.SubmitResponse(
        total=total,
        correct=correct_count,
        score_percent=score_percent,
        results=results,
        result_id=db_result.id,
    )


@app.get("/results", response_model=list[schemas.TestResultOut])
def get_results(db: Session = Depends(get_db)):
    rows = db.query(models.TestResult).order_by(models.TestResult.taken_at.desc()).all()
    out = []
    for r in rows:
        out.append(
            schemas.TestResultOut(
                id=r.id,
                total_questions=r.total_questions,
                correct_count=r.correct_count,
                score_percent=r.score_percent,
                taken_at=r.taken_at,
                mode=r.mode or "normal",
                details=json.loads(r.details),
            )
        )
    return out
