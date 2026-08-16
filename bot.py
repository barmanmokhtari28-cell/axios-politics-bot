import os
import json
import time
import html
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from curl_cffi import requests as curl_requests
from deep_translator import GoogleTranslator

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
HISTORY_FILE = "posted_urls.json"
TARGET_URL = "https://www.axios.com/politics-policy"
RSS_URL = "https://www.axios.com/feeds/feed.rss"

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
    """Translates the English headline into fluent Persian."""
    if not text:
        return ""
    try:
        translated = GoogleTranslator(source='auto', target='fa').translate(text)
        return translated if translated else text
    except Exception as e:
        print(f"Translation warning: {e}")
        return text  # Fallback to English if translation service is unreachable

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
    except Exception as e:
        print(f"Error sending message to Telegram: {e}")

def fetch_from_rss():
    """Fetches real-time chronological politics articles from Axios RSS feed."""
    articles = []
    try:
        print("Fetching real-time RSS feed...")
        res = curl_requests.get(
            RSS_URL,
            impersonate="chrome120",
            timeout=20
        )
        if res.status_code == 200:
            root = ET.fromstring(res.content)
            for item in root.findall("./channel/item"):
                link = item.findtext("link", "").strip().split("?")[0]
                title = item.findtext("title", "").strip()
                categories = [c.text.lower() for c in item.findall("category") if c.text]

                is_politics = (
                    "politics" in link
                    or "policy" in link
                    or any("politic" in c or "policy" in c or "government" in c or "congress" in c or "white house" in c for c in categories)
                )

                if is_politics and link and title:
                    articles.append({
                        "title": title,
                        "url": link
                    })
    except Exception as e:
        print(f"RSS fetch warning: {e}")
    return articles

def fetch_from_webpage():
    """Scrapes latest chronological articles from the politics page."""
    articles = []
    try:
        print(f"Fetching stream from {TARGET_URL}...")
        res = curl_requests.get(
            TARGET_URL,
            impersonate="chrome120",
            headers={"Accept-Language": "en-US,en;q=0.9"},
            timeout=25
        )
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")

            for a in soup.find_all("a", href=True):
                href = a["href"]
                if any(k in href for k in ["/202", "/politics-policy/"]) and not href.endswith(("/politics-policy", "/newsletters", "#")):
                    full_url = urljoin(TARGET_URL, href).split("?")[0]
                    title = a.get_text(strip=True)

                    if title and len(title.split()) >= 4:
                        if not any(item["url"] == full_url for item in articles):
                            articles.append({"title": title, "url": full_url})
    except Exception as e:
        print(f"Webpage fetch warning: {e}")
    return articles

def get_latest_politics_news():
    rss_articles = fetch_from_rss()
    web_articles = fetch_from_webpage()

    combined = []
    seen = set()

    for item in rss_articles + web_articles:
        if item["url"] not in seen:
            seen.add(item["url"])
            combined.append(item)

    return combined

def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
        return

    history = load_history()
    articles = get_latest_politics_news()
    print(f"Total articles retrieved: {len(articles)}")

    new_articles = [a for a in articles if a["url"] not in history]
    print(f"New recent articles to post: {len(new_articles)}")

    # On first run, post only the 3 latest to prevent channel spam
    if not history and len(new_articles) > 3:
        new_articles = new_articles[:3]

    # Post from oldest to newest among new arrivals
    for article in reversed(new_articles):
        # Translate headline to Persian
        persian_title = translate_to_persian(article['title'])
        safe_persian_title = html.escape(persian_title)

        # Build formatted Telegram message
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
    print("Completed successfully.")

if __name__ == "__main__":
    main()
