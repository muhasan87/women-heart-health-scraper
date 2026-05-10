import re
import time
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime, timezone
from pathlib import Path
import instaloader
import os

from common import (
    classify_topic,
    extract_tags,
    normalise_text,
    save_json,
    save_stats,
    now_iso,
    create_stats,
    add_section,
    analyse_sentiment,
    update_stats,
    CHART_DIR,
)

PROFILE_USERNAME = "womensheartalliance"
MAX_POSTS        = 300
SESSION_FILE = "ig_session"

SECTIONS = [
    {
        "name": "instagram_posts",
        "username": PROFILE_USERNAME,
        "content_type": "post",
        "source_classification": "factual",
        "id_prefix": "wha_ig",
    },
]

JUNK_PHRASES = [
    "link in bio",
    "swipe left",
    "swipe up",
    "tap the link",
    "follow us",
    "double tap",
    "tag a friend",
    "comment below",
    "dm us",
    "click the link",
]

def get_loader() -> instaloader.Instaloader:
    loader = instaloader.Instaloader(
        download_pictures=False,
        download_videos=False,
        download_video_thumbnails=False,
        download_geotags=False,
        download_comments=False,
        save_metadata=False,
        compress_json=False,
        quiet=True,
    )

    # macOS/Linux default path the CLI saves to
    session_path = Path.home() / ".config" / "instaloader" / "session-womenshearthealthscraper"

    if not session_path.exists():
        raise FileNotFoundError(
            f"Session file not found at {session_path}.\n"
            "Run this in your terminal first:\n"
            "  instaloader --login womenshearthealthscraper"
        )

    print(f"  Loading session from: {session_path}")
    loader.load_session_from_file("womenshearthealthscraper", str(session_path))
    print(f"  Logged in as: {loader.context.username}")
    return loader

def extract_hashtags(caption: str) -> list[str]:
    return re.findall(r"#\w+", caption.lower())


def extract_mentions(caption: str) -> list[str]:
    return re.findall(r"@\w+", caption.lower())


def clean_caption(caption: str) -> str:
    if not caption:
        return ""

    # Split on the first line that is mostly hashtags/mentions
    lines = caption.splitlines()
    body_lines = []
    for line in lines:
        tokens = line.split()
        if tokens and sum(1 for t in tokens if t.startswith(("#", "@"))) / len(tokens) >= 0.6:
            break
        body_lines.append(line)

    cleaned = " ".join(body_lines).strip()
    # Collapse internal whitespace
    return normalise_text(cleaned)


def extract_summary(content: str) -> str:
    if not content:
        return ""
    # Split on sentence-ending punctuation
    match = re.split(r"(?<=[.!?])\s+", content)
    return match[0] if match else content[:200]


def infer_media_type(post: instaloader.Post) -> str:
    type_map = {
        "GraphImage":   "image",
        "GraphVideo":   "video",
        "GraphSidecar": "carousel",   # multi-image post
    }
    return type_map.get(post.typename, "image")

def build_post_record(
    post: instaloader.Post,
    item_id: str,
    content_type: str,
    source_classification: str,
) -> dict:
    raw_caption = post.caption or ""

    hashtags = extract_hashtags(raw_caption)
    content  = clean_caption(raw_caption)
    summary  = extract_summary(content)

    first_line = content.split(".")[0].strip() if content else ""
    title      = first_line[:120] if first_line else None

    text_for_tags = f"{content}"
    tags = extract_tags(text_for_tags)

    publish_time = (
        post.date_utc.strftime("%Y-%m-%dT%H:%M:%S.000Z")
        if post.date_utc
        else None
    )

    return {
        "id": item_id,
        "source": "Women's Heart Alliance",
        "source_category": "social_media",
        "source_type": "organisation",
        "source_classification": source_classification,
        "url": f"https://www.instagram.com/p/{post.shortcode}/",
        "title": title,
        "content": content,
        "summary": summary,
        "author": "Women's Heart Alliance",
        "author_type": "organisation",
        "publish_time": publish_time,
        "scrape_time": now_iso(),
        "tags": tags,
        "hashtags": hashtags,
        "engagement": {
            "likes": post.likes,
            "comments": post.comments,
            "shares": None,          # Instagram does not expose share counts
        },
        "media_type": infer_media_type(post),
        "content_type": content_type,
        "language": "en",
    }

def main() -> None:
    records: list[dict] = []
    stats = create_stats("Women's Heart Alliance")
    topics = ["general_health", "heart_health", "women_heart_health"]

    loader = get_loader()

    for section in SECTIONS:
        print(f"\n=== Women's Heart Alliance — Instagram (@{section['username']}) ===")

        try:
            profile = instaloader.Profile.from_username(loader.context, section["username"])
        except instaloader.exceptions.LoginRequiredException as e:
            print(f"  Session not authenticated — try re-running: instaloader --login womenshearthealthscraper")
            continue
        except instaloader.exceptions.ProfileNotExistsException as e:
            print(f"  ProfileNotExistsException (may be an auth issue): {e}")
            continue
        except Exception as e:
            print(f"  {type(e).__name__}: {e}")
            continue

        print(f"  Posts on profile: {profile.mediacount}")
        section_name = section["name"]

        for index, post in enumerate(profile.get_posts(), start=1):
            if index > MAX_POSTS:
                break

            print(f"\n  Post {index}: instagram.com/p/{post.shortcode}/")

            try:
                record = build_post_record(
                    post,
                    f"{section['id_prefix']}_{index:03d}",
                    section["content_type"],
                    section["source_classification"],
                )
            except Exception as e:
                print(f"  Error processing post: {e}")
                continue

            print(f"  Caption preview: {(record['content'] or '')[:80]}...")

            topic = classify_topic(post["title"] or "", post["content"] or "")
            tags = extract_tags(f"{post['title'] or ''} {post['content'] or ''}")
            sentiment = analyse_sentiment(post["content"] or "")
            update_stats(
                stats,
                topic=topic,
                tags=tags,
                sentiment=sentiment,
                source_classification=post["source_classification"],
                publish_time=post["publish_time"]
            )

            if topic == "women_heart_health":
                records.append(record)

            time.sleep(1.5)

    if records:
        save_json(records, "womensheartalliance.json")
        print(f"\nSaved {len(records)} posts to womensheartalliance.json")
    else:
        print("\nNo women's heart health posts found.")

    save_stats(stats, "ig_wha_stats.json")

    print("\nScraping Summary:")
    total = sum(stats["by_topic"].values())
    if total > 0:
        for topic, count in stats["by_topic"].items():
            pct = (count / total) * 100
            print(f"{topic}: {count} ({pct:.1f}%)")

    labels = ["General Health", "Heart Health", "Women's Heart Health"]
    values = [stats["by_topic"][t] for t in topics]

    plt.figure()
    plt.bar(labels, values)
    plt.xticks(["General Health", "Heart Health", "Women's Heart Health"])
    plt.title("Instagram @womensheartalliance Topic Distribution")
    plt.xlabel("Topic")
    plt.ylabel("Number of Articles")
    plt.tight_layout()

    timestamp  = datetime.now().strftime("%Y%m%d_%H%M")
    chart_path = CHART_DIR / f"womensheartalliance_summary_{timestamp}.png"
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