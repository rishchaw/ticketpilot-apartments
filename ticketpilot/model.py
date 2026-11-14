"""TF-IDF input features feeding a small PyTorch multilayer perceptron."""
from __future__ import annotations
import os
from functools import lru_cache
from pathlib import Path

import joblib
import numpy as np
import torch
from torch import nn

LABELS = ("access", "billing", "infrastructure", "product")
ROOT = Path(__file__).resolve().parents[1]

class TicketNet(nn.Module):
    def __init__(self, vocab_size: int, hidden: int = 64, num_classes: int = 4):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(vocab_size, hidden),
            nn.ReLU(),
            nn.Dropout(0.12),
            nn.Linear(hidden, num_classes),
        )

    def forward(self, features: torch.Tensor) -> torch.Tensor:
        return self.net(features)

@lru_cache(maxsize=1)
def load_model():
    """Load only artifacts bundled within this repository (never user uploads)."""
    artifacts = Path(os.getenv("MODEL_DIR", ROOT / "artifacts"))
    vectorizer = joblib.load(artifacts / "vectorizer.joblib")
    network = TicketNet(len(vectorizer.vocabulary_))
    network.load_state_dict(torch.load(artifacts / "model.pt", map_location="cpu", weights_only=True))
    network.eval()
    return vectorizer, network


def classify(text: str) -> tuple[str, float, dict[str, float]]:
    vectorizer, network = load_model()
    features = vectorizer.transform([text]).toarray().astype(np.float32)
    with torch.inference_mode():
        probabilities = torch.softmax(network(torch.from_numpy(features)), dim=1)[0].numpy()
    scores = {label: round(float(score), 4) for label, score in zip(LABELS, probabilities)}
    index = int(np.argmax(probabilities))
    return LABELS[index], float(probabilities[index]), scores
