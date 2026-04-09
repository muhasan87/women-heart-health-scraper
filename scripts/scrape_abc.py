from common import (
    build_record,
    classify_topic,
    clean_paragraph_list,
    extract_author_generic,
    extract_publish_time_generic,
    extract_summary_from_paragraphs,
    extract_title_generic,
    get_soup,
    save_json,
)

LISTING_URL = "https://www.abc.net.au/news/health"


def collect_article_links() -> list[str]:
    soup = get_soup(LISTING_URL)
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
    cleaned = clean_paragraph_list(paragraphs, junk_phrases=junk_phrases, min_length=40)

    content = "\n".join(cleaned[:15])
    summary = extract_summary_from_paragraphs(cleaned, title)

    return content, summary


def build_article_record(article_url: str, item_id: str) -> dict:
    soup = get_soup(article_url)

    title = extract_title_generic(soup, [" - ABC News"])
    author = extract_author_generic(soup)
    publish_time = extract_publish_time_generic(soup)
    content, summary = extract_content_and_summary(soup, title)
    topic = classify_topic(title, content)

    return build_record(
        item_id=item_id,
        source="ABC News",
        platform="news",
        source_type="media",
        url=article_url,
        title=title,
        content=content,
        summary=summary,
        author=author,
        author_type="journalist" if author else "",
        publish_time=publish_time,
        topic=topic,
    )


def main() -> None:
    links = collect_article_links()
    print(f"Found {len(links)} possible article links")

    if not links:
        print("No article links found.")
        return

    print("\nFirst 10 candidate links:")
    for i, link in enumerate(links[:10], start=1):
        print(f"{i}. {link}")

    matched_article = None

    for index, link in enumerate(links[:20], start=1):
        print(f"\nChecking article {index}: {link}")

        try:
            article = build_article_record(link, f"abc_{index:03d}")
        except Exception as error:
            print(f"Error reading article: {error}")
            continue

        print("Title:", article["title"])
        print("Author:", article["author"])
        print("Publish time:", article["publish_time"])
        print("Topic:", article["topic"])

        if article["topic"] == "women_heart_health":
            matched_article = article
            break

    if matched_article:
        save_json(matched_article, "abc_heart_sample.json")
        print("\nSaved article to data/json/abc_heart_sample.json")
        print("Title:", matched_article["title"])
        print("URL:", matched_article["url"])
        print("Topic:", matched_article["topic"])
    else:
        print("\nNo women heart health article found in first 20 ABC links.")


if __name__ == "__main__":
    main()