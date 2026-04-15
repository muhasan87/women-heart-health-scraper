import json
import matplotlib.pyplot as plt #need to add to requirements.txt
from datetime import datetime, timezone
from pathlib import Path

from common import (
    build_record,
    classify_topic,
    clean_paragraph_list,
    extract_author_generic,
    extract_publish_time_generic,
    extract_summary_from_paragraphs,
    extract_title_generic,
    get_soup,
    save_json,
    now_iso,
    CHART_DIR
)

LISTING_URL = "https://heartresearch.com.au/heart-disease/women-and-heart-disease/"
#["https://heartresearch.com.au/heart-disease/women-and-heart-disease/", 
#https://heartresearch.com.au/heart-hub/
#"https://heartresearch.com.au/heart-disease/heart-conditions/"]
BASE_DIR = Path(__file__).resolve().parent.parent

def collect_article_links() -> list[str]:
    soup = get_soup(LISTING_URL)
    links = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]

        if href.startswith("/heart-disease/"):
            href = f"https://heartresearch.com.au{href}"

        if not href.startswith("https://heartresearch.com.au/heart-disease/"):
            continue

        if "#" in href:
            continue

        #if "/news/20" not in href:
            continue

        if href not in links:
            links.append(href)

    return links

def extract_content_and_summary(soup, title: str) -> tuple[str, str]:
    junk_phrases = [
        "read more",
        "subscribe",
        "newsletter",
        "donate",
        "share this",
        "facebook",
        "instagram",
        "twitter",
        "linkedin",
        "click here",
        "tax deductible",
        "abn",
        "monthly donation",
        "one-off gift",
    ]

    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    cleaned = clean_paragraph_list(paragraphs, junk_phrases=junk_phrases, min_length=40)

    content = "\n".join(cleaned[:15])
    summary = extract_summary_from_paragraphs(cleaned, title)

    return content, summary

def build_article_record(article_url: str, item_id: str) -> dict:
    soup = get_soup(article_url)

    title = extract_title_generic(soup, [" – Heart Research Australia", " - Heart Research Australia"])
    author = extract_author_generic(soup)
    publish_time = extract_publish_time_generic(soup)
    content, summary = extract_content_and_summary(soup, title)

    record = {
        "id": item_id,
        "source": "Heart Research Australia",
        "source_category": "institutional",
        "source_type": "media",
        "source_classification": "factual",
        "url": article_url,
        "title": title,
        "content": content,
        "summary": summary,
        "author": author or None,
        "author_type": "organisation" if author else None,
        "publish_time": publish_time or None,
        "scrape_time": now_iso(),
        "tags": [], #need to be improved later
        "hashtags": [],
        "mentions": [],
        "engagement": {
            "likes": None, 
            "comments": None, 
            "shares": None, 
        },
        "media_type": "text",
        "content_type": "report",
        "language": "en",
    }

    return record

def main() -> None:
    links = collect_article_links()
    print(f"Found {len(links)} possible article links")
    
    records = []
    total_examined = 0
    general_count = 0
    heart_count = 0
    women_heart_count = 0

    if not links:
        print("No article links found.")
        return

    for index, link in enumerate(links[:200], start=1):
        total_examined += 1
        print(f"\nChecking article {index}: {link}")

        try:
            article = build_article_record(link, f"abc_{index:03d}")
        except Exception as error:
            print(f"Error reading article: {error}")
            continue
        
        print("Title:", article["title"])
        
        topic = classify_topic(article["title"] or "", article["content"] or "")
        if topic == "general_health":
            general_count += 1
        elif topic == "heart_health":
            heart_count += 1
        elif topic == "women_heart_health":
            women_heart_count += 1
            records.append(article)

    if records:
        save_json(records, "hra_heart_test")
        print(f"\n Saved {len(records)} articles to JSON")
    else:
        print("\nNo women heart health articles found in first 200 HRA links.")
    
        # print summary
    print("\nScraping Summary:")
    print(f"Total examined: {total_examined}")
    print(f"General health: {general_count}")
    print(f"Heart health: {heart_count}")
    print(f"Women's heart health: {women_heart_count}")
    
    
    # visualisation
    labels = ["general_health", "heart_health", "women_heart_health"]
    values = [general_count, heart_count, women_heart_count]
    
    plt.figure()
    plt.bar(labels, values)
    
    plt.title("Health Research Australia Article Summary")
    plt.xlabel("Category")
    plt.ylabel("Number of Articles")
    
    plt.xticks(rotation=20)
    plt.tight_layout()
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    chart_path = CHART_DIR / "hra_classification_summary_{timestamp}.png"
    plt.savefig(chart_path)
    plt.close()
    
    print(f"Chart saved to: {chart_path}")


if __name__ == "__main__":
    main()