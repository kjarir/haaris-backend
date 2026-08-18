import os
import json
from typing import List, Optional
from datetime import datetime
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
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

class Listing(BaseModel):
    id: str
    sellerName: str
    price: float
    currency: str = "INR"
    url: str
    inStock: bool
    lastCheckedAt: str

class SearchResponse(BaseModel):
    product: Optional[Product]
    listings: List[Listing]

# Load Static Kaggle Dataset
DATASET_PATH = os.path.join(os.path.dirname(__file__), "kaggle_seeded_dataset.json")
try:
    with open(DATASET_PATH, "r") as f:
        database = json.load(f)
except Exception as e:
    print(f"Error loading local Kaggle dataset: {e}")
    database = {"products": []}

# Crawl4AI Configuration for Background Crawls (Bonus / Reference)
# Using JsonCssExtractionStrategy for structured page extraction
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

@app.get("/search", response_model=SearchResponse)
async def search_dataset(q: str = Query(..., description="Product query to search")):
    query = q.strip().lower()
    print(f"Processing database lookup search for: '{query}'")

    if not query:
        raise HTTPException(status_code=400, detail="Search query is required")

    best_match = None
    highest_score = 0

    # Clean query to extract matchable tokens
    query_tokens = set(query.split())

    for item in database.get("products", []):
        title_lower = item["title"].lower()
        brand_lower = item["brand"].lower()
        id_lower = item["id"].lower()

        # Simple overlap scoring
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

    # Threshold for matching to prevent arbitrary incorrect query bindings
    if best_match and highest_score >= 2:
        print(f"Match found in static Kaggle dataset: {best_match['title']}")
        product = Product(
            id=best_match["id"],
            title=best_match["title"],
            brand=best_match["brand"],
            category=best_match["category"],
            imageUrl=best_match["imageUrl"]
        )
        listings = [
            Listing(
                id=l["id"],
                sellerName=l["sellerName"],
                price=l["price"],
                currency=l["currency"],
                url=l["url"],
                inStock=l["inStock"],
                lastCheckedAt=l["lastCheckedAt"]
            ) for l in best_match.get("listings", [])
        ]
        return SearchResponse(product=product, listings=listings)

    print("No matching product found in Kaggle dataset. Returning empty state.")
    return SearchResponse(product=None, listings=[])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=3050, reload=True)
