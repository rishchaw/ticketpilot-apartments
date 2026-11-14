"""Lightweight CPU inference: same PyTorch-trained linear layers, exported to NumPy.
The classifier remains a PyTorch training project. Only serving avoids the
PyTorch binary to reduce cloud image size and storage costs.
"""
from __future__ import annotations
import os
from functools import lru_cache
from pathlib import Path
import joblib
import numpy as np

LABELS = ("access", "billing", "infrastructure", "product")
ROOT = Path(__file__).resolve().parents[1]

@lru_cache(maxsize=1)
def load_model():
    artifacts = Path(os.getenv("MODEL_DIR", ROOT / "artifacts"))
    vectorizer = joblib.load(artifacts / "vectorizer.joblib")
    with np.load(artifacts / "model_numpy.npz", allow_pickle=False) as data:
        weights = {key: np.asarray(data[key], dtype=np.float32) for key in ("w1", "b1", "w2", "b2")}
    return vectorizer, weights

def classify(text: str) -> tuple[str, float, dict[str, float]]:
    vectorizer, w = load_model()
    x = vectorizer.transform([text]).toarray().astype(np.float32)
    hidden = np.maximum(x @ w["w1"].T + w["b1"], 0)
    logits = (hidden @ w["w2"].T + w["b2"])[0]
    shifted = logits - float(np.max(logits))
    scores_raw = np.exp(shifted)
    probs = scores_raw / float(np.sum(scores_raw))
    scores = {label: round(float(v), 4) for label, v in zip(LABELS, probs)}
    index = int(np.argmax(probs))
    return LABELS[index], float(probs[index]), scores
