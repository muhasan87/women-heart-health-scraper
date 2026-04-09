from common import (
    build_record,
    clean_paragraph_list,
    extract_author_generic,
    extract_publish_time_generic,
    extract_summary_from_paragraphs,
    extract_title_generic,
    get_soup,
    save_json,
)

ARTICLE_URL = "https://heartresearch.com.au/heart-disease/women-and-heart-disease/"


def extract_content_and_summary(soup, title: str) -> tuple[str, str]:
    junk_phrases = [
        "read more",
        "subscribe",
        "newsletter",
        "donate",
        "share this",
        "facebook",
        "instagram",
        "twitter",
        "linkedin",
        "click here",
        "tax deductible",
        "abn",
        "monthly donation",
        "one-off gift",
    ]

    paragraphs = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
    cleaned = clean_paragraph_list(paragraphs, junk_phrases=junk_phrases, min_length=40)

    content = "\n".join(cleaned[:15])
    summary = extract_summary_from_paragraphs(cleaned, title)

    return content, summary


def build_article_record(article_url: str, item_id: str) -> dict:
    soup = get_soup(article_url)

    title = extract_title_generic(soup, [" – Heart Research Australia", " - Heart Research Australia"])
    author = extract_author_generic(soup)
    publish_time = extract_publish_time_generic(soup)
    content, summary = extract_content_and_summary(soup, title)

    return build_record(
        item_id=item_id,
        source="Heart Research Australia",
        platform="news",
        source_type="institution",
        url=article_url,
        title=title,
        content=content,
        summary=summary,
        author=author,
        author_type="journalist" if author else "organisation",
        publish_time=publish_time,
        topic="women_heart_health",
    )


def main() -> None:
    try:
        record = build_article_record(ARTICLE_URL, "heart_res_aus_samp")
    except Exception as error:
        print(f"Error scraping article: {error}")
        return

    save_json(record, "heart_res_aus_samp.json")

    print("Saved article to data/json/heart_res_aus_samp.json")
    print("Title:", record["title"])
    print("URL:", record["url"])
    print("Summary:", record["summary"][:150])


if __name__ == "__main__":
    main()