import json
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup


LISTING_URL = "https://www.abc.net.au/news/health"
BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "data" / "json"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def get_soup(url: str) -> BeautifulSoup:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=20)
    response.raise_for_status()
    return BeautifulSoup(response.text, "lxml")


def collect_article_links() -> list[str]:
    soup = get_soup(LISTING_URL)
    links = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]

        if href.startswith("/news/"):
            href = f"https://www.abc.net.au{href}"

        if not href.startswith("https://www.abc.net.au/news/"):
            continue

        if "#" in href:
            continue

        if "/news/20" not in href:
            continue

        if href not in links:
            links.append(href)

    return links


def is_heart_health_related(title: str, content: str) -> bool:
    text = f"{title} {content}".lower()

    keywords = [
        "heart",
        "cardiovascular",
        "cardiac",
        "heart attack",
        "stroke",
        "cholesterol",
        "blood pressure",
        "coronary",
        "artery",
    ]

    return any(keyword in text for keyword in keywords)


def extract_article(article_url: str, item_id: str) -> dict:
    soup = get_soup(article_url)

    title_tag = soup.find("h1")
    title = title_tag.get_text(strip=True) if title_tag else ""

    author = ""
    for tag in soup.find_all(["a", "span", "p"]):
        text = tag.get_text(" ", strip=True)
        if text.lower().startswith("by "):
            author = text[3:].strip()
            break

    publish_time = ""
    time_tag = soup.find("time")
    if time_tag:
        publish_time = time_tag.get("datetime", "") or time_tag.get_text(strip=True)

    paragraphs = soup.find_all("p")
    content_parts = []

    for p in paragraphs:
        text = p.get_text(" ", strip=True)
        if len(text) > 40:
            content_parts.append(text)

    content = "\n".join(content_parts[:20])
    summary = content_parts[0] if content_parts else ""

    topic = (
        "women_heart_health"
        if is_heart_health_related(title, content)
        else "general_health"
    )

    record = {
        "id": item_id,
        "source": "ABC News",
        "platform": "news",
        "source_type": "media",
        "url": article_url,
        "title": title,
        "content": content,
        "summary": summary,
        "author": author,
        "author_type": "journalist" if author else "",
        "publish_time": publish_time,
        "scrape_time": datetime.now().isoformat(),
        "tags": [],
        "hashtags": [],
        "mentions": [],
        "engagement": {"likes": None, "comments": None, "shares": None, "views": None},
        "media_type": "text",
        "media_url": "",
        "topic": topic,
        "content_type": "article",
        "language": "en",
    }

    return record


def save_json(record: dict, filename: str) -> None:
    output_path = OUTPUT_DIR / filename
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(record, file, indent=2, ensure_ascii=False)


def main() -> None:
    links = collect_article_links()
    print(f"Found {len(links)} possible article links")

    if not links:
        print("No article links found.")
        return

    print("\nFirst 10 candidate links:")
    for i, link in enumerate(links[:10], start=1):
        print(f"{i}. {link}")

    matched_article = None

    for index, link in enumerate(links[:15], start=1):
        print(f"\nChecking article {index}: {link}")
        article = extract_article(link, f"abc_{index:03d}")
        print("Title:", article["title"])
        print("Topic:", article["topic"])

        if article["topic"] == "women_heart_health":
            matched_article = article
            break

    if matched_article:
        save_json(matched_article, "abc_heart_sample.json")
        print("\nSaved heart-related article to data/json/abc_heart_sample.json")
        print("Title:", matched_article["title"])
        print("URL:", matched_article["url"])
    else:
        print("\nNo heart-related article found in first 15 ABC links.")


if __name__ == "__main__":
    main()
