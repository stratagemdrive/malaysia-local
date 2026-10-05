import os
import json
import re
from datetime import datetime, timezone, timedelta
import dateutil.parser
import feedparser
from deep_translator import GoogleTranslator

# Configuration
COUNTRY = "australia"
OUTPUT_DIR = "docs"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, f"{COUNTRY}_news.json")
MAX_STORIES_PER_CATEGORY = 20
MAX_AGE_DAYS = 7

# RSS Feed sources
FEEDS = {
    "ABC News Australia": "https://www.abc.net.au/news/feed/51120/rss.xml",
    "News.com.au": "https://www.news.com.au/content-feeds/rss/",
    "Google News Australia": "https://news.google.com/rss?gl=AU&hl=en-AU&ceid=AU:en",
    "The Guardian Australia": "https://www.theguardian.com/au/rss"
}

# Category keyword routing
CATEGORIES = {
    "Diplomacy": [
        r"\bdiplomacy\b", r"\bdiplomatic\b", r"\bambassador\b", r"\btreaty\b",
        r"\bforeign affairs\b", r"\bbilateral\b", r"\bsummit\b", r"\bsanctions\b",
        r"\bembassy\b", r"\bquad\b", r"\baukus\b", r"\bpacific islands\b", r"\bun\b",
        r"\bforeign minister\b", r"\balbanese\b", r"\bpenny wong\b"
    ],
    "Military": [
        r"\bmilitary\b", r"\bdefence\b", r"\bdefense\b", r"\bnavy\b", r"\barmy\b",
        r"\bair force\b", r"\badf\b", r"\bsubmarine\b", r"\bmissile\b", r"\bwarship\b",
        r"\btroops\b", r"\bsecurity forces\b", r"\bpentagon\b", r"\bwar\b", r"\bconflict\b"
    ],
    "Energy": [
        r"\benergy\b", r"\bpower\b", r"\belectricity\b", r"\bsolar\b", r"\bwind\b",
        r"\bcoal\b", r"\bgas\b", r"\bnuclear\b", r"\brenewable\b", r"\bemissions\b",
        r"\bnet zero\b", r"\bgrid\b", r"\bhydrogen\b", r"\bbattery\b", r"\boffshore wind\b"
    ],
    "Economy": [
        r"\beconomy\b", r"\beconomic\b", r"\brba\b", r"\breserve bank\b", r"\binflation\b",
        r"\binterest rate\b", r"\bgdp\b", r"\btrade\b", r"\btax\b", r"\bbudget\b",
        r"\bhousing market\b", r"\brecession\b", r"\bunemployment\b", r"\bmortgage\b",
        r"\basx\b", r"\bshares\b", r"\btreasurer\b", r"\bjim chalmers\b"
    ],
    "Local Events": [
        r"\bpolice\b", r"\bcourt\b", r"\bcrime\b", r"\bweather\b", r"\bstorm\b",
        r"\bbushfire\b", r"\bflood\b", r"\bsydney\b", r"\bmelbourne\b", r"\bbrisbane\b",
        r"\bperth\b", r"\badelaide\b", r"\bcanberra\b", r"\bqueensland\b", r"\bvictoria\b",
        r"\bnsw\b", r"\bhospital\b", r"\btraffic\b", r"\bcommunity\b"
    ]
}

def translate_to_english(text: str) -> str:
    """Ensure text is translated into English if necessary."""
    if not text:
        return ""
    try:
        # Most Australian sources are already in English; fallback safely if non-English
        return GoogleTranslator(source='auto', target='en').translate(text)
    except Exception:
        return text

def parse_date(date_str: str) -> datetime:
    """Parse various RSS date formats into UTC datetime object."""
    try:
        parsed_dt = dateutil.parser.parse(date_str)
        if parsed_dt.tzinfo is None:
            parsed_dt = parsed_dt.replace(tzinfo=timezone.utc)
        else:
            parsed_dt = parsed_dt.astimezone(timezone.utc)
        return parsed_dt
    except Exception:
        return datetime.now(timezone.utc)

def categorize_story(title: str, summary: str = "") -> str:
    """Classify story into one of the 5 categories using keyword matching."""
    combined_text = f"{title} {summary}".lower()
    
    for category, patterns in CATEGORIES.items():
        for pattern in patterns:
            if re.search(pattern, combined_text):
                return category
                
    return "Local Events"

def load_existing_data(file_path: str) -> list:
    """Load existing JSON file if present."""
    if os.path.exists(file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    now = datetime.now(timezone.utc)
    cutoff_date = now - timedelta(days=MAX_AGE_DAYS)

    # Load existing data and retain stories <= 7 days old
    existing_stories = load_existing_data(OUTPUT_FILE)
    valid_existing = []
    for story in existing_stories:
        try:
            story_dt = parse_date(story.get("published_date", ""))
            if story_dt >= cutoff_date:
                valid_existing.append(story)
        except Exception:
            continue

    # Fetch new stories
    new_stories = []
    seen_urls = {s["url"] for s in valid_existing}

    for source_name, feed_url in FEEDS.items():
        try:
            parsed_feed = feedparser.parse(feed_url)
            for entry in parsed_feed.entries:
                url = entry.get("link", "")
                if not url or url in seen_urls:
                    continue

                raw_title = entry.get("title", "")
                summary = entry.get("summary", "")
                pub_date_str = entry.get("published", entry.get("updated", ""))

                story_dt = parse_date(pub_date_str)
                if story_dt < cutoff_date:
                    continue

                title = translate_to_english(raw_title)
                category = categorize_story(title, summary)

                new_story = {
                    "title": title,
                    "source": source_name,
                    "url": url,
                    "published_date": story_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "category": category
                }

                new_stories.append(new_story)
                seen_urls.add(url)
        except Exception as e:
            print(f"Error processing feed {source_name}: {e}")

    # Combine existing valid stories with new stories
    all_stories = valid_existing + new_stories

    # Group stories by category
    categorized_groups = {
        "Diplomacy": [],
        "Military": [],
        "Energy": [],
        "Economy": [],
        "Local Events": []
    }

    for story in all_stories:
        cat = story.get("category", "Local Events")
        if cat in categorized_groups:
            categorized_groups[cat].append(story)
        else:
            categorized_groups["Local Events"].append(story)

    # Deduplicate, sort by date descending, and keep up to 20 newest per category
    final_output = []
    for category, stories in categorized_groups.items():
        # Sort newest first
        stories.sort(
            key=lambda x: parse_date(x["published_date"]), 
            reverse=True
        )
        # Retain top 20 newest stories
        retained = stories[:MAX_STORIES_PER_CATEGORY]
        final_output.extend(retained)

    # Sort overall list by category then date
    final_output.sort(key=lambda x: (x["category"], parse_date(x["published_date"])), reverse=True)

    # Write output JSON
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=2, ensure_ascii=False)

    print(f"Successfully saved {len(final_output)} stories to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
