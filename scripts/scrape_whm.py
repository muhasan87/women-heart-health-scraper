
import re
import matplotlib.pyplot as plt
from datetime import datetime, timezone

import os
import time
import requests
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
    normalise_text,
    save_json,
    now_iso,
    CHART_DIR,
)

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
    return BeautifulSoup(response.text, "html.parser")

BASE_URL    = "https://www.womenshealthmag.com/health/"
BASE_DOMAIN = "https://www.womenshealthmag.com"
MAX_LOAD_MORE_CLICKS = 10
MAX_ARTICLES = 300

JUNK_PHRASES = [
    "advertisement",
    "continue reading below",
    "related stories",
    "shop now",
    "buy now",
    "this content is created",
    "hearst",
    "privacy policy",
    "terms and conditions",
    "meet the experts",
    "read full bio",
    "newsletter",
    "subscribe",
    "follow us",
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


def collect_article_links() -> list[str]:
    driver = get_driver()
    links = []

    try:
        driver.get(BASE_URL)

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located(
                    (By.XPATH, "//a[@data-theme-key='custom-item']")
                )
            )
        except TimeoutException:
            print("  Timed out waiting for articles.")
            return links

        click_num = 0
        while click_num < MAX_LOAD_MORE_CLICKS:
            try:
                see_more = WebDriverWait(driver, 6).until(
                    EC.element_to_be_clickable((
                        By.XPATH,
                        "//button[normalize-space(.)='See More']",
                    ))
                )
                driver.execute_script(
                    "arguments[0].scrollIntoView({block: 'center'});", see_more
                )
                time.sleep(0.5)

                current_count = len(
                    driver.find_elements(By.XPATH, "//a[@data-theme-key='custom-item']")
                )

                try:
                    see_more.click()
                except ElementClickInterceptedException:
                    driver.execute_script("arguments[0].click();", see_more)

                click_num += 1
                print(f"  Clicked 'See More' ({click_num})")

                try:
                    WebDriverWait(driver, 8).until(
                        lambda d: len(
                            d.find_elements(By.XPATH, "//a[@data-theme-key='custom-item']")
                        ) > current_count
                    )
                except TimeoutException:
                    pass

            except TimeoutException:
                print(f"  No more 'See More' button after {click_num} click(s).")
                break

        soup = BeautifulSoup(driver.page_source, "html.parser")

        for a_tag in soup.find_all("a", attrs={"data-theme-key": "custom-item"}):
            href = a_tag.get("href", "").strip()
            if not href:
                continue
            if not href.startswith("http"):
                href = f"{BASE_DOMAIN}{href}"
            if not href.startswith(f"{BASE_DOMAIN}/health/"):
                continue
            skip = ["/author/", "/tag/", "/topic/"]
            if any(s in href for s in skip):
                continue
            if "?page=" in href:
                continue
            if href not in links:
                links.append(href)

        print(f"  Found {len(links)} article links total")

    finally:
        driver.quit()

    return links


def extract_title(soup) -> str:
    h1 = soup.find("h1")
    if h1:
        return normalise_text(h1.get_text(" ", strip=True))
    return ""


def extract_summary(soup) -> str:
    deck = soup.find("div", class_=lambda c: c and "e1f1sunr6" in c)
    if deck:
        p = deck.find("p")
        if p:
            text = normalise_text(p.get_text(" ", strip=True))
            if len(text) > 20:
                return text
    return ""


def extract_author(soup) -> str | None:
    address = soup.find("address")
    if address:
        byline = address.find("span", attrs={"data-theme-key": "by-line-name"})
        if byline:
            a_tag = byline.find("a")
            if a_tag:
                return normalise_text(a_tag.get_text(" ", strip=True)) or None
    return None


def parse_wh_date(raw: str) -> str:
    raw = re.sub(r"^(updated|published)\s*:\s*", "", raw.strip(), flags=re.IGNORECASE)

    raw = re.sub(r"\s+[A-Z]{2,4}$", "", raw.strip())

    for fmt in (
        "%b %d, %Y %I:%M %p",
        "%B %d, %Y %I:%M %p",
        "%b %d, %Y",
        "%B %d, %Y",
    ):
        try:
            dt = datetime.strptime(raw.strip(), fmt)
            return dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        except ValueError:
            continue

    return raw


def extract_publish_time(soup) -> str:
    time_tag = soup.find("time", class_=lambda c: c and "e1f1sunr4" in c)
    if time_tag:
        dt_attr = time_tag.get("datetime", "").strip()
        if dt_attr:
            return dt_attr
        raw = normalise_text(time_tag.get_text(" ", strip=True))
        if raw:
            return parse_wh_date(raw)
    return ""


def extract_content(soup, title: str) -> str:
    body = soup.find(attrs={"data-journey-body": "longform-article"})

    if not body:
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        cleaned = clean_paragraph_list(paragraphs, junk_phrases=JUNK_PHRASES, min_length=40)
        return "\n".join(cleaned[:15])

    for section in body.find_all(
        "section",
        attrs={"data-embed": True, "data-type": True}
    ):
        section.decompose()

    for embed in body.find_all(attrs={"data-embed": True}):
        embed.decompose()

    paragraphs = [p.get_text(" ", strip=True) for p in body.find_all("p")]
    cleaned = clean_paragraph_list(paragraphs, junk_phrases=JUNK_PHRASES, min_length=40)
    return "\n".join(cleaned[:15])


def build_article_record(article_url: str, item_id: str) -> dict:
    soup = get_soup(article_url)

    title        = extract_title(soup)
    author       = extract_author(soup)
    publish_time = extract_publish_time(soup)
    summary      = extract_summary(soup)
    content      = extract_content(soup, title or "")

    if not summary and content:
        paragraphs = content.split("\n")
        summary = extract_summary_from_paragraphs(paragraphs, title or "")

    return { #order needs to be rearranged i think
        "id": item_id,
        "source": "Women's Health",
        "source_category": "news",
        "source_type": "media",
        "source_classification": "mixed",
        "url": article_url,
        "title": title,
        "content": content,
        "summary": summary,
        "author": author or "Women's Health",
        "author_type": "individual" if author else "organisation",
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
        "content_type": "article",
        "language": "en",
    }


def main() -> None:
    links = collect_article_links()
    print(f"\nFound {len(links)} possible article links")

    if not links:
        print("No article links found.")
        return

    records = []
    general_count = 0
    heart_count = 0
    women_heart_count = 0

    for index, link in enumerate(links[:MAX_ARTICLES], start=1):
        print(f"\nChecking article {index}: {link}")

        try:
            article = build_article_record(link, f"wh_{index:03d}")
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

    if records:
        save_json(records, "womenshealth.json")
        print(f"\nSaved {len(records)} articles to womenshealth.json")
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
    plt.title("Women's Health Article Summary")
    plt.xlabel("Category")
    plt.ylabel("Number of Articles")
    plt.xticks(rotation=20)
    plt.tight_layout()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    chart_path = CHART_DIR / f"womenshealth_summary_{timestamp}.png"
    plt.savefig(chart_path)
    plt.close()
    print(f"Chart saved to: {chart_path}")


if __name__ == "__main__":
    main()