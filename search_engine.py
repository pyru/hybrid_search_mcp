import re
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity


class HybridSearchEngine:
    """
    Three search modes on a CSV-backed parts catalog:
      keyword  — BM25 on tokenized text
      semantic — cosine similarity on sentence embeddings
      hybrid   — weighted blend of both (min-max normalised)
    """

    def __init__(
        self,
        csv_path: str,
        model_name: str = "all-MiniLM-L6-v2",
        cache_dir: str = "./cache",
        verbose: bool = True,
    ):
        self.csv_path = csv_path
        self.model_name = model_name
        self.cache_dir = Path(cache_dir)
        self.verbose = verbose
        self.cache_dir.mkdir(exist_ok=True)

        self.df: pd.DataFrame = None
        self.bm25: BM25Okapi = None
        self.model: SentenceTransformer = None
        self.embeddings: np.ndarray = None

        self._load_data()
        self._build_indexes()

    # ── private helpers ────────────────────────────────────────────────────

    def _log(self, msg: str) -> None:
        if self.verbose:
            print(msg)

    def _load_data(self) -> None:
        self.df = pd.read_csv(self.csv_path)
        self.df["search_text"] = (
            self.df["part_id"].fillna("") + " | "
            + self.df["name"].fillna("") + " | "
            + self.df["category"].fillna("") + " | "
            + self.df["vehicle_model"].fillna("") + " | "
            + self.df["year"].astype(str) + " | "
            + self.df["symptoms"].fillna("") + " | "
            + self.df["description"].fillna("")
        )
        self._log(f"[load] {len(self.df)} parts from {self.csv_path}")

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        text = re.sub(r"[^a-z0-9\s\-]", " ", text.lower())
        return [t for t in text.split() if t]

    @staticmethod
    def _minmax(scores: np.ndarray) -> np.ndarray:
        lo, hi = float(scores.min()), float(scores.max())
        if hi - lo < 1e-9:
            return np.zeros_like(scores)
        return (scores - lo) / (hi - lo)

    def _build_indexes(self) -> None:
        corpus_tokens = [self._tokenize(t) for t in self.df["search_text"]]
        self.bm25 = BM25Okapi(corpus_tokens)
        self._log("[index] BM25 ready")

        self.model = SentenceTransformer(self.model_name)
        emb_cache = self.cache_dir / "embeddings.pkl"

        if emb_cache.exists():
            cached = pickle.loads(emb_cache.read_bytes())
            if cached["count"] == len(self.df):
                self.embeddings = cached["embeddings"]
                self._log(f"[index] embeddings loaded from cache {self.embeddings.shape}")
                return

        self._log("[index] encoding corpus (first run ~30 s)…")
        self.embeddings = self.model.encode(
            self.df["search_text"].tolist(),
            show_progress_bar=self.verbose,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        emb_cache.write_bytes(
            pickle.dumps({"count": len(self.df), "embeddings": self.embeddings})
        )
        self._log(f"[index] embeddings built and cached {self.embeddings.shape}")

    def _row_dict(self, i: int) -> dict:
        """Shared row extractor used by all three search modes."""
        row = self.df.iloc[i]
        return {
            "part_id":       row["part_id"],
            "name":          row["name"],
            "category":      row["category"],
            "vehicle_model": row["vehicle_model"],
            "year":          int(row["year"]) if str(row["year"]).isdigit() else row["year"],
            "symptoms":      row["symptoms"],
            "description":   row["description"],
        }

    # ── public search API ──────────────────────────────────────────────────

    def keyword_search(self, query: str, top_k: int = 5) -> list[dict]:
        scores = np.array(self.bm25.get_scores(self._tokenize(query)))
        norm = self._minmax(scores)
        return [
            {**self._row_dict(i), "score": round(float(norm[i]), 4),
             "bm25_score": round(float(scores[i]), 4)}
            for i in np.argsort(scores)[::-1][:top_k]
        ]

    def semantic_search(self, query: str, top_k: int = 5) -> list[dict]:
        q_emb = self.model.encode([query], normalize_embeddings=True)
        scores = cosine_similarity(q_emb, self.embeddings)[0]
        norm = self._minmax(scores)
        return [
            {**self._row_dict(i), "score": round(float(norm[i]), 4),
             "semantic_score": round(float(scores[i]), 4)}
            for i in np.argsort(scores)[::-1][:top_k]
        ]

    def hybrid_search(
        self,
        query: str,
        top_k: int = 5,
        w_keyword: float = 0.4,
        w_semantic: float = 0.6,
    ) -> list[dict]:
        bm25_raw  = np.array(self.bm25.get_scores(self._tokenize(query)))
        bm25_norm = self._minmax(bm25_raw)

        q_emb    = self.model.encode([query], normalize_embeddings=True)
        sem_norm = self._minmax(cosine_similarity(q_emb, self.embeddings)[0])

        final = w_keyword * bm25_norm + w_semantic * sem_norm

        results = []
        for i in np.argsort(final)[::-1][:top_k]:
            if bm25_norm[i] > 0.5 and sem_norm[i] > 0.5:
                match_type = "both"
            elif bm25_norm[i] > sem_norm[i]:
                match_type = "keyword"
            else:
                match_type = "semantic"

            results.append({
                **self._row_dict(i),
                "score":          round(float(final[i]), 4),
                "bm25_score":     round(float(bm25_norm[i]), 4),
                "semantic_score": round(float(sem_norm[i]), 4),
                "match_type":     match_type,
            })
        return results


if __name__ == "__main__":
    engine = HybridSearchEngine("data/parts.csv")
    for q in [
        "BRK-2045",
        "car shakes when I drive on the highway",
        "grinding noise when braking Honda Civic",
    ]:
        print(f"\n=== {q} ===")
        for r in engine.hybrid_search(q, top_k=3):
            print(f"  [{r['match_type']:8s}] {r['part_id']:10s} {r['name']:30s} score={r['score']}")
