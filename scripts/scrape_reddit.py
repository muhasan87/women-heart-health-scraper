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
        response = requests.get(
            url,
            headers=HEADERS,
            timeout=20,
        )

        print(f"Status: {response.status_code}")

        if response.status_code != 200:
            return None

        html = response.text

        if "prove you are human" in html.lower():
            print("Blocked by Reddit")
            return None

        return BeautifulSoup(html, "html.parser")

    except Exception as error:
        print(f"Request failed: {error}")
        return None


def parse_score(score_text: str) -> int | None:
    if not score_text:
        return None

    score_text = str(score_text).strip().lower()

    if score_text in ["•", "vote", "votes"]:
        return 0

    multiplier = 1

    if "k" in score_text:
        multiplier = 1000
        score_text = score_text.replace("k", "")

    try:
        return int(float(score_text) * multiplier)

    except ValueError:
        return None


def collect_post_links() -> list[str]:
    links = []
    seen = set()

    current_url = SUBREDDIT_URL

    while len(links) < MAX_POSTS and current_url:
        print(f"\nLoading: {current_url}")

        soup = get_soup(current_url)

        if not soup:
            break

        posts = soup.find_all("div", class_="thing")

        print(f"Posts found: {len(posts)}")

        for post in posts:
            permalink = post.get("data-permalink")

            if not permalink:
                continue

            full_url = f"{BASE_DOMAIN}{permalink}"

            if full_url not in seen:
                seen.add(full_url)
                links.append(full_url)

                print(f"Collected: {full_url}")

            if len(links) >= MAX_POSTS:
                break

        next_button = soup.find("span", class_="next-button")

        if not next_button:
            print("No next page button")
            break

        next_link = next_button.find("a")

        if not next_link:
            print("No next page URL")
            break

        current_url = next_link.get("href")

        time.sleep(2)

    return links[:MAX_POSTS]


def extract_post_content(soup: BeautifulSoup) -> str:
    paragraphs = []

    main_post = soup.find(
        "div",
        attrs={"data-type": "link"}
    )

    if not main_post:
        return ""

    expando = main_post.find(
        "div",
        class_="expando"
    )

    if not expando:
        return ""

    usertext = expando.find(
        "div",
        class_="usertext-body"
    )

    if not usertext:
        return ""

    for p in usertext.find_all("p"):
        text = normalise_text(
            p.get_text(" ", strip=True)
        )

        if text:
            paragraphs.append(text)

    cleaned = clean_paragraph_list(
        paragraphs,
        junk_phrases=JUNK_PHRASES,
        min_length=5,
    )

    return "\n".join(cleaned[:10])

#local function since all heart health discussed in this subreddit would technically be womens heart health
def classify_reddit_topic(title: str, content: str) -> str:
    text = f"{title} {content}".lower()

    heart_terms = [
        "heart", "heart disease", "heart attack", "cardiac", "cardiovascular",
        "coronary", "stroke", "blood pressure", "hypertension", "cholesterol", "artery",
        "atherosclerosis", "palpitations", "tachycardia", "arrhythmia", "chest pain",
        "fainting", "shortness of breath", "preeclampsia",
    ]

    has_heart = any(term in text for term in heart_terms)

    if has_heart:
        return "women_heart_health"

    return "general_health"

def build_post_record(
    post_url: str,
    item_id: str,
) -> dict | None:

    soup = get_soup(post_url)

    if not soup:
        return None

    post = soup.find("div", class_="thing")

    if not post:
        print("No post found")
        return None

    title_tag = soup.find("a", class_="title")
    title = (
        normalise_text(
            title_tag.get_text(" ", strip=True)
        )
        if title_tag
        else None
    )
    author_tag = soup.find("a", class_="author")
    author = (
        normalise_text(
            author_tag.get_text(strip=True)
        )
        if author_tag
        else None
    )
    time_tag = soup.find("time")
    publish_time = (
        time_tag.get("datetime")
        if time_tag
        else None
    )
    score = parse_score(
        post.get("data-score", "")
    )
    comments = parse_score(
        post.get("data-comments-count", "")
    )
    content = extract_post_content(soup)
    summary = None

    if content:
        summary = content.split("\n")[0][:300]

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
        "tags": [],
        "hashtags": [],
        "engagement": {
            "likes": score,
            "comments": comments,
            "shares": None,
        },
        "media_type": "text",
        "content_type": "post",
        "language": "en",
    }


def main() -> None:
    records = []

    general_count = 0
    heart_count = 0
    women_heart_count = 0

    print("\n=== Reddit WomensHealth Scraper ===")

    links = collect_post_links()

    print(f"\nFound {len(links)} post links")

    for index, link in enumerate(links, start=1):
        print(f"\nChecking post {index}: {link}")

        try:
            post = build_post_record(
                link,
                f"reddit_wh_{index:03d}",
            )

            if not post:
                continue

        except Exception as error:
            print(f"Error reading post: {error}")
            continue

        print(f"Title: {post['title']}")

        topic = classify_reddit_topic(
            post["title"] or "",
            post["content"] or "",
        )

        if topic == "general_health":
            general_count += 1

        elif topic == "heart_health":
            heart_count += 1

        elif topic == "women_heart_health":
            women_heart_count += 1
            records.append(post)

        time.sleep(1)

    if records:
        save_json(records, "reddit_womenshealth.json")

        print(f"\nSaved {len(records)} posts")

    else:
        print("\nNo women's heart health posts found.")

    print("\nScraping Summary:")
    print(
        f"Total examined: "
        f"{general_count + heart_count + women_heart_count}"
    )

    print(f"General health: {general_count}")
    print(f"Heart health: {heart_count}")
    print(f"Women's heart health: {women_heart_count}")

    labels = [
        "general_health",
        "heart_health",
        "women_heart_health",
    ]

    values = [
        general_count,
        heart_count,
        women_heart_count,
    ]

    plt.figure()

    plt.bar(labels, values)

    plt.title("Reddit WomensHealth Summary")
    plt.xlabel("Category")
    plt.ylabel("Number of Posts")

    plt.xticks(rotation=20)

    plt.tight_layout()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")

    chart_path = (
        CHART_DIR
        / f"reddit_womenshealth_summary_{timestamp}.png"
    )

    plt.savefig(chart_path)
    plt.close()

    print(f"Chart saved to: {chart_path}")


if __name__ == "__main__":
    main()