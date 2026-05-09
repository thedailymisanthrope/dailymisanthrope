#!/usr/bin/env python3
"""
The Daily Misanthrope — Automated Curation Agent
Runs once daily via GitHub Actions. Discovers, filters, ranks, and publishes
stories of human folly. Also reads editor tips from a Google Sheet.
"""

import json
import os
import re
import hashlib
import csv
import io
from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import requests
from openai import OpenAI

# ── Configuration ───────────────────────────────────────────────
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
GOOGLE_SHEET_CSV_URL = os.environ.get("GOOGLE_SHEET_CSV_URL", "")
STORIES_JSON_PATH = Path("data/stories.json")
TIPS_ARCHIVE_PATH = Path("data/tips_archive.json")
MODEL = "gpt-4o"  # or "gpt-4o-mini" for lower cost
MAX_STORIES = 8
FOLLY_COUNT = 1

# RSS feeds to check
RSS_FEEDS = [
    # Core aggregators
    "https://www.fark.com/fark.rss",
    "https://www.reddit.com/r/nottheonion/.rss",
    "https://www.reddit.com/r/FloridaMan/.rss",
    "https://boingboing.net/feed",
    "https://www.thesmokinggun.com/rss.xml",
    "https://www.odditycentral.com/feed",
    "https://www.upi.com/Odd_News/feed/",
    # Personal confession & self-inflicted folly
    "https://www.reddit.com/r/tifu/.rss",
    "https://www.reddit.com/r/AmItheAsshole/.rss",
    "https://www.reddit.com/r/mildlyinfuriating/.rss",
    "https://www.reddit.com/r/EntitledPeople/.rss",
    "https://www.reddit.com/r/ChoosingBeggars/.rss",
    "https://www.reddit.com/r/quityourbullshit/.rss",
    # Florida sources (The Motherland)
    "https://www.reddit.com/r/florida/.rss",
    # Alaska sources (The Other Motherland)
    "https://www.reddit.com/r/alaska/.rss",
    "https://www.adn.com/feed/",
    # Other states of notable folly
    "https://www.reddit.com/r/texas/.rss",
    "https://www.reddit.com/r/Ohio/.rss",
    "https://www.reddit.com/r/newjersey/.rss",
    "https://www.reddit.com/r/california/.rss",
    # Broader weird news subreddits
    "https://www.reddit.com/r/WTF/.rss",
    "https://www.reddit.com/r/IdiotsFightingThings/.rss",
    "https://www.reddit.com/r/Whatcouldgowrong/.rss",
    "https://www.reddit.com/r/trashy/.rss",
    "https://www.reddit.com/r/PublicFreakout/.rss",
    "https://www.reddit.com/r/mildlyinteresting/.rss",
    # Legal absurdity
    "https://loweringthebar.net/feed",
    "https://www.reddit.com/r/bestoflegaladvice/.rss",
    "https://www.reddit.com/r/legaladvice/.rss",
    "https://abovethelaw.com/feed/",
    # British tabloid gold
    "https://www.dailymail.co.uk/news/index.rss",
    "https://www.thesun.co.uk/news/feed/",
    "https://www.mirror.co.uk/news/weird-news/rss.xml",
    "https://news.google.com/rss/search?q=british+man+OR+british+woman+bizarre+OR+UK+man+arrested+OR+UK+woman+fined&hl=en-US",
    # NY Post weird news
    "https://nypost.com/weird-but-true/feed/",
    # Australian folly
    "https://www.reddit.com/r/australia/.rss",
    "https://news.google.com/rss/search?q=australia+man+OR+australia+woman+bizarre+OR+queensland+man+OR+sydney+man+arrested&hl=en-US",
    # Google News odd/bizarre stories
    "https://news.google.com/rss/search?q=bizarre+OR+odd+news+OR+weird+OR+strange&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=alaska+man+OR+alaska+woman+OR+alaska+bizarre&hl=en-US&gl=US&ceid=US:en",
    "https://news.google.com/rss/search?q=man+arrested+for+OR+woman+arrested+for+bizarre+OR+unusual+arrest&hl=en-US",
    # Stupid criminals (worldwide)
    "https://news.google.com/rss/search?q=stupid+criminal+OR+dumb+criminal+OR+worst+burglar+OR+failed+robbery&hl=en-US",
    "https://news.google.com/rss/search?q=robber+forgot+OR+burglar+fell+asleep+OR+thief+left+ID+OR+getaway+driver&hl=en-US",
    "https://news.google.com/rss/search?q=bizarre+court+case+OR+outlandish+lawsuit+OR+strange+legal&hl=en-US",
    "https://news.google.com/rss/search?q=sued+for+OR+lawsuit+filed+OR+man+sues+OR+woman+sues+bizarre&hl=en-US",
    "https://www.reddit.com/r/therewasanattempt/.rss",
    "https://www.reddit.com/r/instantkarma/.rss",
    "https://www.reddit.com/r/KarmaIsABitch/.rss",
    # HOA and bureaucratic petty tyranny
    "https://www.reddit.com/r/fuckHOA/.rss",
    "https://news.google.com/rss/search?q=HOA+fined+OR+HOA+bans+OR+city+council+bans+OR+ordinance+bans+bizarre&hl=en-US",
    "https://news.google.com/rss/search?q=bureaucrat+OR+government+worker+OR+city+official+bizarre+decision&hl=en-US",
    # Ignorance & educational folly
    "https://news.google.com/rss/search?q=college+students+cant+answer+OR+students+dont+know+OR+spring+break+quiz+OR+man+on+the+street+quiz&hl=en-US",
    "https://news.google.com/rss/search?q=Americans+cant+name+OR+Americans+dont+know+OR+geography+fail+OR+history+fail&hl=en-US",
    "https://news.google.com/rss/search?q=survey+finds+Americans+OR+poll+Americans+dont+know+OR+percent+of+Americans+believe&hl=en-US",
    "https://www.reddit.com/r/confidentlyincorrect/.rss",
    "https://www.reddit.com/r/facepalm/.rss",
    "https://www.reddit.com/r/iamverysmart/.rss",
    # Remarks from the Throne — bipartisan political stupidity
    "https://news.google.com/rss/search?q=politician+gaffe+OR+senator+says+OR+congressman+says+OR+bizarre+statement&hl=en-US",
    "https://news.google.com/rss/search?q=mayor+says+OR+governor+says+OR+minister+says+bizarre+OR+politician+claims&hl=en-US",
    "https://www.reddit.com/r/PoliticalHumor/.rss",
    # The Treadwell Effect — humans vs. nature hubris
    "https://news.google.com/rss/search?q=exotic+pet+attack+OR+wild+animal+pet+OR+tourist+wildlife+encounter+OR+bear+attack+tourist&hl=en-US",
    "https://news.google.com/rss/search?q=Darwin+Award+OR+selfie+with+wild+animal+OR+approached+bear+OR+pet+tiger+OR+pet+alligator&hl=en-US",
    "https://news.google.com/rss/search?q=ignored+warning+OR+despite+signs+OR+against+advice+OR+tourist+ignored&hl=en-US",
    "https://www.reddit.com/r/DarwinAwards/.rss",
    "https://www.reddit.com/r/winstupidprizes/.rss",
    "https://www.reddit.com/r/interestingasfuck/.rss",
    # International weird news
    "https://news.google.com/rss/search?q=bizarre+news+OR+odd+news+OR+weird+news&hl=en",
    "https://news.google.com/rss/search?q=russia+man+OR+china+man+OR+india+man+bizarre+OR+germany+man+arrested&hl=en-US",
    "https://www.reddit.com/r/ANormalDayInRussia/.rss",
    "https://www.reddit.com/r/CasualUK/.rss",
    "https://www.reddit.com/r/australia/.rss",
    "https://www.reddit.com/r/canada/.rss",
    # Sports folly
    "https://news.google.com/rss/search?q=athlete+arrested+OR+player+suspended+bizarre+OR+coach+ejected+OR+fan+arrested+stadium&hl=en-US",
    # Corporate and tech idiocy
    "https://news.google.com/rss/search?q=company+bans+OR+employer+fires+for+OR+HR+policy+bizarre+OR+corporate+memo&hl=en-US",
    "https://www.reddit.com/r/antiwork/.rss",
    "https://www.reddit.com/r/MaliciousCompliance/.rss",
]

# Keywords that suggest amusing stupidity (boost signal)
BOOST_KEYWORDS = [
    "florida man", "florida woman", "bizarre", "odd", "weird",
    "stupid", "fails", "accidentally", "mistakenly", "confused",
    "lawsuit", "HOA", "council votes", "banned", "fined",
    # Legal & court absurdity
    "judge ruled", "plaintiff", "sued", "court ordered", "pro se",
    "sovereign citizen", "injunction", "frivolous", "dismissed",
    "restraining order", "small claims", "neighbor dispute",
    # Drudge-style weirdness
    "outrage", "baffled", "stunned", "inexplicable", "unprecedented",
    # Florida-specific
    "alligator", "manatee", "walmart", "naked", "arrested for",
    # Alaska-specific
    "alaska man", "alaska woman", "moose", "grizzly", "snowmobile",
    "frostbite", "bush pilot", "remote village", "tundra",
    "iditarod", "frozen", "permafrost", "backcountry",
    # Other state-specific folly
    "texas man", "texas woman", "ohio man", "ohio woman",
    "florida man", "florida woman",
    # Stupid criminals (global)
    "burglar", "robber", "thief", "caught on camera", "called police on himself",
    "returned to the scene", "left ID at scene", "fell asleep", "getaway",
    "disguise", "accomplice", "botched", "bungled", "inept",
    "dumbest criminal", "worst robbery", "failed heist",
    # Bizarre legal (global)
    "judge ordered", "unusual sentence", "bizarre ruling", "strange verdict",
    "nuisance lawsuit", "vexatious litigant", "courtroom outburst",
    # International folly
    "australia man", "australia woman", "british man", "british woman",
    "russian man", "russian woman", "german man", "german woman",
    "japan man", "india man", "brazil man",
    # Ignorance & educational folly
    "can't name", "can't find", "don't know", "couldn't answer",
    "couldn't name", "couldn't find", "thought that",
    "spring break", "college students", "survey finds", "poll reveals",
    "geography fail", "history fail", "basic knowledge",
    "confidently incorrect", "dunning-kruger",
    # The Treadwell Effect — humans vs. nature hubris
    "exotic pet", "pet tiger", "pet alligator", "pet monkey", "pet snake",
    "selfie with bear", "approached the", "tried to pet",
    "darwin award", "wild animal", "wildlife encounter",
    "ignored warnings", "despite signs", "against advice",
    "national park", "fed the", "tourist bitten",
    # Remarks from the Throne — bipartisan political idiocy
    "gaffe", "misspoke", "walked back", "clarified", "did not mean",
    "controversial remark", "bizarre claim", "baseless",
    "senator says", "congressman says", "politician claims",
]

# Keywords that suggest violence/tragedy/exploitation (filter out)
# This is a HARD filter — stories matching these terms are never shown.
REJECT_KEYWORDS = [
    # Violence & death
    "killed", "murdered", "died", "shooting", "stabbing",
    "terrorist", "massacre", "suicide", "overdose", "fatal",
    "homicide", "manslaughter",
    # Sexual assault & exploitation — zero tolerance
    "sexual assault", "sexually assaulted", "rape", "raped",
    "molestation", "molested", "molester",
    "sex offender", "sex trafficking", "trafficking",
    "indecent", "indecency",
    "groping", "groped",
    # Crimes against children — absolute zero tolerance
    "child abuse", "child porn", "child exploitation",
    "child sex", "child molest", "child assault",
    "pedophil", "paedophil",  # catches pedophile, pedophilia, etc.
    "minor victim", "minors were",
    "underage", "prepubescent",
    "csam", "csem",
    "abuse of a child", "abuse of children",
    "crimes against children", "against a child",
    "juvenile victim",
    # General abuse
    "domestic violence", "domestic abuse",
    "abuse",  # broad but important — catches edge cases
    # Sexual content that skews uncomfortable
    "fetish", "sex act", "sex crime", "sexual misconduct",
    "revenge porn", "sextortion", "explicit",
]

client = OpenAI(api_key=OPENAI_API_KEY)


# ── Step 0: Read Editor Tips from Google Sheet ─────────────────

def read_editor_tips():
    """
    Read story tips/links/ideas from the editor's Google Sheet.
    The sheet is published as CSV. Columns expected:
      Timestamp, Type (link/idea/search), Content, Notes, Used
    
    Returns tips that haven't been marked as 'Used' yet.
    """
    if not GOOGLE_SHEET_CSV_URL:
        print("  ℹ No Google Sheet URL configured — skipping editor tips")
        return []
    
    try:
        resp = requests.get(GOOGLE_SHEET_CSV_URL, timeout=15)
        resp.raise_for_status()
        
        reader = csv.DictReader(io.StringIO(resp.text))
        tips = []
        for row in reader:
            # Skip if already used
            used = row.get("Used", "").strip().lower()
            if used in ("yes", "true", "1", "x"):
                continue
            
            tip_type = row.get("Type", "idea").strip().lower()
            content = row.get("Content", "").strip()
            notes = row.get("Notes", "").strip()
            timestamp = row.get("Timestamp", "").strip()
            
            if not content:
                continue
            
            tips.append({
                "type": tip_type,  # "link", "idea", or "search"
                "content": content,
                "notes": notes,
                "timestamp": timestamp,
                "source": "Editor Tip",
                "is_editor_tip": True,
            })
        
        print(f"  Found {len(tips)} unused editor tips")
        return tips
        
    except Exception as e:
        print(f"  ⚠ Failed to read editor tips: {e}")
        return []


def extract_youtube_id(url):
    """Extract YouTube video ID from a URL."""
    import re
    match = re.search(
        r'(?:youtube\.com/(?:watch\?v=|embed/)|youtu\.be/)([\w-]{11})', url
    )
    return match.group(1) if match else None


def process_editor_tips(tips):
    """
    Process editor tips into candidate stories.
    - Links: fetch the page title/summary (or handle YouTube)
    - Ideas: pass through as search suggestions
    - Search terms: use Google News to find matching stories
    """
    candidates = []
    search_terms = []
    
    youtube_tips = []

    for tip in tips:
        if tip["type"] == "link" and extract_youtube_id(tip["content"]):
            # YouTube link — treat as Video of the Day candidate
            youtube_tips.append(tip)
            continue

        if tip["type"] == "link":
            # Fetch the linked page to get title/summary
            try:
                resp = requests.get(tip["content"], timeout=10, 
                                   headers={"User-Agent": "DailyMisanthrope/1.0"})
                # Extract title from HTML (basic)
                title_match = re.search(r"<title[^>]*>(.*?)</title>", 
                                       resp.text, re.IGNORECASE | re.DOTALL)
                title = title_match.group(1).strip() if title_match else tip["content"]
                # Clean up title
                title = re.sub(r"\s*[|\-–—]\s*.*$", "", title)  # remove site name suffix
                
                candidates.append({
                    "title": title,
                    "url": tip["content"],
                    "summary": tip.get("notes", title),
                    "source": "Editor Submission",
                    "id": hashlib.md5(tip["content"].encode()).hexdigest()[:12],
                    "boost": 10,  # Editor tips get maximum priority
                    "is_editor_tip": True,
                    "editor_notes": tip.get("notes", ""),
                })
            except Exception as e:
                print(f"  ⚠ Failed to fetch tip link {tip['content'][:50]}: {e}")
                # Still add it with whatever we have
                candidates.append({
                    "title": tip.get("notes", tip["content"][:80]),
                    "url": tip["content"],
                    "summary": tip.get("notes", ""),
                    "source": "Editor Submission",
                    "id": hashlib.md5(tip["content"].encode()).hexdigest()[:12],
                    "boost": 10,
                    "is_editor_tip": True,
                    "editor_notes": tip.get("notes", ""),
                })
        
        elif tip["type"] == "search":
            # Collect search terms to run later
            search_terms.append(tip["content"])
        
        elif tip["type"] == "idea":
            # Ideas get passed to the LLM as context for the day's curation
            # We don't add them as candidates directly
            pass
    
    # Run searches for any search terms
    for term in search_terms:
        try:
            # Use Google News RSS for free search
            search_url = (
                f"https://news.google.com/rss/search?"
                f"q={requests.utils.quote(term)}&hl=en-US&gl=US&ceid=US:en"
            )
            feed = feedparser.parse(search_url)
            for entry in feed.entries[:5]:  # top 5 results per search
                candidates.append({
                    "title": entry.get("title", "").strip(),
                    "url": entry.get("link", ""),
                    "summary": entry.get("summary", "")[:500],
                    "source": f"Search: {term}",
                    "id": hashlib.md5(entry.get("title", "").lower().encode()).hexdigest()[:12],
                    "boost": 8,  # Editor searches get high priority
                    "is_editor_tip": True,
                })
            print(f"  Searched '{term}': found {min(5, len(feed.entries))} results")
        except Exception as e:
            print(f"  ⚠ Search failed for '{term}': {e}")
    
    return candidates, [t for t in tips if t["type"] == "idea"], youtube_tips


# ── Step 1: Gather ─────────────────────────────────────────────

def gather_candidates():
    """Pull stories from all RSS feeds."""
    candidates = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:30]:
                title = entry.get("title", "").strip()
                link = entry.get("link", "")
                summary = entry.get("summary", "")[:500]
                source = feed.feed.get("title", feed_url)
                
                if not title:
                    continue
                    
                candidates.append({
                    "title": title,
                    "url": link,
                    "summary": summary,
                    "source": source,
                    "id": hashlib.md5(title.lower().encode()).hexdigest()[:12],
                })
        except Exception as e:
            print(f"  ⚠ Failed to fetch {feed_url}: {e}")
    
    # Deduplicate by title hash
    seen = set()
    unique = []
    for c in candidates:
        if c["id"] not in seen:
            seen.add(c["id"])
            unique.append(c)
    
    print(f"  Gathered {len(unique)} unique candidates from {len(RSS_FEEDS)} feeds")
    return unique


# ── Step 2: Pre-filter ─────────────────────────────────────────

def pre_filter(candidates):
    """Quick keyword-based filter before sending to LLM."""
    filtered = []
    for c in candidates:
        text = (c["title"] + " " + c.get("summary", "")).lower()
        
        # Reject violence/tragedy (but never reject editor tips)
        if not c.get("is_editor_tip") and any(kw in text for kw in REJECT_KEYWORDS):
            continue
        
        # Boost score for folly keywords
        boost = c.get("boost", 0) + sum(1 for kw in BOOST_KEYWORDS if kw in text)
        c["boost"] = boost
        filtered.append(c)
    
    # Sort by boost score (editor tips will be at top)
    filtered.sort(key=lambda x: x.get("boost", 0), reverse=True)
    
    # Take top 40 for LLM evaluation
    filtered = filtered[:40]
    print(f"  Pre-filtered to {len(filtered)} candidates")
    return filtered


# ── Step 3: LLM Classification ─────────────────────────────────

def classify_stories(candidates, editor_ideas=None):
    """Use LLM to classify each story as amusing-folly or not."""
    
    stories_text = "\n".join([
        f"[{i}] {'⭐ EDITOR TIP: ' if c.get('is_editor_tip') else ''}{c['title']}\n"
        f"    {c.get('summary', '')[:200]}"
        f"{chr(10) + '    Editor notes: ' + c['editor_notes'] if c.get('editor_notes') else ''}"
        for i, c in enumerate(candidates)
    ])
    
    # Include editor ideas as context
    ideas_context = ""
    if editor_ideas:
        ideas_text = "\n".join([f"- {idea['content']}" + 
                                (f" ({idea['notes']})" if idea.get('notes') else "")
                                for idea in editor_ideas])
        ideas_context = f"""

The editor has also submitted these IDEAS for today's edition. 
Use these to inform your selections — look for stories that match these themes:
{ideas_text}
"""
    
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.3,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": f"""You are the editorial filter for "The Daily Misanthrope," 
a content aggregator that showcases amusing human stupidity and folly.

Your job: classify each story as one of:
- "FOLLY" — genuinely amusing human stupidity, bureaucratic absurdity, 
  self-inflicted problems, petty tyranny, or spectacular bad judgment. 
  The kind of thing that makes a misanthrope chuckle darkly.
- "SKIP" — too violent, too tragic, too political, too boring, 
  or just not funny enough.

IMPORTANT GUIDELINES:
- Keep it LIGHT. No death, serious injury, or genuine suffering.
- ABSOLUTE HARD RULES (never break these):
  * NO sexual assault, rape, or sexual violence of any kind
  * NO crimes against children of any kind — zero tolerance
  * NO child abuse, exploitation, trafficking, or endangerment
  * NO stories involving minors as victims in any context
  * If in doubt about whether a story involves any of the above, SKIP it.
- Political stories are fine IF they showcase bipartisan stupidity.
- Corporate/bureaucratic absurdity is gold.
- Self-inflicted problems where nobody was seriously hurt are perfect.
- HOA disputes, bizarre lawsuits, and "Florida Man" stories are ideal.
- GEOGRAPHIC DIVERSITY: Don't just pick Florida stories. This is a GLOBAL
  catalogue of human folly. Alaska, Texas, Ohio, Russia, Australia, the UK,
  and anywhere else humans do stupid things. Moose encounters, snowmobile mishaps,
  backcountry misadventures, and small-town bureaucratic absurdity are all gold.
  Aim for at most 2-3 Florida stories per day — fill the rest from elsewhere.
- STUPID CRIMINALS are gold. Burglars who fall asleep on the job, robbers who
  leave their ID at the scene, getaway drivers who run out of gas, criminals who
  call the police on themselves. These are the site's bread and butter.
- BIZARRE LEGAL CASES from anywhere in the world. Outlandish lawsuits, absurd
  court rulings, vexatious litigants, unusual sentences, courtroom theatrics.
- IGNORANCE & EDUCATIONAL FOLLY: surveys showing Americans can't find countries
  on a map, college students who can't name a single Supreme Court justice,
  spring break interviews where nobody knows who won the Civil War, polls
  revealing spectacular gaps in basic knowledge. The Dunning-Kruger beat.
- REMARKS FROM THE THRONE: spectacularly dumb things said by politicians of
  ANY party, ANY country. Gaffes, bizarre claims, statements that defy basic
  logic or science. This is STRICTLY BIPARTISAN — mock the left and right
  equally. The site hates everybody. If you include a Republican gaffe, try
  to pair it with a Democrat one (or vice versa) in the same edition. The
  category name should be "Remarks from the Throne" or similar.
- THE TREADWELL EFFECT: stories about humans who approach wild nature with
  catastrophic naivete — buying exotic predators as pets, approaching bears
  for selfies, ignoring every warning sign at national parks, treating wild
  animals as stuffed toys. The category name comes from Timothy Treadwell.
  For these stories use category name: "Treadwell Effect"
  IMPORTANT: For Treadwell stories, focus the headline and commentary on the
  DECISION and the HUBRIS, not the gory outcome. "Man Purchases Adult Tiger
  on Craigslist, Expresses Surprise at Subsequent Events" — not a graphic
  description of what happened next. The comedy is in the presumption, not
  the consequence. These stories are an EXCEPTION to the violence filter —
  they can be included even if outcomes are serious, as long as the framing
  stays focused on the folly of the decision itself.
- Stories marked ⭐ EDITOR TIP were personally submitted by the editor — 
  give them strong preference unless they're clearly inappropriate.
{ideas_context}
Return JSON: {{"classifications": [{{"index": 0, "verdict": "FOLLY", "category": "Bureaucratic Farce"}}, ...]}}
Categories should be dry and sardonic."""
            },
            {
                "role": "user",
                "content": f"Classify these stories:\n\n{stories_text}"
            }
        ]
    )
    
    result = json.loads(response.choices[0].message.content)
    classifications = {c["index"]: c for c in result["classifications"]}
    
    folly_stories = []
    for i, candidate in enumerate(candidates):
        cl = classifications.get(i, {})
        if cl.get("verdict") == "FOLLY":
            candidate["category"] = cl.get("category", "General Folly")
            folly_stories.append(candidate)
    
    print(f"  LLM classified {len(folly_stories)} as FOLLY out of {len(candidates)}")
    return folly_stories


# ── Step 4: Rank & Select ──────────────────────────────────────

def rank_stories(folly_stories):
    """Use LLM to rank stories by entertainment value."""
    
    if len(folly_stories) <= MAX_STORIES:
        # If we have editor tips, prefer them for FOTD
        for s in folly_stories:
            s["is_fotd"] = False
        editor_tips = [s for s in folly_stories if s.get("is_editor_tip")]
        if editor_tips:
            editor_tips[0]["is_fotd"] = True
        elif folly_stories:
            folly_stories[0]["is_fotd"] = True
        return folly_stories
    
    stories_text = "\n".join([
        f"[{i}] {'⭐ ' if s.get('is_editor_tip') else ''}[{s['category']}] {s['title']}"
        for i, s in enumerate(folly_stories)
    ])
    
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.5,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": f"""You are ranking stories for "The Daily Misanthrope."
Pick the {MAX_STORIES} most entertaining stories. Prioritize:
1. Stories marked ⭐ (editor submissions — always include these)
2. STRICT GEOGRAPHIC VARIETY — MAXIMUM 2 Florida stories total per edition.
   If you have more than 2 Florida stories, drop the weakest ones in favor of
   stories from other states or countries. The whole world is stupid, not just
   Florida. Actively prefer non-Florida stories of equal quality.
3. Category variety (mix lawsuits, bureaucracy, self-inflicted, wildlife,
   political, ignorance, Treadwell, international, etc.)
4. Inherent absurdity and humor
5. One story should be the "Folly of the Day" (best overall — prefer ⭐ stories)

Return JSON: {{"ranked": [0, 3, 7, ...], "folly_of_the_day": 3}}"""
            },
            {
                "role": "user",
                "content": f"Rank these {len(folly_stories)} stories:\n\n{stories_text}"
            }
        ]
    )
    
    result = json.loads(response.choices[0].message.content)
    ranked_indices = result["ranked"][:MAX_STORIES]
    fotd_index = result.get("folly_of_the_day", ranked_indices[0])
    
    selected = [folly_stories[i] for i in ranked_indices if i < len(folly_stories)]
    
    for s in selected:
        s["is_fotd"] = False
    if fotd_index < len(folly_stories):
        folly_stories[fotd_index]["is_fotd"] = True
        if folly_stories[fotd_index] not in selected:
            selected.insert(0, folly_stories[fotd_index])
    
    print(f"  Selected {len(selected)} stories")
    return selected


# ── Step 5: Write Commentary ───────────────────────────────────

def write_commentary(fotd_story):
    """Write the Folly of the Day expanded commentary."""
    
    editor_context = ""
    if fotd_story.get("editor_notes"):
        editor_context = f"\nEditor's notes on this story: {fotd_story['editor_notes']}"
    
    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.7,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system",
                "content": """You are the editor of "The Daily Misanthrope."
Write the expanded "Folly of the Day" entry. Your voice is:
- Erudite but accessible (think a classics professor at a bar)
- Dry wit, never cruel
- Observational, not preachy
- Occasionally references history, philosophy, or literature
- Finds the universal human condition in specific stupidity

Return JSON:
{
  "headline": "...",
  "summary": "A 2-3 paragraph expanded telling of the story (150-250 words).",
  "commentary": "A 1-2 sentence editorial observation. Wry, philosophical.",
  "epigraph": {
    "text": "Idiocracy is not a comedy. It's a documentary",
    "attribution": "Jesus of Nazareth"
  },
  "misanthrope_index": {
    "value": 7.4,
    "label": "Disappointing"
  }
}

For the epigraph: Choose a fresh, fitting quote about human folly, stupidity,
civilization's decline, or misanthropy. Draw from philosophers, writers, satirists,
historians, or wits — Mencken, Twain, Bierce, Wilde, Voltaire, Swift, Schopenhauer,
Nietzsche, Chesterton, Orwell, Waugh, or others. The quote should be genuinely
attributed and accurate. Keep it dry and pointed, not maudlin.

For the Misanthrope Index (1-10 scale):
1-3: "Merely Disappointing" (calm day)
4-5: "Disappointing" (normal nonsense)
6-7: "Quite Disappointing" (typical folly)
8-9: "Approaching Full Walken" (spectacular stupidity)
10: "Full Walken" (reserved for truly epic folly)"""
            },
            {
                "role": "user",
                "content": f"""Write the Folly of the Day for this story:

Title: {fotd_story['title']}
Source: {fotd_story['source']}
Summary: {fotd_story.get('summary', '')}
Category: {fotd_story['category']}{editor_context}"""
            }
        ]
    )
    
    return json.loads(response.choices[0].message.content)


# ── Step 6: Assemble & Publish ─────────────────────────────────

def publish(selected_stories, commentary, youtube_tips=None):
    """Assemble the final stories.json and write it."""
    
    now = datetime.now(timezone.utc)
    # Convert to Central Time for the edition line
    ct = now - timedelta(hours=5)  # CDT (adjust to -6 for CST)
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", 
                 "Friday", "Saturday", "Sunday"]
    day_name = day_names[ct.weekday()]
    
    # Separate FOTD, Treadwell stories, and wire
    fotd = None
    treadwell_stories = []
    wire_stories = []
    treadwell_categories = {"treadwell effect", "treadwell", "wildlife hubris", 
                            "misguided naturalist", "nature's correction",
                            "man vs beast", "hubris vs nature"}
    for s in selected_stories:
        if s.get("is_fotd"):
            fotd = s
        elif s.get("category", "").lower() in treadwell_categories:
            treadwell_stories.append(s)
        else:
            wire_stories.append(s)
    
    if not fotd and selected_stories:
        fotd = selected_stories[0]
        wire_stories = selected_stories[1:]
    
    # Some headlines ALL CAPS (Drudge style)
    for i, s in enumerate(wire_stories):
        if i % 3 == 0:
            s["title"] = s["title"].upper()
    
    output = {
        "lastUpdated": now.isoformat(),
        "edition": f"Vol. I, No. {ct.timetuple().tm_yday} — {day_name}, "
                   f"{ct.strftime('%B %d, %Y')}",
        "epigraph": commentary.get("epigraph", {
            "text": "Every normal man must be tempted, at times, to spit on his hands, hoist the black flag, and begin slitting throats.",
            "attribution": "H.L. Mencken"
        }),
        "follyOfTheDay": {
            "headline": commentary.get("headline", fotd["title"]),
            "summary": commentary.get("summary", fotd.get("summary", "")),
            "source": fotd["source"],
            "sourceUrl": fotd["url"],
            "category": fotd["category"],
            "commentary": commentary.get("commentary", "No comment necessary.")
        },
        "stories": [
            {
                "headline": s["title"],
                "url": s["url"],
                "source": s["source"],
                "category": s["category"]
            }
            for s in wire_stories
        ],
        "misanthropeIndex": {
            "value": commentary.get("misanthrope_index", {}).get("value", 6.5),
            "label": commentary.get("misanthrope_index", {}).get("label", "Disappointing"),
            "scale": "Disappointing — Full Walken"
        },
        "treadwellCorner": [
            {
                "headline": s["title"],
                "url": s["url"],
                "source": s["source"],
                "category": s["category"]
            }
            for s in treadwell_stories
        ] if treadwell_stories else None
    }

    # Add Video of the Day if a YouTube tip was submitted
    if youtube_tips:
        yt = youtube_tips[0]  # Use the most recent YouTube tip
        output["videoOfTheDay"] = {
            "url": yt["content"],
            "title": yt.get("notes", "Video of the Day"),
            "caption": yt.get("notes", ""),
            "category": "Exhibit A",
        }
        print(f"  ✓ Video of the Day: {yt['content'][:60]}")
    else:
        output["videoOfTheDay"] = None
    
    STORIES_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORIES_JSON_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"  ✓ Published {len(wire_stories)} wire stories + FOTD")
    print(f"  ✓ Misanthrope Index: {output['misanthropeIndex']['value']} "
          f"({output['misanthropeIndex']['label']})")
    return output


# ── Main Pipeline ──────────────────────────────────────────────

def main():
    print("═" * 50)
    print("THE DAILY MISANTHROPE — Curation Agent")
    print(f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("═" * 50)
    
    # Step 0: Read editor tips
    print("\n📬 Step 0: Reading editor tips...")
    editor_tips = read_editor_tips()
    tip_candidates, editor_ideas, youtube_tips = process_editor_tips(editor_tips) if editor_tips else ([], [], [])
    if tip_candidates:
        print(f"  Processed {len(tip_candidates)} tip candidates, {len(editor_ideas)} ideas")
    
    # Step 1: Gather RSS candidates
    print("\n📡 Step 1: Gathering RSS candidates...")
    rss_candidates = gather_candidates()
    
    # Merge: editor tips first, then RSS
    candidates = tip_candidates + rss_candidates
    if not candidates:
        print("  ✗ No candidates found. Humanity gets a pass today.")
        return
    
    # Step 2: Pre-filter
    print("\n🔍 Step 2: Pre-filtering...")
    filtered = pre_filter(candidates)
    if not filtered:
        print("  ✗ All candidates filtered out. Suspicious.")
        return
    
    # Step 3: LLM Classification
    print("\n🧠 Step 3: LLM Classification...")
    folly_stories = classify_stories(filtered, editor_ideas)
    if not folly_stories:
        print("  ✗ No stories classified as FOLLY. An unusually wise day.")
        return
    
    # Step 4: Rank & Select
    print("\n📊 Step 4: Ranking & Selection...")
    selected = rank_stories(folly_stories)
    
    fotd = next((s for s in selected if s.get("is_fotd")), selected[0])
    
    # Step 5: Write commentary
    print("\n✍️  Step 5: Writing commentary...")
    commentary = write_commentary(fotd)
    
    # Step 6: Publish
    print("\n📰 Step 6: Publishing...")
    publish(selected, commentary, youtube_tips)
    
    print("\n" + "═" * 50)
    print("Done. Humanity remains disappointing.")
    print("═" * 50)


if __name__ == "__main__":
    main()

