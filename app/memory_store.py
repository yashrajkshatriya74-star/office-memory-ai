"""
Storage layer - Simple JSON + numpy based vector store.
ChromaDB avoid kiya kyunki Windows pe C++ Build Tools maangta hai (chroma-hnswlib).
Ye approach halka hai, koi native build nahi chahiye, aur hackathon demo ke liye kaafi fast hai.
"""
import json
import os
import time
import numpy as np
from sentence_transformers import SentenceTransformer

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)

MESSAGES_FILE = os.path.join(DATA_DIR, "messages.json")
DECISIONS_FILE = os.path.join(DATA_DIR, "decisions.json")

# Free local embedding model - koi API cost nahi, offline chalta hai
_model = SentenceTransformer("all-MiniLM-L6-v2")


def _load(filepath):
    if not os.path.exists(filepath):
        return []
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(filepath, data):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _embed(text: str):
    return _model.encode(text).tolist()


def _cosine_sim(a, b):
    a, b = np.array(a), np.array(b)
    denom = (np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0:
        return 0.0
    return float(np.dot(a, b) / denom)


def store_message(channel_id: str, user_id: str, text: str, ts: str):
    data = _load(MESSAGES_FILE)
    data.append({
        "id": f"{channel_id}-{ts}",
        "text": text,
        "embedding": _embed(text),
        "channel": channel_id,
        "user": user_id,
        "ts": ts,
    })
    _save(MESSAGES_FILE, data)


def store_decision(channel_id: str, user_id: str, original_text: str, summary: str, ts: str):
    data = _load(DECISIONS_FILE)
    combined_text = f"{original_text}\n\n{summary}"
    data.append({
        "id": f"decision-{channel_id}-{ts}",
        "text": combined_text,
        "embedding": _embed(combined_text),
        "channel": channel_id,
        "user": user_id,
        "ts": ts,
        "original_text": original_text,
        "summary": summary,
        "stored_at": time.time(),
    })
    _save(DECISIONS_FILE, data)


def _query(filepath, question: str, n_results: int = 3):
    data = _load(filepath)
    if not data:
        return {"documents": [[]], "metadatas": [[]], "scores": [[]]}

    q_embedding = _embed(question)
    scored = [
        (item, _cosine_sim(q_embedding, item["embedding"]))
        for item in data
    ]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:n_results]

    documents = [item["text"] for item, score in top]
    metadatas = [
        {"channel": item["channel"], "user": item["user"], "ts": item["ts"]}
        for item, score in top
    ]
    scores = [score for item, score in top]
    return {"documents": [documents], "metadatas": [metadatas], "scores": [scores]}


def query_decisions(question: str, n_results: int = 3):
    return _query(DECISIONS_FILE, question, n_results)


def query_all(question: str, n_results: int = 5):
    return _query(MESSAGES_FILE, question, n_results)


def get_similar_past_decisions(new_decision_text: str, channel_id: str, similarity_threshold: float = 0.45, n_results: int = 2):
    """
    Naya decision store karne se PEHLE call karo - dekhta hai kya isi topic pe
    pehle se koi decision store hai (possible contradiction/update ke liye).
    Sirf threshold se upar wale (genuinely related) matches return karta hai.
    """
    data = _load(DECISIONS_FILE)
    data = [d for d in data if d["channel"] == channel_id]
    if not data:
        return []

    q_embedding = _embed(new_decision_text)
    scored = [
        (item, _cosine_sim(q_embedding, item["embedding"]))
        for item in data
    ]
    scored = [(item, score) for item, score in scored if score >= similarity_threshold]
    scored.sort(key=lambda x: x[1], reverse=True)
    top = scored[:n_results]

    return [
        {
            "text": item["original_text"],
            "summary": item["summary"],
            "ts": item["ts"],
            "score": score,
        }
        for item, score in top
    ]
