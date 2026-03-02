# services/ml/classifier/train.py

import asyncio
import os
import pickle
from typing import Dict, Tuple

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

from database.db import db
from services.ml.classifier.featurize import build_text

ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")
os.makedirs(ARTIFACTS_DIR, exist_ok=True)

MODEL_PATH = os.path.join(ARTIFACTS_DIR, "model.pkl")
VECTORIZER_PATH = os.path.join(ARTIFACTS_DIR, "vectorizer.pkl")
LABEL_MAP_PATH = os.path.join(ARTIFACTS_DIR, "label_map.pkl")


async def load_training_data() -> Tuple[pd.DataFrame, Dict[int, str]]:
    """
    Грузим данные для обучения:
      - note, amount, category_id
      - + имя категории для label_map (id -> name)
    """
    rows = await db.execute(
        """
        SELECT
            t.note,
            t.amount,
            t.category_id,
            c.name AS category_name
        FROM transactions t
        JOIN categories c
            ON c.id = t.category_id
        WHERE t.type = 'expense'
          AND t.note IS NOT NULL
          AND t.category_id IS NOT NULL
          AND c.type = 'expense'
        """,
        fetch=True
    )

    data = []
    label_map: Dict[int, str] = {}

    for r in rows:
        note = str(r["note"]).strip() if r["note"] is not None else ""
        amount = float(r["amount"]) if r["amount"] is not None else 0.0
        category_id = int(r["category_id"])
        category_name = str(r["category_name"]).strip() if r["category_name"] is not None else str(category_id)

        # маппинг id -> name
        label_map[category_id] = category_name

        # общий формат текста (ВАЖНО: одинаково с predict)
        text = build_text(note, amount)

        if text:
            data.append({"text": text, "label": category_id})

    df = pd.DataFrame(data)
    return df, label_map


async def train():
    df, label_map = await load_training_data()

    if df.empty or df["label"].nunique() < 2:
        raise ValueError("Недостаточно данных для обучения ML-классификатора (нужно >=2 разных категорий).")

    vectorizer = TfidfVectorizer(
        ngram_range=(1, 2),
        min_df=2,
        max_features=5000
    )

    X = vectorizer.fit_transform(df["text"])
    y = df["label"].astype(int)

    model = LogisticRegression(
        max_iter=2000,
        n_jobs=-1,
        class_weight="balanced"
    )
    model.fit(X, y)

    with open(VECTORIZER_PATH, "wb") as f:
        pickle.dump(vectorizer, f)

    with open(MODEL_PATH, "wb") as f:
        pickle.dump(model, f)

    with open(LABEL_MAP_PATH, "wb") as f:
        pickle.dump(label_map, f)

    print("✅ ML-классификатор обучен и сохранён")
    print(f"✅ label_map.pkl сохранён ({len(label_map)} категорий)")


if __name__ == "__main__":
    asyncio.run(train())
