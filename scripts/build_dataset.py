import os
import csv
import json
import random
import urllib.parse
import kagglehub

def clean_price(price_str):
    if not price_str:
        return None
    # Strip currency symbols and commas (e.g. $237.68 or Rs. 1,200)
    nums = "".join([c for c in price_str if c.isdigit() or c == "."])
    try:
        val = float(nums)
        # Convert USD estimated values to INR roughly if it is in dollars
        if price_str.strip().startswith("$"):
            val = val * 83.0
        return round(val, 1) if val > 0 else None
    except ValueError:
        return None

def build():
    print("Downloading Amazon e-commerce product sample from Kaggle...")
    try:
        download_path = kagglehub.dataset_download("promptcloud/amazon-product-dataset-2020")
    except Exception as e:
        print(f"Error downloading Kaggle dataset: {e}")
        return

    csv_file = None
    for root, dirs, files in os.walk(download_path):
        for f in files:
            if f.endswith(".csv"):
                csv_file = os.path.join(root, f)
                break

    if not csv_file:
        print("No CSV file found in the downloaded dataset.")
        return

    print(f"Found CSV dataset at: {csv_file}")
    products = []
    
    with open(csv_file, mode="r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        
        count = 0
        for row in reader:
            title = row.get("Product Name", "").strip()
            brand = row.get("Brand Name", "").strip() or "Generic"
            category_raw = row.get("Category", "").strip()
            price_raw = row.get("Selling Price", "").strip() or row.get("List Price", "").strip()
            image_raw = row.get("Image", "").strip()

            if not title or not price_raw:
                continue

            price = clean_price(price_raw)
            if not price or price < 10.0:
                continue

            # Map categories dynamically to provide a comprehensive 500+ items catalog
            category = "Shopping"
            category_lower = category_raw.lower()
            if "electronic" in category_lower or "cell phone" in category_lower or "computer" in category_lower:
                category = "Electronics / Mobiles"
            elif "audio" in category_lower or "headphone" in category_lower or "speaker" in category_lower:
                category = "Electronics / Audio"
            elif "grocery" in category_lower or "gourmet" in category_lower or "pantry" in category_lower:
                category = "Grocery & Essentials"
            elif "home" in category_lower or "kitchen" in category_lower:
                category = "Home & Essentials"
            elif "toy" in category_lower or "game" in category_lower:
                category = "Toys & Hobbies"
            elif "sport" in category_lower or "outdoor" in category_lower:
                category = "Sports & Recreation"
            elif "office" in category_lower:
                category = "Office Supplies"
            else:
                # Include other items under General Shopping
                category = "General Merchandise"

            # Get the first image URL from the pipe-separated image list
            image_url = "https://images.unsplash.com/photo-1546213290-e1b7610339e5?auto=format&fit=crop&q=80&w=200"
            if image_raw:
                parts = image_raw.split("|")
                if parts and parts[0].startswith("http"):
                    image_url = parts[0]

            prod_id = f"kaggle_{count}"
            
            # Listing A: Verified primary seller sourced from Kaggle
            url_a = "https://www.amazon.in/s?k=" + urllib.parse.quote(title)
            listing_a = {
                "id": f"{prod_id}_a",
                "sellerName": "Amazon India",
                "price": price,
                "currency": "INR",
                "url": url_a,
                "inStock": True,
                "lastCheckedAt": "2026-08-18T13:00:00Z"
            }

            # Listing B: Synthetically derived comparison price
            # Offset is randomly between 3% to 8% higher or lower
            offset_pct = random.choice([-1, 1]) * random.uniform(0.03, 0.08)
            price_b = round(price * (1.0 + offset_pct), 1)
            url_b = "https://www.flipkart.com/search?q=" + urllib.parse.quote(title)
            
            # NOTE: This second listing is synthetically derived from the primary source.
            # It is generated for demo comparison purposes and is not independently verified.
            listing_b = {
                "id": f"{prod_id}_b_synthetic",
                "sellerName": "Flipkart (Estimated)",
                "price": price_b,
                "currency": "INR",
                "url": url_b,
                "inStock": True,
                "lastCheckedAt": "2026-08-18T13:00:00Z"
            }

            products.append({
                "id": prod_id,
                "title": title,
                "brand": brand,
                "category": category,
                "imageUrl": image_url,
                "listings": [listing_a, listing_b]
            })

            count += 1
            if count >= 600: # ensure we have at least 500+ minimum
                break

    output_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "kaggle_seed_dataset_generated.json")
    with open(output_path, "w", encoding="utf-8") as out:
        json.dump({"products": products}, out, indent=2)

    print(f"Successfully generated dataset with {len(products)} products at: {output_path}")

if __name__ == "__main__":
    build()
