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
        print("Message posted to Telegram successfully.")
    except Exception as e:
        print(f"Error sending message to Telegram: {e}")

def fetch_from_axios_api_feed():
    """Fetches real-time articles from the official Axios feed."""
    articles = []
    feed_urls = [
        "https://api.axios.com/feed/",
        "https://news.google.com/rss/search?q=site:axios.com+politics&hl=en-US&gl=US&ceid=US:en"
    ]

    for feed_url in feed_urls:
        try:
            print(f"Fetching from: {feed_url}")
            res = curl_requests.get(feed_url, impersonate="chrome120", timeout=20)
            if res.status_code == 200:
                root = ET.fromstring(res.content)
                for item in root.findall(".//item"):
                    link = item.findtext("link", "").strip().split("?")[0]
                    title = item.findtext("title", "").strip()
                    
                    # Clean up Google News title prefix/suffix if present
                    if " - Axios" in title:
                        title = title.replace(" - Axios", "").strip()

                    categories = [c.text.lower() for c in item.findall("category") if c.text is not None]
                    
                    # Filter for politics & government
                    is_politics = (
                        "politics" in link.lower()
                        or "policy" in link.lower()
                        or "politics" in feed_url
                        or any(k in " ".join(categories) for k in ["politic", "policy", "congress", "white house", "election", "trump", "biden", "senate"])
                    )

                    if is_politics and link and title:
                        if not any(a["url"] == link for a in articles):
                            articles.append({"title": title, "url": link})
        except Exception as e:
            print(f"Feed error ({feed_url}): {e}")

    return articles

def fetch_from_webpage():
    """Scrapes Axios Politics & Policy using Next.js data and fallback HTML parsing."""
    articles = []
    target_url = "https://www.axios.com/politics-policy"
    try:
        print(f"Fetching HTML stream from {target_url}...")
        res = curl_requests.get(
            target_url,
            impersonate="chrome120",
            headers={"Accept-Language": "en-US,en;q=0.9"},
            timeout=25
        )
        if res.status_code == 200:
            soup = BeautifulSoup(res.text, "html.parser")

            # 1. Try parsing Next.js internal JSON data
            next_data_script = soup.find("script", id="__NEXT_DATA__")
            if next_data_script and next_data_script.string:
                try:
                    data = json.loads(next_data_script.string)
                    # Recursively search for stories inside Next.js data
                    def extract_stories(obj):
                        if isinstance(obj, dict):
                            if "headline" in obj and ("permalink" in obj or "slug" in obj):
                                h = obj.get("headline", "")
                                u = obj.get("permalink") or obj.get("slug")
                                if h and u:
                                    full_u = urljoin(target_url, u)
                                    articles.append({"title": h, "url": full_u})
                            for v in obj.values():
                                extract_stories(v)
                        elif isinstance(obj, list):
                            for item in obj:
                                extract_stories(item)

                    extract_stories(data)
                except Exception as e:
                    print(f"Next.js JSON parse notice: {e}")

            # 2. Direct HTML fallback
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if any(year in href for year in ["/2024/", "/2025/", "/2026/", "/2027/"]) or "/politics-policy/" in href:
                    if not href.endswith(("/politics-policy", "/newsletters", "#")):
                        full_url = urljoin(target_url, href).split("?")[0]
                        title = a.get_text(" ", strip=True)
                        if title and len(title.split()) >= 4:
                            if not any(item["url"] == full_url for item in articles):
                                articles.append({"title": title, "url": full_url})
    except Exception as e:
        print(f"Webpage fetch notice: {e}")

    return articles

def get_all_politics_news():
    api_articles = fetch_from_axios_api_feed()
    web_articles = fetch_from_webpage()

    combined = []
    seen = set()

    for item in api_articles + web_articles:
        if item["url"] not in seen:
            seen.add(item["url"])
            combined.append(item)

    return combined

def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
        return

    history = load_history()
    articles = get_all_politics_news()
    print(f"Total articles retrieved: {len(articles)}")

    new_articles = [a for a in articles if a["url"] not in history]
    print(f"New recent articles to post: {len(new_articles)}")

    # On first run, post 3 latest to initialize without spamming
    if not history and len(new_articles) > 3:
        new_articles = new_articles[:3]

    # Post from oldest to newest among new arrivals
    for article in reversed(new_articles):
        # Translate headline into Persian
        persian_title = translate_to_persian(article['title'])
        safe_persian_title = html.escape(persian_title)

        # Message format requested
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
    print("Execution completed.")

if __name__ == "__main__":
    main()
