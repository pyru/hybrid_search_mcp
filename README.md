# Hybrid_Search_MCP

An AI agent that understands a customer's natural-language complaint, identifies
the right auto part from a local catalog using hybrid search (BM25 + semantic),
searches six B2C and B2B eCommerce sites for live product listings, generates an
AI-powered recommendation via Gemini, saves the results to a local file, and
displays everything on a live Prefab web dashboard.

---

## How it works — end-to-end flow

```
Customer query
"My Honda Civic brakes are making squealing noise"
        │
        ▼
search_ecommerce (MCP Tool 1)
 ├─ Hybrid search (BM25 + semantic) on local parts catalog
 │          → identifies "Front Brake Pad Set"
 ├─ Builds query  "Front Brake Pad Set Honda Civic 2020"
 ├─ Searches 6 eCommerce sites via DuckDuckGo
 │           B2C    → Amazon, eBay
 │           B2B    → AutoZone, RockAuto, Advance Auto Parts, O'Reilly
 └─ Calls Gemini (gemini-2.5-flash-lite) → AI-powered best-pick recommendation
        │
        ▼
crud_file (MCP Tool 2)
 └─ Saves all listings + recommendation to honda_civic_brake_pads.txt
        │
        ▼
push_to_prefab (MCP Tool 3) ×4
 └─ Pushes four cards to Prefab dashboard at http://localhost:5050
    Card 1 – Customer Query & Diagnosis
    Card 2 – B2C Listings (Amazon, eBay)
    Card 3 – B2B / Auto Parts Retailers
    Card 4 – Best Pick & Summary  ← Gemini-generated recommendation
```

---

## Project layout

```
hybrid_search_prefab/
│
├── run_demo.py                   # Standalone runner — no Claude needed
├── mcp_server.py                 # MCP server — 3 agent tools
├── search_engine.py              # Hybrid search backend (BM25 + semantic)
├── evaluate.py                   # 20-query evaluation harness
├── claude_mcp_config.json        # MCP registration config for Claude Desktop
├── demo_prompt.md                # Copy-paste prompt for the Claude demo
├── .env                          # GEMINI_API_KEY and GEMINI_MODEL (not committed)
│
├── prefab_dashboard/
│   ├── server.py                 # Flask server  →  http://localhost:5050
│   ├── templates/index.html      # Dashboard UI (light-orange theme, auto-refresh 3 s, query input)
│   └── data/dashboard.json       # Shared JSON written by tools, read by dashboard
│
├── data/
│   └── parts.csv                 # 67 automotive parts catalog
├── cache/                        # Sentence-transformer embeddings (auto-generated)
├── results/                      # Evaluation output (auto-generated)
└── requirements.txt
```

---

## Prerequisites

- Python 3.10 or later
- Internet access (DuckDuckGo site-search + Gemini API)
- Claude Code CLI only needed for the **optional** Claude-driven mode

---

## One-time setup

```bash
# 1. Create and activate a virtual environment
python -m venv venv

# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate

# 2. Install all dependencies
pip install -r requirements.txt
```

The first run downloads the `all-MiniLM-L6-v2` model (~90 MB) and encodes the
67-part catalog (~30 s on CPU). The embeddings are cached in `./cache/` — every
subsequent run loads in under a second.

### Configure Gemini

The `.env` file in the project root is loaded automatically at startup:

```
GEMINI_API_KEY=<your-key>
GEMINI_MODEL=gemini-2.5-flash-lite
```

Gemini is called once per `search_ecommerce` invocation to generate the
"Best Pick & Summary" card content.  If the key is missing or the call fails,
the tool falls back to a site-based recommendation silently.

---

## Option A — Standalone (no Claude, no registration)

This is the simplest way to run the full demo.  `run_demo.py` imports the three
tool functions directly and executes the pipeline without any AI agent involved.

### Step 1 — Start the Prefab dashboard

Open a terminal and keep it running:

```bash
python prefab_dashboard/server.py
```

Open **http://localhost:5050** in your browser.

### Step 2 — Run the demo script

Open a second terminal:

```bash
python run_demo.py
```

Expected output:

```
============================================================
 Auto Parts eCommerce Search — Standalone Demo
============================================================

[Step 1] Searching eCommerce sites for 'Front Brake Pad Set'
         User query  : My Honda Civic brakes are making squealing noise
         Vehicle     : Honda Civic 2020
         Search query: Front Brake Pad Set Honda Civic 2020
         Amazon (B2C): 2 listing(s)
         eBay (B2C): 2 listing(s)
         AutoZone (B2B/Retail): 2 listing(s)
         RockAuto (B2B/Retail): 2 listing(s)
         Advance Auto Parts (B2B/Retail): 2 listing(s)
         O'Reilly Auto Parts (B2B/Retail): 2 listing(s)

[Step 2] Saving results to data/honda_civic_brake_pads.txt
         Created 'honda_civic_brake_pads.txt' (XXXX chars).

[Step 3] Pushing 4 cards to Prefab dashboard (http://localhost:5050)
         Card 1 pushed: Customer Query & Diagnosis
         Card 2 pushed: B2C Listings
         Card 3 pushed: B2B / Auto Parts Retailers
         Card 4 pushed: Best Pick & Summary

============================================================
 Done.
 Dashboard : http://localhost:5050
 File      : data/honda_civic_brake_pads.txt
============================================================
```

Switch to **http://localhost:5050** — the four cards appear within seconds.
Card 4 shows the Gemini-generated recommendation.

### Step 2b — Run any query from the browser (alternative to Step 2)

Instead of re-running `run_demo.py` manually, you can type any query directly
in the dashboard UI and click **Run Query**. The server spawns the pipeline in
the background and the four cards update within ~30 seconds.

Six sample queries are pre-loaded as clickable chips (e.g. "My Toyota Camry
has an oil leak", "Car battery keeps dying overnight"). Click any chip to fill
the input and submit automatically.

### Reset between runs

Click **Reset** in the dashboard top-right, or:

```bash
curl -X POST http://localhost:5050/api/reset
```

---

## Option B — Claude-driven (MCP agent)

Use this when you want Claude to call the tools autonomously in response to a
natural-language prompt.  Requires the Claude Code CLI.

> **Just want to run a custom query?**  Use the dashboard query input instead
> (Option A, Step 2b) — no Claude Code or MCP registration required.  Option B
> is for interactive AI-driven sessions where you want Claude to reason about
> which tools to call and how to fill their arguments.

### Step 1 — Start the Prefab dashboard

```bash
python prefab_dashboard/server.py
```

### Step 2 — Register the MCP server with Claude Code

Claude Code's health check runs from a different working directory, so register
with **absolute paths**.

Find your Python executable:

```bash
python -c "import sys; print(sys.executable)"
```

Register the server (replace `<PYTHON>` and `<PROJECT>` with your actual paths):

```bash
claude mcp add hybrid-search-mcp \
  -e PYTHONPATH=<PROJECT> \
  -- <PYTHON> <PROJECT>/mcp_server.py
```

**Exact command on this machine:**

```bash
claude mcp add hybrid-search-mcp \
  -e PYTHONPATH="c:/Ramesh_data/2026_Ramesh/TSAI/hybrid_search_prefab/hybrid_search_prefab" \
  -- "C:/Users/Admin/AppData/Local/Microsoft/WindowsApps/PythonSoftwareFoundation.Python.3.12_qbz5n2kfra8p0/python.exe" \
     "c:/Ramesh_data/2026_Ramesh/TSAI/hybrid_search_prefab/hybrid_search_prefab/mcp_server.py"
```

Confirm connected:

```bash
claude mcp list
# hybrid-search-mcp: ... - ✓ Connected
```

> **Claude Desktop alternative:** Copy `claude_mcp_config.json` into your Claude
> Desktop config and restart the app.
> - Windows: `%APPDATA%\Claude\claude_desktop_config.json`
> - macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

### Step 3 — Open a Claude session and paste the prompt

```bash
claude
```

Paste the prompt from `demo_prompt.md` (also shown below):

```
I am a customer whose Honda Civic brakes are making a squealing noise.

My query is: "My Honda Civic brakes are making squealing noise"

Please do ALL of the following steps in order and do not skip any:

STEP 1 — Search eCommerce sites for the right part
Call search_ecommerce with:
  user_query   = "My Honda Civic brakes are making squealing noise"
  product_hint = "Front Brake Pad Set"
  vehicle_info = "Honda Civic 2020"
  max_per_site = 2

STEP 2 — Save the results to a local file
Call crud_file with operation "create" and filename "honda_civic_brake_pads.txt".
Include the original complaint, matched part, all site listings, and the
Gemini-generated best-pick recommendation.

STEP 3 — Display everything on the Prefab dashboard
Call push_to_prefab FOUR times:
  Card 1 "Customer Query & Diagnosis"  type: data
  Card 2 "B2C Listings"                type: search
  Card 3 "B2B / Auto Parts Retailers"  type: info
  Card 4 "Best Pick & Summary"         type: success

Confirm at the end that the file was created and all four cards are live at
http://localhost:5050.
```

Watch **http://localhost:5050** — cards appear in real time as Claude calls
`push_to_prefab`. The activity log on the right sidebar records every tool call.

> **Tip:** `product_hint` and `vehicle_info` are optional.  If you omit them,
> the hybrid search engine (BM25 + semantic) identifies the correct part and
> vehicle automatically from the natural-language `user_query`.

---

## Choosing between Option A and Option B

| | Option A — Script | Option A — Dashboard UI | Option B — Claude |
|-|-------------------|------------------------|-------------------|
| Claude Code CLI needed | No | No | Yes |
| MCP registration needed | No | No | Yes |
| How it runs | `python run_demo.py` | Type query in browser → auto-triggers pipeline | Claude calls MCP tools |
| Good for | CI, scripting, default demo | Ad-hoc custom queries, quick testing | Interactive AI-driven sessions |
| Files used | `run_demo.py` | `prefab_dashboard/server.py` | `mcp_server.py` + `demo_prompt.md` |

All three modes produce identical output on the dashboard and in `./data/`.

---

## MCP tools reference

### `search_ecommerce`

| Argument | Type | Description |
|----------|------|-------------|
| `user_query` | str | Natural-language complaint, e.g. `"brakes making squealing noise"` |
| `product_hint` | str | Explicit product name — skips the catalog lookup when provided |
| `vehicle_info` | str | `"Make Model Year"` appended to the eCommerce search query |
| `max_per_site` | int | Listings per site, 1–3 (default 2) |

**Internal pipeline:**
1. Hybrid search (BM25 + sentence-transformer) on `data/parts.csv` identifies the best-matching part
2. Builds targeted query: `<product_name> <vehicle_info>`
3. Searches each site with `site:<domain> <query>` via DuckDuckGo
4. Calls Gemini (`gemini-2.5-flash-lite`) to generate a natural-language best-pick recommendation

**Sites searched:**

| Site | Channel |
|------|---------|
| Amazon | B2C |
| eBay | B2C |
| AutoZone | B2B / Retail |
| RockAuto | B2B / Retail |
| Advance Auto Parts | B2B / Retail |
| O'Reilly Auto Parts | B2B / Retail |

**Returns:** JSON with `catalog_match`, `search_query`, `listings` keyed by site, and
`gemini_recommendation` (empty string if Gemini is unavailable).

---

### `crud_file`

| Operation | Behaviour |
|-----------|-----------|
| `create`  | Write a new file; errors if it already exists |
| `read`    | Return full file contents |
| `update`  | Overwrite an existing file |
| `append`  | Add text to the end of an existing file |
| `delete`  | Remove the file |
| `list`    | Return a JSON array of all files with size and modified date |

Files are stored in `./data/`.  Path traversal is blocked — filename only.

---

### `push_to_prefab`

Writes a card to `prefab_dashboard/data/dashboard.json`.  The dashboard polls
this file every 3 seconds and renders new cards immediately.

| Argument | Description |
|----------|-------------|
| `title` | Card heading |
| `content` | Body text (multi-line supported) |
| `card_type` | `info` \| `success` \| `warning` \| `data` \| `search` |
| `metadata` | Optional JSON string rendered as a key/value table |

---

## Evaluate the local search engine

```bash
python evaluate.py
```

Runs 20 labelled test queries, prints Precision@5, Recall@5, and MRR for keyword,
semantic, and hybrid modes, and saves results to `./results/`.

| Mode | Precision@5 | Recall@5 | MRR |
|------|-------------|----------|-----|
| Keyword | 0.34 | 0.875 | 0.975 |
| Semantic | 0.39 | 0.967 | 0.833 |
| **Hybrid** | **0.39** | **0.967** | **0.975** |

Hybrid ties or beats the best single mode on 20 / 20 test queries.

---

## Hybrid scoring formula

```
final_score = w_keyword  × minmax(BM25_score)
            + w_semantic × minmax(cosine_similarity)
```

Default: `w_keyword = 0.4`, `w_semantic = 0.6`. Both signals are min-max
normalised per query before blending so neither dominates due to scale.
