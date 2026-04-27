"""
Standalone demo — no Claude or MCP registration required.

Runs the full 3-tool pipeline:
  1. search_ecommerce  — searches B2C + B2B auto-parts sites
  2. crud_file         — saves results to ./data/<slug>.txt
  3. push_to_prefab    — pushes 4 cards to the Prefab dashboard

The user query is read from the dashboard's current_query field (set via the
web UI at http://localhost:5050) and falls back to DEFAULT_QUERY if none is set.

Usage:
    # Terminal 1 (keep running)
    python prefab_dashboard/server.py

    # Terminal 2
    python run_demo.py
"""

import json
import re

from mcp_server import (
    DASHBOARD_FILE,
    search_ecommerce,
    crud_file,
    push_to_prefab,
)

# ── defaults ───────────────────────────────────────────────────────────────

DEFAULT_QUERY   = "My Honda Civic brakes are making squealing noise"
DEFAULT_HINT    = "Front Brake Pad Set"
DEFAULT_VEHICLE = "Honda Civic 2020"

B2C_SITES = {"Amazon", "eBay"}
PREFERRED_SITES = [
    "AutoZone", "Advance Auto Parts", "O'Reilly Auto Parts",
    "RockAuto", "Amazon", "eBay",
]


# ── helpers ────────────────────────────────────────────────────────────────

def _read_dashboard_query() -> str:
    """Return current_query from dashboard.json, or empty string on failure."""
    try:
        data = json.loads(DASHBOARD_FILE.read_text(encoding="utf-8"))
        return (data.get("current_query") or "").strip()
    except Exception:
        return ""


def _slugify(text: str) -> str:
    """Turn a sentence into a safe filename stem."""
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug[:60]


def _count_ok(listings: list[dict]) -> int:
    return len([x for x in listings if "error" not in x])


def _top_item(listings: list[dict]) -> dict | None:
    return next(
        (item for item in listings if "error" not in item and item.get("title")),
        None,
    )


def _find_best(listings: dict) -> tuple[str | None, dict | None]:
    """Return (site_name, item) for the highest-priority result, or (None, None)."""
    for site in PREFERRED_SITES:
        item = _top_item(listings.get(site, []))
        if item:
            return site, item
    return None, None


# ── pipeline steps ─────────────────────────────────────────────────────────

def step1_search(user_query: str, product_hint: str, vehicle_info: str) -> dict:
    print(f"\n[Step 1] Searching eCommerce sites")
    print(f"         Query   : {user_query}")
    print(f"         Hint    : {product_hint}")
    print(f"         Vehicle : {vehicle_info}")

    raw  = search_ecommerce(
        user_query=user_query,
        product_hint=product_hint,
        vehicle_info=vehicle_info,
        max_per_site=2,
    )
    data = json.loads(raw)

    print(f"         Search  : {data['search_query']}")
    for site, items in data["listings"].items():
        channel = items[0].get("channel", "") if items else ""
        print(f"         {site} ({channel}): {_count_ok(items)} listing(s)")
    return data


def step2_save(data: dict, output_file: str) -> None:
    print(f"\n[Step 2] Saving results to data/{output_file}")

    lines = [
        f"Customer Query  : {data['user_query']}",
        f"Product Searched: {data['search_query']}",
        f"Sites Searched  : {data['sites_searched']}",
        "=" * 60,
        "",
    ]
    for site, items in data["listings"].items():
        channel = items[0].get("channel", "") if items else ""
        lines.append(f"[{site}]  ({channel})")
        top = _top_item(items)
        if top:
            lines.append(f"  Title  : {top['title']}")
            lines.append(f"  URL    : {top['url']}")
            if top.get("snippet"):
                lines.append(f"  Snippet: {top['snippet'][:150]}")
        else:
            lines.append("  (no results)")
        lines.append("")

    best_site, best = _find_best(data["listings"])
    if best:
        lines += [
            "=" * 60,
            "BEST PICK",
            f"  Site : {best_site}",
            f"  Title: {best['title']}",
            f"  URL  : {best['url']}",
        ]

    content = "\n".join(lines)
    crud_file("delete", output_file)
    result = crud_file("create", output_file, content)
    print(f"         {result}")


def step3_dashboard(data: dict, product_hint: str, vehicle_info: str, output_file: str) -> None:
    print("\n[Step 3] Pushing 4 cards to Prefab dashboard (http://localhost:5050)")

    b2c_counts = {
        s: f"{_count_ok(v)} result(s)"
        for s, v in data["listings"].items() if s in B2C_SITES
    }
    b2b_counts = {
        s: f"{_count_ok(v)} result(s)"
        for s, v in data["listings"].items() if s not in B2C_SITES
    }

    # Card 1 — diagnosis
    push_to_prefab(
        title="Customer Query & Diagnosis",
        content=(
            f"Customer complaint:\n{data['user_query']}\n\n"
            f"Hybrid search identified:\n{data['search_query']}"
        ),
        card_type="data",
        metadata=json.dumps({
            "Part":     product_hint,
            "Vehicle":  vehicle_info,
            "Method":   "hybrid BM25 + semantic + product_hint",
        }),
    )
    print("         Card 1 pushed: Customer Query & Diagnosis")

    # Card 2 — B2C listings
    b2c_lines = [
        f"{site}:\n  {top['title']}\n  {top['url']}"
        for site in ["Amazon", "eBay"]
        if (top := _top_item(data["listings"].get(site, [])))
    ]
    push_to_prefab(
        title="B2C Listings  (Amazon · eBay)",
        content="\n\n".join(b2c_lines) or "No B2C listings found.",
        card_type="search",
        metadata=json.dumps(b2c_counts),
    )
    print("         Card 2 pushed: B2C Listings")

    # Card 3 — B2B listings
    b2b_lines = [
        f"{site}:\n  {top['title']}\n  {top['url']}"
        for site in ["AutoZone", "RockAuto", "Advance Auto Parts", "O'Reilly Auto Parts"]
        if (top := _top_item(data["listings"].get(site, [])))
    ]
    push_to_prefab(
        title="B2B / Auto Parts Retailers",
        content="\n\n".join(b2b_lines) or "No B2B listings found.",
        card_type="info",
        metadata=json.dumps(b2b_counts),
    )
    print("         Card 3 pushed: B2B / Auto Parts Retailers")

    # Card 4 — best pick / Gemini summary
    best_site, best = _find_best(data["listings"])
    gemini_rec  = data.get("gemini_recommendation", "")
    best_content = (
        gemini_rec
        or (f"Recommended from {best_site}:\n{best['title']}\n{best['url']}" if best
            else "No recommendation available.")
    )
    push_to_prefab(
        title="Best Pick & Summary",
        content=best_content,
        card_type="success",
        metadata=json.dumps({
            "File saved":     output_file,
            "Sites searched": str(data["sites_searched"]),
            "Best from":      best_site or "N/A",
        }),
    )
    print("         Card 4 pushed: Best Pick & Summary")


# ── main ───────────────────────────────────────────────────────────────────

def main() -> None:
    # Read query from dashboard if set, otherwise use the default
    user_query = _read_dashboard_query() or DEFAULT_QUERY
    product_hint = DEFAULT_HINT
    vehicle_info = DEFAULT_VEHICLE
    output_file  = _slugify(user_query) + ".txt"

    print("=" * 60)
    print(" Auto Parts eCommerce Search — Standalone Demo")
    print("=" * 60)
    print(f" Query source : {'dashboard' if _read_dashboard_query() else 'default'}")

    data = step1_search(user_query, product_hint, vehicle_info)
    step2_save(data, output_file)
    step3_dashboard(data, product_hint, vehicle_info, output_file)

    print("\n" + "=" * 60)
    print(" Done.")
    print(f" Dashboard : http://localhost:5050")
    print(f" File      : data/{output_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()
