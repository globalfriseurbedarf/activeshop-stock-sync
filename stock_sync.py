import os
import re
import time
import csv
import io
import sys
import math
import requests
import pandas as pd
from datetime import datetime
from typing import Dict, Any, Optional


# ==========================================================
# AYARLAR
# ==========================================================

FEED_URL = os.getenv(
    "FEED_URL",
    "https://b2b.activeshop.com.pl/media/productsfeed/b2b-de.csv"
)

SHOPIFY_SHOP = os.getenv("SHOPIFY_SHOP", "bzjwyw-jv.myshopify.com")
SHOPIFY_ACCESS_TOKEN = os.getenv("SHOPIFY_ACCESS_TOKEN")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2026-04")

# ActiveShop CSV kolonlari
# Stok kolonu ekran goruntusune gore: qty
FEED_SKU_COLUMN = os.getenv("FEED_SKU_COLUMN", "sku").strip()
FEED_STOCK_COLUMN = os.getenv("FEED_STOCK_COLUMN", "qty").strip()

# Shopify lokasyon ID bos birakilirsa ilk aktif lokasyon kullanilir.
SHOPIFY_LOCATION_ID = os.getenv("SHOPIFY_LOCATION_ID", "").strip()

# Ilk testte true kalsin. Gercek guncelleme icin GitHub workflow icinde false yapilacak.
DRY_RUN = os.getenv("DRY_RUN", "true").lower() == "true"

# Feed dosyasinda olmayan SKU'lar Shopify'da 0 yapilsin mi?
# Guvenli olmasi icin false.
SET_MISSING_SKU_TO_ZERO = os.getenv("SET_MISSING_SKU_TO_ZERO", "false").lower() == "true"

# Shopify istekleri arasinda bekleme
REQUEST_SLEEP = float(os.getenv("REQUEST_SLEEP", "0.35"))


# ==========================================================
# GENEL YARDIMCI FONKSIYONLAR
# ==========================================================

def log(message: str):
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}", flush=True)


def normalize_col_name(value: str) -> str:
    value = str(value).strip().lower()
    value = value.replace("ı", "i").replace("ğ", "g").replace("ü", "u")
    value = value.replace("ş", "s").replace("ö", "o").replace("ç", "c")
    value = value.replace("ä", "a").replace("ß", "ss")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def clean_sku(value: Any) -> str:
    if pd.isna(value):
        return ""

    sku = str(value).strip()

    # Excel bazen 12345.0 gibi okuyabilir
    if re.fullmatch(r"\d+\.0", sku):
        sku = sku[:-2]

    return sku


def parse_stock(value: Any) -> Optional[int]:
    if pd.isna(value):
        return None

    raw = str(value).strip().lower()

    if raw == "":
        return None

    # Feed bazen metin stok bilgisi gonderirse
    positive_words = [
        "in stock",
        "available",
        "auf lager",
        "lagernd",
        "verfügbar",
        "verfugbar",
        "yes",
        "ja",
        "true"
    ]

    negative_words = [
        "out of stock",
        "not available",
        "nicht verfügbar",
        "nicht verfugbar",
        "no",
        "nein",
        "false"
    ]

    if raw in positive_words:
        return 999

    if raw in negative_words:
        return 0

    cleaned = raw.replace(" ", "")

    # 1.234,00 veya 1,234.00 formatlarini temizle
    if "," in cleaned and "." in cleaned:
        if cleaned.rfind(",") > cleaned.rfind("."):
            cleaned = cleaned.replace(".", "").replace(",", ".")
        else:
            cleaned = cleaned.replace(",", "")
    elif "," in cleaned:
        cleaned = cleaned.replace(",", ".")

    match = re.search(r"-?\d+(\.\d+)?", cleaned)

    if not match:
        return None

    qty = float(match.group(0))

    if qty < 0:
        qty = 0

    return int(math.floor(qty))


def find_column(df: pd.DataFrame, wanted_col: str, label: str) -> str:
    """
    Kolon adini buyuk/kucuk harf farki olmadan bulur.
    Ornegin qty, QTY, Qty hepsi kabul edilir.
    """

    if not wanted_col:
        raise RuntimeError(f"{label} kolonu belirtilmedi.")

    normalized_wanted = normalize_col_name(wanted_col)

    for col in df.columns:
        if normalize_col_name(col) == normalized_wanted:
            return col

    raise RuntimeError(
        f"{label} kolonu bulunamadi: {wanted_col}\n"
        f"CSV kolonlari: {list(df.columns)}"
    )


# ==========================================================
# ACTVIESHOP CSV INDIRME VE OKUMA
# ==========================================================

def download_feed() -> pd.DataFrame:
    log(f"ActiveShop CSV indiriliyor: {FEED_URL}")

    response = requests.get(FEED_URL, timeout=120)
    response.raise_for_status()

    content = response.content

    text = None
    for encoding in ["utf-8-sig", "utf-8", "cp1250", "iso-8859-2", "latin1"]:
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue

    if text is None:
        raise RuntimeError("CSV kodlamasi okunamadi.")

    sample = text[:5000]

    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=";,|\t,")
        separator = dialect.delimiter
    except Exception:
        separator = ";"

    log(f"CSV ayirici: {repr(separator)}")

    df = pd.read_csv(
        io.StringIO(text),
        sep=separator,
        dtype=str,
        engine="python",
        keep_default_na=False
    )

    df.columns = [str(col).strip() for col in df.columns]

    log(f"CSV satir sayisi: {len(df)}")
    log(f"CSV kolonlari: {list(df.columns)}")

    return df


def build_feed_stock_map(df: pd.DataFrame) -> Dict[str, int]:
    sku_col = find_column(df, FEED_SKU_COLUMN, "SKU")
    stock_col = find_column(df, FEED_STOCK_COLUMN, "STOCK")

    log(f"Kullanilan ActiveShop SKU kolonu: {sku_col}")
    log(f"Kullanilan ActiveShop stok kolonu: {stock_col}")

    stock_map: Dict[str, int] = {}

    for _, row in df.iterrows():
        sku = clean_sku(row.get(sku_col))
        if not sku:
            continue

        qty = parse_stock(row.get(stock_col))
        if qty is None:
            continue

        # Ayni SKU feed icinde birden fazla varsa en yuksek stok alinir.
        if sku in stock_map:
            stock_map[sku] = max(stock_map[sku], qty)
        else:
            stock_map[sku] = qty

    log(f"Feed icinden okunan benzersiz SKU sayisi: {len(stock_map)}")

    return stock_map


# ==========================================================
# SHOPIFY REST API
# ==========================================================

def shopify_headers() -> Dict[str, str]:
    if not SHOPIFY_ACCESS_TOKEN:
        raise RuntimeError("SHOPIFY_ACCESS_TOKEN tanimli degil.")

    return {
        "X-Shopify-Access-Token": SHOPIFY_ACCESS_TOKEN,
        "Content-Type": "application/json",
    }


def shopify_get_url(url: str, params: Optional[dict] = None) -> requests.Response:
    while True:
        response = requests.get(
            url,
            headers=shopify_headers(),
            params=params,
            timeout=120
        )

        if response.status_code == 429:
            log("Shopify rate limit. 3 saniye bekleniyor...")
            time.sleep(3)
            continue

        if response.status_code >= 400:
            log(f"Shopify GET hata: {response.status_code}")
            log(response.text[:1000])

        response.raise_for_status()
        time.sleep(REQUEST_SLEEP)
        return response


def shopify_get(path: str, params: Optional[dict] = None) -> requests.Response:
    url = f"https://{SHOPIFY_SHOP}/admin/api/{SHOPIFY_API_VERSION}{path}"
    return shopify_get_url(url, params=params)


def shopify_post(path: str, payload: dict) -> requests.Response:
    url = f"https://{SHOPIFY_SHOP}/admin/api/{SHOPIFY_API_VERSION}{path}"

    while True:
        response = requests.post(
            url,
            headers=shopify_headers(),
            json=payload,
            timeout=120
        )

        if response.status_code == 429:
            log("Shopify rate limit. 3 saniye bekleniyor...")
            time.sleep(3)
            continue

        if response.status_code >= 400:
            log(f"Shopify POST hata: {response.status_code}")
            log(response.text[:1000])

        response.raise_for_status()
        time.sleep(REQUEST_SLEEP)
        return response


def get_next_link(response: requests.Response) -> Optional[str]:
    """
    Shopify pagination Link header icinden next URL alir.
    """

    link_header = response.headers.get("Link")

    if not link_header:
        return None

    links = link_header.split(",")

    for link in links:
        if 'rel="next"' in link:
            match = re.search(r"<([^>]+)>", link)
            if match:
                return match.group(1)

    return None


def get_location_id() -> int:
    if SHOPIFY_LOCATION_ID:
        log(f"Manuel Shopify Location ID kullaniliyor: {SHOPIFY_LOCATION_ID}")
        return int(SHOPIFY_LOCATION_ID)

    log("Shopify lokasyonlari cekiliyor...")

    response = shopify_get("/locations.json")
    locations = response.json().get("locations", [])

    if not locations:
        raise RuntimeError("Shopify lokasyonu bulunamadi.")

    active_locations = [loc for loc in locations if loc.get("active", True)]

    selected_location = active_locations[0] if active_locations else locations[0]

    log(
        f"Kullanilan Shopify lokasyonu: "
        f"{selected_location.get('name')} / ID: {selected_location.get('id')}"
    )

    return int(selected_location["id"])


def fetch_shopify_variants_by_sku() -> Dict[str, dict]:
    """
    Shopify urunlerini ceker.
    SKU -> variant bilgisi map olusturur.
    """

    log("Shopify urunleri ve varyantlari cekiliyor...")

    sku_map: Dict[str, dict] = {}

    url = f"https://{SHOPIFY_SHOP}/admin/api/{SHOPIFY_API_VERSION}/products.json"
    params = {
        "limit": 250,
        "fields": "id,title,variants"
    }

    page = 1

    while True:
        response = shopify_get_url(url, params=params)
        products = response.json().get("products", [])

        log(f"Shopify sayfa {page}: {len(products)} urun")

        for product in products:
            product_id = product.get("id")
            product_title = product.get("title", "")

            for variant in product.get("variants", []):
                sku = clean_sku(variant.get("sku"))

                if not sku:
                    continue

                if sku in sku_map:
                    log(f"UYARI: Shopify icinde ayni SKU birden fazla var: {sku}")

                sku_map[sku] = {
                    "product_id": product_id,
                    "product_title": product_title,
                    "variant_id": variant.get("id"),
                    "sku": sku,
                    "inventory_item_id": variant.get("inventory_item_id"),
                    "old_inventory_quantity": variant.get("inventory_quantity"),
                    "inventory_management": variant.get("inventory_management"),
                }

        next_url = get_next_link(response)

        if not next_url:
            break

        url = next_url
        params = None
        page += 1

    log(f"Shopify icinden okunan benzersiz SKU sayisi: {len(sku_map)}")

    return sku_map


def set_inventory_level(location_id: int, inventory_item_id: int, quantity: int):
    payload = {
        "location_id": location_id,
        "inventory_item_id": inventory_item_id,
        "available": quantity
    }

    if DRY_RUN:
        return

    shopify_post("/inventory_levels/set.json", payload)


# ==========================================================
# ANA ISLEM
# ==========================================================

def main():
    log("==============================================")
    log("ActiveShop -> Shopify stok senkronizasyonu basladi")
    log("==============================================")
    log(f"Shopify magaza: {SHOPIFY_SHOP}")
    log(f"Shopify API versiyon: {SHOPIFY_API_VERSION}")
    log(f"DRY_RUN: {DRY_RUN}")

    df = download_feed()
    feed_stock_map = build_feed_stock_map(df)

    location_id = get_location_id()
    shopify_sku_map = fetch_shopify_variants_by_sku()

    matched = 0
    updated = 0
    skipped_same = 0
    missing_in_shopify = 0
    skipped_no_inventory_item = 0
    skipped_tracking_off = 0
    errors = 0

    report_rows = []

    for sku, new_qty in feed_stock_map.items():
        variant = shopify_sku_map.get(sku)

        if not variant:
            missing_in_shopify += 1
            report_rows.append({
                "sku": sku,
                "status": "SHOPIFYDA_SKU_BULUNAMADI",
                "old_qty": "",
                "new_qty": new_qty,
                "product_title": ""
            })
            continue

        matched += 1

        inventory_item_id = variant.get("inventory_item_id")
        old_qty = variant.get("old_inventory_quantity")
        inventory_management = variant.get("inventory_management")

        if not inventory_item_id:
            skipped_no_inventory_item += 1
            report_rows.append({
                "sku": sku,
                "status": "INVENTORY_ITEM_ID_YOK",
                "old_qty": old_qty,
                "new_qty": new_qty,
                "product_title": variant.get("product_title", "")
            })
            continue

        if inventory_management != "shopify":
            skipped_tracking_off += 1
            report_rows.append({
                "sku": sku,
                "status": "SHOPIFY_STOK_TAKIBI_KAPALI",
                "old_qty": old_qty,
                "new_qty": new_qty,
                "product_title": variant.get("product_title", "")
            })
            continue

        if old_qty == new_qty:
            skipped_same += 1
            report_rows.append({
                "sku": sku,
                "status": "STOK_AYNI_ATLANDI",
                "old_qty": old_qty,
                "new_qty": new_qty,
                "product_title": variant.get("product_title", "")
            })
            continue

        try:
            log(
                f"Guncelleniyor | SKU: {sku} | "
                f"{old_qty} -> {new_qty} | "
                f"{variant.get('product_title')}"
            )

            set_inventory_level(
                location_id=location_id,
                inventory_item_id=int(inventory_item_id),
                quantity=int(new_qty)
            )

            updated += 1

            report_rows.append({
                "sku": sku,
                "status": "DRY_RUN_GUNCELLENECEK" if DRY_RUN else "GUNCELLENDI",
                "old_qty": old_qty,
                "new_qty": new_qty,
                "product_title": variant.get("product_title", "")
            })

        except Exception as error:
            errors += 1

            log(f"HATA | SKU: {sku} | {error}")

            report_rows.append({
                "sku": sku,
                "status": f"HATA: {error}",
                "old_qty": old_qty,
                "new_qty": new_qty,
                "product_title": variant.get("product_title", "")
            })

    if SET_MISSING_SKU_TO_ZERO:
        log("Feed icinde olmayan Shopify SKU'lari 0 yapilacak.")

        for sku, variant in shopify_sku_map.items():
            if sku in feed_stock_map:
                continue

            inventory_item_id = variant.get("inventory_item_id")
            inventory_management = variant.get("inventory_management")
            old_qty = variant.get("old_inventory_quantity")

            if not inventory_item_id:
                continue

            if inventory_management != "shopify":
                continue

            if old_qty == 0:
                continue

            try:
                log(
                    f"Feedde yok, 0 yapiliyor | SKU: {sku} | "
                    f"{old_qty} -> 0 | {variant.get('product_title')}"
                )

                set_inventory_level(
                    location_id=location_id,
                    inventory_item_id=int(inventory_item_id),
                    quantity=0
                )

                updated += 1

            except Exception as error:
                errors += 1
                log(f"HATA | Feedde olmayan SKU sifirlama | SKU: {sku} | {error}")

    report_file = "stock_sync_report.csv"

    pd.DataFrame(report_rows).to_csv(
        report_file,
        index=False,
        encoding="utf-8-sig"
    )

    log("==============================================")
    log("ISLEM OZETI")
    log("==============================================")
    log(f"Feed SKU sayisi: {len(feed_stock_map)}")
    log(f"Shopify SKU sayisi: {len(shopify_sku_map)}")
    log(f"Eslesen SKU: {matched}")
    log(f"Guncellenen stok: {updated}")
    log(f"Stok ayni oldugu icin atlanan: {skipped_same}")
    log(f"Shopify'da bulunamayan SKU: {missing_in_shopify}")
    log(f"Inventory item olmayan: {skipped_no_inventory_item}")
    log(f"Shopify stok takibi kapali olan: {skipped_tracking_off}")
    log(f"Hata: {errors}")
    log(f"Rapor dosyasi: {report_file}")
    log("==============================================")

    if errors > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
