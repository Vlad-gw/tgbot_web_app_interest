# services/ml/classifier/predict.py

import os
import pickle
from typing import List, Optional, Tuple, Any

import numpy as np

from services.ml.classifier.rules import KEYWORD_RULES
from services.ml.classifier.featurize import build_text

ARTIFACTS_DIR = os.path.join(os.path.dirname(__file__), "artifacts")

with open(os.path.join(ARTIFACTS_DIR, "model.pkl"), "rb") as f:
    model = pickle.load(f)

with open(os.path.join(ARTIFACTS_DIR, "vectorizer.pkl"), "rb") as f:
    vectorizer = pickle.load(f)

LABEL_MAP_PATH = os.path.join(ARTIFACTS_DIR, "label_map.pkl")
label_map = None
if os.path.exists(LABEL_MAP_PATH):
    with open(LABEL_MAP_PATH, "rb") as f:
        label_map = pickle.load(f)


def keyword_rule_predict(note: str) -> Optional[str]:
    """
    Простой rule-based слой.
    Возвращает название категории, если найдено ключевое слово.
    """
    if not note:
        return None

    text = note.lower()
    for category, keywords in KEYWORD_RULES.items():
        for kw in keywords:
            if kw in text:
                return category
    return None


def _safe_softmax(x: np.ndarray) -> np.ndarray:
    x = x.astype(float)
    x = x - np.max(x)
    e = np.exp(x)
    return e / (np.sum(e) + 1e-12)


def _decode_label(label: Any) -> str:
    """
    Приводит метку модели к нормальному названию категории.
    Если label_map есть и метка числовая -> маппим в имя.
    """
    if isinstance(label, (np.integer,)):
        label = int(label)

    if label_map is not None:
        if isinstance(label, int) and label in label_map:
            return str(label_map[label])
        if isinstance(label, str) and label.isdigit():
            li = int(label)
            if li in label_map:
                return str(label_map[li])

    return str(label)


def predict_category(note: str, amount: float, top_k: int = 3) -> Tuple[Optional[str], float, List[Tuple[str, float]]]:
    """
    Возвращает:
      best_category_name: str | None
      confidence: float (0..1)
      top: [(category_name, prob), ...]
    """
    note = (note or "").strip()
    if not note:
        return None, 0.0, []

    # 1) правила -> 100%
    rule_category = keyword_rule_predict(note)
    if rule_category:
        return rule_category, 1.0, [(rule_category, 1.0)]

    # 2) ML (ВАЖНО: одинаковая фичефикация как при обучении)
    text = build_text(note, amount)
    X = vectorizer.transform([text])

    classes = getattr(model, "classes_", None)
    if classes is None:
        pred = model.predict(X)[0]
        pred_name = _decode_label(pred)
        return pred_name, 0.0, [(pred_name, 0.0)]

    # вероятности
    if hasattr(model, "predict_proba"):
        proba = model.predict_proba(X)[0]
    elif hasattr(model, "decision_function"):
        scores = np.array(model.decision_function(X)).reshape(-1)
        proba = _safe_softmax(scores)
    else:
        pred = model.predict(X)[0]
        pred_name = _decode_label(pred)
        return pred_name, 0.0, [(pred_name, 0.0)]

    proba = np.array(proba).reshape(-1)

    best_idx = int(np.argmax(proba))
    best_label = classes[best_idx]
    best_name = _decode_label(best_label)
    best_conf = float(proba[best_idx])

    k = min(int(top_k), len(classes))
    top_idx = np.argsort(proba)[::-1][:k]

    top: List[Tuple[str, float]] = []
    for i in top_idx:
        name = _decode_label(classes[i])
        top.append((name, float(proba[i])))

    return best_name, best_conf, top
