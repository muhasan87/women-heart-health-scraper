import re
import time
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timezone
from bs4 import BeautifulSoup

from common import (
    classify_topic,
    clean_paragraph_list,
    extract_publish_time_generic,
    extract_title_generic,
    extract_tags,
    normalise_text,
    save_json,
    now_iso,
    save_stats,
    create_stats,
    add_section,
    analyse_sentiment,
    update_stats,
    CHART_DIR,
    HEADERS,
    get_soup,
)

HUB_URL      = "https://heartresearch.com.au/heart-hub/"
RESEARCH_URL = "https://heartresearch.com.au/research-projects/"
BASE_DOMAIN  = "https://heartresearch.com.au"
MAX_ARTICLES = 300

SECTIONS = [
    {
        "name": "informative",
        "url": HUB_URL,
        "type": "hub",
        "content_type": "article",
        "source_classification": "factual",
        "id_prefix": "hra_hub",
    },
    {
        "name": "research",
        "url": RESEARCH_URL,
        "type": "paginated",
        "content_type": "article",
        "source_classification": "factual",
        "id_prefix": "hra_research",
    },
]

JUNK_PHRASES = [
    "read more",
    "learn more",
    "click here",
    "subscribe",
    "newsletter",
    "donate",
    "share this",
    "follow us",
    "sign up",
    "back to top",
    "privacy policy",
    "terms of use",
    "contact us",
    "note: these are general guidelines",
    "heart research australia",
    "north shore cardiovascular",
    "tel:",
    "visit austroads",
]

def _loop_item_links(soup: BeautifulSoup) -> list[str]:
    links = []
    for card in soup.find_all("div", class_=lambda c: c and "e-loop-item" in c):
        a = card.find("a", href=True)
        if a:
            href = a["href"].strip()
            if not href.startswith("http"):
                href = f"{BASE_DOMAIN}{href}"
            if href not in links:
                links.append(href)
    return links


def collect_hub_article_links() -> list[str]:
    print(f"  Fetching hub index: {HUB_URL}")
    hub_soup = get_soup(HUB_URL)

    category_pattern = re.compile(
        r"^https://heartresearch\.com\.au/heart-hub/[^/]+/?$"
    )
    category_urls = [
        href for href in _loop_item_links(hub_soup)
        if category_pattern.match(href)
    ]
    print(f"  Found {len(category_urls)} categories")

    article_urls: list[str] = []

    for cat_url in category_urls:
        cat_name = cat_url.rstrip("/").split("/")[-1]
        print(f"    Category: {cat_name}")

        try:
            cat_soup = get_soup(cat_url)
        except Exception as e:
            print(f"    Error fetching category page: {e}")
            continue

        article_pattern = re.compile(
            r"^https://heartresearch\.com\.au/heart-hub/[^/]+/[^/]+/?$"
        )
        for href in _loop_item_links(cat_soup):
            if article_pattern.match(href) and href not in article_urls:
                article_urls.append(href)

        time.sleep(0.5)

    print(f"  Found {len(article_urls)} heart hub articles total")
    return article_urls


def collect_research_links() -> list[str]:
    links: list[str] = []
    page_url: str | None = RESEARCH_URL
    page_num = 1

    while page_url:
        print(f"  Page {page_num}: {page_url}")
        try:
            soup = get_soup(page_url)
        except Exception as e:
            print(f"  Error fetching page: {e}")
            break

        for href in _loop_item_links(soup):
            if (
                href != page_url
                and "/heart-hub/" not in href
                and "/research-projects/" not in href
                and href not in links
            ):
                links.append(href)

        nav = soup.find("nav", class_="elementor-pagination")
        page_url = None
        if nav:
            next_a = nav.find("a", class_=lambda c: c and "next" in c)
            if next_a and next_a.get("href"):
                page_url = next_a["href"].strip()

        page_num += 1
        time.sleep(0.5)

    print(f"  Found {len(links)} research articles total")
    return links

def extract_title(soup: BeautifulSoup) -> str:
    h1 = soup.find("h1", class_=lambda c: c and "elementor-heading-title" in c)
    if h1:
        return normalise_text(h1.get_text(" ", strip=True))
    return extract_title_generic(
        soup,
        [
            " | Heart Research Australia",
            " - Heart Research Australia",
            " – Heart Research Australia",
        ],
    )


def extract_content(soup: BeautifulSoup) -> str:
    paragraphs: list[str] = []

    for widget in soup.find_all(
        "div", attrs={"data-widget_type": "text-editor.default"}
    ):
        for el in widget.find_all(["p", "li"]):
            text = el.get_text(" ", strip=True)
            if text:
                paragraphs.append(text)

    if not paragraphs:
        paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]

    cleaned = clean_paragraph_list(
        paragraphs, junk_phrases=JUNK_PHRASES, min_length=40
    )
    return "\n".join(cleaned[:15]) if cleaned else ""

def build_article_record(
    url: str,
    item_id: str,
    content_type: str,
    source_classification: str,
) -> dict:
    soup = get_soup(url)

    title   = extract_title(soup)
    content = extract_content(soup)

    summary = ""
    if content:
        first_para = content.split("\n")[0]
        summary = first_para if first_para != title else ""

    publish_time = extract_publish_time_generic(soup)

    text_for_tags = f"{title or ''} {content or ''}"
    tags = extract_tags(text_for_tags)

    return {
        "id": item_id,
        "source": "Heart Research Australia",
        "source_category": "website",
        "source_type": "organisation",
        "source_classification": source_classification,
        "url": url,
        "title": title,
        "content": content,
        "summary": summary,
        "author": "Heart Research Australia",
        "author_type": "organisation",
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
        "content_type": content_type,
        "language": "en",
    }

def main() -> None:
    records: list[dict] = []
    records = []
    stats = create_stats("Heart Research Australia")
    add_section(stats, "informative")
    add_section(stats, "research")
    #stats: dict[str, dict[str, int]] = {
        #"heart_hub": {"general": 0, "heart": 0, "women_heart": 0},
        #"research":  {"general": 0, "heart": 0, "women_heart": 0},
    #}
    topics = ["general_health", "heart_health", "women_heart_health"]
    #topic_map = {
        #"general_health":      "general",
        #"heart_health":        "heart",
        #"women_heart_health":  "women_heart",
    #}

    for section in SECTIONS:
        print(f"\n=== Heart Research Australia — {section['name'].replace('_', ' ').title()} ===")

        if section["type"] == "hub":
            links = collect_hub_article_links()
        elif section["type"] == "paginated":
            links = collect_research_links()
        else:
            print(f"  Unknown section type '{section['type']}' — skipping.")
            continue

        if not links:
            print(f"  No links found for {section['name']} section.")
            continue

        print(f"\nFirst 3 links:")
        for link in links[:3]:
            print(f"  {link}")

        section_name = section["name"]

        for index, link in enumerate(links[:MAX_ARTICLES], start=1):
            print(f"\nChecking {section_name} {index}: {link}")

            try:
                article = build_article_record(
                    link,
                    f"{section['id_prefix']}_{index:03d}",
                    section["content_type"],
                    section["source_classification"],
                )
            except Exception as error:
                print(f"  Error reading article: {error}")
                continue

            print(f"  Title: {article['title']}")

            section_name = section["name"]
            topic = classify_topic(article["title"] or "", article["content"] or "")
            tags = extract_tags(f"{article['title'] or ''} {article['content'] or ''}")
            sentiment = analyse_sentiment(article["content"] or "")
            update_stats(
                stats,
                topic=topic,
                tags=tags,
                sentiment=sentiment,
                source_classification=section["source_classification"],
                section=section_name,
                publish_time=article["publish_time"]
            )
            #stats[section_name][topic_map[topic]] += 1

            if topic == "women_heart_health":
                records.append(article)

            time.sleep(0.3)

    if records:
        save_json(records, "heartresearch.json")
        print(f"\nSaved {len(records)} articles to heartresearch.json")
    else:
        print("\nNo women's heart health articles found.")

    save_stats(stats, "healthresearch.json")
    
    print("\nScraping Summary:")
    for section_name, counts in stats["by_section"].items():
        total = sum(counts.values())
        if total == 0:
            continue

        print(f"\n{section_name.upper()}")
        for k, v in counts.items():
            pct = (v / total) * 100
            print(f"  {k}: {v} ({pct:.1f}%)")

    informative_vals = [stats["by_section"]["informative"][t] for t in topics]
    research_vals = [stats["by_section"]["research"][t] for t in topics]

    x = np.arange(len(topics))

    plt.figure()
    plt.bar(x, informative_vals,      label="Informative")
    plt.bar(x, research_vals, bottom=informative_vals, label="Research Projects")

    plt.xticks(x, ["General Health", "Heart Health", "Women's Heart Health"])
    plt.title("Heart Research Australia Topic Distribution")
    plt.xlabel("Topic")
    plt.ylabel("Number of Articles")
    plt.legend()
    plt.tight_layout()

    timestamp  = datetime.now().strftime("%Y%m%d_%H%M")
    chart_path = CHART_DIR / f"heartresearch_summary_{timestamp}.png"
    plt.savefig(chart_path)
    plt.close()
    print(f"Chart saved to: {chart_path}")

    total_all = stats["total_examined"]
    overall_womens_heart = stats["by_topic"]["women_heart_health"]

    print("\n=== Overall Coverage ===")
    print(f"Total articles: {total_all}")
    if total_all:
        pct = (overall_womens_heart / total_all) * 100
        print(f"Women's heart health: {overall_womens_heart} ({pct:.1f}%)")


if __name__ == "__main__":
    main()