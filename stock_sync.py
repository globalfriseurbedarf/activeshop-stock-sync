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
from typing import Dict, Any, Optional, List, Tuple


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
FEED_SKU_COLUMN = os.getenv("FEED_SKU_COLUMN", "sku").strip()
FEED_STOCK_COLUMN = os.getenv("FEED_STOCK_COLUMN", "qty").strip()

# Dogru depo: Lager in Wroclaw
# Bu ID senin verdigin lokasyon ID'sidir.
SHOPIFY_LOCATION_ID = os.getenv("SHOPIFY_LOCATION_ID", "119279812950").strip()

# Yanlis lokasyonlarda kalan stoklari 0 yap.
ZERO_OTHER_LOCATIONS = os.getenv("ZERO_OTHER_LOCATIONS", "true").lower() == "true"

# True ise Shopify'a yazmaz, sadece raporlar.
DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# Feed dosyasinda olmayan Shopify SKU'lari 0 yapilsin mi?
# Guvenli olmasi icin false.
SET_MISSING_SKU_TO_ZERO = os.getenv("SET_MISSING_SKU_TO_ZERO", "false").lower() == "true"

# Shopify istekleri arasinda bekleme
REQUEST_SLEEP = float(os.getenv("REQUEST_SLEEP", "0.25"))

# Inventory level endpointinde tek istekte kac inventory item sorgulansin
INVENTORY_LEVEL_BATCH_SIZE = int(os.getenv("INVENTORY_LEVEL_BATCH_SIZE", "50"))


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

    positive_words = [
        "in stock", "available", "auf lager", "lagernd",
        "verfügbar", "verfugbar", "yes", "ja", "true"
    ]

    negative_words = [
        "out of stock", "not available", "nicht verfügbar",
        "nicht verfugbar", "no", "nein", "false"
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


def chunk_list(values: List[int], size: int) -> List[List[int]]:
    return [values[i:i + size] for i in range(0, len(values), size)]


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


def get_all_locations() -> List[dict]:
    log("Shopify lokasyonlari cekiliyor...")
    response = shopify_get("/locations.json")
    locations = response.json().get("locations", [])

    active_locations = [loc for loc in locations if loc.get("active", True)]

    log("Shopify aktif lokasyon listesi:")
    for loc in active_locations:
        log(f"- {loc.get('name')} / ID: {loc.get('id')}")

    if not active_locations:
        raise RuntimeError("Aktif Shopify lokasyonu bulunamadi.")

    return active_locations


def get_selected_location_id(active_locations: List[dict]) -> int:
    if SHOPIFY_LOCATION_ID:
        selected_id = int(SHOPIFY_LOCATION_ID)
        found = any(int(loc["id"]) == selected_id for loc in active_locations)

        if not found:
            raise RuntimeError(
                f"Verilen SHOPIFY_LOCATION_ID aktif lokasyonlar arasinda bulunamadi: {selected_id}"
            )

        selected_location = next(loc for loc in active_locations if int(loc["id"]) == selected_id)
        log(
            f"Kullanilan Shopify lokasyonu: "
            f"{selected_location.get('name')} / ID: {selected_location.get('id')}"
        )
        return selected_id

    selected_location = active_locations[0]
    log(
        f"SHOPIFY_LOCATION_ID bos oldugu icin ilk lokasyon kullaniliyor: "
        f"{selected_location.get('name')} / ID: {selected_location.get('id')}"
    )
    return int(selected_location["id"])


def fetch_shopify_variants_by_sku() -> Dict[str, List[dict]]:
    """
    Shopify urunlerini ceker.
    SKU -> variant listesi map olusturur.
    Ayni SKU birden fazla varyantta varsa hepsi guncellenir.
    """

    log("Shopify urunleri ve varyantlari cekiliyor...")

    sku_map: Dict[str, List[dict]] = {}

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

                variant_data = {
                    "product_id": product_id,
                    "product_title": product_title,
                    "variant_id": variant.get("id"),
                    "sku": sku,
                    "inventory_item_id": variant.get("inventory_item_id"),
                    "inventory_management": variant.get("inventory_management"),
                }

                sku_map.setdefault(sku, []).append(variant_data)

        next_url = get_next_link(response)

        if not next_url:
            break

        url = next_url
        params = None
        page += 1

    duplicate_skus = {sku: variants for sku, variants in sku_map.items() if len(variants) > 1}
    for sku, variants in duplicate_skus.items():
        log(f"UYARI: Shopify icinde ayni SKU birden fazla var: {sku} / adet: {len(variants)}")

    log(f"Shopify icinden okunan benzersiz SKU sayisi: {len(sku_map)}")
    log(f"Shopify toplam varyant SKU kaydi: {sum(len(v) for v in sku_map.values())}")

    return sku_map


def fetch_inventory_levels(
    inventory_item_ids: List[int],
    location_ids: List[int]
) -> Dict[Tuple[int, int], Optional[int]]:
    """
    Inventory item + location bazinda mevcut stoklari ceker.
    Sonuc: {(inventory_item_id, location_id): available}
    """

    unique_inventory_item_ids = sorted(set(int(x) for x in inventory_item_ids if x))
    unique_location_ids = sorted(set(int(x) for x in location_ids if x))

    levels: Dict[Tuple[int, int], Optional[int]] = {}

    if not unique_inventory_item_ids or not unique_location_ids:
        return levels

    batches = chunk_list(unique_inventory_item_ids, INVENTORY_LEVEL_BATCH_SIZE)

    log(
        f"Inventory levels cekiliyor: "
        f"{len(unique_inventory_item_ids)} inventory item, "
        f"{len(unique_location_ids)} lokasyon, "
        f"{len(batches)} paket"
    )

    for index, batch in enumerate(batches, start=1):
        params = {
            "inventory_item_ids": ",".join(str(x) for x in batch),
            "location_ids": ",".join(str(x) for x in unique_location_ids),
            "limit": 250
        }

        response = shopify_get("/inventory_levels.json", params=params)
        inventory_levels = response.json().get("inventory_levels", [])

        for level in inventory_levels:
            inventory_item_id = int(level["inventory_item_id"])
            location_id = int(level["location_id"])
            available = level.get("available")
            levels[(inventory_item_id, location_id)] = available

        if index % 10 == 0 or index == len(batches):
            log(f"Inventory level paketi: {index}/{len(batches)}")

    log(f"Okunan inventory level kaydi: {len(levels)}")

    return levels


def set_inventory_level(location_id: int, inventory_item_id: int, quantity: int):
    payload = {
        "location_id": int(location_id),
        "inventory_item_id": int(inventory_item_id),
        "available": int(quantity)
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
    log(f"ZERO_OTHER_LOCATIONS: {ZERO_OTHER_LOCATIONS}")
    log(f"SHOPIFY_LOCATION_ID: {SHOPIFY_LOCATION_ID}")

    df = download_feed()
    feed_stock_map = build_feed_stock_map(df)

    active_locations = get_all_locations()
    selected_location_id = get_selected_location_id(active_locations)
    active_location_ids = [int(loc["id"]) for loc in active_locations]
    other_location_ids = [loc_id for loc_id in active_location_ids if loc_id != selected_location_id]

    if ZERO_OTHER_LOCATIONS:
        log(f"Diger lokasyonlar 0 yapilacak: {other_location_ids}")
    else:
        log("Diger lokasyonlar oldugu gibi birakilacak.")

    shopify_sku_map = fetch_shopify_variants_by_sku()

    # Eslesen tum inventory_item_id degerlerini topla.
    matched_inventory_item_ids: List[int] = []
    for sku in feed_stock_map.keys():
        variants = shopify_sku_map.get(sku, [])
        for variant in variants:
            inventory_item_id = variant.get("inventory_item_id")
            if inventory_item_id:
                matched_inventory_item_ids.append(int(inventory_item_id))

    locations_to_check = [selected_location_id]
    if ZERO_OTHER_LOCATIONS:
        locations_to_check += other_location_ids

    inventory_levels = fetch_inventory_levels(
        inventory_item_ids=matched_inventory_item_ids,
        location_ids=locations_to_check
    )

    matched_sku_count = 0
    matched_variant_count = 0
    changed_variant_count = 0
    selected_location_updates = 0
    other_location_zero_updates = 0
    skipped_same = 0
    missing_in_shopify = 0
    skipped_no_inventory_item = 0
    skipped_tracking_off = 0
    errors = 0

    report_rows = []

    for sku, new_qty in feed_stock_map.items():
        variants = shopify_sku_map.get(sku, [])

        if not variants:
            missing_in_shopify += 1
            report_rows.append({
                "sku": sku,
                "status": "SHOPIFYDA_SKU_BULUNAMADI",
                "selected_location_id": selected_location_id,
                "selected_old_qty": "",
                "new_qty": new_qty,
                "other_locations_old_qty": "",
                "product_title": "",
                "variant_id": "",
                "inventory_item_id": ""
            })
            continue

        matched_sku_count += 1

        for variant in variants:
            matched_variant_count += 1

            inventory_item_id = variant.get("inventory_item_id")
            inventory_management = variant.get("inventory_management")

            if not inventory_item_id:
                skipped_no_inventory_item += 1
                report_rows.append({
                    "sku": sku,
                    "status": "INVENTORY_ITEM_ID_YOK",
                    "selected_location_id": selected_location_id,
                    "selected_old_qty": "",
                    "new_qty": new_qty,
                    "other_locations_old_qty": "",
                    "product_title": variant.get("product_title", ""),
                    "variant_id": variant.get("variant_id", ""),
                    "inventory_item_id": ""
                })
                continue

            inventory_item_id = int(inventory_item_id)

            if inventory_management != "shopify":
                skipped_tracking_off += 1
                report_rows.append({
                    "sku": sku,
                    "status": "SHOPIFY_STOK_TAKIBI_KAPALI",
                    "selected_location_id": selected_location_id,
                    "selected_old_qty": inventory_levels.get((inventory_item_id, selected_location_id)),
                    "new_qty": new_qty,
                    "other_locations_old_qty": "",
                    "product_title": variant.get("product_title", ""),
                    "variant_id": variant.get("variant_id", ""),
                    "inventory_item_id": inventory_item_id
                })
                continue

            selected_old_qty = inventory_levels.get((inventory_item_id, selected_location_id))

            other_old_qty_map = {
                loc_id: inventory_levels.get((inventory_item_id, loc_id))
                for loc_id in other_location_ids
            }

            need_selected_update = selected_old_qty != new_qty
            need_other_zero = False

            if ZERO_OTHER_LOCATIONS:
                for loc_id, old_value in other_old_qty_map.items():
                    if old_value not in (None, 0):
                        need_other_zero = True
                        break

            if not need_selected_update and not need_other_zero:
                skipped_same += 1
                report_rows.append({
                    "sku": sku,
                    "status": "STOK_AYNI_ATLANDI",
                    "selected_location_id": selected_location_id,
                    "selected_old_qty": selected_old_qty,
                    "new_qty": new_qty,
                    "other_locations_old_qty": str(other_old_qty_map),
                    "product_title": variant.get("product_title", ""),
                    "variant_id": variant.get("variant_id", ""),
                    "inventory_item_id": inventory_item_id
                })
                continue

            try:
                log(
                    f"Guncelleniyor | SKU: {sku} | "
                    f"secili depo {selected_old_qty} -> {new_qty} | "
                    f"diger depolar: {other_old_qty_map} | "
                    f"{variant.get('product_title')}"
                )

                if need_selected_update:
                    set_inventory_level(
                        location_id=selected_location_id,
                        inventory_item_id=inventory_item_id,
                        quantity=int(new_qty)
                    )
                    selected_location_updates += 1

                if ZERO_OTHER_LOCATIONS:
                    for other_location_id, old_value in other_old_qty_map.items():
                        if old_value not in (None, 0):
                            set_inventory_level(
                                location_id=other_location_id,
                                inventory_item_id=inventory_item_id,
                                quantity=0
                            )
                            other_location_zero_updates += 1

                changed_variant_count += 1

                report_rows.append({
                    "sku": sku,
                    "status": "DRY_RUN_GUNCELLENECEK" if DRY_RUN else "GUNCELLENDI",
                    "selected_location_id": selected_location_id,
                    "selected_old_qty": selected_old_qty,
                    "new_qty": new_qty,
                    "other_locations_old_qty": str(other_old_qty_map),
                    "product_title": variant.get("product_title", ""),
                    "variant_id": variant.get("variant_id", ""),
                    "inventory_item_id": inventory_item_id
                })

            except Exception as error:
                errors += 1

                log(f"HATA | SKU: {sku} | {error}")

                report_rows.append({
                    "sku": sku,
                    "status": f"HATA: {error}",
                    "selected_location_id": selected_location_id,
                    "selected_old_qty": selected_old_qty,
                    "new_qty": new_qty,
                    "other_locations_old_qty": str(other_old_qty_map),
                    "product_title": variant.get("product_title", ""),
                    "variant_id": variant.get("variant_id", ""),
                    "inventory_item_id": inventory_item_id
                })

    if SET_MISSING_SKU_TO_ZERO:
        log("Feed icinde olmayan Shopify SKU'lari secili depoda ve diger depolarda 0 yapilacak.")

        for sku, variants in shopify_sku_map.items():
            if sku in feed_stock_map:
                continue

            for variant in variants:
                inventory_item_id = variant.get("inventory_item_id")
                inventory_management = variant.get("inventory_management")

                if not inventory_item_id or inventory_management != "shopify":
                    continue

                inventory_item_id = int(inventory_item_id)

                for loc_id in locations_to_check:
                    old_qty = inventory_levels.get((inventory_item_id, loc_id))
                    if old_qty in (None, 0):
                        continue

                    try:
                        log(f"Feedde yok, 0 yapiliyor | SKU: {sku} | lokasyon {loc_id} | {old_qty} -> 0")
                        set_inventory_level(
                            location_id=loc_id,
                            inventory_item_id=inventory_item_id,
                            quantity=0
                        )
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
    log(f"Shopify benzersiz SKU sayisi: {len(shopify_sku_map)}")
    log(f"Eslesen SKU sayisi: {matched_sku_count}")
    log(f"Eslesen varyant sayisi: {matched_variant_count}")
    log(f"Degisen varyant sayisi: {changed_variant_count}")
    log(f"Secili lokasyon stok guncellemesi: {selected_location_updates}")
    log(f"Diger lokasyon 0 yapma islemi: {other_location_zero_updates}")
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
