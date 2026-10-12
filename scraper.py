import os
import json
import time
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

# Učitavanje varijabli iz .env fajla
load_dotenv()

BASE_SEARCH_URL = os.getenv("SEARCH_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

if not all([BASE_SEARCH_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID]):
    raise ValueError("❌ Neke od varijabli nisu podešene u .env fajlu!")

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Greška pri slanju poruke: {e}")

def get_page_url(base_url, page_num):
    if page_num == 1:
        return base_url
    return f"{base_url}&page={page_num}" if "?" in base_url else f"{base_url}?page={page_num}"

def scrape_all_available_pages():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    IGNORE_CLASSES = [
        "banner-list-item", 
        "banner-item", 
        "promo-item", 
        "native-ad", 
        "google-ad", 
        "partner-item"
    ]

    total_ads_found = 0
    all_ads = []
    seen_ids_in_this_run = set()
    
    page = 1
    print("🔎 Pokrećem automatski skreping kroz SVE dostupne stranice...\n")

    while True:
        url = get_page_url(BASE_SEARCH_URL, page)
        print(f"📄 Učitavam stranicu {page}: {url}")

        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"❌ Greška pri dohvatanju stranice {page}: status {response.status_code}")
            break

        soup = BeautifulSoup(response.text, "html.parser")
        raw_ads = soup.find_all("div", class_="product-item")

        if not raw_ads:
            print(f"🛑 Stranica {page} nema oglasa. Prekidam pretragu.")
            break

        page_ads_count = 0
        new_ids_on_this_page = 0

        for ad in raw_ads:
            # Preskakanje banera i reklama
            ad_classes = ad.get("class", [])
            if any(ignore_cls in ad_classes for ignore_cls in IGNORE_CLASSES):
                continue

            # Pravi oglasi moraju imati data-id
            ad_id = ad.get("data-id")
            if not ad_id or ad_id in seen_ids_in_this_run:
                continue

            # Izvlačenje naslova i linka
            title_element = ad.find(["h2", "h8", "h3"], class_=["ad-title", "product-title"])
            if not title_element:
                title_element = ad.find("a", class_="product-link") or ad.find("a", class_="ad-link")

            if not title_element:
                continue

            a_tag = title_element.find("a") if title_element.name != "a" else title_element
            if not a_tag or not a_tag.get("href"):
                continue

            title = a_tag.text.strip()
            link = "https://www.halooglasi.com" + a_tag["href"] if not a_tag["href"].startswith("http") else a_tag["href"]

            # Izvlačenje cene
            price_element = ad.find("div", class_="central-feature") or ad.find("span", class_="price")
            price = price_element.text.strip().replace("\xa0", " ") if price_element else "Cena na upit"

            # Izvlačenje lokacije
            location_element = ad.find("ul", class_="subtitle-places")
            location = " | ".join([li.text.strip() for li in location_element.find_all("li")]) if location_element else ""

            # -------------------------------------------------------------
            # IZVLAČENJE DATUMA OBJAVE
            # -------------------------------------------------------------
            date_element = ad.find("span", class_="publish-date") or ad.find("div", class_="publish-date") or ad.find("span", class_="time")
            publish_date = date_element.text.strip() if date_element else "Nepoznat datum"

            total_ads_found += 1
            page_ads_count += 1
            new_ids_on_this_page += 1
            seen_ids_in_this_run.add(ad_id)

            all_ads.append({
                "number": total_ads_found,
                "page": page,
                "id": ad_id,
                "title": title,
                "price": price,
                "location": location,
                "date": publish_date,
                "link": link
            })

        if new_ids_on_this_page == 0:
            print(f"🛑 Na stranici {page} nema novih/jedinstvenih oglasa. Završeno skrepovanje.")
            break

        print(f"   ✅ Na strani {page} pronađeno {page_ads_count} pravih oglasa.\n")
        page += 1
        time.sleep(1)

    # --- ISPIS REZULTATA U TERMINALU ---
    print("==================================================")
    print(f"📋 USPEŠNO PRONAĐENO UKUPNO {total_ads_found} OGLASA KROZ {page - 1} STRANICA:")
    print("==================================================\n")

    for ad in all_ads:
        print(f"{ad['number']}. [Strana {ad['page']}] [ID: {ad['id']}] {ad['title']}")
        print(f"   💶 Cena: {ad['price']}")
        if ad['location']:
            print(f"   📍 Lokacija: {ad['location']}")
        print(f"   🕒 Objavljeno: {ad['date']}")
        print(f"   🔗 Link: {ad['link']}\n")

    print("==================================================")

if __name__ == "__main__":
    scrape_all_available_pages()