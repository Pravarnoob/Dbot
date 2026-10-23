"""Posts new posts from a subreddit to a Discord channel via webhook.

Usage:
  python bot.py          # runs forever, checks every 5 minutes
  python bot.py --once   # checks once and exits (for GitHub Actions / cron)

Environment variables:
  DISCORD_WEBHOOK  (required) your Discord webhook URL
  SUBREDDIT        (optional) subreddit name, default "python"
"""
import json
import os
import sys
import time

import feedparser
import requests

SUBREDDIT = os.environ.get("SUBREDDIT", "python")
WEBHOOK = os.environ["DISCORD_WEBHOOK"]
INTERVAL = 300  # seconds (5 minutes)
SEEN_FILE = "seen.json"
FEED_URL = f"https://www.reddit.com/r/{SUBREDDIT}/new/.rss"
USER_AGENT = "reddit-discord-notifier/0.1"


def load_seen():
    try:
        with open(SEEN_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None  # None = first ever run


def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(seen[-300:], f)  # keep the file small


def send(entry):
    payload = {"content": f"**New post in r/{SUBREDDIT}**\n**{entry.title}**\n{entry.link}"}
    while True:
        r = requests.post(WEBHOOK, json=payload, timeout=15)
        if r.status_code == 429:  # rate limited by Discord
            time.sleep(r.json().get("retry_after", 2))
            continue
        r.raise_for_status()
        return


def check():
    seen = load_seen()
    first_run = seen is None
    seen = seen or []

    feed = feedparser.parse(FEED_URL, agent=USER_AGENT)
    if not feed.entries:
        print(f"No entries returned (HTTP {getattr(feed, 'status', '?')}). Will retry.")
        return

    new = [e for e in reversed(feed.entries) if e.id not in seen]  # oldest first
    for entry in new:
        if not first_run:  # on the very first run, just remember existing posts
            try:
                send(entry)
                print("Posted:", entry.title)
                time.sleep(1)
            except requests.RequestException as e:
                print("Discord error:", e)
                continue  # not marked as seen, so it retries next time
        seen.append(entry.id)

    save_seen(seen)


if __name__ == "__main__":
    if "--once" in sys.argv:
        check()
    else:
        while True:
            try:
                check()
            except Exception as e:  # keep the bot alive no matter what
                print("Error:", e)
            time.sleep(INTERVAL)
