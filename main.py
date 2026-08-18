import os
import json
from typing import List, Optional, Dict
from datetime import datetime
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx

app = FastAPI(title="Haaris - Live Price Aggregator")

# CORS for Flutter client
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ────────────────────────────────────────────────────
# Pydantic Models
# ────────────────────────────────────────────────────

class Product(BaseModel):
    id: str
    title: str
    brand: str
    category: str
    imageUrl: str
    verified: bool
    specs: Optional[Dict[str, str]] = None

class Listing(BaseModel):
    id: str
    sellerName: str
    price: float
    currency: str = "INR"
    url: str
    inStock: bool
    lastCheckedAt: str
    linkType: str = "search"   # "direct" | "search"

class SearchResponse(BaseModel):
    product: Optional[Product]
    listings: List[Listing]

# ────────────────────────────────────────────────────
# Fallback Local Dataset (loaded at startup)
# ────────────────────────────────────────────────────

_local_db: List[dict] = []

def _load_local_db():
    base = os.path.dirname(__file__)
    for fname, verified in [
        ("manual_seed_dataset.json", True),
        ("kaggle_seed_dataset_generated.json", False),
    ]:
        path = os.path.join(base, fname)
        if not os.path.exists(path):
            continue
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data.get("products", []):
                item["verified"] = verified
                _local_db.append(item)
            print(f"[startup] Loaded {len(data.get('products', []))} products from {fname}")
        except Exception as e:
            print(f"[startup] Could not load {fname}: {e}")

_load_local_db()

# ────────────────────────────────────────────────────
# SearchApi.io config
# ────────────────────────────────────────────────────

SEARCHAPI_KEY = "r7MunZoUvuNCepWGptEyjApy"
SEARCHAPI_URL = "https://www.searchapi.io/api/v1/search"

# Keyword → category mapping used when building the Product object from live results
_CATEGORY_RULES = [
    ({"headphone", "earbud", "earphone", "speaker", "soundbar", "audio", "buds"}, "Electronics / Audio"),
    ({"tv", "television", "qled", "oled", "monitor", "display"}, "Electronics / TV"),
    ({"laptop", "notebook", "macbook"}, "Electronics / Laptops"),
    ({"milk", "atta", "rice", "oil", "dal", "masala", "biscuit", "grocery",
      "chocolate", "snack", "beverage", "chai", "coffee"}, "Grocery & Essentials"),
    ({"watch", "smartwatch", "band", "fitness tracker"}, "Electronics / Wearables"),
    ({"camera", "dslr", "lens", "mirrorless"}, "Electronics / Cameras"),
]

def _infer_category(query: str) -> str:
    q = query.lower()
    for keywords, cat in _CATEGORY_RULES:
        if any(kw in q for kw in keywords):
            return cat
    return "Electronics / Mobiles"

def _extract_specs(title: str) -> Dict[str, str]:
    specs: Dict[str, str] = {}
    t = title.lower()
    for ram in ["4gb", "6gb", "8gb", "12gb", "16gb", "32gb", "4 gb", "6 gb", "8 gb"]:
        if ram in t:
            specs["RAM"] = ram.replace(" ", "").upper()
            break
    for storage in ["64gb", "128gb", "256gb", "512gb", "1tb", "2tb"]:
        if storage in t:
            specs["Storage"] = storage.upper()
            break
    return specs

# ────────────────────────────────────────────────────
# Local fallback search (token-scored)
# ────────────────────────────────────────────────────

def _local_search(query: str) -> SearchResponse:
    print(f"[fallback] Searching local DB for: '{query}'")
    tokens = query.lower().split()
    best, best_score = None, 0

    for item in _local_db:
        score = 0
        title = item.get("title", "").lower()
        brand = item.get("brand", "").lower()
        for tok in tokens:
            if tok in title:
                score += 2
            if tok in brand:
                score += 1
        if score > best_score:
            best_score = score
            best = item

    if best and best_score >= 2:
        product = Product(
            id=best["id"],
            title=best["title"],
            brand=best["brand"],
            category=best["category"],
            imageUrl=best["imageUrl"],
            verified=best.get("verified", False),
            specs=best.get("specs", {}),
        )
        listings = [
            Listing(
                id=l["id"],
                sellerName=l["sellerName"],
                price=float(l["price"]),
                currency=l.get("currency", "INR"),
                url=l["url"],
                inStock=l.get("inStock", True),
                lastCheckedAt=l["lastCheckedAt"],
                linkType=l.get("linkType", "search"),
            )
            for l in best.get("listings", [])
        ]
        return SearchResponse(product=product, listings=listings)

    return SearchResponse(product=None, listings=[])

# ────────────────────────────────────────────────────
# Main live search endpoint
# ────────────────────────────────────────────────────

def _parse_budget(query: str):
    """
    Detect budget constraint from query strings like:
      'phone under 15k', 'laptop below 50000', 'tv under 30k'
    Returns (clean_query, max_price_inr) or (query, None) if no budget found.
    """
    import re
    # Match patterns like "under 15k", "below 20000", "within 10k", "less than 30k"
    pattern = r'\b(?:under|below|within|less than|upto|up to)\s*(?:rs\.?|inr|₹)?\s*(\d+(?:\.\d+)?)\s*(k|thousand|lakh)?\b'
    m = re.search(pattern, query.lower())
    if m:
        value = float(m.group(1))
        unit = (m.group(2) or '').lower()
        if unit in ('k', 'thousand'):
            value *= 1000
        elif unit == 'lakh':
            value *= 100000
        clean = re.sub(pattern, '', query, flags=re.IGNORECASE).strip()
        clean = re.sub(r'\s+', ' ', clean).strip()
        return clean, int(value)
    return query, None


@app.get("/search", response_model=SearchResponse)
async def search(q: str = Query(..., description="Product search query")):
    query = q.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    # Parse budget hint from query (e.g. "phone under 15k" → max_price=15000)
    clean_query, max_price = _parse_budget(query)
    if not clean_query:
        clean_query = query

    print(f"[search] '{query}' → clean='{clean_query}' budget={max_price}")

    # ── 1. Try SearchApi.io Google Shopping (India) ──────────────────────────
    try:
        params: dict = {
            "engine": "google_shopping",
            "q": clean_query,
            "gl": "in",
            "hl": "en",
            "api_key": SEARCHAPI_KEY,
        }
        # Add Google Shopping price filter if budget detected
        if max_price:
            # tbs=mr:1,price:1,ppr_max:XXXXX  (max price in same currency as results)
            params["tbs"] = f"mr:1,price:1,ppr_max:{max_price}"

        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.get(SEARCHAPI_URL, params=params)

        if resp.status_code == 200:
            data = resp.json()
            results = data.get("shopping_results", [])
            if results:
                first = results[0]
                category = _infer_category(clean_query)
                specs = _extract_specs(first.get("title", ""))

                product = Product(
                    id=f"live_{first.get('product_id', 'unknown')}",
                    title=first.get("title", clean_query.title()),
                    brand=first.get("seller", "Various"),
                    category=category,
                    imageUrl=first.get("thumbnail", ""),
                    verified=True,
                    specs=specs,
                )

                listings: List[Listing] = []
                for i, item in enumerate(results):
                    price = item.get("extracted_price")
                    if not price:
                        continue
                    # Honour the budget filter: skip listings above max_price
                    if max_price and float(price) > max_price * 1.05:
                        continue
                    url = item.get("product_link") or item.get("offers_link") or ""
                    listings.append(
                        Listing(
                            id=f"live_{i}_{item.get('product_id', i)}",
                            sellerName=item.get("seller", "Seller"),
                            price=float(price),
                            currency="INR",
                            url=url,
                            inStock=True,
                            lastCheckedAt=datetime.utcnow().isoformat() + "Z",
                            linkType="direct",
                        )
                    )

                if listings:
                    print(f"[search] Live: {len(listings)} listings from Google Shopping")
                    return SearchResponse(product=product, listings=listings)
        else:
            print(f"[search] SearchApi returned {resp.status_code}: {resp.text[:200]}")

    except Exception as exc:
        print(f"[search] Live query error: {exc}")

    # ── 2. Fallback to local database ────────────────────────────────────────
    return _local_search(clean_query)



@app.get("/health")
async def health():
    return {"status": "ok", "db_products": len(_local_db)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=3050, reload=False)
