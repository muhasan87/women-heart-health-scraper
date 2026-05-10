import time
import matplotlib.pyplot as plt
from datetime import datetime
import os

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException
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
    save_stats,
    save_json,
    create_stats,
    add_section,
    analyse_sentiment,
    update_stats,
    get_soup,
    save_json,
    now_iso,
    CHART_DIR,
)

LISTING_URL = "https://www.heartfoundation.org.au/media-releases"
BASE_DOMAIN = "https://www.heartfoundation.org.au"
MAX_PAGES = 10
MAX_ARTICLES = 200


def collect_article_links() -> list[str]:
    options = Options()
    os.makedirs("./selenium_cache", exist_ok=True)
    os.environ["SE_CACHE_PATH"] = "./selenium_cache"
    options.add_argument("--headless=new")
    options.add_argument("--window-size=1400,2200")

    driver = webdriver.Chrome(options=options)
    wait = WebDriverWait(driver, 10)
    links = []

    try:
        driver.get(LISTING_URL)
        time.sleep(2)

        for page_num in range(1, MAX_PAGES + 1):
            print(f"Scraping page {page_num}...")

            soup = BeautifulSoup(driver.page_source, "lxml")
            found_on_page = 0

            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]

                if href.startswith("/"):
                    href = f"{BASE_DOMAIN}{href}"

                if not href.startswith(BASE_DOMAIN):
                    continue

                if not any(
                    segment in href
                    for segment in ["/media-releases/", "/news-media/", "/articles/"]
                ):
                    continue

                if "#" in href or href == LISTING_URL:
                    continue

                if href not in links:
                    links.append(href)
                    found_on_page += 1

            print(f"  Found {found_on_page} new links on page {page_num} ({len(links)} total)")

            try:
                next_button = wait.until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        (
                            "//button[@aria-label='Go to next page' or @aria-label='next' or contains(@class,'next')]"
                            " | //a[@aria-label='Next page' or @aria-label='next' or contains(@class,'next')]"
                            " | //li[contains(@class,'next')]/a"
                        ),
                    ))
                )

                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", next_button
                )
                time.sleep(0.5)

                try:
                    next_button.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", next_button)

                time.sleep(2)

            except TimeoutException:
                print("No next page button found — reached last page.")
                break

    finally:
        driver.quit()

    return links


def extract_content_and_summary(soup, title: str) -> tuple[str, str]:
    junk_phrases = [
        "read more",
        "subscribe",
        "newsletter",
        "donate",
        "share this",
        "media contact",
        "for more information",
        "about heart foundation",
        "heart foundation is",
        "click here",
        "follow us",
        "sign up",
        "learn more",
    ]

    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    cleaned = clean_paragraph_list(paragraphs, junk_phrases=junk_phrases, min_length=40)

    content = "\n".join(cleaned[:15]) if cleaned else ""
    summary = extract_summary_from_paragraphs(cleaned, title)

    return content, summary


def build_article_record(article_url: str, item_id: str) -> dict:
    soup = get_soup(article_url)

    title = extract_title_generic(
        soup, [" | Heart Foundation", " - Heart Foundation", " – Heart Foundation"]
    )
    author = extract_author_generic(soup)
    publish_time = extract_publish_time_generic(soup)
    content, summary = extract_content_and_summary(soup, title or "")

    text_for_tags = f"{title or ''} {content or ''}"
    tags = extract_tags(text_for_tags)

    return {
        "id": item_id,
        "source": "Heart Foundation",
        "source_category": "institutional",
        "source_type": "organisation",
        "source_classification": "factual",
        "url": article_url,
        "title": title,
        "content": content,
        "summary": summary,
        "author": author or None,
        "author_type": "organisation" if author else None,
        "publish_time": publish_time or None,
        "scrape_time": now_iso(),
        "tags": tags,
        "hashtags": [],
        "engagement": {
            "likes": None,
            "comments": None,
            "shares": None,
        },
        "media_type": "text",
        "content_type": "media_release",
        "language": "en",
    }


def main() -> None:
    links = collect_article_links()
    print(f"\nFound {len(links)} possible article links.")

    if not links:
        print("No article links found.")
        return

    records = []
    stats = create_stats("Heart Foundation")
    topics = ["general_health", "heart_health", "women_heart_health"]

    for index, link in enumerate(links[:MAX_ARTICLES], start=1):
        print(f"\nChecking article {index}: {link}")

        try:
            article = build_article_record(link, f"hf_{index:03d}")
        except Exception as error:
            print(f"Error reading article: {error}")
            continue

        print("Title:", article["title"])

        #topic = classify_topic(article["title"] or "", article["content"] or "")
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
        
        if topic == "women_heart_health":
            records.append(article)

    if records:
        save_json(records, "heartfoundation.json")
        print(f"\nSaved {len(records)} articles to heartfoundation.json")
    else:
        print("\nNo women's heart health articles found.")

    save_stats(stats, "hf_stats.json")
    #total_examined = general_count + heart_count + women_heart_count

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
    plt.title("Heart Foundation Topic Distribution")
    plt.xlabel("Topic")
    plt.ylabel("Number of Articles")
    plt.tight_layout()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    chart_path = CHART_DIR / f"heartfoundation_summary_{timestamp}.png"
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