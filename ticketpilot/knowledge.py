"""Small inspectable TF-IDF retrieval index. Offline; no vector database bill."""
from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

ROOT = Path(__file__).resolve().parents[1]

@lru_cache(maxsize=1)
def index():
    documents = json.loads((ROOT / "data" / "knowledge_base.json").read_text(encoding="utf-8"))
    corpus = [" ".join([d["title"] + "."] * 2 + [d["summary"]] + d["tags"] * 2 + d["steps"]) for d in documents]
    vectorizer = TfidfVectorizer(ngram_range=(1, 2), stop_words="english", max_features=6000)
    matrix = vectorizer.fit_transform(corpus)
    return documents, vectorizer, matrix

def find_articles(question: str, category: str | None = None, top_k: int = 3) -> list[dict]:
    docs, vec, matrix = index()
    score = cosine_similarity(vec.transform([question]), matrix)[0]
    results = []
    for i, base in enumerate(score):
        if base < 0.08:  # irrelevant requests have no forced answer
            continue
        boosted = float(base) + (0.045 if category and docs[i]["category"] == category else 0)
        results.append((boosted, docs[i]))
    results.sort(key=lambda pair: pair[0], reverse=True)
    return [{**d, "relevance": round(float(s), 3)} for s, d in results[:max(1, min(5, top_k))]]
