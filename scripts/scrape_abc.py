import json
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
    now_iso
)

LISTING_URL = "https://www.abc.net.au/news/topic/heart-disease"

BASE_DIR = Path(__file__).resolve().parent.parent
#OUTPUT_DIR = BASE_DIR / "data" / "json"
#OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

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


def extract_content_and_summary(soup, title: str) -> tuple[str, str]:
    junk_phrases = [
        "find any issues using dark mode",
        "please let us know",
        "do you have a story to share",
        "email",
        "read more",
        "skip to",
        "listen",
        "posted",
        "share this article",
        "loading",
    ]

    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    cleaned = clean_paragraph_list(paragraphs, junk_phrases=junk_phrases)

    content = "\n".join(cleaned[:15]) if cleaned else ""
    summary = extract_summary_from_paragraphs(cleaned, title)

    return content, summary

#def is_heart_related(title: str, content: str) -> bool:
    text = f"{title} {content}".lower() #needs to be integrated into common.py eventually
    heart_keywords = [
        "heart", "cardio", "cardiovascular", "stroke", 
        "blood pressure", "cardiac", "coronary", "hypertension",
        "cholesterol", "artery", "heart disease", "heart attack"
    ]
    women_keywords = [
        "women", "woman", "female", "menopause", "pregnancy",
        "pregnant", "postpartum", "gender", "sex", "disparity"
    ]
    exclusions = [
        "vaccin", "immunis", "flu", "covid"
    ]
    
    has_heart = any(k in text for k in heart_keywords)
    has_women = any(w in text for w in women_keywords)
    has_exclusion = any(exc in text for exc in exclusions)
    
    return has_heart and has_women and not has_exclusion


def build_article_record(article_url: str, item_id: str) -> dict:
    soup = get_soup(article_url)

    #is_heart = is_heart_health_related(title or "", content or "")
    title = extract_title_generic(soup)
    author = extract_author_generic(soup)
    publish_time = extract_publish_time_generic(soup)
    content, summary = extract_content_and_summary(soup, title or "")

    record = {
        "id": item_id,
        "source": "ABC News",
        "source_category": "news",
        "source_type": "media",
        "source_classification": "factual",
        "url": article_url,
        "title": title,
        "content": content,
        "summary": summary,
        "author": author or None,
        "author_type": "individual" if author else None,
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
        "content_type": "article",
        "language": "en",
    }

    return record



#def save_json(record: dict, filename: str) -> None:
    output_path = OUTPUT_DIR / filename
    with open(output_path, "w", encoding="utf-8") as file:
        json.dump(record, file, indent=2, ensure_ascii=False)


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

    print("\nFirst 10 candidate links:")
    for i, link in enumerate(links[:10], start=1):
        print(f"{i}. {link}")

    matched_article = None

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
        save_json(records, "abcnews_heart_test")
        print(f"\n Saved {len(records)} articles to JSON")

    #if matched_article:
        #save_json(matched_article, "abc_heart_sample.json")
        #print("\nSaved article to data/json/abc_heart_sample.json")
        #print("Title:", matched_article["title"])
        #print("URL:", matched_article["url"])
        #print("Topic:", matched_article["topic"])
    else:
        print("\nNo women heart health articles found in first 200 ABC links.")
    
    #notes:
    # - currently only scrapes 22 articles (front page), need to use APIs to scrape more
    
    # print summary
    print("\nScraping Summary:")
    print(f"Total examined: {total_examined}")
    print(f"General health: {general_count}")
    print(f"Heart health: {heart_count}")
    print(f"Women's heart health: {women_heart_count}")


if __name__ == "__main__":
    main()