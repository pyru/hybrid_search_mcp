import json
import os
import datetime
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from ddgs import DDGS
from mcp.server.fastmcp import FastMCP
from search_engine import HybridSearchEngine

BASE_DIR       = Path(__file__).parent
DATA_DIR       = BASE_DIR / "data"
DASHBOARD_FILE = BASE_DIR / "prefab_dashboard" / "data" / "dashboard.json"

_EMPTY = {
    "cards":         [],
    "activity_log":  [],
    "last_updated":  None,
    "current_query": "",
}

# B2C + B2B auto-parts sites searched by search_ecommerce.
# Tuple: (display_name, domain, channel)
ECOMMERCE_SITES: list[tuple[str, str, str]] = [
    ("Amazon",              "amazon.com",           "B2C"),
    ("eBay",                "ebay.com",             "B2C"),
    ("AutoZone",            "autozone.com",         "B2B/Retail"),
    ("RockAuto",            "rockauto.com",         "B2B/Retail"),
    ("Advance Auto Parts",  "advanceautoparts.com", "B2B/Retail"),
    ("O'Reilly Auto Parts", "oreillyauto.com",      "B2B/Retail"),
]

mcp = FastMCP("Hybrid_Search_MCP")

# Lazy-loaded — pays the model-loading cost only on first search call.
_engine: HybridSearchEngine | None = None


# ── dashboard helpers ──────────────────────────────────────────────────────

def _init_dashboard() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    DASHBOARD_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DASHBOARD_FILE.exists():
        DASHBOARD_FILE.write_text(json.dumps(_EMPTY, indent=2))

_init_dashboard()


def _now() -> str:
    return datetime.datetime.now().isoformat()


def _read_dash() -> dict:
    try:
        return json.loads(DASHBOARD_FILE.read_text(encoding="utf-8"))
    except Exception:
        return dict(_EMPTY)


def _write_dash(data: dict) -> None:
    DASHBOARD_FILE.write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _log(message: str) -> None:
    data = _read_dash()
    data.setdefault("activity_log", []).insert(
        0, {"message": message, "timestamp": _now()}
    )
    data["activity_log"] = data["activity_log"][:30]
    _write_dash(data)


# ── search helpers ─────────────────────────────────────────────────────────

def _get_engine() -> HybridSearchEngine:
    global _engine
    if _engine is None:
        _engine = HybridSearchEngine(
            str(BASE_DIR / "data" / "parts.csv"), verbose=False
        )
    return _engine


def _gemini_recommend(user_query: str, search_query: str, listings: dict) -> str:
    """Ask Gemini to pick the best listing. Returns empty string on any failure."""
    api_key = os.getenv("GEMINI_API_KEY", "")
    model   = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-lite")
    if not api_key:
        return ""

    listing_lines = [
        f"- [{site}] {item['title']} | {item['url']}"
        for site, items in listings.items()
        for item in items
        if "error" not in item and item.get("title")
    ]
    if not listing_lines:
        return ""

    prompt = (
        f'A customer said: "{user_query}"\n'
        f'We searched for: "{search_query}"\n\n'
        f"Here are the top listings found:\n"
        + "\n".join(listing_lines[:12])
        + "\n\nIn 2-3 sentences, recommend the best option and briefly explain why "
          "(consider fitment, store reliability, and availability). Be direct."
    )

    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(model=model, contents=prompt)
        return response.text.strip()
    except Exception:
        return ""


# ── MCP Tool 1 — eCommerce search ─────────────────────────────────────────

@mcp.tool()
def search_ecommerce(
    user_query: str,
    product_hint: str = "",
    vehicle_info: str = "",
    max_per_site: int = 2,
) -> str:
    """
    Search B2C and B2B auto-parts eCommerce sites from a natural-language query.

    Pipeline:
      1. Run the local hybrid search engine (BM25 + semantic) against the parts
         catalog to identify the best-matching part name.
      2. Optionally override with an explicit product_hint.
      3. Search Amazon, eBay, AutoZone, RockAuto, Advance Auto Parts, and
         O'Reilly Auto Parts using site-targeted DuckDuckGo queries.

    Args:
        user_query:   Natural-language problem description, e.g.
                      "My Honda Civic brakes are making squealing noise"
        product_hint: Explicit product name that skips the catalog lookup, e.g.
                      "Front Brake Pad Set"
        vehicle_info: "Make Model Year" appended to site search for fitment, e.g.
                      "Honda Civic 2020"
        max_per_site: Listings to fetch per site (1–3, default 2)

    Returns:
        JSON with catalog_match, search_query used, and per-site listings.
    """
    max_per_site = max(1, min(3, max_per_site))

    # Step 1 — identify product from local catalog (unless caller already knows it)
    catalog_match: dict | None = None
    if product_hint:
        product_name = product_hint
    else:
        hits = _get_engine().hybrid_search(user_query, top_k=1)
        if hits:
            h = hits[0]
            catalog_match = {
                "part_id":    h["part_id"],
                "name":       h["name"],
                "category":   h["category"],
                "symptoms":   h["symptoms"],
                "score":      h["score"],
                "match_type": h["match_type"],
            }
            product_name = h["name"]
        else:
            product_name = user_query

    # Step 2 — build eCommerce search string
    search_query = f"{product_name} {vehicle_info}".strip()

    # Step 3 — query each site (small delay between requests to avoid rate limits)
    listings: dict[str, list[dict]] = {}
    for display_name, domain, channel in ECOMMERCE_SITES:
        try:
            raw = list(
                DDGS().text(f"site:{domain} {search_query}", max_results=max_per_site)
            )
            listings[display_name] = [
                {
                    "channel": channel,
                    "title":   r.get("title", ""),
                    "url":     r.get("href", ""),
                    "snippet": r.get("body", ""),
                }
                for r in raw
            ]
        except Exception as exc:
            listings[display_name] = [{"channel": channel, "error": str(exc)}]
        time.sleep(0.4)

    total = sum(
        len(v) for v in listings.values()
        if isinstance(v, list) and not any("error" in item for item in v)
    )
    _log(f"search_ecommerce: '{search_query}' -> {total} listings across {len(ECOMMERCE_SITES)} sites")

    return json.dumps(
        {
            "user_query":            user_query,
            "catalog_match":         catalog_match,
            "product_hint":          product_hint or None,
            "search_query":          search_query,
            "sites_searched":        len(ECOMMERCE_SITES),
            "listings":              listings,
            "gemini_recommendation": _gemini_recommend(user_query, search_query, listings),
        },
        indent=2,
        ensure_ascii=False,
    )


# ── MCP Tool 2 — Local file CRUD ──────────────────────────────────────────

@mcp.tool()
def crud_file(operation: str, filename: str, content: str = "") -> str:
    """
    CRUD operations on text files inside the ./data directory.

    Args:
        operation: create | read | update | append | delete | list
        filename:  File name only, e.g. 'results.txt'  (path traversal is blocked)
        content:   Text for create / update / append

    Returns:
        File text (read), status message, or JSON file listing (list).
    """
    name = Path(filename).name
    path = DATA_DIR / name

    ops = {
        "create": lambda: _file_create(path, name, content),
        "read":   lambda: _file_read(path, name),
        "update": lambda: _file_update(path, name, content),
        "append": lambda: _file_append(path, name, content),
        "delete": lambda: _file_delete(path, name),
        "list":   lambda: _file_list(),
    }
    handler = ops.get(operation)
    if handler is None:
        return (
            f"ERROR: Unknown operation '{operation}'. "
            "Use create / read / update / append / delete / list."
        )
    return handler()


def _file_create(path: Path, name: str, content: str) -> str:
    if path.exists():
        return f"ERROR: '{name}' already exists. Use 'update' to overwrite."
    path.write_text(content, encoding="utf-8")
    _log(f"crud_file create: {name}")
    return f"Created '{name}' ({len(content)} chars)."

def _file_read(path: Path, name: str) -> str:
    if not path.exists():
        return f"ERROR: '{name}' not found."
    _log(f"crud_file read: {name}")
    return path.read_text(encoding="utf-8")

def _file_update(path: Path, name: str, content: str) -> str:
    if not path.exists():
        return f"ERROR: '{name}' not found. Use 'create' first."
    path.write_text(content, encoding="utf-8")
    _log(f"crud_file update: {name}")
    return f"Updated '{name}' ({len(content)} chars)."

def _file_append(path: Path, name: str, content: str) -> str:
    with path.open("a", encoding="utf-8") as fh:
        fh.write(content)
    _log(f"crud_file append: {name}")
    return f"Appended {len(content)} chars to '{name}'."

def _file_delete(path: Path, name: str) -> str:
    if not path.exists():
        return f"ERROR: '{name}' not found."
    path.unlink()
    _log(f"crud_file delete: {name}")
    return f"Deleted '{name}'."

def _file_list() -> str:
    entries = [
        {
            "name":     f.name,
            "bytes":    f.stat().st_size,
            "modified": datetime.datetime.fromtimestamp(f.stat().st_mtime).isoformat(),
        }
        for f in sorted(DATA_DIR.iterdir()) if f.is_file()
    ]
    return json.dumps(entries, indent=2)


# ── MCP Tool 3 — Push to Prefab dashboard ─────────────────────────────────

@mcp.tool()
def push_to_prefab(
    title: str,
    content: str,
    card_type: str = "info",
    metadata: str = "",
) -> str:
    """
    Publish a card to the live Prefab web dashboard at http://localhost:5050.

    Args:
        title:     Card heading
        content:   Body text (multi-line supported)
        card_type: Visual style — info | success | warning | data | search | error
        metadata:  Optional JSON string of key/value pairs shown as a table,
                   e.g. '{"Store": "AutoZone", "Price": "$34.99"}'

    Returns:
        Confirmation with the dashboard URL.
    """
    data = _read_dash()

    parsed_meta = None
    if metadata and metadata.strip():
        try:
            parsed_meta = json.loads(metadata)
        except json.JSONDecodeError:
            parsed_meta = {"raw": metadata}

    card = {
        "id":        len(data.get("cards", [])) + 1,
        "title":     title,
        "content":   content,
        "type":      card_type,
        "timestamp": _now(),
        "metadata":  parsed_meta,
    }
    data.setdefault("cards", []).insert(0, card)
    data["cards"]        = data["cards"][:50]
    data["last_updated"] = _now()

    _write_dash(data)
    _log(f"push_to_prefab: '{title}' [{card_type}]")
    return f"Card '{title}' pushed. Open http://localhost:5050 to view."


if __name__ == "__main__":
    mcp.run(transport="stdio")
