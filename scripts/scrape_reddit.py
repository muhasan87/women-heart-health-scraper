import os
import time
import requests
import matplotlib.pyplot as plt

from datetime import datetime
from bs4 import BeautifulSoup

from common import (
    classify_topic,
    clean_paragraph_list,
    normalise_text,
    save_json,
    save_stats,
    extract_tags,
    create_stats,
    add_section,
    analyse_sentiment,
    update_stats,
    now_iso,
    CHART_DIR,
)

SUBREDDIT_URL = "https://old.reddit.com/r/WomensHealth/new/"
BASE_DOMAIN = "https://old.reddit.com"

MAX_POSTS = 300

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

JUNK_PHRASES = [
    "reddit",
    "share",
    "award",
    "sort by",
    "moderator",
    "removed",
    "deleted",
]


def get_soup(url: str) -> BeautifulSoup | None:
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)

        if response.status_code != 200:
            return None

        html = response.text

        if "prove you are human" in html.lower():
            return None

        return BeautifulSoup(html, "html.parser")

    except Exception:
        return None


def collect_post_links() -> list[str]:
    links = []
    seen = set()
    current_url = SUBREDDIT_URL

    while len(links) < MAX_POSTS and current_url:
        soup = get_soup(current_url)
        if not soup:
            break

        posts = soup.find_all("div", class_="thing")

        for post in posts:
            permalink = post.get("data-permalink")
            if not permalink:
                continue

            full_url = f"{BASE_DOMAIN}{permalink}"

            if full_url not in seen:
                seen.add(full_url)
                links.append(full_url)

            if len(links) >= MAX_POSTS:
                break

        next_button = soup.find("span", class_="next-button")
        if not next_button or not next_button.find("a"):
            break

        current_url = next_button.find("a").get("href")
        time.sleep(1)

    return links[:MAX_POSTS]


def extract_post_content(soup: BeautifulSoup) -> str:
    paragraphs = []

    main_post = soup.find("div", attrs={"data-type": "link"})
    if not main_post:
        return ""

    usertext = main_post.find("div", class_="usertext-body")
    if not usertext:
        return ""

    for p in usertext.find_all("p"):
        text = normalise_text(p.get_text(" ", strip=True))
        if text:
            paragraphs.append(text)

    cleaned = clean_paragraph_list(
        paragraphs,
        junk_phrases=JUNK_PHRASES,
        min_length=5,
    )

    return "\n".join(cleaned[:10])


def classify_reddit_topic(title: str, content: str) -> str:
    text = f"{title} {content}".lower()

    heart_terms = [
        "heart", "cardiac", "cardiovascular", "coronary",
        "stroke", "blood pressure", "hypertension", "cholesterol",
        "arrhythmia", "chest pain",
    ]

    return "women_heart_health" if any(t in text for t in heart_terms) else "general_health"


def build_post_record(post_url: str, item_id: str) -> dict | None:
    soup = get_soup(post_url)
    if not soup:
        return None

    post = soup.find("div", class_="thing")
    if not post:
        return None

    title_tag = soup.find("a", class_="title")
    title = normalise_text(title_tag.get_text(strip=True)) if title_tag else ""

    author_tag = soup.find("a", class_="author")
    author = normalise_text(author_tag.get_text(strip=True)) if author_tag else None

    time_tag = soup.find("time")
    publish_time = time_tag.get("datetime") if time_tag else None

    content = extract_post_content(soup)
    summary = content.split("\n")[0][:300] if content else ""

    content_for_tags = f"{title or ''} {content or ''}"
    tags = extract_tags(content_for_tags)
    
    return {
        "id": item_id,
        "source": "Reddit",
        "source_category": "forum",
        "source_type": "community",
        "source_classification": "opinion/anecdotal",
        "url": post_url,
        "title": title,
        "content": content,
        "summary": summary,
        "author": author,
        "author_type": "individual",
        "publish_time": publish_time,
        "scrape_time": now_iso(),
        "tags": tags,
        "hashtags": [],
        "engagement": {
            "likes": None,
            "comments": None,
            "shares": None,
        },
        "media_type": "text",
        "content_type": "post",
        "language": "en",
    }


def main() -> None:
    records = []
    stats = create_stats("Reddit r/WomensHealth")
    topics = ["general_health", "heart_health", "women_heart_health"]

    print("\n=== Reddit WomensHealth Scraper ===")

    links = collect_post_links()
    print(f"\nFound {len(links)} post links")

    for index, link in enumerate(links, start=1):
        print(f"\nChecking post {index}: {link}")

        post = build_post_record(link, f"reddit_wh_{index:03d}")
        if not post:
            continue

        topic = classify_reddit_topic(
            post["title"] or "",
            post["content"] or "",
        )
        
        topic = classify_reddit_topic(post["title"] or "", post["content"] or "")
        tags = extract_tags(f"{post['title'] or ''} {post['content'] or ''}")
        sentiment = analyse_sentiment(post["content"] or "")
        update_stats(
            stats,
            topic=topic,
            tags=tags,
            sentiment=sentiment,
            source_classification=post["source_classification"],
            publish_time=post["publish_time"]
        )
        #if topic == "general_health":
            #general_count += 1
        #elif topic == "heart_health":
            #heart_count += 1
        #else:
            #women_heart_count += 1
        if topic == "women_heart_health":
            records.append(post)

        time.sleep(1)

    if records:
        save_json(records, "reddit_womenshealth.json")

    save_stats(stats, "reddit_womenshealth_stats.json")

    print("\nScraping Summary:")
    total = sum(stats["by_topic"].values())
    if total > 0:
        for topic, count in stats["by_topic"].items():
            pct = (count / total) * 100
            print(f"{topic}: {count} ({pct:.1f}%)")

    labels = ["General Health", "Heart Health", "Women's Heart Health"]
    values = [stats["by_topic"][t] for t in topics]

    plt.figure()
    plt.bar(labels, values)
    plt.xticks(["General Health", "Heart Health", "Women's Heart Health"])
    plt.title("Reddit r/WomensHealth Topic Distribution")
    plt.xlabel("Topic")
    plt.ylabel("Number of Posts")
    plt.tight_layout()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    chart_path = CHART_DIR / f"reddit_womenshealth_summary_{timestamp}.png"
    plt.savefig(chart_path)
    plt.close()

    print(f"Chart saved to: {chart_path}")

    total_all = stats["total_examined"]
    overall_womens_heart = stats["by_topic"]["women_heart_health"]
    
    print("\n=== Overall Coverage ===")
    print(f"Total articles: {total_all}")
    print(f"Women's heart health: {overall_womens_heart} ({(overall_womens_heart/total_all)*100:.1f}%)")

if __name__ == "__main__":
    main()