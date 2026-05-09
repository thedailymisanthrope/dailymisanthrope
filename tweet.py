#!/usr/bin/env python3
"""
Daily Misanthrope — X (Twitter) posting script
Posts today's edition headline and link to @DMisanthro24714
"""
import json
import sys
import warnings
warnings.filterwarnings("ignore")

try:
    import tweepy
except ImportError:
    print("tweepy not installed. Run: pip3 install tweepy")
    sys.exit(1)

API_KEY = "cdGU1tVb5rx3MGmeNbY9whY1Y"
API_SECRET = "vlEkBei8SHbu5px4qMSa7PpvtMVI1exiJBJTDBfwq7p3BWM75M"
ACCESS_TOKEN = "2046423353074794496-SN6bYqiVX4t7PyraGa3kUrdMxFRRQ9"
ACCESS_SECRET = "GXNvP3Ay3QN6qd7E71zD7Xl1p2M09O15ThOURk5D7Io6m"

SITE_URL = "https://dailymisanthrope.com"
DATA_FILE = "/tmp/misanthrope/data/stories.json"

def build_tweet(data):
    edition = data.get("edition", "")
    epigraph = data.get("epigraph", {})
    folly = data.get("follyOfTheDay", {})

    lines = []

    if folly.get("headline"):
        headline = folly["headline"]
        if len(headline) > 200:
            headline = headline[:197] + "..."
        lines.append(headline)

    if epigraph.get("text") and epigraph.get("attribution"):
        quote = f'"{epigraph["text"]}" — {epigraph["attribution"]}'
        if len(quote) <= 140:
            lines.append(quote)

    lines.append(SITE_URL)

    tweet = "\n\n".join(lines)

    if len(tweet) > 280:
        tweet = f'{folly["headline"][:200]}...\n\n{SITE_URL}'

    return tweet


def main():
    with open(DATA_FILE) as f:
        data = json.load(f)

    tweet_text = build_tweet(data)
    print("Posting tweet:")
    print("-" * 40)
    print(tweet_text)
    print("-" * 40)
    print(f"Length: {len(tweet_text)} chars")

    client = tweepy.Client(
        consumer_key=API_KEY,
        consumer_secret=API_SECRET,
        access_token=ACCESS_TOKEN,
        access_token_secret=ACCESS_SECRET
    )

    resp = client.create_tweet(text=tweet_text)
    print(f"SUCCESS — Tweet ID: {resp.data['id']}")
    return resp.data["id"]


if __name__ == "__main__":
    main()
