# Demo Prompt — Hybrid_Search_MCP

## Before you start

Open **two terminals** in the project directory.

**Terminal 1 — Prefab dashboard**
```bash
python prefab_dashboard/server.py
```
Open http://localhost:5050 and keep it visible — cards appear here in real time.

**Terminal 2 — Claude with MCP**
```bash
claude
```
The MCP server (`hybrid-search-mcp`) must be registered (see README Option B) and
show `✓ Connected` in `claude mcp list` before you paste the prompt.

---

## The Prompt

Paste this verbatim into the Claude session:

---

> I am a customer whose **Honda Civic brakes are making a squealing noise**.
>
> My query is: **"My Honda Civic brakes are making squealing noise"**
>
> Please do ALL of the following steps in order and do not skip any:
>
> ---
>
> **Step 1 — Search eCommerce sites for the right part**
>
> Call `search_ecommerce` with:
> - `user_query` = "My Honda Civic brakes are making squealing noise"
> - `product_hint` = "Front Brake Pad Set"
> - `vehicle_info` = "Honda Civic 2020"
> - `max_per_site` = 2
>
> This will search Amazon, eBay, AutoZone, RockAuto, Advance Auto Parts, and
> O'Reilly Auto Parts for the product.
>
> ---
>
> **Step 2 — Save the results to a local file**
>
> Call `crud_file` with operation `create` and filename `honda_civic_brake_pads.txt`.
>
> The file must contain:
> - The customer's original complaint
> - The matched part name and part ID from the local catalog
> - For every eCommerce site: site name, channel (B2C or B2B/Retail), and the
>   top listings with title and URL
> - A "best pick" recommendation at the end
>
> ---
>
> **Step 3 — Display everything on the Prefab dashboard**
>
> Call `push_to_prefab` **four times** to publish these cards to http://localhost:5050:
>
> 1. **Card — "Customer Query & Diagnosis"** (type: `data`)
>    Content: the original complaint + how the hybrid search identified "Front Brake Pad Set"
>    Metadata JSON: `{"Part ID": "BRK-2045", "Category": "Brakes", "Match": "hybrid"}`
>
> 2. **Card — "B2C Listings"** (type: `search`)
>    Content: top results from Amazon and eBay with titles and URLs
>    Metadata JSON: `{"Amazon": "<count> results", "eBay": "<count> results"}`
>
> 3. **Card — "B2B / Auto Parts Retailers"** (type: `info`)
>    Content: top results from AutoZone, RockAuto, Advance Auto Parts, O'Reilly
>    Metadata JSON: one key per retailer with result count
>
> 4. **Card — "Best Pick & Summary"** (type: `success`)
>    Content: your recommended product with reasoning (price, fitment, availability)
>    Metadata JSON: `{"File saved": "honda_civic_brake_pads.txt", "Sites searched": "6"}`
>
> ---
>
> Confirm at the end:
> - The file `honda_civic_brake_pads.txt` was created in `./data/`
> - All four cards are live on the Prefab dashboard at http://localhost:5050

---

## What each step exercises

| Step | MCP Tool            | Requirement                           |
|------|---------------------|---------------------------------------|
| 1    | `search_ecommerce`  | Internet search on B2C + B2B sites    |
| 2    | `crud_file`         | CRUD — create a local file            |
| 3    | `push_to_prefab`    | Communicate back via Prefab UI        |

The Prefab dashboard auto-refreshes every 3 seconds — watch the four cards appear
live as the agent calls `push_to_prefab`.  The activity log on the right sidebar
records every tool call with its timestamp.
