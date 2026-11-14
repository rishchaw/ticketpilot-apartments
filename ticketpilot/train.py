"""Train, evaluate and bundle the model using synthetic demonstration data."""
from __future__ import annotations
import csv
import json
import random
from pathlib import Path

import joblib
import numpy as np
import torch
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score
from sklearn.model_selection import train_test_split

from ticketpilot.data import save_data
from ticketpilot.model import LABELS, ROOT, TicketNet


def train(seed: int = 42, epochs: int = 65) -> dict:
    torch.set_num_threads(2)
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    data_path = ROOT / "data/synthetic_tickets.csv"
    if not data_path.exists():
        save_data(data_path)
    with data_path.open(encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))
    train_rows, test_rows = train_test_split(rows, test_size=0.25, random_state=seed, stratify=[r["category"] for r in rows])
    # Vocabulary is fitted only on the training partition to avoid evaluation leakage.
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), max_features=1200, min_df=1, sublinear_tf=True)
    X_train = torch.from_numpy(vectorizer.fit_transform([r["text"] for r in train_rows]).toarray().astype(np.float32))
    X_test = torch.from_numpy(vectorizer.transform([r["text"] for r in test_rows]).toarray().astype(np.float32))
    labels = {label: idx for idx, label in enumerate(LABELS)}
    y_train = torch.tensor([labels[r["category"]] for r in train_rows], dtype=torch.long)
    y_test = np.array([labels[r["category"]] for r in test_rows])
    model = TicketNet(X_train.shape[1])
    optimizer = torch.optim.Adam(model.parameters(), lr=0.014, weight_decay=0.002)
    criterion = torch.nn.CrossEntropyLoss()
    for epoch in range(epochs):
        model.train()
        optimizer.zero_grad()
        logits = model(X_train)
        loss = criterion(logits, y_train)
        loss.backward()
        optimizer.step()
    model.eval()
    with torch.inference_mode():
        probs = torch.softmax(model(X_test), dim=1).numpy()
    predicted = probs.argmax(axis=1)
    confidence = probs.max(axis=1)
    threshold = 0.7
    selected = confidence >= threshold
    metrics = {
        "dataset": "Synthetic templated examples only; NOT production validation",
        "train_samples": len(train_rows),
        "test_samples": len(test_rows),
        "test_accuracy": round(float(accuracy_score(y_test, predicted)), 4),
        "macro_f1": round(float(f1_score(y_test, predicted, average="macro")), 4),
        "automatic_routing_coverage_at_0_70": round(float(selected.mean()), 4),
        "selective_accuracy_at_0_70": round(float((predicted[selected] == y_test[selected]).mean()), 4) if selected.any() else None,
        "confusion_matrix_label_order": list(LABELS),
        "confusion_matrix": confusion_matrix(y_test, predicted, labels=list(range(len(LABELS)))).tolist(),
        "per_class": classification_report(y_test, predicted, target_names=list(LABELS), output_dict=True, zero_division=0),
        "important_caveat": "Random split over templated synthetic data likely overstates performance; test on manually labeled unseen real tickets before production use."
    }
    output_dir = ROOT / "artifacts"
    output_dir.mkdir(exist_ok=True)
    torch.save(model.state_dict(), output_dir / "model.pt")
    joblib.dump(vectorizer, output_dir / "vectorizer.joblib")
    (output_dir / "evaluation.json").write_text(json.dumps(metrics, indent=2), encoding="utf-8")
    print(f"Test macro-F1 (synthetic only): {metrics['macro_f1']}; auto-coverage: {metrics['automatic_routing_coverage_at_0_70']}")
    return metrics

if __name__ == "__main__":
    train()
