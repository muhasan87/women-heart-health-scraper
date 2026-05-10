import json
from pathlib import Path
from collections import defaultdict, Counter
from datetime import datetime

import matplotlib.pyplot as plt
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
STATS_DIR = BASE_DIR / "data" / "json" / "stats"
CHART_DIR = BASE_DIR / "data" / "charts"

CHART_DIR.mkdir(parents=True, exist_ok=True)

def load_files():
    stats_files = list(STATS_DIR.glob("*stats.json"))

    all_stats = []

    for file in stats_files:
        try:
            with open(file, "r", encoding="utf-8") as f:
                data = json.load(f)
                all_stats.append(data)
        except Exception as e:
            print(f"Failed loading {file.name}: {e}")

    return all_stats

def aggregate(all_stats):
    total_examined = 0
    source_totals = defaultdict(int)
    topic_totals = defaultdict(int)
    tag_totals = defaultdict(int)
    sentiment_totals = defaultdict(int)
    classification_totals = defaultdict(int)
    topic_matrix = defaultdict(lambda: defaultdict(int))
    sentiment_matrix = defaultdict(lambda: defaultdict(int))
    date_ranges = []

    for entry in all_stats:
        source = entry.get("source", "Unknown")
        source_total = entry.get("total_examined", 0)
        total_examined += source_total
        source_totals[source] += source_total
        by_topic = entry.get("by_topic", {})

        #total
        for topic, count in by_topic.items():
            topic_totals[topic] += count
            topic_matrix[source][topic] += count

        #tags
        by_tags = entry.get("by_tags", {})
        
        for tag, count in by_tags.items():
            tag_totals[tag] += count

        #sentiment
        by_sentiment = entry.get("by_sentiment", {})

        for sentiment, count in by_sentiment.items():
            sentiment_totals[sentiment] += count
            sentiment_matrix[source][sentiment] += count

        #classification
        by_classification = entry.get(
            "by_classification",
            {}
        )

        for cls, count in by_classification.items():
            classification_totals[cls] += count

        #date range
        date_range = entry.get("date_range", {})
        earliest = date_range.get("earliest")
        latest = date_range.get("latest")

        if earliest:
            date_ranges.append(earliest)

        if latest:
            date_ranges.append(latest)

    return {
        "total_examined": total_examined,
        "source_totals": source_totals,
        "topic_totals": topic_totals,
        "tag_totals": tag_totals,
        "sentiment_totals": sentiment_totals,
        "classification_totals": classification_totals,
        "topic_matrix": topic_matrix,
        "sentiment_matrix": sentiment_matrix,
        "date_ranges": date_ranges,
    }

def print_section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)

def print_summary(results):
    total_examined = results["total_examined"]
    source_totals = results["source_totals"]
    topic_totals = results["topic_totals"]
    tag_totals = results["tag_totals"]
    sentiment_totals = results["sentiment_totals"]
    classification_totals = results["classification_totals"]
    topic_matrix = results["topic_matrix"]
    date_ranges = results["date_ranges"]

    print_section("GLOBAL OVERVIEW")
    print(f"Total records examined: {total_examined}")

    women_total = topic_totals.get("women_heart_health", 0)

    women_pct = (
        women_total / total_examined * 100
        if total_examined else 0
    )

    print(f"Women's heart health records: {women_total}")
    print(f"Women's heart health proportion: {women_pct:.1f}%")

    print_section("DATE COVERAGE")

    if date_ranges:
        earliest = min(date_ranges)
        latest = max(date_ranges)
        print(f"Earliest article: {earliest}")
        print(f"Latest article:   {latest}")

    else:
        print("No dates available.")

    print_section("SOURCE BREAKDOWN")

    for source, total in sorted(
        source_totals.items(),
        key=lambda x: x[1],
        reverse=True,
    ):
        pct = (
            total / total_examined * 100
            if total_examined else 0
        )
        print(f"{source}: {total} ({pct:.1f}%)")

    print_section("TOPIC DISTRIBUTION")

    for topic, total in sorted(
        topic_totals.items(),
        key=lambda x: x[1],
        reverse=True,
    ):
        pct = (
            total / total_examined * 100
            if total_examined else 0
        )
        print(f"{topic}: {total} ({pct:.1f}%)")

    print_section("SOURCE × TOPIC BREAKDOWN")

    for source, topics in topic_matrix.items():
        print(f"\n{source}")
        source_total = source_totals[source]

        for topic, count in sorted(
            topics.items(),
            key=lambda x: x[1],
            reverse=True,
        ):
            pct = (
                count / source_total * 100
                if source_total else 0
            )
            print(f"  {topic}: {count} ({pct:.1f}%)")

    print_section("TOP TAGS")
    total_tags = sum(tag_totals.values())
    
    if total_tags == 0:
        print("No tags found.")

    else:
        for tag, count in sorted(
            tag_totals.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:20]:
            pct = (
                count / total_tags * 100
                if total_tags else 0
            )
            print(f"{tag}: {count} ({pct:.1f}%)")

    print_section("SENTIMENT DISTRIBUTION")
    total_sentiment = sum(sentiment_totals.values())

    if total_sentiment == 0:
        print("No sentiment data found.")

    else:
        for sentiment, count in sorted(
            sentiment_totals.items(),
            key=lambda x: x[1],
            reverse=True,
        ):
            pct = (
                count / total_sentiment * 100
                if total_sentiment else 0
            )
            print(f"{sentiment}: {count} ({pct:.1f}%)")

    print_section("SOURCE CLASSIFICATION")

    total_classification = sum(
        classification_totals.values()
    )

    if total_classification == 0:
        print("No classification data found.")

    else:
        for cls, count in sorted(
            classification_totals.items(),
            key=lambda x: x[1],
            reverse=True,
        ):
            pct = (
                count / total_classification * 100
                if total_classification else 0
            )
            print(f"{cls}: {count} ({pct:.1f}%)")

    print_section("KEY INSIGHTS")

    if topic_totals:
        most_common_topic = max(
            topic_totals.items(),
            key=lambda x: x[1]
        )
        print(
            f"Most common topic: "
            f"{most_common_topic[0]} "
            f"({most_common_topic[1]})"
        )

    if source_totals:
        largest_source = max(
            source_totals.items(),
            key=lambda x: x[1]
        )
        print(
            f"Largest source: "
            f"{largest_source[0]} "
            f"({largest_source[1]})"
        )

    if tag_totals:
        top_tag = max(
            tag_totals.items(),
            key=lambda x: x[1]
        )
        print(
            f"Most common tag: "
            f"{top_tag[0]} "
            f"({top_tag[1]})"
        )

    print(
        f"Women's heart health proportion: "
        f"{women_pct:.1f}%"
    )


#charts
def create_topic_chart(topic_totals):
    topics = [
        "general_health",
        "heart_health",
        "women_heart_health",
    ]
    values = [topic_totals.get(t, 0) for t in topics]

    plt.figure(figsize=(8, 5))
    plt.bar(
        [
            "General Health",
            "Heart Health",
            "Women's Heart Health",
        ],
        values,
    )

    plt.title("Topic Distribution")
    plt.ylabel("Article Count")
    plt.tight_layout()
    path = CHART_DIR / "topic_distribution.png"

    plt.savefig(path)
    plt.close()

    print(f"Saved chart: {path}")


def create_source_chart(source_totals):
    labels = list(source_totals.keys())
    values = list(source_totals.values())
    plt.figure(figsize=(10, 6))
    plt.bar(labels, values)
    plt.xticks(rotation=45, ha="right")
    plt.title("Records by Source")
    plt.ylabel("Record Count")
    plt.tight_layout()
    path = CHART_DIR / "source_distribution.png"

    plt.savefig(path)
    plt.close()

    print(f"Saved chart: {path}")


def create_tag_chart(tag_totals):
    sorted_tags = sorted(
        tag_totals.items(),
        key=lambda x: x[1],
        reverse=True,
    )[:15]

    labels = [x[0] for x in sorted_tags]
    values = [x[1] for x in sorted_tags]

    plt.figure(figsize=(10, 6))
    plt.barh(labels, values)
    plt.gca().invert_yaxis()
    plt.title("Top Tags")
    plt.xlabel("Count")
    plt.tight_layout()
    path = CHART_DIR / "top_tags.png"

    plt.savefig(path)
    plt.close()

    print(f"Saved chart: {path}")


def create_sentiment_chart(sentiment_totals):
    labels = list(sentiment_totals.keys())
    values = list(sentiment_totals.values())

    if sum(values) == 0:
        return

    plt.figure(figsize=(6, 6))
    plt.pie(
        values,
        labels=labels,
        autopct="%1.1f%%",
    )

    plt.title("Sentiment Distribution")
    path = CHART_DIR / "sentiment_distribution.png"
    plt.savefig(path)
    plt.close()

    print(f"Saved chart: {path}")


def create_classification_chart(classification_totals):
    labels = list(classification_totals.keys())
    values = list(classification_totals.values())
    
    if sum(values) == 0:
        return

    plt.figure(figsize=(7, 5))
    plt.bar(labels, values)
    plt.title("Source Classification")
    plt.ylabel("Count")
    plt.tight_layout()
    path = CHART_DIR / "source_classification.png"

    plt.savefig(path)
    plt.close()

    print(f"Saved chart: {path}")

def main():
    all_stats = load_files()

    if not all_stats:
        print("No stats files found.")
        return

    results = aggregate(all_stats)
    print_summary(results)

    create_topic_chart(
        results["topic_totals"]
    )

    create_source_chart(
        results["source_totals"]
    )

    create_tag_chart(
        results["tag_totals"]
    )

    create_sentiment_chart(
        results["sentiment_totals"]
    )

    create_classification_chart(
        results["classification_totals"]
    )

    print("\nAnalysis complete.")


if __name__ == "__main__":
    main()