import os
import json
import time
import html
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from curl_cffi import requests as curl_requests
from deep_translator import GoogleTranslator

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
HISTORY_FILE = "posted_urls.json"
TARGET_URL = "https://www.axios.com/politics-policy"

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            return []
    return []

def save_history(history):
    # Keep the last 300 URLs in history
    history = history[-300:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

def translate_to_persian(text):
    """Translates the English headline into Persian."""
    if not text:
        return ""
    try:
        translated = GoogleTranslator(source='auto', target='fa').translate(text)
        return translated if translated else text
    except Exception as e:
        print(f"Translation warning: {e}")
        return text

def send_telegram_message(text):
    api_url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False
    }
    try:
        response = requests.post(api_url, json=payload, timeout=15)
        response.raise_for_status()
        print("Successfully sent message to Telegram.")
    except Exception as e:
        print(f"Error sending message to Telegram: {e}")

def scrape_axios_politics():
    """Scrapes news articles directly from https://www.axios.com/politics-policy"""
    articles = []
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.google.com/",
    }

    try:
        print(f"Fetching direct URL: {TARGET_URL} ...")
        response = curl_requests.get(
            TARGET_URL,
            headers=headers,
            impersonate="chrome120",
            timeout=30
        )
        print(f"HTTP Status: {response.status_code}")
        
        if response.status_code != 200:
            return []

        soup = BeautifulSoup(response.text, "html.parser")

        # Method 1: Extract from Next.js server-rendered data tree
        next_data_script = soup.find("script", id="__NEXT_DATA__")
        if next_data_script and next_data_script.string:
            try:
                data = json.loads(next_data_script.string)

                def extract_from_json(obj):
                    if isinstance(obj, dict):
                        headline = obj.get("headline") or obj.get("title")
                        slug = obj.get("permalink") or obj.get("slug") or obj.get("url")

                        if headline and slug and isinstance(headline, str) and isinstance(slug, str):
                            if len(headline.split()) >= 3:
                                full_url = urljoin("https://www.axios.com", slug).split("?")[0]
                                if not any(x in full_url for x in ["/authors/", "/category/", "/newsletters", "/events"]):
                                    if not any(a["url"] == full_url for a in articles):
                                        articles.append({"title": headline.strip(), "url": full_url})
                        for v in obj.values():
                            extract_from_json(v)
                    elif isinstance(obj, list):
                        for item in obj:
                            extract_from_json(item)

                extract_from_json(data)
                print(f"Extracted {len(articles)} stories from page data.")
            except Exception as e:
                print(f"Next.js parse error: {e}")

        # Method 2: HTML Anchor Extraction
        ignore_paths = [
            "/politics-policy", "/authors", "/newsletters", "/events", "/local",
            "/about", "/privacy-policy", "/terms", "/contact", "/search", "#"
        ]

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith("/"):
                full_url = urljoin("https://www.axios.com", href).split("?")[0]
            elif href.startswith("https://www.axios.com"):
                full_url = href.split("?")[0]
            else:
                continue

            if any(full_url.rstrip("/").endswith(p) or f"{p}/" in full_url for p in ignore_paths):
                continue
            if full_url in ["https://www.axios.com", "https://www.axios.com/politics-policy"]:
                continue

            # Extract headline text from inner tags
            title = ""
            for tag in ["h1", "h2", "h3", "h4", "p", "span"]:
                child = a.find(tag)
                if child and child.get_text(strip=True):
                    title = child.get_text(" ", strip=True)
                    break
            if not title:
                title = a.get_text(" ", strip=True)

            if title and len(title.split()) >= 4:
                if not any(item["url"] == full_url for item in articles):
                    articles.append({"title": title, "url": full_url})

    except Exception as e:
        print(f"Scraping error: {e}")

    return articles

def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
        return

    history = load_history()
    articles = scrape_axios_politics()
    print(f"Total articles found directly on Axios: {len(articles)}")

    new_articles = [a for a in articles if a["url"] not in history]
    print(f"New articles to post: {len(new_articles)}")

    # On first execution, post only the 3 newest to prevent flooding
    if not history and len(new_articles) > 3:
        new_articles = new_articles[:3]

    # Post from oldest to newest among new arrivals
    for article in reversed(new_articles):
        # Translate headline to Persian
        persian_title = translate_to_persian(article['title'])
        safe_persian_title = html.escape(persian_title)

        # Message Format
        message = (
            f"⚡️ <b>{safe_persian_title}</b>\n\n"
            f"<a href=\"{article['url']}\">🧿 اکـســـیــوس 🧿</a>\n\n"
            f"🤖 @secretollah\n"
            f"#axios"
        )

        send_telegram_message(message)
        history.append(article["url"])
        time.sleep(2)

    save_history(history)
    print("Run completed.")

if __name__ == "__main__":
    main()
