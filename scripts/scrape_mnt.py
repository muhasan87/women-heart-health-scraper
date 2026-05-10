import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
from pathlib import Path

from common import (
    classify_topic,
    clean_paragraph_list,
    extract_author_generic,
    extract_publish_time_generic,
    extract_summary_from_paragraphs,
    extract_tags,
    extract_title_generic,
    get_soup,
    save_json,
    save_stats,
    create_stats,
    add_section,
    analyse_sentiment,
    update_stats,
    now_iso,
    CHART_DIR,
)

BASE_DOMAIN = "https://www.medicalnewstoday.com"
MAX_ARTICLES = 300

SECTIONS = [
    {
        "name": "cardiovascular_health",
        "url": f"{BASE_DOMAIN}/cardiovascular-health",
        "id_prefix": "mnt_cardio",
        "source_classification": "factual"
    },
    {
        "name": "womens_health",
        "url": f"{BASE_DOMAIN}/womens-health",
        "id_prefix": "mnt_womens",
        "source_classification": "factual"
    },
    {
        "name": "heart_disease",
        "url": f"{BASE_DOMAIN}/categories/heart-disease",
        "id_prefix": "mnt_heart",
        "source_classification": "factual"
    },
]

JUNK_PHRASES = [
    "medical news today has strict sourcing guidelines",
    "fact checked",
    "copy edited by",
    "latest news",
    "related coverage",
    "share on pinterest",
    "share on facebook",
    "share on twitter",
    "read this next",
    "was this helpful",
    "how we reviewed this article",
    "optum perks is owned by",
]

def collect_article_links(url: str) -> list[str]:
    print(f"  Scanning: {url}")
    soup = get_soup(url)
    links = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]

        if href.startswith("/"):
            href = f"{BASE_DOMAIN}{href}"

        if not href.startswith(f"{BASE_DOMAIN}/articles/"):
            continue

        if "#" in href:
            continue

        if href not in links:
            links.append(href)

    return links

def extract_content_and_summary(soup, title: str) -> tuple[str, str]:
    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    cleaned = clean_paragraph_list(paragraphs, junk_phrases=JUNK_PHRASES, min_length=40)

    content = "\n".join(cleaned[:15]) if cleaned else ""
    summary = extract_summary_from_paragraphs(cleaned, title)

    return content, summary

def build_article_record(article_url: str, item_id: str) -> dict:
    soup = get_soup(article_url)

    title        = extract_title_generic(soup, [" - Medical News Today"])
    author       = extract_author_generic(soup)
    publish_time = extract_publish_time_generic(soup)
    content, summary = extract_content_and_summary(soup, title)

    text_for_tags = f"{title or ''} {content or ''}"
    tags = extract_tags(text_for_tags)

    return {
        "id": item_id,
        "source": "Medical News Today",
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
    records: list[dict] = []
    stats = create_stats("Medical News Today")
    
    add_section(stats, "cardiovascular_health")
    add_section(stats, "womens_health")
    add_section(stats, "heart_disease")
    topics = ["general_health", "heart_health", "women_heart_health"]

    global_index = 1

    for section in SECTIONS:
        print(f"\n=== Medical News Today — {section['name'].replace('_', ' ').title()} ===")

        links = collect_article_links(section["url"])
        print(f"  Found {len(links)} article links")

        if not links:
            print(f"  No links found — skipping.")
            continue

        print(f"\nFirst 3 links:")
        for link in links[:3]:
            print(f"  {link}")

        section_name = section["name"]

        for link in links[:MAX_ARTICLES]:
            print(f"\nChecking {section_name} [{global_index}]: {link}")

            try:
                article = build_article_record(
                    link,
                    f"{section['id_prefix']}_{global_index:03d}",
                )
            except Exception as error:
                print(f"  Error reading article: {error}")
                global_index += 1
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

            if topic == "women_heart_health":
                records.append(article)

            global_index += 1

    if records:
        save_json(records, "medicalnewstoday.json")
        print(f"\nSaved {len(records)} articles to medicalnewstoday.json")
    else:
        print("\nNo women's heart health articles found.")
    
    save_stats(stats, "medicalnewstoday_stats.json")

    print("\nScraping Summary:")
    for section_name, counts in stats["by_section"].items():
        total = sum(counts.values())
        if total == 0:
            continue

        print(f"\n{section_name.upper()}")
        for k, v in counts.items():
            pct = (v / total) * 100
            print(f"  {k}: {v} ({pct:.1f}%)")

    n_sections = len(SECTIONS)
    n_topics   = len(topics)
    x = np.arange(n_topics)
    bar_width  = 0.8 / n_sections

    plt.figure()
    for i, section in enumerate(SECTIONS):
        section_name = section["name"]
        values = [stats["by_section"][section_name][t] for t in topics]
        offsets = x - 0.4 + (i + 0.5) * bar_width
        label = section_name.replace("_", " ").title()
        plt.bar(offsets, values, width=bar_width, label=label)
    plt.xticks(x, ["General Health", "Heart Health", "Women's Heart Health"])
    plt.title("Medical News Today Topic Distribution")
    plt.xlabel("Topic")
    plt.ylabel("Number of Articles")
    plt.legend()
    plt.tight_layout()

    timestamp  = datetime.now().strftime("%Y%m%d_%H%M")
    chart_path = CHART_DIR / f"medicalnewstoday_summary_{timestamp}.png"
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