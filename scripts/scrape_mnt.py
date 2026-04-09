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

BASE_CATEGORY_URL = "https://www.medicalnewstoday.com/categories/heart-disease"
MAX_PAGES = 10


def build_page_url(page_number: int) -> str:
    if page_number == 1:
        return BASE_CATEGORY_URL
    return f"{BASE_CATEGORY_URL}?page={page_number}"


def title_looks_heart_related(title: str) -> bool:
    title_lower = title.lower()

    keywords = [
        "heart",
        "cardio",
        "cardiovascular",
        "cardiac",
        "coronary",
        "stroke",
        "blood pressure",
        "hypertension",
        "cholesterol",
        "artery",
        "atherosclerosis",
    ]

    return any(word in title_lower for word in keywords)


def collect_article_links_from_page(page_url: str) -> list[str]:
    soup = get_soup(page_url)
    links = []

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"]
        link_text = a_tag.get_text(" ", strip=True)

        if href.startswith("/"):
            href = f"https://www.medicalnewstoday.com{href}"

        if not href.startswith("https://www.medicalnewstoday.com/articles/"):
            continue

        if any(
            bad in href
            for bad in ["/articles/in-conversation-podcast", "/articles/content-hubs"]
        ):
            continue

        if not link_text:
            continue

        if not title_looks_heart_related(link_text):
            continue

        if href not in links:
            links.append(href)

    return links


def collect_article_links(max_pages: int = MAX_PAGES) -> list[str]:
    all_links = []

    for page_number in range(1, max_pages + 1):
        page_url = build_page_url(page_number)
        print(f"Scanning page {page_number}: {page_url}")

        try:
            page_links = collect_article_links_from_page(page_url)
            print(f"Found {len(page_links)} links on page {page_number}")

            for link in page_links:
                if link not in all_links:
                    all_links.append(link)

        except Exception as error:
            print(f"Error scanning page {page_number}: {error}")

    return all_links


def extract_content_and_summary(soup, title: str) -> tuple[str, str]:
    junk_phrases = [
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

    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    cleaned = clean_paragraph_list(paragraphs, junk_phrases=junk_phrases, min_length=40)

    content = "\n".join(cleaned[:15])
    summary = extract_summary_from_paragraphs(cleaned, title)

    return content, summary


def build_article_record(article_url: str, item_id: str) -> dict:
    soup = get_soup(article_url)

    title = extract_title_generic(soup, [" - Medical News Today"])
    author = extract_author_generic(soup)
    publish_time = extract_publish_time_generic(soup)
    content, summary = extract_content_and_summary(soup, title)
    topic = classify_topic(title, content)

    return build_record(
        item_id=item_id,
        source="Medical News Today",
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


def is_valid_record(record: dict) -> bool:
    return bool(record["title"].strip() and record["content"].strip() and record["summary"].strip())


def main() -> None:
    links = collect_article_links(MAX_PAGES)
    print(f"\nFound {len(links)} total filtered links")

    if not links:
        print("No suitable links found.")
        return

    print("\nFirst 10 links:")
    for i, link in enumerate(links[:10], start=1):
        print(f"{i}. {link}")

    matched_article = None

    for index, link in enumerate(links[:20], start=1):
        print(f"\nChecking article {index}: {link}")

        try:
            article = build_article_record(link, f"mnt_{index:03d}")
        except Exception as error:
            print(f"Error reading article: {error}")
            continue

        if not is_valid_record(article):
            print("Skipping invalid article record")
            continue

        print("Title:", article["title"])
        print("Author:", article["author"])
        print("Publish time:", article["publish_time"])
        print("Topic:", article["topic"])

        if article["topic"] in ["women_heart_health", "general_heart_health"]:
            matched_article = article
            break

    if matched_article:
        save_json(matched_article, "mnt_sample.json")
        print("\nSaved article to data/json/mnt_sample.json")
        print("Title:", matched_article["title"])
        print("URL:", matched_article["url"])
        print("Topic:", matched_article["topic"])
    else:
        print("\nNo suitable heart-related article found.")


if __name__ == "__main__":
    main()