import os
import json
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
HISTORY_FILE = "posted_urls.json"
TARGET_URL = "https://www.axios.com/politics-policy"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_history(history):
    # Keep only the last 200 URLs to keep the file lightweight
    history = history[-200:]
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

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

def scrape_axios_politics():
    print(f"Fetching {TARGET_URL}...")
    response = requests.get(TARGET_URL, headers=HEADERS, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    articles = []

    # Target story anchor tags and headlines
    for a in soup.find_all("a", href=True):
        href = a["href"]
        # Filter article URLs
        if (
            any(k in href for k in ["/202", "/politics-policy/", "/news/"]) 
            and not href.endswith(("/politics-policy", "/newsletters", "#"))
        ):
            full_url = urljoin(TARGET_URL, href).split("?")[0]
            title = a.get_text(strip=True)

            # Avoid empty or single-word links
            if title and len(title.split()) > 3:
                # Deduplicate within current page scrape
                if not any(item["url"] == full_url for item in articles):
                    articles.append({"title": title, "url": full_url})

    return articles

def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("Missing TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID.")
        return

    history = load_history()
    articles = scrape_axios_politics()
    print(f"Found {len(articles)} total articles on page.")

    # Filter out already posted articles
    new_articles = [a for a in articles if a["url"] not in history]
    print(f"New articles to post: {len(new_articles)}")

    # On the very first run, only post the latest 3 to prevent spamming
    if not history and len(new_articles) > 3:
        new_articles = new_articles[:3]

    # Post from oldest to newest among new items
    for article in reversed(new_articles):
        message = f"📰 <b>{article['title']}</b>\n\n🔗 <a href='{article['url']}'>Read on Axios</a>"
        send_telegram_message(message)
        history.append(article["url"])
        time.sleep(2)  # Avoid Telegram rate limits

    save_history(history)
    print("Done!")

if __name__ == "__main__":
    main()
