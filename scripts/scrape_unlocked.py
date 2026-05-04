import time
import re
import os
import matplotlib.pyplot as plt
from datetime import datetime

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
    now_iso,
    CHART_DIR,
)

BASE_DOMAIN = "https://healthunlocked.com"

COMMUNITIES = [
    {
        "name": "Heart Failure Support",
        "url": "https://healthunlocked.com/arrhythmia-alliance-heart-failure",
        "id_prefix": "hu_hf",
    },
    {
        "name": "Atrial Fibrillation Support",
        "url": "https://healthunlocked.com/afassociation",
        "id_prefix": "hu_afs",
    },
    {
        "name": "Women's Health",
        "url": "https://healthunlocked.com/womenshealth",
        "id_prefix": "hu_wh",
    },
    {
        "name": "Menopause and Perimenopause Support",
        "url": "https://healthunlocked.com/menopause-perimenopause-support",
        "id_prefix": "hu_mps",
    },
    {
        "name": "Cholesterol Support",
        "url": "https://healthunlocked.com/cholesterol-support",
        "id_prefix": "hu_cs",
    }
    
]

MAX_SCROLLS = 6
MAX_POSTS_PER_COMMUNITY = 100

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
        print("  Timed out waiting for post links — page may require login")
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
            print("    Clicked 'See more posts'")
            time.sleep(2)
        except TimeoutException:
            print("    No more 'See more posts' button")
            break


def collect_links(driver: webdriver.Chrome) -> list[str]:
    links = []
    elements = driver.find_elements(
        By.XPATH, "//a[@data-sentry-component='PostLink']"
    )
    for el in elements:
        href = el.get_attribute("href") or ""
        if re.search(r"/posts/\d+/", href) and href not in links:
            links.append(href)
    return links


def extract_post(driver: webdriver.Chrome, url: str) -> tuple[str, str, str, str | None, str | None]:
    driver.get(url)

    wait = WebDriverWait(driver, 10)

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
        publish_time = time_el.get_attribute("datetime") or normalise_text(time_el.text) or None
    except NoSuchElementException:
        pass

    author = None
    try:
        el = driver.find_element(By.CSS_SELECTOR, "button.author")
        candidate = normalise_text(el.text)
        if candidate and candidate.lower() not in ("join or log in", "log in", "join"):
            author = candidate
    except NoSuchElementException:
        pass

    return title, content, summary, publish_time, author


def main() -> None:
    driver = get_driver()

    records = []
    general_count = 0
    heart_count = 0
    women_heart_count = 0
    total_examined = 0

    try:
        for community in COMMUNITIES:
            print(f"\n=== {community['name']} ===")

            load_all_posts(driver, community["url"])
            links = collect_links(driver)
            print(f"  Found {len(links)} post links")

            for index, link in enumerate(links[:MAX_POSTS_PER_COMMUNITY], start=1):
                total_examined += 1
                print(f"\nChecking post {index}: {link}")

                try:
                    title, content, summary, publish_time, author = extract_post(driver, link)
                except Exception as error:
                    print(f"  Error reading post: {error}")
                    continue

                print("  Title:", title)

                topic = classify_topic(title or "", content or "")

                if topic == "general_health":
                    general_count += 1
                elif topic == "heart_health":
                    heart_count += 1
                elif topic == "women_heart_health":
                    women_heart_count += 1

                    record = {
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
                        "author_type": "individual" if author else None,
                        "publish_time": publish_time,
                        "scrape_time": now_iso(),
                        "tags": [],
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

                    records.append(record)

    finally:
        driver.quit()

    if records:
        save_json(records, "healthunlocked.json")
        print(f"\nSaved {len(records)} posts to healthunlocked.json")
    else:
        print("\nNo women's heart health posts found.")

    print("\nScraping Summary:")
    print(f"Total examined: {total_examined}")
    print(f"General health: {general_count}")
    print(f"Heart health: {heart_count}")
    print(f"Women's heart health: {women_heart_count}")

    labels = ["general_health", "heart_health", "women_heart_health"]
    values = [general_count, heart_count, women_heart_count]

    plt.figure()
    plt.bar(labels, values)
    plt.title("HealthUnlocked Post Summary")
    plt.xlabel("Category")
    plt.ylabel("Number of Posts")
    plt.xticks(rotation=20)
    plt.tight_layout()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    chart_path = CHART_DIR / f"healthunlocked_summary_{timestamp}.png"
    plt.savefig(chart_path)
    plt.close()
    print(f"Chart saved to: {chart_path}")


if __name__ == "__main__":
    main()