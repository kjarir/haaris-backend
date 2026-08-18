import os
import json
from typing import List, Optional, Dict
from datetime import datetime
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig
from crawl4ai.extraction_strategy import JsonCssExtractionStrategy

app = FastAPI(title="Smart Price Aggregator Static Dataset Backend")

# Enable CORS for Flutter Client
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Product(BaseModel):
    id: str
    title: str
    brand: str
    category: str
    imageUrl: str
    verified: bool  # Displays whether the product is hand-verified or bulk-generated
    specs: Optional[Dict[str, str]] = None  # Key-value maps for product specifications

class Listing(BaseModel):
    id: str
    sellerName: str
    price: float
    currency: str = "INR"
    url: str
    inStock: bool
    lastCheckedAt: str
    linkType: str = "search"  # "direct" or "search"

class SearchResponse(BaseModel):
    product: Optional[Product]
    listings: List[Listing]

# Merged Database Store (Fallback database)
merged_database = []

# Load Hand-Curated Verified Dataset
MANUAL_PATH = os.path.join(os.path.dirname(__file__), "manual_seed_dataset.json")
try:
    with open(MANUAL_PATH, "r") as f:
        manual_data = json.load(f)
        for item in manual_data.get("products", []):
            item["verified"] = True
            merged_database.append(item)
    print(f"Loaded {len(manual_data.get('products', []))} hand-verified products.")
except Exception as e:
    print(f"Error loading manual verified dataset: {e}")

# Load Bulk Kaggle Generated Dataset
KAGGLE_PATH = os.path.join(os.path.dirname(__file__), "kaggle_seed_dataset_generated.json")
try:
    if os.path.exists(KAGGLE_PATH):
        with open(KAGGLE_PATH, "r") as f:
            kaggle_data = json.load(f)
            for item in kaggle_data.get("products", []):
                item["verified"] = False
                merged_database.append(item)
        print(f"Loaded {len(kaggle_data.get('products', []))} bulk generated products.")
    else:
        print("Generated Kaggle dataset file not found. Run scripts/build_dataset.py first.")
except Exception as e:
    print(f"Error loading generated Kaggle dataset: {e}")

# SearchApi.io Config
SEARCHAPI_KEY = "r7MunZoUvuNCepWGptEyjApy"
SEARCHAPI_URL = "https://www.searchapi.io/api/v1/search"

# Crawl4AI Configuration for Background Crawls (Bonus / Reference)
product_schema = {
    "name": "E-Commerce Product details",
    "baseSelector": "body",
    "fields": [
        {"name": "title", "selector": "h1", "type": "text"},
        {"name": "price", "selector": ".a-price-whole, ._30jeq3", "type": "text"},
        {"name": "in_stock", "selector": "#availability", "type": "text"}
    ]
}

browser_config = BrowserConfig(
    headless=True,
    ignore_https_errors=True
)

crawler_run_config = CrawlerRunConfig(
    extraction_strategy=JsonCssExtractionStrategy(schema=product_schema),
    word_count_threshold=10,
    always_by_pass_cache=True
)

async def background_crawl_job(target_url: str):
    """
    Scheduled background crawler task using Crawl4AI JsonCssExtractionStrategy.
    """
    print(f"Starting scheduled crawl on: {target_url}")
    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=target_url, config=crawler_run_config)
        if result.success:
            print("Extracted Data:", result.extracted_content)
            return result.extracted_content
    return None

def fallback_local_search(query: str) -> SearchResponse:
    print(f"Falling back to local dataset query match for: '{query}'")
    best_match = None
    highest_score = 0
    query_tokens = set(query.split())

    for item in merged_database:
        title_lower = item["title"].lower()
        brand_lower = item["brand"].lower()
        id_lower = item["id"].lower()

        score = 0
        for token in query_tokens:
            if token in title_lower:
                score += 2
            if token in brand_lower:
                score += 1
            if token in id_lower:
                score += 2

        if score > highest_score:
            highest_score = score
            best_match = item

    if best_match and highest_score >= 2:
        product = Product(
            id=best_match["id"],
            title=best_match["title"],
            brand=best_match["brand"],
            category=best_match["category"],
            imageUrl=best_match["imageUrl"],
            verified=best_match["verified"],
            specs=best_match.get("specs", {})
        )
        listings = [
            Listing(
                id=l["id"],
                sellerName=l["sellerName"],
                price=l["price"],
                currency=l["currency"],
                url=l["url"],
                inStock=l["inStock"],
                lastCheckedAt=l["lastCheckedAt"],
                linkType=l.get("linkType", "search")
            ) for l in best_match.get("listings", [])
        ]
        return SearchResponse(product=product, listings=listings)

    return SearchResponse(product=None, listings=[])

@app.get("/search", response_model=SearchResponse)
async def search_dataset(q: str = Query(..., description="Product query to search")):
    query = q.strip().lower()
    print(f"Received live shopping search request: '{query}'")

    if not query:
        raise HTTPException(status_code=400, detail="Search query is required")

    # Try Live SearchApi.io Shopping Query first
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            params = {
                "engine": "google_shopping",
                "q": query,
                "gl": "in",
                "hl": "en",
                "api_key": SEARCHAPI_KEY
            }
            response = await client.get(SEARCHAPI_URL, params=params)
            
            if response.status_code == 200:
                data = response.json()
                shopping_results = data.get("shopping_results", [])
                
                if shopping_results:
                    first_item = shopping_results[0]
                    # Guess category dynamically based on search keywords
                    category = "Electronics / Mobiles"
                    if "headphone" in query or "earbud" in query or "audio" in query:
                        category = "Electronics / Audio"
                    elif "tv" in query or "television" in query:
                        category = "Electronics / TV"
                    elif "milk" in query or "atta" in query or "oil" in query or "chocolate" in query or "grocery" in query:
                        category = "Grocery & Essentials"

                    # Generate spec tags based on title if possible
                    specs = {}
                    title_lower = first_item.get("title", "").lower()
                    for ram_val in ["4gb", "8gb", "12gb", "16gb", "32gb"]:
                        if ram_val in title_lower:
                            specs["RAM"] = ram_val.upper()
                            break
                    for storage_val in ["64gb", "128gb", "256gb", "512gb", "1tb"]:
                        if storage_val in title_lower:
                            specs["Storage"] = storage_val.upper()
                            break

                    product = Product(
                        id=f"live_{first_item.get('product_id', 'id')}",
                        title=first_item.get("title", query.title()),
                        brand=first_item.get("seller", "Generic"),
                        category=category,
                        imageUrl=first_item.get("thumbnail", ""),
                        verified=True, # Sourced in real-time from active Google index!
                        specs=specs
                    )

                    listings = []
                    for index, item in enumerate(shopping_results):
                        extracted_price = item.get("extracted_price")
                        if not extracted_price:
                            continue
                        
                        listings.append(Listing(
                            id=f"live_offer_{index}_{item.get('product_id', '')}",
                            sellerName=item.get("seller", "Google Shopping Seller"),
                            price=float(extracted_price),
                            currency="INR",
                            url=item.get("product_link") or item.get("offers_link") or "",
                            inStock=True,
                            lastCheckedAt=datetime.now().isoformat(),
                            linkType="direct" # Leads directly to specific product page
                        ))
                    
                    if listings:
                        print(f"Successfully returned {len(listings)} live shopping listings from Google.")
                        return SearchResponse(product=product, listings=listings)

    except Exception as e:
        print(f"Live SearchApi query failed: {e}")

    # Fallback to local database
    return fallback_local_search(query)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=3050, reload=True)
