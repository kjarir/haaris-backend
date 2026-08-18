import os
import csv
import json
import random
import urllib.parse
import kagglehub

# Approximate exchange rate from EUR to INR (not live FX)
EUR_TO_INR = 90.0

def clean_price(price_str):
    if not price_str:
        return None
    # Strip symbols and commas
    nums = "".join([c for c in price_str if c.isdigit() or c == "."])
    try:
        val = float(nums)
        return round(val, 1) if val > 0 else None
    except ValueError:
        return None

def parse_smartphones(download_path, limit=200):
    print("Parsing Smartphones Dataset...")
    csv_file = None
    for root, dirs, files in os.walk(download_path):
        for f in files:
            if f.endswith("smartphones.csv"):
                csv_file = os.path.join(root, f)
                break

    if not csv_file:
        print("smartphones.csv not found.")
        return []

    products = []
    count = 0
    with open(csv_file, mode="r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get("Smartphone", "").strip()
            brand = row.get("Brand", "").strip()
            model = row.get("Model", "").strip()
            price_raw = row.get("Final Price", "").strip()

            # Spec Columns
            ram = row.get("RAM", "").strip()
            storage = row.get("Storage", "").strip()
            color = row.get("Color", "").strip()

            if not title or title.lower() == "generic":
                title = f"{brand} {model}".strip()

            if not title or not price_raw:
                continue

            eur_price = clean_price(price_raw)
            if not eur_price or eur_price <= 0:
                continue

            # Convert EUR to INR using approximate exchange rate
            price_inr = round(eur_price * EUR_TO_INR, 1)
            prod_id = f"phone_{count}"

            # Listing A: Sourced from smartphones dataset (search-query style)
            url_a = "https://www.amazon.in/s?k=" + urllib.parse.quote(title)
            listing_a = {
                "id": f"{prod_id}_a",
                "sellerName": "Retailer A (EUR Match)",
                "price": price_inr,
                "currency": "INR",
                "url": url_a,
                "inStock": True,
                "lastCheckedAt": "2026-08-18T13:00:00Z",
                "linkType": "search"
            }

            # Listing B: Synthetically derived comparison price (search-query style)
            offset_pct = random.choice([-1, 1]) * random.uniform(0.03, 0.08)
            price_b = round(price_inr * (1.0 + offset_pct), 1)
            url_b = "https://www.flipkart.com/search?q=" + urllib.parse.quote(title)
            
            # NOTE: This second listing's price is synthetically derived from Listing A.
            # It is not independently verified and is generated for demo comparison purposes.
            listing_b = {
                "id": f"{prod_id}_b_synthetic",
                "sellerName": "Flipkart (Estimated)",
                "price": price_b,
                "currency": "INR",
                "url": url_b,
                "inStock": True,
                "lastCheckedAt": "2026-08-18T13:00:00Z",
                "linkType": "search"
            }

            # Build spec map
            specs = {}
            if ram: specs["RAM"] = ram
            if storage: specs["Storage"] = storage
            if color: specs["Color"] = color

            products.append({
                "id": prod_id,
                "title": title,
                "brand": brand or "Generic",
                "category": "Electronics / Mobiles",
                "imageUrl": "https://images.unsplash.com/photo-1510557880182-3d4d3cba35a5?auto=format&fit=crop&q=80&w=200",
                "listings": [listing_a, listing_b],
                "specs": specs
            })

            count += 1
            if count >= limit:
                break

    return products

def parse_amazon_electronics(download_path):
    print("Parsing and balancing Amazon Electronics Dataset...")
    csv_file = None
    for root, dirs, files in os.walk(download_path):
        for f in files:
            if f.endswith("electronics_product.csv"):
                csv_file = os.path.join(root, f)
                break

    if not csv_file:
        print("electronics_product.csv not found.")
        return []

    laptops = []
    audio = []
    tvs = []
    others = []

    with open(csv_file, mode="r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get("name", "").strip()
            image_url = row.get("image", "").strip()
            link = row.get("link", "").strip()
            price_raw = row.get("discount_price", "").strip() or row.get("actual_price", "").strip()

            if not title or not price_raw:
                continue

            price = clean_price(price_raw)
            if not price or price <= 0:
                continue

            title_lower = title.lower()

            # 1. Real Laptop Computers
            if "laptop" in title_lower and price > 15000:
                if len(laptops) < 50:
                    laptops.append((title, "Electronics / Mobiles", price, image_url, link))
            
            # 2. Smart TVs (Check before generic audio mapping)
            elif "tv" in title_lower or "television" in title_lower or "led tv" in title_lower:
                if len(tvs) < 50:
                    tvs.append((title, "Electronics / TV", price, image_url, link))

            # 3. Audio Products
            elif "headphone" in title_lower or "earbud" in title_lower or "earphone" in title_lower or "speaker" in title_lower or "soundbar" in title_lower or "audio" in title_lower or "buds" in title_lower or "airdopes" in title_lower:
                if len(audio) < 100:
                    audio.append((title, "Electronics / Audio", price, image_url, link))

            # 4. Other Electronics
            else:
                if len(others) < 100:
                    others.append((title, "Electronics / Other", price, image_url, link))

    print(f"Acquired balanced subsets - Laptops: {len(laptops)}, Audio: {len(audio)}, TVs: {len(tvs)}, Others: {len(others)}")

    products = []
    count = 0
    for title, cat, price, img, link in (laptops + audio + tvs + others):
        prod_id = f"elec_{count}"

        # Listing A: Sourced direct link from Amazon (direct type)
        listing_a = {
            "id": f"{prod_id}_a",
            "sellerName": "Amazon India",
            "price": price,
            "currency": "INR",
            "url": link,
            "inStock": True,
            "lastCheckedAt": "2026-08-18T13:00:00Z",
            "linkType": "direct"
        }

        # Listing B: Synthetically derived comparison price (search type)
        offset_pct = random.choice([-1, 1]) * random.uniform(0.03, 0.08)
        price_b = round(price * (1.0 + offset_pct), 1)
        url_b = "https://www.flipkart.com/search?q=" + urllib.parse.quote(title)
        
        # NOTE: This second listing's price is synthetically derived from Listing A.
        # It is not independently verified and is generated for demo comparison purposes.
        listing_b = {
            "id": f"{prod_id}_b_synthetic",
            "sellerName": "Flipkart (Estimated)",
            "price": price_b,
            "currency": "INR",
            "url": url_b,
            "inStock": True,
            "lastCheckedAt": "2026-08-18T13:00:00Z",
            "linkType": "search"
        }

        # Attempt to parse specs for Laptops (RAM/Storage/Processor keywords in title)
        specs = {}
        if "laptop" in title.lower():
            title_lower = title.lower()
            # simple keyword matching
            for ram_val in ["4gb", "8gb", "16gb", "32gb", "4 gb", "8 gb", "16 gb", "32 gb"]:
                if ram_val in title_lower:
                    specs["RAM"] = ram_val.upper().replace(" ", "")
                    break
            for ssd_val in ["128gb", "256gb", "512gb", "1tb", "1 tb", "2tb", "2 tb", "ssd"]:
                if ssd_val in title_lower:
                    specs["Storage"] = ssd_val.upper().replace(" ", "")
                    break

        products.append({
            "id": prod_id,
            "title": title,
            "brand": "Generic",
            "category": cat,
            "imageUrl": img or "https://images.unsplash.com/photo-1546435770-a3e426bf472b?auto=format&fit=crop&q=80&w=200",
            "listings": [listing_a, listing_b],
            "specs": specs
        })
        count += 1

    return products

def parse_bigbasket(download_path, limit=150):
    print("Parsing BigBasket Grocery Dataset...")
    csv_file = None
    for root, dirs, files in os.walk(download_path):
        for f in files:
            if f.endswith("BigBasket Products.csv"):
                csv_file = os.path.join(root, f)
                break

    if not csv_file:
        print("BigBasket Products.csv not found.")
        return []

    # Valid food categories to enforce coverage of real grocery staples
    food_categories = {
        "snacks & branded foods",
        "foodgrains, oil & masala",
        "bakery, cakes & dairy",
        "beverages"
    }

    products = []
    count = 0
    with open(csv_file, mode="r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for row in reader:
            title = row.get("product", "").strip()
            brand = row.get("brand", "Generic").strip()
            cat_raw = row.get("category", "").strip().lower()
            sale_price_raw = row.get("sale_price", "").strip()
            market_price_raw = row.get("market_price", "").strip()

            if not title or not sale_price_raw or not market_price_raw:
                continue

            # Enforce food category filter
            if cat_raw not in food_categories:
                continue

            sale_price = clean_price(sale_price_raw)
            market_price = clean_price(market_price_raw)

            if not sale_price or not market_price:
                continue

            # Skip bad/erroneous rows
            if sale_price > market_price:
                continue

            prod_id = f"grocery_{count}"
            url_bb = "https://www.bigbasket.com/ps/?q=" + urllib.parse.quote(title)

            # Generate two real listings representing the retailer's own discounted vs MRP prices
            # Both point to search query pages on BigBasket, so linkType is search
            listing_bb = {
                "id": f"{prod_id}_sale",
                "sellerName": "BigBasket",
                "price": sale_price,
                "currency": "INR",
                "url": url_bb,
                "inStock": True,
                "lastCheckedAt": "2026-08-18T13:00:00Z",
                "linkType": "search"
            }

            listing_mrp = {
                "id": f"{prod_id}_mrp",
                "sellerName": "BigBasket (MRP/List)",
                "price": market_price,
                "currency": "INR",
                "url": url_bb,
                "inStock": True,
                "lastCheckedAt": "2026-08-18T13:00:00Z",
                "linkType": "search"
            }

            products.append({
                "id": prod_id,
                "title": title,
                "brand": brand,
                "category": "Grocery & Essentials",
                "imageUrl": "https://images.unsplash.com/photo-1542838132-92c53300491e?auto=format&fit=crop&q=80&w=200",
                "listings": [listing_bb, listing_mrp],
                "specs": {}
            })

            count += 1
            if count >= limit:
                break

    return products

def build():
    try:
        # Download datasets
        path_phones = kagglehub.dataset_download("juanmerinobermejo/smartphones-price-dataset")
        path_elec = kagglehub.dataset_download("akeshkumarhp/electronics-products-amazon-10k-items")
        path_grocery = kagglehub.dataset_download("surajjha101/bigbasket-entire-product-list-28k-datapoints")

        phones = parse_smartphones(path_phones, limit=200)
        elec = parse_amazon_electronics(path_elec)
        grocery = parse_bigbasket(path_grocery, limit=150)

        all_products = phones + elec + grocery

        output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "kaggle_seed_dataset_generated.json")
        with open(output_path, "w", encoding="utf-8") as out:
            json.dump({"products": all_products}, out, indent=2)

        print(f"\nSuccessfully created merged dataset at: {output_path}")
        print(f"Total Phones: {len(phones)}")
        print(f"Total Electronics: {len(elec)}")
        print(f"Total Groceries: {len(grocery)}")
        print(f"Total Combined Products: {len(all_products)}")

    except Exception as e:
        print(f"Error building unified dataset: {e}")

if __name__ == "__main__":
    build()
