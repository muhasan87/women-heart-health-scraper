import os
import re
import time
import matplotlib.pyplot as plt
from datetime import datetime, timezone

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from common import (
    classify_topic,
    clean_paragraph_list,
    extract_summary_from_paragraphs,
    extract_title_generic,
    normalise_text,
    save_json,
    now_iso,
    CHART_DIR,
)

NEWS_URL    = "https://www.jeanhailes.org.au/latest-news/"
STORIES_URL = "https://www.jeanhailes.org.au/stories/"
BASE_DOMAIN = "https://www.jeanhailes.org.au"
MAX_ARTICLES = 300

SECTIONS = [
    {
        "name": "news",
        "url": NEWS_URL,
        "link_path": "/articles/", 
        "content_type": "article",
        "source_classification": "factual",
        "id_prefix": "jh_news",
    },
    {
        "name": "stories",
        "url": STORIES_URL,
        "link_path": "/stories/",
        "content_type": "post",
        "source_classification": "opinion/anecdotal",
        "id_prefix": "jh_story",
    },
]

JUNK_PHRASES = [
    "read more",
    "load more",
    "subscribe",
    "newsletter",
    "donate",
    "share this",
    "click here",
    "follow us",
    "sign up",
    "jean hailes is",
    "about jean hailes",
    "our supporters",
    "privacy policy",
    "terms of use",
    "back to top",
    "this information has been",
    "reviewed by",
    "last updated",
]


def get_driver() -> webdriver.Chrome:
    os.makedirs("./selenium_cache", exist_ok=True)
    os.environ["SE_CACHE_PATH"] = "./selenium_cache"

    options = webdriver.ChromeOptions()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument(
        "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    return webdriver.Chrome(options=options)


def remaining_count_from_button(driver: webdriver.Chrome) -> int:
    try:
        btn = driver.find_element(By.CSS_SELECTOR, "button.c-post-filters__load-more")
        match = re.search(r"\((\d+)\)", btn.text)
        return int(match.group(1)) if match else 0
    except Exception:
        return 0


def collect_article_links(listing_url: str, link_path: str) -> list[str]:
    driver = get_driver()
    links = []

    try:
        driver.get(listing_url)

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(
                    (By.XPATH, f"//a[contains(@href, '{link_path}')]")
                )
            )
        except TimeoutException:
            print(f"  Timed out waiting for links at {listing_url}")
            return links

        click_num = 0
        while True:
            remaining = remaining_count_from_button(driver)
            if remaining == 0:
                print(f"  No more articles to load (clicked {click_num} time(s))")
                break

            print(f"  {remaining} articles remaining — clicking Load more ({click_num + 1})")

            try:
                btn = WebDriverWait(driver, 8).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "button.c-post-filters__load-more")
                    )
                )
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", btn
                )
                time.sleep(0.3)
                try:
                    btn.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", btn)

                click_num += 1

                current_count = len(
                    driver.find_elements(By.XPATH, f"//a[contains(@href, '{link_path}')]")
                )
                try:
                    WebDriverWait(driver, 8).until(
                        lambda d: len(
                            d.find_elements(By.XPATH, f"//a[contains(@href, '{link_path}')]")
                        ) > current_count
                    )
                except TimeoutException:
                    pass

            except TimeoutException:
                print("  Load more button not clickable — stopping.")
                break

        soup = BeautifulSoup(driver.page_source, "html.parser")

        for a_tag in soup.find_all("a", href=True):
            href = a_tag["href"].strip()
            if not href.startswith("http"):
                href = f"{BASE_DOMAIN}{href}"
            if link_path in href and href not in links:
                links.append(href)

        print(f"  Found {len(links)} links")

    finally:
        driver.quit()

    return links


def extract_date(soup: BeautifulSoup) -> str:
    raw = ""
    for div in soup.find_all("div", class_=lambda c: c and "font-medium" in c):
        if "date added" in div.get_text(strip=True).lower():
            sibling = div.find_next_sibling("div")
            if sibling:
                raw = normalise_text(sibling.get_text(strip=True))
                break

    if not raw:
        return ""

    # Try known Jean Hailes date formats: "April 21 2026", "21 April 2026"
    for fmt in ("%B %d %Y", "%d %B %Y", "%B %d, %Y"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%dT00:00:00.000Z")
        except ValueError:
            continue

    return raw


def extract_summary_from_html(soup: BeautifulSoup) -> str:
    for div in soup.find_all("div", class_=lambda c: c and "c-post-content" in c):
        inner = div.find("div", class_=lambda c: c and "title-t" in c)
        if inner:
            paragraphs = [p.get_text(" ", strip=True) for p in inner.find_all("p")]
            cleaned = [p for p in paragraphs if len(p) > 40]
            if cleaned:
                return cleaned[0]
    return ""


def extract_content_from_html(soup: BeautifulSoup, title: str) -> str:
    paragraphs = []
    for div in soup.find_all("div", class_=lambda c: c and "o-type--wysiwyg-lg" in c):
        for p in div.find_all("p"):
            text = p.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)

    if not paragraphs:
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]

    cleaned = clean_paragraph_list(paragraphs, junk_phrases=JUNK_PHRASES, min_length=40)
    return "\n".join(cleaned[:15]) if cleaned else ""


def extract_content_and_summary(soup: BeautifulSoup, title: str) -> tuple[str, str]:
    summary = extract_summary_from_html(soup)
    content = extract_content_from_html(soup, title)

    if not summary and content:
        first_para = content.split("\n")[0]
        summary = first_para if first_para != title else ""

    return content, summary


def build_article_record(
    driver: webdriver.Chrome,
    article_url: str,
    item_id: str,
    content_type: str,
    source_classification: str,
) -> dict:
    driver.get(article_url)

    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )
    except TimeoutException:
        pass

    soup = BeautifulSoup(driver.page_source, "html.parser")

    title_tag = soup.find("h1", class_=lambda c: c and "title-t" in c)
    if title_tag:
        title = normalise_text(title_tag.get_text(" ", strip=True))
    else:
        title = extract_title_generic(
            soup,
            [" | Jean Hailes", " - Jean Hailes", " – Jean Hailes",
             " | Jean Hailes for Women's Health"],
        )

    author = None
    author_type = None
    if content_type == "article":
        for li in soup.find_all("li"):
            label = li.find("div", class_=lambda c: c and "font-medium" in c)
            if label and "author" in label.get_text(strip=True).lower():
                value = label.find_next_sibling("div")
                if value:
                    candidate = normalise_text(value.get_text(strip=True))
                    if candidate:
                        author = candidate
                        author_type = "individual"
                        break

    if not author:
        author = "Jean Hailes"
        author_type = "organisation"

    publish_time = extract_date(soup)
    content, summary = extract_content_and_summary(soup, title or "")

    return {
        "id": item_id,
        "source": "Jean Hailes",
        "source_category": "website",
        "source_type": "organisation",
        "source_classification": source_classification,
        "url": article_url,
        "title": title,
        "content": content,
        "summary": summary,
        "author": author,
        "author_type": author_type,
        "publish_time": publish_time or None,
        "scrape_time": now_iso(),
        "tags": [],
        "hashtags": [],
        "engagement": {
            "likes": None,
            "comments": None,
            "shares": None,
        },
        "media_type": "text",
        "content_type": content_type,
        "language": "en",
    }


def main() -> None:
    records = []
    general_count = 0
    heart_count = 0
    women_heart_count = 0

    driver = get_driver()

    try:
        for section in SECTIONS:
            print(f"\n=== Jean Hailes — {section['name'].title()} ===")

            links = collect_article_links(section["url"], section["link_path"])

            if not links:
                print(f"  No links found for {section['name']} section.")
                continue

            print(f"\nFirst 3 links:")
            for link in links[:3]:
                print(f"  {link}")

            for index, link in enumerate(links[:MAX_ARTICLES], start=1):
                print(f"\nChecking {section['name']} {index}: {link}")

                try:
                    article = build_article_record(
                        driver,
                        link,
                        f"{section['id_prefix']}_{index:03d}",
                        section["content_type"],
                        section["source_classification"],
                    )
                except Exception as error:
                    print(f"  Error reading article: {error}")
                    continue

                print(f"  Title: {article['title']}")

                topic = classify_topic(article["title"] or "", article["content"] or "")

                if topic == "general_health":
                    general_count += 1
                elif topic == "heart_health":
                    heart_count += 1
                elif topic == "women_heart_health":
                    women_heart_count += 1
                    records.append(article)

    finally:
        driver.quit()

    if records:
        save_json(records, "jeanhailes.json")
        print(f"\nSaved {len(records)} articles to jeanhailes.json")
    else:
        print("\nNo women's heart health articles found.")

    print("\nScraping Summary:")
    print(f"Total examined: {general_count + heart_count + women_heart_count}")
    print(f"General health: {general_count}")
    print(f"Heart health: {heart_count}")
    print(f"Women's heart health: {women_heart_count}")

    labels = ["general_health", "heart_health", "women_heart_health"]
    values = [general_count, heart_count, women_heart_count]

    plt.figure()
    plt.bar(labels, values)
    plt.title("Jean Hailes Article Summary")
    plt.xlabel("Category")
    plt.ylabel("Number of Articles")
    plt.xticks(rotation=20)
    plt.tight_layout()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    chart_path = CHART_DIR / f"jeanhailes_summary_{timestamp}.png"
    plt.savefig(chart_path)
    plt.close()
    print(f"Chart saved to: {chart_path}")


if __name__ == "__main__":
    main()