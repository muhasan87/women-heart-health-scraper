import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from bs4 import BeautifulSoup

#for json
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data" / "json"
DATA_DIR.mkdir(parents=True, exist_ok=True)

#for analysis visualisation
CHART_DIR = BASE_DIR / "data" / "charts"
CHART_DIR.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


def get_soup(url: str) -> BeautifulSoup:
    response = requests.get(url, headers=HEADERS, timeout=20)
    response.raise_for_status()
    return BeautifulSoup(response.text, "lxml")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


#def clean_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


#def normalise_text(text: str) -> str:
    return clean_whitespace(text).replace("\xa0", " ")

def normalise_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).replace("\xa0", " ").strip()


# extraction
def extract_meta_content(soup: BeautifulSoup, attrs_list: list[dict[str, str]]) -> str:
    for attrs in attrs_list:
        tag = soup.find("meta", attrs=attrs)
        if tag and tag.get("content"):
            return normalise_text(tag["content"])
    return ""


def extract_jsonld_objects(soup: BeautifulSoup) -> list[Any]:
    objects = []

    for tag in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = tag.string or tag.get_text(strip=True)
        if not raw:
            continue

        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                objects.extend(parsed)
            else:
                objects.append(parsed)
        except Exception:
            continue

    return objects


def extract_author_from_jsonld(soup: BeautifulSoup) -> str:
    for obj in extract_jsonld_objects(soup):
        if not isinstance(obj, dict):
            continue

        author = obj.get("author")
        if isinstance(author, dict):
            name = author.get("name", "")
            if name:
                return normalise_text(name)

        if isinstance(author, list):
            for item in author:
                if isinstance(item, dict) and item.get("name"):
                    return normalise_text(item["name"])

    return ""


def extract_date_from_jsonld(soup: BeautifulSoup) -> str:
    for obj in extract_jsonld_objects(soup):
        if not isinstance(obj, dict):
            continue

        for key in ["datePublished", "dateCreated", "dateModified"]:
            value = obj.get(key, "")
            if isinstance(value, str) and value.strip():
                return value.strip()

    return ""


def extract_title_generic(
    soup: BeautifulSoup, site_suffixes: list[str] | None = None
) -> str:
    selectors = ["h1", "meta[property='og:title']", "title"]

    for selector in selectors:
        tag = soup.select_one(selector)
        if not tag:
            continue

        if selector.startswith("meta"):
            title = normalise_text(tag.get("content", ""))
        else:
            title = normalise_text(tag.get_text(" ", strip=True))

        if site_suffixes:
            for suffix in site_suffixes:
                if title.endswith(suffix):
                    title = title[: -len(suffix)].strip()

        if title:
            return title

    return ""


def extract_author_generic(soup: BeautifulSoup) -> str:
    meta_author = extract_meta_content(
        soup,
        [
            {"name": "author"},
            {"property": "author"},
            {"property": "article:author"},
        ],
    )
    if meta_author:
        if meta_author.startswith("http"): #grabs text rather than author's link
            meta_author = meta_author.split("/")[-2].replace("-", " ").title()
        return meta_author

    jsonld_author = extract_author_from_jsonld(soup)
    if jsonld_author:
        if jsonld_author.startswith("http"):
            jsonld_author = jsonld_author.split("/")[-2].replace("-", " ").title()
        return jsonld_author

    for tag in soup.find_all(["span", "p", "div"]):
        text = normalise_text(tag.get_text(" ", strip=True))
        if text.lower().startswith("by "):
            return text[3:].strip()

    return ""


def extract_publish_time_generic(soup: BeautifulSoup) -> str:
    time_tag = soup.find("time")
    if time_tag:
        value = time_tag.get("datetime", "") or time_tag.get_text(strip=True)
        value = value.strip()
        if value:
            return value

    meta_time = extract_meta_content(
        soup,
        [
            {"property": "article:published_time"},
            {"name": "article:published_time"},
            {"property": "og:published_time"},
            {"name": "pubdate"},
            {"name": "publish-date"},
        ],
    )
    if meta_time:
        return meta_time

    jsonld_time = extract_date_from_jsonld(soup)
    if jsonld_time:
        return jsonld_time

    return ""


def clean_paragraph_list(
    paragraphs: list[str],
    junk_phrases: list[str] | None = None,
    min_length: int = 40,
) -> list[str]:
    junk_phrases = [j.lower() for j in (junk_phrases or [])]
    cleaned = []

    for paragraph in paragraphs:
        text = normalise_text(paragraph)
        if len(text) < min_length:
            continue

        lower = text.lower()
        if any(junk in lower for junk in junk_phrases):
            continue

        cleaned.append(text)

    return cleaned


def extract_summary_from_paragraphs(paragraphs: list[str], title: str = "") -> str:
    title_lower = normalise_text(title).lower()

    for p in paragraphs:
        p_lower = p.lower()

        if p_lower == title_lower:
            continue

        if not p_lower.startswith(("moreover", "however", "also", "and", "but")):
            return p

    return paragraphs[0] if paragraphs else ""


def classify_topic(title: str, content: str) -> str:
    text = f"{title} {content}".lower()

    women_terms = ["women", "woman", "female", "menopause", "maternal", "pregnancy"]
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
        "atherosclerosis",
        "heart"
    ]

    has_women = any(term in text for term in women_terms)
    has_heart = any(term in text for term in heart_terms)

    if has_women and has_heart:
        return "women_heart_health"
    if has_heart:
        return "heart_health"
    return "general_health"


def build_record(
    *,
    item_id: str,
    source: str,
    source_category: str,
    source_type: str,
    source_classification: str,
    url: str,
    title: str,
    content: str,
    summary: str,
    author: str,
    author_type: str,
    publish_time: str,
    #topic: str,
    media_type: str = "text",
    content_type: str = "article",
    language: str = "en",
) -> dict:
    return {
        "id": item_id,
        "source": source,
        "source_category": source_category,
        "source_type": source_type,
        "source_classification": source_classification,
        "url": url,
        "title": title,
        "content": content,
        "summary": summary,
        "author": author or None,
        "author_type": author_type or None,
        "publish_time": publish_time or None,
        "scrape_time": now_iso(),
        "tags": [],
        "hashtags": [],
        #"mentions": [],
        "engagement": {
            "likes": None,
            "comments": None,
            "shares": None,
            #"views": None,
        },
        "media_type": media_type,
        #"topic": topic,
        "content_type": content_type,
        "language": language,
    }


def save_json(records: list[dict], filename: str) -> None:
    output_path = DATA_DIR / filename
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)