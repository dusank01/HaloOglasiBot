import os
import json
import time
import random
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from curl_cffi import requests

# Učitavanje varijabli iz .env fajla
load_dotenv()

BASE_SEARCH_URL = os.getenv("SEARCH_URL")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_IDS_RAW = os.getenv("TELEGRAM_CHAT_ID")
PROXY_URL = os.getenv("PROXY_URL")

CACHE_FILE = "seen_ads.json"

if not all([BASE_SEARCH_URL, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_IDS_RAW]):
    raise ValueError("❌ Neke od varijabli nisu podešene u .env fajlu!")

TELEGRAM_CHAT_IDS = [chat_id.strip() for chat_id in TELEGRAM_CHAT_IDS_RAW.split(",") if chat_id.strip()]

def load_seen_ads():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception as e:
            print(f"⚠️ Greška pri čitanju {CACHE_FILE}: {e}")
    return set()

def save_seen_ads(seen_ads):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(list(seen_ads), f, indent=2, ensure_ascii=False)
        print(f"💾 Baza uspešno ažurirana. Ukupno zapamćeno {len(seen_ads)} oglasa.")
    except Exception as e:
        print(f"❌ Greška pri čuvanju {CACHE_FILE}: {e}")

def send_telegram_message(text):
    """Šalje poruku na sve podešene Telegram naloge uz detaljan ispis rezultata."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    for chat_id in TELEGRAM_CHAT_IDS:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False
        }
        try:
            res = requests.post(url, json=payload, timeout=10)
            if res.status_code == 200:
                print(f"✅ Poruka uspešno poslata na CHAT_ID: {chat_id}")
            else:
                print(f"⚠️ Telegram API vratio status {res.status_code} za CHAT_ID {chat_id}: {res.text}")
        except Exception as e:
            print(f"❌ Greška pri slanju poruke na CHAT_ID {chat_id}: {e}")

def get_page_url(base_url, page_num):
    if page_num == 1:
        return base_url
    return f"{base_url}&page={page_num}" if "?" in base_url else f"{base_url}?page={page_num}"

def scrape_and_notify_new_ads():
    session = requests.Session(impersonate="chrome124")

    proxies = {
        "http": PROXY_URL,
        "https": PROXY_URL
    } if PROXY_URL else None

    if PROXY_URL:
        print("🌐 Koristim proxy server za preusmeravanje zahteva...")

    IGNORE_CLASSES = [
        "banner-list-item", 
        "banner-item", 
        "promo-item", 
        "native-ad", 
        "google-ad", 
        "partner-item"
    ]

    previously_seen_ads = load_seen_ads()
    current_run_active_ads = set()  # Sakupljamo sve oglase koji TRENUTNO postoje na sajtu
    
    new_ads_found = []
    seen_ids_in_this_run = set()
    
    page = 1
    print(f"🔎 Pokrećem proveru novih oglasa na Halo Oglasima (Slanje na {len(TELEGRAM_CHAT_IDS)} Telegram naloga)...\n")

    while True:
        url = get_page_url(BASE_SEARCH_URL, page)
        print(f"📄 Učitavam stranicu {page}: {url}")

        try:
            response = session.get(url, proxies=proxies, timeout=15)
            if response.status_code != 200:
                print(f"❌ Greška pri dohvatanju stranice {page}: status {response.status_code}")
                break
        except Exception as e:
            print(f"❌ Izuzetak pri dohvatanju stranice {page}: {e}")
            break

        soup = BeautifulSoup(response.text, "html.parser")
        raw_ads = soup.find_all("div", class_="product-item")

        if not raw_ads:
            print(f"🛑 Stranica {page} nema oglasa. Prekidam pretragu.")
            break

        page_ads_count = 0
        new_ids_on_this_page = 0

        for ad in raw_ads:
            ad_classes = ad.get("class", [])
            if any(ignore_cls in ad_classes for ignore_cls in IGNORE_CLASSES):
                continue

            ad_id = ad.get("data-id")
            if not ad_id or ad_id in seen_ids_in_this_run:
                continue

            seen_ids_in_this_run.add(ad_id)
            page_ads_count += 1
            new_ids_on_this_page += 1

            # Dodajemo oglas u skup trenutno aktivnih na sajtu
            current_run_active_ads.add(ad_id)

            # Ako je oglas već zabeležen ranije, preskačemo slanje poruke
            if ad_id in previously_seen_ads:
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

            price_element = ad.find("div", class_="central-feature") or ad.find("span", class_="price")
            price = price_element.text.strip().replace("\xa0", " ") if price_element else "Cena na upit"

            location_element = ad.find("ul", class_="subtitle-places")
            location = " | ".join([li.text.strip() for li in location_element.find_all("li")]) if location_element else ""

            date_element = ad.find("span", class_="publish-date") or ad.find("div", class_="publish-date") or ad.find("span", class_="time")
            publish_date = date_element.text.strip() if date_element else "Nepoznat datum"

            new_ads_found.append({
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

        print(f"   ✅ Na strani {page} analizirano {page_ads_count} pravih oglasa.\n")
        page += 1
        time.sleep(random.uniform(2.0, 4.0))

    print("==================================================")
    if new_ads_found:
        print(f"🎉 PRONAĐENO JE {len(new_ads_found)} POTPUNO NOVIH OGLASA!\n")
        for idx, ad in enumerate(reversed(new_ads_found), start=1):
            print(f"{idx}. [ID: {ad['id']}] {ad['title']} - {ad['price']}")
            
            msg = (
                f"🚨 <b>NOVI OGLAS ZA STAN!</b>\n\n"
                f"📌 <b>Naslov:</b> {ad['title']}\n"
                f"💶 <b>Cena:</b> {ad['price']}\n"
            )
            if ad['location']:
                msg += f"📍 <b>Lokacija:</b> {ad['location']}\n"
            msg += (
                f"🕒 <b>Objavljeno:</b> {ad['date']}\n\n"
                f"🔗 <a href='{ad['link']}'>Pogledaj oglas na Halo Oglasima</a>"
            )
            send_telegram_message(msg)
            time.sleep(1)
    else:
        print("ℹ️ Nema novih oglasa od poslednje provere.")
        # Slanje obaveštenja na Telegram da je provera izvršena i da nema novih stanova
        status_msg = f"ℹ️ <b>Halo Oglasi Provera:</b> Trenutno nema novih stanova u ponudi. (Aktivno oglasa: {len(current_run_active_ads)})"
        send_telegram_message(status_msg)

    print("==================================================")

    # Čuvamo SAMO trenutno aktivne oglase (oglasi koji su u međuvremenu obrisani/skinuti se automatski brišu iz fajla)
    save_seen_ads(current_run_active_ads)

if __name__ == "__main__":
    scrape_and_notify_new_ads()