import time
import re
import os
import matplotlib.pyplot as plt
from datetime import datetime
import numpy as np

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

from common import (
    classify_topic,
    clean_paragraph_list,
    extract_summary_from_paragraphs,
    normalise_text,
    save_json,
    save_stats,
    now_iso,
    extract_tags,
    create_stats,
    add_section,
    analyse_sentiment,
    update_stats,
    CHART_DIR,
)

BASE_DOMAIN = "https://healthunlocked.com"

COMMUNITIES = [
    {
        "name": "Heart Failure Support",
        "url": "https://healthunlocked.com/arrhythmia-alliance-heart-failure",
        "id_prefix": "hu_hf",
        "source_classification": "factual",
    },
    {
        "name": "Atrial Fibrillation Support",
        "url": "https://healthunlocked.com/afassociation",
        "id_prefix": "hu_afs",
        "source_classification": "factual",
    },
    {
        "name": "Women's Health",
        "url": "https://healthunlocked.com/womenshealth",
        "id_prefix": "hu_wh",
        "source_classification": "factual",
    },
    {
        "name": "Menopause and Perimenopause Support",
        "url": "https://healthunlocked.com/menopause-perimenopause-support",
        "id_prefix": "hu_mps",
        "source_classification": "factual",
    },
    {
        "name": "Cholesterol Support",
        "url": "https://healthunlocked.com/cholesterol-support",
        "id_prefix": "hu_cs",
        "source_classification": "factual",
    }
]

MAX_SCROLLS = 6
MAX_POSTS_PER_COMMUNITY = 60

JUNK_PHRASES = [
    "we use cookies",
    "our use of cookies",
    "cookie policy",
    "privacy policy",
    "join or log in",
    "content on healthunlocked does not replace",
    "never delay seeking advice",
    "healthunlocked",
    "sign in",
    "register",
    "reply",
    "like",
    "report",
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


def load_all_posts(driver: webdriver.Chrome, url: str) -> None:
    latest_url = f"{url.rstrip('/')}/posts?filter=latest"
    print(f"  Scanning: {latest_url}")

    driver.get(latest_url)
    time.sleep(5)

    wait = WebDriverWait(driver, 15)

    try:
        wait.until(
            EC.presence_of_element_located(
                (By.XPATH, "//a[@data-sentry-component='PostLink']")
            )
        )
    except TimeoutException:
        print("  Timed out waiting for post links")
        return

    for i in range(MAX_SCROLLS):
        print(f"  Scroll {i + 1}")
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)

        try:
            button = wait.until(
                EC.element_to_be_clickable(
                    (By.XPATH, "//button[contains(., 'See more posts')]")
                )
            )
            driver.execute_script("arguments[0].click();", button)
            time.sleep(2)
        except TimeoutException:
            break


def collect_links(driver: webdriver.Chrome) -> list[str]:
    links = []
    elements = driver.find_elements(By.XPATH, "//a[@data-sentry-component='PostLink']")

    for el in elements:
        href = el.get_attribute("href") or ""
        if re.search(r"/posts/\d+/", href) and href not in links:
            links.append(href)

    return links


def extract_post(driver: webdriver.Chrome, url: str):
    driver.get(url)
    wait = WebDriverWait(driver, 5)

    title = ""
    try:
        el = wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='post-heading']"))
        )
        title = normalise_text(el.text)
    except TimeoutException:
        title = url.rstrip("/").split("/")[-1].replace("-", " ").title()

    paragraphs = []
    try:
        body = driver.find_element(By.CSS_SELECTOR, ".js-post-body")
        paragraphs = [p.text.strip() for p in body.find_elements(By.TAG_NAME, "p")]
    except NoSuchElementException:
        paragraphs = [p.text.strip() for p in driver.find_elements(By.TAG_NAME, "p")]

    cleaned = clean_paragraph_list(paragraphs, junk_phrases=JUNK_PHRASES, min_length=30)
    content = "\n".join(cleaned[:15]) if cleaned else ""
    summary = extract_summary_from_paragraphs(cleaned, title) if cleaned else title

    publish_time = None
    try:
        time_el = driver.find_element(By.CSS_SELECTOR, "[data-testid='date-time']")
        publish_time = time_el.get_attribute("datetime") or normalise_text(time_el.text)
    except NoSuchElementException:
        pass

    author = None
    try:
        el = driver.find_element(By.CSS_SELECTOR, "button.author")
        candidate = normalise_text(el.text)
        if candidate.lower() not in ("join or log in", "log in", "join"):
            author = candidate
    except NoSuchElementException:
        pass

    return title, content, summary, publish_time, author


def main() -> None:
    driver = get_driver()

    records = []
    stats = create_stats("Health Unlocked")
    add_section(stats, "Heart Failure Support")
    add_section(stats, "Atrial Fibrillation Support")
    add_section(stats, "Women's Health")
    add_section(stats, "Menopause and Perimenopause Support")
    add_section(stats, "Cholesterol Support")
    
    topics = ["general_health", "heart_health", "women_heart_health"]

    try:
        for community in COMMUNITIES:
            print(f"\n=== {community['name']} ===")

            load_all_posts(driver, community["url"])
            links = collect_links(driver)
            print(f"  Found {len(links)} post links")

            for index, link in enumerate(links[:MAX_POSTS_PER_COMMUNITY], start=1):
                #total_examined += 1

                try:
                    title, content, summary, publish_time, author = extract_post(driver, link)
                except Exception as error:
                    print(f"  Error: {error}")
                    continue

                section_name = community["name"]
                topic = classify_topic(title or "", content or "")
                tags = extract_tags(f"{title or ''} {content or ''}")
                sentiment = analyse_sentiment(content or "")
                update_stats(
                    stats,
                    topic=topic,
                    tags=tags,
                    sentiment=sentiment,
                    source_classification=community["source_classification"],
                    section=section_name,
                    publish_time=publish_time
                )
                if topic == "women_heart_health":
                    #text_for_tags = f"{title or ''} {content or ''}"
                    #tags = extract_tags(text_for_tags)
                    records.append({
                        "id": f"{community['id_prefix']}_{index:03d}",
                        "source": "HealthUnlocked",
                        "source_category": "forum",
                        "source_type": "community",
                        "source_classification": "opinion/anecdotal",
                        "url": link,
                        "title": title,
                        "content": content,
                        "summary": summary,
                        "author": author,
                        "publish_time": publish_time,
                        "scrape_time": now_iso(),
                        "tags": tags,
                        "hashtags": [],
                        "engagement": {"likes": None, "comments": None, "shares": None},
                        "media_type": "text",
                        "content_type": "post",
                        "language": "en",
                    })

    finally:
        driver.quit()

    if records:
        save_json(records, "healthunlocked.json")
        print(f"\nSaved {len(records)} posts")

    save_stats(stats, "healthunlocked_stats.json")

    print("\nScraping Summary:")
    for section_name, counts in stats["by_section"].items():
        total = sum(counts.values())
        if total == 0:
            continue

        print(f"\n{section_name.upper()}")
        for k, v in counts.items():
            pct = (v / total) * 100
            print(f"  {k}: {v} ({pct:.1f}%)")

    heartf_vals = [stats["by_section"]["Heart Failure Support"][t] for t in topics]
    atrial_vals = [stats["by_section"]["Atrial Fibrillation Support"][t] for t in topics]
    womens_vals = [stats["by_section"]["Women's Health"][t] for t in topics]
    menopause_vals = [stats["by_section"]["Menopause and Perimenopause Support"][t] for t in topics]
    cholesterol_vals = [stats["by_section"]["Cholesterol Support"][t] for t in topics]

    x = np.arange(len(topics))
    plt.figure()
    plt.bar(x, heartf_vals, label="Heart Failure Support")
    plt.bar(x, atrial_vals, label="Atrial Fibrillation Support")
    plt.bar(x, womens_vals, label="Women's Health")
    plt.bar(x, menopause_vals, label="Menopause and Perimenopause Support")
    plt.bar(x, cholesterol_vals, label="Cholesterol Support")
    
    plt.xticks(x, ["General Health", "Heart Health", "Women's Heart Health"])
    plt.title("HealthUnlocked Topic Distribution")
    plt.xlabel("Topic")
    plt.ylabel("Posts")
    plt.tight_layout()

    ts = datetime.now().strftime("%Y%m%d_%H%M")
    chart_path = CHART_DIR / f"healthunlocked_summary_{ts}.png"
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