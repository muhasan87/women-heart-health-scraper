# scrape_healthboards.py
import os
import re
import time
import matplotlib.pyplot as plt
from datetime import datetime

from bs4 import BeautifulSoup
import undetected_chromedriver as uc

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

from common import (
    classify_topic,
    clean_paragraph_list,
    extract_summary_from_paragraphs,
    normalise_text,
    extract_tags,
    save_stats,
    save_json,
    now_iso,
    CHART_DIR,
)

BASE_URL = "https://www.healthboards.com/boards/heart-disorders/"
BASE_DOMAIN = "https://www.healthboards.com"

MAX_PAGES = 50
MAX_THREADS = 300
DELAY = 2

JUNK_PHRASES = [
    "reply with quote",
    "click to expand",
    "originally posted by",
    "advertisement",
    "all times are gmt",
    "powered by vbulletin",
    "copyright",
    "healthboards.com",
    "sign up",
    "log in",
    "privacy policy",
    "terms of service",
    "contact us",
    "archive",
    "top",
]


def get_driver():

    os.makedirs("./selenium_cache", exist_ok=True)
    os.environ["SE_CACHE_PATH"] = "./selenium_cache"

    options = webdriver.ChromeOptions()

    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")

    options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )

    return webdriver.Chrome(options=options)


def get_soup(driver, url: str) -> BeautifulSoup:
    driver.get(url)
    time.sleep(3)

    html = driver.page_source
    return BeautifulSoup(html, "html.parser")

def parse_hb_date(raw: str) -> str:
    match = re.search(
        r"(\d{2}-\d{2}-\d{4}),?\s*(\d{1,2}:\d{2}\s*[AP]M)",
        raw,
        re.IGNORECASE,
    )

    if match:
        date_part = match.group(1)
        time_part = match.group(2).strip().upper()

        try:
            dt = datetime.strptime(
                f"{date_part} {time_part}",
                "%m-%d-%Y %I:%M %p"
            )

            return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

        except Exception:
            pass

    return raw.strip()

def build_listing_url(page: int) -> str:
    if page == 1:
        return BASE_URL

    return f"{BASE_URL}index{page}.html"


def collect_thread_stubs(driver, max_pages: int = MAX_PAGES) -> list[dict]:
    stubs = []
    seen_urls = set()

    url = BASE_URL
    page_num = 1

    while url and page_num <= max_pages:
        print(f"\nListing page {page_num}: {url}")

        driver.get(url)
        time.sleep(5)

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # DEBUG
        print("Page title:", soup.title.text if soup.title else "No title")

        thread_links = soup.find_all(
            "a",
            id=lambda x: x and x.startswith("thread_title_")
        )

        print(f"  Found {len(thread_links)} threads")

        if not thread_links:
            print("  No threads found — stopping")
            break

        for a_tag in thread_links:
            href = a_tag.get("href", "").strip()

            if not href:
                continue

            if not href.startswith("http"):
                href = f"{BASE_DOMAIN}{href}"

            if href in seen_urls:
                continue

            seen_urls.add(href)

            title = normalise_text(a_tag.get_text(" ", strip=True))

            thread_id = a_tag["id"].replace("thread_title_", "")

            td_title = soup.find("td", id=f"td_threadtitle_{thread_id}")

            op_author = ""
            replies = None
            views = None

            if td_title:
                author_div = td_title.find("div", class_="smallfont")

                if author_div:
                    op_author = normalise_text(author_div.get_text(" ", strip=True))

                parent_tr = td_title.find_parent("tr")

                if parent_tr:
                    stats_td = parent_tr.find(
                        "td",
                        title=lambda x: x and "Replies:" in x
                    )

                    if stats_td:
                        stats_text = stats_td.get("title", "")

                        match = re.search(
                            r"Replies:\s*([\d,]+),\s*Views:\s*([\d,]+)",
                            stats_text,
                        )

                        if match:
                            replies = int(match.group(1).replace(",", ""))
                            views = int(match.group(2).replace(",", ""))

            stubs.append({
                "url": href,
                "title": title,
                "op_author": op_author,
                "replies": replies,
                "views": views,
            })

        # NEXT PAGE
        next_link = soup.find("a", rel="next")

        if next_link:
            next_href = next_link.get("href", "").strip()

            if not next_href.startswith("http"):
                next_href = f"{BASE_DOMAIN}{next_href}"

            url = next_href
        else:
            url = None

        page_num += 1
        time.sleep(DELAY)

    print(f"\nCollected {len(stubs)} thread stubs total")
    return stubs

def extract_first_post(soup):

    post_td = soup.find(
        "td",
        id=lambda x: x and x.startswith("td_post_")
    )

    if not post_td:
        return "", "", ""

    post_id = post_td["id"].replace("td_post_", "")

    # content
    content = ""

    message_div = soup.find(
        "div",
        id=f"post_message_{post_id}"
    )

    if message_div:

        for br in message_div.find_all("br"):
            br.replace_with("\n")

        raw_text = message_div.get_text("\n", strip=False)

        paragraphs = [
            p.strip()
            for p in raw_text.split("\n")
            if p.strip()
        ]

        cleaned = clean_paragraph_list(
            paragraphs,
            junk_phrases=JUNK_PHRASES,
            min_length=20,
        )

        content = "\n".join(cleaned[:20])

    # author
    author = ""

    author_div = soup.find(
        "div",
        id=f"postmenu_{post_id}"
    )

    if author_div:
        author = normalise_text(
            author_div.get_text(strip=True)
        )

    publish_time = ""

    post_row = post_td.find_parent("tr")

    if post_row:
        prev_row = post_row.find_previous_sibling("tr")

        if prev_row:
            thead_td = prev_row.find("td", class_="thead")

            if thead_td:
                raw_date = normalise_text(
                    thead_td.get_text(" ", strip=True)
                )
                publish_time = parse_hb_date(raw_date)

    return content, author, publish_time


def build_record(driver, stub: dict, item_id: str):
    soup = get_soup(driver, stub["url"])
    h1 = soup.find("h1")
    title = (
        normalise_text(h1.get_text(" ", strip=True))
        if h1 else stub["title"]
    )
    content, author, publish_time = extract_first_post(soup)
    summary = extract_summary_from_paragraphs(
        content.split("\n"),
        title
    ) if content else title
    
    content_for_tags = f"{title or ''} {content or ''}"
    tags = extract_tags(content_for_tags)

    return {
        "id": item_id,
        "source": "HealthBoards",
        "source_category": "community",
        "source_type": "forum",
        "source_classification": "user_generated",
        "url": stub["url"],
        "title": title,
        "content": content,
        "summary": summary,
        "author": author or stub["author"] or None,
        "author_type": "individual",
        "publish_time": publish_time or None,
        "scrape_time": now_iso(),
        "tags": tags,
        "hashtags": [],
        "mentions": [],
        "engagement": {
            "likes": None,
            "comments": stub["replies"],
            "shares": None,
            "views": stub["views"],
        },
        "media_type": "text",
        "content_type": "post",
        "language": "en",
    }


def main():
    driver = get_driver()
    try:
        stubs = collect_thread_stubs(driver)

        if not stubs:
            print("No threads found")
            return
        records = []
        
        stats = {
            "general_health": 0,
            "heart_health": 0,
            "women_heart_health": 0,
        }

        general_count = 0
        heart_count = 0
        women_heart_count = 0

        for index, stub in enumerate(stubs[:MAX_THREADS], start=1):
            print(f"\nChecking thread {index}: {stub['url']}")

            try:
                record = build_record(
                    driver,
                    stub,
                    f"hb_{index:04d}"
                )

            except Exception as error:
                print(f"  Error scraping thread: {error}")
                continue

            print(f"  Title: {record['title']}")

            topic = classify_topic(
                record["title"] or "",
                record["content"] or ""
            )

            if topic == "general_health":
                general_count += 1
                stats["general_health"] += 1

            elif topic == "heart_health":
                heart_count += 1
                stats["heart_health"] += 1

            elif topic == "women_heart_health":
                women_heart_count += 1
                stats["women_heart_health"] += 1
                records.append(record)

                print(
                    f"  ✓ Saved women's heart health thread "
                    f"({len(records)} total)"
                )

            time.sleep(DELAY)

        if records:

            save_json(records, "healthboards.json")
            
            save_stats(
                {
                    "source": "HealthBoards",
                    "total_examined": len(stubs),
                    "by_topic": stats,
                },
                "healthboards_stats.json",
            )

            print(
                f"\nSaved {len(records)} records "
                f"to healthboards.json"
            )

        else:
            print("\nNo women's heart health threads found.")

        # summary
        total = (
            general_count
            + heart_count
            + women_heart_count
        )

        total = len(stubs)

        print("\nScraping Summary:")
        print(f"Total examined: {total}")
        print(f"General health: {stats['general_health']}")
        print(f"Heart health: {stats['heart_health']}")
        print(f"Women's heart health: {stats['women_heart_health']}")

        # chart
        labels = [
            "general_health",
            "heart_health",
            "women_heart_health"
        ]

        values = [
            stats["general_health"],
            stats["heart_health"],
            stats["women_heart_health"]
        ]

        plt.figure()
        plt.bar(labels, values)

        plt.title("HealthBoards Summary")
        plt.xlabel("Category")
        plt.ylabel("Number of Threads")

        plt.xticks(rotation=20)
        plt.tight_layout()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M")

        chart_path = (
            CHART_DIR
            / f"healthboards_summary_{timestamp}.png"
        )

        plt.savefig(chart_path)
        plt.close()

        print(f"\nChart saved to: {chart_path}")

    finally:
        driver.quit()


if __name__ == "__main__":
    main()