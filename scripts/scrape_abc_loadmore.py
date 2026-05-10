import time
import os
import matplotlib.pyplot as plt
from datetime import datetime
from pathlib import Path

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import (
    TimeoutException,
    ElementClickInterceptedException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from common import (
    classify_topic,
    clean_paragraph_list,
    extract_author_generic,
    extract_publish_time_generic,
    extract_summary_from_paragraphs,
    extract_title_generic,
    extract_tags,
    get_soup,
    save_stats,
    save_json,
    create_stats,
    add_section,
    analyse_sentiment,
    update_stats,
    now_iso,
    CHART_DIR,
)

BASE_URL = "https://www.abc.net.au/news/health"

MAX_LOAD_MORE_ROUNDS = 15
MAX_ARTICLES = 300

ABCTEST_CHART_DIR = CHART_DIR / "abc_charts"
ABCTEST_CHART_DIR.mkdir(parents=True, exist_ok=True)


def get_listing_soup_with_load_more() -> BeautifulSoup:
    options = Options()
    os.makedirs("./selenium_cache", exist_ok=True)
    os.environ["SE_CACHE_PATH"] = "./selenium_cache"
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1400,2200")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 10)

    try:
        driver.get(BASE_URL)
        time.sleep(2)

        rounds = 0

        while rounds < MAX_LOAD_MORE_ROUNDS:
            try:
                load_more = wait.until(
                    EC.element_to_be_clickable(
                        (
                            By.XPATH,
                            "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'load more')]"
                            " | //a[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'load more')]"
                        )
                    )
                )

                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", load_more
                )
                time.sleep(1)

                try:
                    load_more.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", load_more)

                rounds += 1
                print(f"Clicked load more: round {rounds}")
                time.sleep(2)

            except TimeoutException:
                print("No more load more button found.")
                break

        return BeautifulSoup(driver.page_source, "lxml")

    finally:
        driver.quit()


def collect_article_links() -> list[str]:
    soup = get_listing_soup_with_load_more()
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


def build_article_record(article_url: str, item_id: str) -> dict:
    soup = get_soup(article_url)

    title = extract_title_generic(soup)
    author = extract_author_generic(soup)
    publish_time = extract_publish_time_generic(soup)
    content, summary = extract_content_and_summary(soup, title or "")

    text_for_tags = f"{title or ''} {content or ''}"
    tags = extract_tags(text_for_tags)

    return {
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
        "tags": tags,
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


def main() -> None:
    links = collect_article_links()
    print(f"Found {len(links)} possible article links after load more.")

    if not links:
        print("No article links found.")
        return

    records = []
    stats = create_stats("ABC News")
    topics = ["general_health", "heart_health", "women_heart_health"]

    for index, link in enumerate(links[:MAX_ARTICLES], start=1):
        print(f"\nChecking article {index}: {link}")

        try:
            article = build_article_record(link, f"abc_{index:03d}")
        except Exception as error:
            print(f"Error reading article: {error}")
            continue

        #topic_raw = classify_topic(article["title"] or "", article["content"] or "")
        #topic = topic_map.get(topic_raw)
        topic = classify_topic(article["title"] or "", article["content"] or "")
        tags = extract_tags(f"{article['title'] or ''} {article['content'] or ''}")
        sentiment = analyse_sentiment(article["content"] or "")
        update_stats(
            stats,
            topic=topic,
            tags=tags,
            sentiment=sentiment,
            source_classification=article["source_classification"],
            publish_time=article["publish_time"]
        )

        if topic == "women_heart":
            records.append(article)

    if records:
        save_json(records, "abc_news.json")
        print(f"\nSaved {len(records)} women heart health articles to abc_news.json")

    save_stats(stats, "abcnews_stats.json")
    
    print("\nScraping Summary:")
    total = sum(stats["by_topic"].values())
    if total > 0:
        for topic, count in stats["by_topic"].items():
            pct = (count / total) * 100
            print(f"{topic}: {count} ({pct:.1f}%)")
    
    #print(f"Total saved: {len(records)}")

    labels = ["General Health", "Heart Health", "Women's Heart Health"]
    values = [stats["by_topic"][t] for t in topics]
    #total = sum(stats.values())

    #for k, v in stats.items():
        #pct = (v / total) * 100 if total else 0
        #print(f"{k.replace('_', ' ').title()}: {v} ({pct:.1f}%)")
    plt.figure()
    plt.bar(labels, values)
    plt.xticks(["General Health", "Heart Health", "Women's Heart Health"])
    plt.title("ABC News Health Topic Distribution")
    plt.xlabel("Topic")
    plt.ylabel("Number of Articles")
    plt.tight_layout()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    chart_path = CHART_DIR / f"abc_news_summary_{timestamp}.png"

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