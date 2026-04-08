import json
import re
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "data" / "json"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

BASE_CATEGORY_URL = "https://www.medicalnewstoday.com/categories/heart-disease"
MAX_PAGES = 10


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


def build_page_url(page_number: int) -> str:
    if page_number == 1:
        return BASE_CATEGORY_URL
    return f"{BASE_CATEGORY_URL}?page={page_number}"


def title_looks_heart_related(title: str) -> bool:
    title_lower = title.lower()

    strong_terms = [
        "heart",
        "cardio",
        "cardiovascular",
        "cardiac",
        "coronary",
        "stroke",
        "blood pressure",
        "hypertension",
        "cholesterol",
        "artery",
        "atherosclerosis",
    ]

    return any(term in title_lower for term in strong_terms)


def collect_article_links_from_page(page_url: str) -> list[str]:
    soup = get_soup(page_url)
    links = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        link_text = a_tag.get_text(" ", strip=True)

        if href.startswith("/"):
            href = f"https://www.medicalnewstoday.com{href}"

        if not href.startswith("https://www.medicalnewstoday.com/articles/"):
            continue

        bad_parts = ["/articles/in-conversation-podcast", "/articles/content-hubs"]
        if any(part in href for part in bad_parts):
            continue

        if not link_text:
            continue

        if not title_looks_heart_related(link_text):
            continue

        if href not in links:
            links.append(href)

    return links


def collect_article_links(max_pages: int = MAX_PAGES) -> list[str]:
    all_links = []

    for page_number in range(1, max_pages + 1):
        page_url = build_page_url(page_number)
        print(f"Scanning page {page_number}: {page_url}")

        try:
            page_links = collect_article_links_from_page(page_url)
            print(f"Found {len(page_links)} filtered links on page {page_number}")

            for link in page_links:
                if link not in all_links:
                    all_links.append(link)

        except Exception as error:
            print(f"Error scanning page {page_number}: {error}")

    return all_links


def clean_paragraphs(paragraphs: list[str]) -> list[str]:
    junk_phrases = [
        "medical news today has strict sourcing guidelines",
        "fact checked",
        "copy edited by",
        "latest news",
        "related coverage",
        "share on pinterest",
        "share on facebook",
        "share on twitter",
        "read this next",
        "was this helpful",
        "how we reviewed this article",
    ]

    cleaned = []

    for p in paragraphs:
        text = p.strip()

        if len(text) < 40:
            continue

        lower_text = text.lower()

        if any(junk in lower_text for junk in junk_phrases):
            continue

        cleaned.append(text)

    return cleaned


def extract_title(soup: BeautifulSoup) -> str:
    for selector in ["h1", "title", "h2"]:
        tag = soup.select_one(selector)
        if tag:
            text = tag.get_text(" ", strip=True)
            if text:
                text = text.replace(" - Medical News Today", "").strip()
                return text
    return ""


def extract_author(soup: BeautifulSoup) -> str:
    for tag in soup.find_all(["span", "p", "a"]):
        text = tag.get_text(" ", strip=True)
        if text.lower().startswith("by "):
            return text[3:].strip()
    return ""


def extract_publish_time(soup: BeautifulSoup) -> str:
    time_tag = soup.find("time")
    if time_tag:
        return time_tag.get("datetime", "") or time_tag.get_text(strip=True)
    return ""


def classify_topic(title: str, content: str) -> str:
    text = f"{title} {content}".lower()

    women_terms = ["women", "woman", "female", "menopause", "maternal"]
    heart_terms = [
        "heart disease",
        "heart attack",
        "cardiovascular",
        "cardiac",
        "coronary",
        "stroke",
        "blood pressure",
        "hypertension",
        "cholesterol",
        "artery",
    ]

    has_women = any(term in text for term in women_terms)
    has_heart = any(term in text for term in heart_terms)

    if has_women and has_heart:
        return "women_heart_health"
    if has_heart:
        return "general_heart_health"
    return "general_health"


def extract_content(soup: BeautifulSoup, title: str) -> tuple[str, str]:
    paragraph_tags = soup.find_all("p")
    raw_paragraphs = [p.get_text(" ", strip=True) for p in paragraph_tags]
    cleaned_paragraphs = clean_paragraphs(raw_paragraphs)

    content = "\n".join(cleaned_paragraphs[:15])

    summary = ""
    title_lower = title.strip().lower()

    for p in cleaned_paragraphs:
        p_lower = p.strip().lower()

        if p_lower == title_lower:
            continue

        if not p_lower.startswith(("moreover", "however", "also", "and", "but")):
            summary = p
            break

    if not summary and cleaned_paragraphs:
        summary = cleaned_paragraphs[0]

    return content, summary


def build_record(article_url: str, item_id: str) -> dict:
    soup = get_soup(article_url)

    title = extract_title(soup)
    author = extract_author(soup)
    publish_time = extract_publish_time(soup)
    content, summary = extract_content(soup, title)
    topic = classify_topic(title, content)

    return {
        "id": item_id,
        "source": "Medical News Today",
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


def save_json(record: dict, filename: str) -> None:
    output_path = OUTPUT_DIR / filename
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(record, file, indent=2, ensure_ascii=False)


def main() -> None:
    links = collect_article_links(MAX_PAGES)
    print(f"\nFound {len(links)} total filtered links across {MAX_PAGES} pages")

    if not links:
        print("No suitable article links found.")
        return

    print("\nFirst 10 filtered links:")
    for i, link in enumerate(links[:10], start=1):
        print(f"{i}. {link}")

    matched_article = None

    for index, link in enumerate(links[:20], start=1):
        print(f"\nChecking article {index}: {link}")
        article = build_record(link, f"mnt_{index:03d}")
        print("Title:", article["title"])
        print("Topic:", article["topic"])

        if article["topic"] in ["women_heart_health", "general_heart_health"]:
            matched_article = article
            break

    if matched_article:
        save_json(matched_article, "mnt_sample.json")
        print("\nSaved article to data/json/mnt_sample.json")
        print("Title:", matched_article["title"])
        print("URL:", matched_article["url"])
        print("Topic:", matched_article["topic"])
        print("Summary:", matched_article["summary"][:150])
    else:
        print("\nNo heart-related article found among the filtered articles.")


if __name__ == "__main__":
    main()
