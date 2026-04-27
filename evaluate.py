"""
Evaluation harness — 20 labelled queries, three search modes.
Run:  python evaluate.py
"""

import json
from pathlib import Path

import pandas as pd
from search_engine import HybridSearchEngine

TEST_QUERIES = [
    # exact ID / technical
    {"q": "BRK-2045",       "relevant": ["BRK-2045"]},
    {"q": "ENG-3310",       "relevant": ["ENG-3310"]},
    {"q": "part BAT-9001",  "relevant": ["BAT-9001"]},
    # structured
    {"q": "Honda Civic 2020 brake pads",    "relevant": ["BRK-2045", "BRK-2046"]},
    {"q": "Toyota Camry 2021 strut",        "relevant": ["SUS-7781"]},
    {"q": "Ford F-150 oxygen sensor",       "relevant": ["ENG-3310", "ENG-3311"]},
    {"q": "spark plugs Toyota Camry",       "relevant": ["ENG-4420"]},
    # natural language symptoms
    {"q": "my car shakes at highway speeds",
     "relevant": ["SUS-7781", "SUS-7782", "BRK-3102"]},
    {"q": "grinding noise when I press the brake pedal",
     "relevant": ["BRK-2045", "BRK-2046", "BRK-3102"]},
    {"q": "car won't start and makes a clicking sound",
     "relevant": ["BAT-9001", "BAT-9002", "ELE-1111"]},
    {"q": "engine overheating and coolant leaking",
     "relevant": ["ENG-9970", "ENG-9971", "COO-8810", "COO-8811"]},
    {"q": "air conditioning blowing warm air",
     "relevant": ["HVC-2020", "HVC-2021"]},
    {"q": "steering feels loose and wanders",
     "relevant": ["SUS-9913", "STR-1011", "SUS-8845"]},
    {"q": "battery keeps dying overnight",
     "relevant": ["BAT-9001", "BAT-9002", "ELE-1110"]},
    {"q": "clicking sound when turning the wheel",
     "relevant": ["TRN-7721", "SUS-8846"]},
    # mixed
    {"q": "Toyota Camry 2021 makes clunking noise over bumps",
     "relevant": ["SUS-7782", "SUS-7781"]},
    {"q": "Honda Civic 2020 rough idle misfire",
     "relevant": ["ENG-5530", "ENG-5531", "SEN-6061"]},
    {"q": "check engine light P0420 Toyota",
     "relevant": ["EXH-9920"]},
    {"q": "Ford F-150 no start intermittent",
     "relevant": ["SEN-6062", "ELE-3330"]},
    {"q": "window won't roll up Chevy Silverado",
     "relevant": ["ELE-4440"]},
]


def precision_at_k(returned: list[dict], relevant: list[str], k: int) -> float:
    top = [r["part_id"] for r in returned[:k]]
    return sum(1 for p in top if p in relevant) / k if top else 0.0


def recall_at_k(returned: list[dict], relevant: list[str], k: int) -> float:
    if not relevant:
        return 0.0
    top = [r["part_id"] for r in returned[:k]]
    return sum(1 for p in relevant if p in top) / len(relevant)


def reciprocal_rank(returned: list[dict], relevant: list[str]) -> float:
    for i, r in enumerate(returned, start=1):
        if r["part_id"] in relevant:
            return 1.0 / i
    return 0.0


def run() -> None:
    engine = HybridSearchEngine("data/parts.csv")
    K = 5
    rows = []

    for t in TEST_QUERIES:
        q, rel = t["q"], t["relevant"]
        kw  = engine.keyword_search(q, top_k=K)
        sem = engine.semantic_search(q, top_k=K)
        hyb = engine.hybrid_search(q, top_k=K)
        rows.append({
            "query":    q,
            "kw_P@5":  round(precision_at_k(kw,  rel, K), 3),
            "sem_P@5": round(precision_at_k(sem, rel, K), 3),
            "hyb_P@5": round(precision_at_k(hyb, rel, K), 3),
            "kw_R@5":  round(recall_at_k(kw,  rel, K), 3),
            "sem_R@5": round(recall_at_k(sem, rel, K), 3),
            "hyb_R@5": round(recall_at_k(hyb, rel, K), 3),
            "kw_MRR":  round(reciprocal_rank(kw,  rel), 3),
            "sem_MRR": round(reciprocal_rank(sem, rel), 3),
            "hyb_MRR": round(reciprocal_rank(hyb, rel), 3),
        })

    df = pd.DataFrame(rows)

    summary = {
        mode: {
            "Precision@5": df[f"{k}_P@5"].mean(),
            "Recall@5":    df[f"{k}_R@5"].mean(),
            "MRR":         df[f"{k}_MRR"].mean(),
        }
        for mode, k in [("Keyword", "kw"), ("Semantic", "sem"), ("Hybrid", "hyb")]
    }
    summary_df = pd.DataFrame(summary).T.round(3)

    print("\n===== Per-query results =====")
    print(df.to_string(index=False))
    print("\n===== Summary (averages over 20 queries) =====")
    print(summary_df.to_string())

    wins = sum(
        1 for _, r in df.iterrows()
        if r["hyb_P@5"] >= max(r["kw_P@5"], r["sem_P@5"])
    )
    print(f"\nHybrid ties-or-beats best single mode on {wins}/{len(df)} queries")

    out = Path("results")
    out.mkdir(exist_ok=True)
    df.to_csv(out / "per_query_results.csv", index=False)
    summary_df.to_csv(out / "summary.csv")
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"Results saved to {out}/")


if __name__ == "__main__":
    run()
