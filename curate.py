#!/usr/bin/env python3
"""
The Daily Misanthrope — Automated Curation Pipeline
Runs once daily. Discovers, filters, and publishes stories of human folly.
Then deploys to Netlify and posts to X.
"""

import json, os, re, hashlib, io, sys, urllib.request, urllib.parse
import warnings
warnings.filterwarnings("ignore")

from datetime import datetime, timezone, timedelta
from pathlib import Path

import feedparser
import anthropic
import tweepy

# ── Configuration ───────────────────────────────────────────────
# Load .env file from same directory if present
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
NETLIFY_TOKEN     = os.environ.get("NETLIFY_TOKEN", "")
NETLIFY_SITE_ID   = os.environ.get("NETLIFY_SITE_ID", "")
GITHUB_PAT        = os.environ.get("GITHUB_PAT", "")
X_API_KEY         = os.environ.get("X_API_KEY", "")
X_API_SECRET      = os.environ.get("X_API_SECRET", "")
X_ACCESS_TOKEN    = os.environ.get("X_ACCESS_TOKEN", "")
X_ACCESS_SECRET   = os.environ.get("X_ACCESS_SECRET", "")

REPO_ROOT     = Path(__file__).parent
STORIES_PATH  = REPO_ROOT / "data" / "stories.json"
SITE_URL      = "https://dailymisanthrope.com"
GITHUB_OWNER  = "thedailymisanthrope"
GITHUB_REPO   = "dailymisanthrope"
MODEL         = "claude-sonnet-4-6"
MIN_WIRE      = 5   # minimum wire stories
MAX_WIRE      = 8

# ── RSS Feeds ────────────────────────────────────────────────────
RSS_FEEDS = [
    # Core aggregators
    "https://www.fark.com/fark.rss",
    "https://www.reddit.com/r/nottheonion/.rss",
    "https://www.reddit.com/r/FloridaMan/.rss",
    "https://www.thesmokinggun.com/rss.xml",
    "https://nypost.com/weird-but-true/feed/",
    "https://www.upi.com/Odd_News/feed/",
    # Reddit folly
    "https://www.reddit.com/r/tifu/.rss",
    "https://www.reddit.com/r/AmItheAsshole/.rss",
    "https://www.reddit.com/r/EntitledPeople/.rss",
    "https://www.reddit.com/r/ChoosingBeggars/.rss",
    "https://www.reddit.com/r/facepalm/.rss",
    "https://www.reddit.com/r/confidentlyincorrect/.rss",
    "https://www.reddit.com/r/iamverysmart/.rss",
    "https://www.reddit.com/r/therewasanattempt/.rss",
    "https://www.reddit.com/r/instantkarma/.rss",
    "https://www.reddit.com/r/DarwinAwards/.rss",
    "https://www.reddit.com/r/MaliciousCompliance/.rss",
    "https://www.reddit.com/r/PublicFreakout/.rss",
    "https://www.reddit.com/r/IdiotsFightingThings/.rss",
    "https://www.reddit.com/r/Whatcouldgowrong/.rss",
    "https://www.reddit.com/r/fuckHOA/.rss",
    "https://www.reddit.com/r/bestoflegaladvice/.rss",
    # Legal absurdity
    "https://loweringthebar.net/feed",
    "https://abovethelaw.com/feed/",
    # British tabloid
    "https://www.mirror.co.uk/news/weird-news/rss.xml",
    # Google News searches
    "https://news.google.com/rss/search?q=stupid+criminal+OR+dumb+criminal+OR+failed+robbery+OR+burglar+fell+asleep&hl=en-US",
    "https://news.google.com/rss/search?q=bizarre+court+case+OR+outlandish+lawsuit+OR+strange+verdict&hl=en-US",
    "https://news.google.com/rss/search?q=HOA+fined+OR+HOA+bans+OR+city+council+bans+bizarre&hl=en-US",
    "https://news.google.com/rss/search?q=darwin+award+OR+exotic+pet+attack+OR+selfie+with+bear+OR+tourist+wildlife&hl=en-US",
    "https://news.google.com/rss/search?q=politician+gaffe+OR+senator+says+bizarre+OR+congressman+claims&hl=en-US",
    "https://news.google.com/rss/search?q=alaska+man+OR+alaska+woman+bizarre&hl=en-US",
    "https://news.google.com/rss/search?q=australia+man+OR+british+man+bizarre+OR+russia+man+arrested&hl=en-US",
    "https://news.google.com/rss/search?q=americans+dont+know+OR+college+students+cant+name+OR+survey+finds+Americans&hl=en-US",
    # Campus Watch feeds
    "https://www.thecollegefix.com/feed/",
    "https://www.campusreform.org/rss.xml",
    "https://www.fire.org/news/feed/",
    "https://news.google.com/rss/search?q=college+students+protest+OR+university+bans+OR+campus+decolonize+OR+students+demand&hl=en-US",
    "https://news.google.com/rss/search?q=college+professor+fired+OR+campus+speech+OR+university+DEI+OR+woke+campus&hl=en-US",
    "https://news.google.com/rss/search?q=campus+protest+OR+student+government+OR+university+resolution+bizarre&hl=en-US",
    # Video hunting
    "https://www.reddit.com/r/PublicFreakout/.rss",
    "https://www.reddit.com/r/winstupidprizes/.rss",
    "https://news.google.com/rss/search?q=viral+video+OR+caught+on+camera+bizarre+OR+man+on+street+quiz&hl=en-US",
]

REJECT_KEYWORDS = [
    "killed", "murdered", "shooting", "stabbing", "terrorist", "massacre",
    "suicide", "overdose", "fatal", "homicide", "manslaughter",
    "sexual assault", "sexually assaulted", "rape", "raped",
    "molestation", "molested", "sex offender", "sex trafficking",
    "child abuse", "child porn", "child exploitation", "child sex",
    "child molest", "pedophil", "paedophil", "minor victim",
    "underage", "csam", "domestic violence", "revenge porn",
]

CAMPUS_KEYWORDS = [
    "university", "college", "campus", "students", "professor", "faculty",
    "student government", "dean", "commencement", "graduation",
    "ivy league", "harvard", "yale", "columbia", "stanford", "berkeley",
    "decolonize", "trigger warning", "safe space", "dei ", "equity office",
    "microaggression", "pronouns policy", "student protest", "campus ban",
]

TREADWELL_KEYWORDS = [
    "exotic pet", "pet tiger", "pet alligator", "pet monkey", "pet bear",
    "selfie with bear", "approached the bear", "tried to pet", "darwin award",
    "wildlife encounter", "ignored warnings", "despite warning signs",
    "tourist bitten", "fed the", "national park attack",
]

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


def call_claude(system, user, max_tokens=2000):
    """Call Claude and return text response."""
    resp = client.messages.create(
        model=MODEL,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user}],
    )
    return resp.content[0].text


def extract_json(text):
    """Extract the first JSON object or array from text."""
    # Try direct parse first
    try:
        return json.loads(text)
    except Exception:
        pass
    # Find JSON block
    match = re.search(r'\{[\s\S]*\}|\[[\s\S]*\]', text)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    raise ValueError(f"No valid JSON found in:\n{text[:300]}")


# ── Step 1: Gather ─────────────────────────────────────────────

def gather_candidates():
    candidates = []
    headers = {"User-Agent": "DailyMisanthrope/1.0 (dailymisanthrope.com)"}

    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url, request_headers=headers)
            for entry in feed.entries[:25]:
                title   = entry.get("title", "").strip()
                link    = entry.get("link", "")
                summary = entry.get("summary", "")[:400]
                source  = feed.feed.get("title", feed_url[:60])
                if not title or not link:
                    continue
                candidates.append({
                    "title": title, "url": link,
                    "summary": summary, "source": source,
                    "id": hashlib.md5(title.lower().encode()).hexdigest()[:12],
                })
        except Exception as e:
            print(f"  ⚠ {feed_url[:55]}: {e}")

    seen = set()
    unique = []
    for c in candidates:
        if c["id"] not in seen:
            seen.add(c["id"])
            unique.append(c)

    print(f"  {len(unique)} unique candidates from {len(RSS_FEEDS)} feeds")
    return unique


# ── Step 2: Pre-filter ─────────────────────────────────────────

def pre_filter(candidates):
    filtered = []
    for c in candidates:
        text = (c["title"] + " " + c.get("summary", "")).lower()
        if any(kw in text for kw in REJECT_KEYWORDS):
            continue
        # Tag campus and treadwell stories
        c["is_campus"]   = any(kw in text for kw in CAMPUS_KEYWORDS)
        c["is_treadwell"] = any(kw in text for kw in TREADWELL_KEYWORDS)
        filtered.append(c)

    print(f"  {len(filtered)} after reject filter")
    return filtered[:60]  # send top 60 to LLM


# ── Step 3: LLM Classification ─────────────────────────────────

def classify_stories(candidates):
    stories_text = "\n".join(
        f"[{i}] {c['title']}\n    {c.get('summary','')[:180]}"
        for i, c in enumerate(candidates)
    )

    system = """You are the editorial filter for "The Daily Misanthrope," a sardonic daily broadsheet cataloguing human folly.

Classify each story as one of:
- "FOLLY" — amusing stupidity, bureaucratic absurdity, self-inflicted problems, petty tyranny, spectacular bad judgment. Misanthropy-inducing in a wry way.
- "CAMPUS" — folly specifically from universities/colleges (student protests, absurd DEI policies, professors fired for wrongthink, students who can't answer basic questions). These go in the Campus Watch section.
- "TREADWELL" — humans approaching wild nature with catastrophic naivete (exotic pets, selfies with bears, ignoring wildlife warnings). Named for Timothy Treadwell.
- "VIDEO" — if the headline clearly describes a viral video of folly. Only use if it's obviously a watchable clip.
- "SKIP" — violent, tragic, boring, or not funny.

ABSOLUTE RULES:
- NO sexual assault, rape, or sexual violence
- NO crimes against children, zero tolerance
- NO death or serious physical injury as the punchline
- SKIP anything involving children as victims

Return ONLY a JSON array: [{"index": 0, "verdict": "FOLLY", "category": "Bureaucratic Farce"}, ...]
Categories should be dry and sardonic. Examples: "Bureaucratic Farce", "Stupid Criminals", "Remarks from the Throne", "Treadwell Effect", "No Intelligence Allowed", "Legal Absurdity", "Corporate Idiocy", "International Folly", "Florida Man Filed a Report"."""

    user = f"Classify these {len(candidates)} stories. Return JSON array only:\n\n{stories_text}"

    text = call_claude(system, user, max_tokens=4000)
    result = extract_json(text)

    # result may be {"classifications": [...]} or just [...]
    if isinstance(result, dict):
        result = result.get("classifications", [])

    verdicts = {item["index"]: item for item in result}

    folly, campus, treadwell, video = [], [], [], []
    for i, c in enumerate(candidates):
        v = verdicts.get(i, {})
        verdict = v.get("verdict", "SKIP")
        c["category"] = v.get("category", "General Folly")
        if verdict == "FOLLY":
            folly.append(c)
        elif verdict == "CAMPUS":
            campus.append(c)
        elif verdict == "TREADWELL":
            treadwell.append(c)
        elif verdict == "VIDEO":
            video.append(c)

    print(f"  FOLLY:{len(folly)} CAMPUS:{len(campus)} TREADWELL:{len(treadwell)} VIDEO:{len(video)}")
    return folly, campus, treadwell, video


# ── Step 4: Rank & Select ──────────────────────────────────────

def rank_and_select(folly_stories, campus_stories, treadwell_stories):
    """Pick FOTD + at least MIN_WIRE wire stories + campus + treadwell items."""

    # Select FOTD + wire from folly pool
    pool_text = "\n".join(
        f"[{i}] [{s['category']}] {s['title']}"
        for i, s in enumerate(folly_stories[:30])
    )

    system = f"""You are the editor of The Daily Misanthrope. Pick the {MAX_WIRE} most entertaining stories.
Rules:
- Maximum 2 Florida stories total
- Variety of categories (lawsuits, bureaucracy, wildlife, political, international, etc.)
- Pick 1 as Folly of the Day (most absurd/entertaining overall)
- If fewer than {MIN_WIRE} stories available, include all of them

Return ONLY JSON: {{"ranked": [0, 3, 7, ...], "folly_of_the_day": 3}}"""

    user = f"Rank these stories:\n\n{pool_text}"

    text = call_claude(system, user, max_tokens=500)
    result = extract_json(text)

    ranked = result.get("ranked", list(range(min(MAX_WIRE, len(folly_stories)))))[:MAX_WIRE]
    fotd_idx = result.get("folly_of_the_day", ranked[0] if ranked else 0)

    selected_wire = [folly_stories[i] for i in ranked if i < len(folly_stories)]

    # Guarantee minimum
    if len(selected_wire) < MIN_WIRE:
        extras = [s for s in folly_stories if s not in selected_wire]
        selected_wire += extras[:MIN_WIRE - len(selected_wire)]

    # Mark FOTD
    fotd = folly_stories[fotd_idx] if fotd_idx < len(folly_stories) else (selected_wire[0] if selected_wire else None)
    wire = [s for s in selected_wire if s is not fotd]

    # Pick campus items (up to 3)
    campus_selected = campus_stories[:3]

    # Pick treadwell items (up to 2)
    treadwell_selected = treadwell_stories[:2]

    print(f"  Selected: FOTD=1, wire={len(wire)}, campus={len(campus_selected)}, treadwell={len(treadwell_selected)}")
    return fotd, wire, campus_selected, treadwell_selected


# ── Step 5: Write Commentary ───────────────────────────────────

def write_commentary(fotd):
    system = """You are the editor of "The Daily Misanthrope." Write the Folly of the Day entry.

Voice: erudite but accessible — a classics professor at a bar. Dry wit, never cruel.
Occasionally references history, philosophy, or literature. Finds the universal in the specific.

Return ONLY valid JSON (no markdown, no code fences):
{
  "headline": "...",
  "summary": "2-3 paragraphs, 150-250 words, expanded telling of the story",
  "commentary": "1-2 sentence wry editorial observation",
  "epigraph": {"text": "quote here", "attribution": "Author Name"},
  "misanthrope_index": {"value": 7.4, "label": "Disappointing"}
}

For epigraph: a fresh, accurate quote about human folly from Mencken, Twain, Wilde, Voltaire, Swift, Schopenhauer, Bierce, Orwell, Waugh, or similar. Must be genuinely attributed — do not fabricate or put words in religious figures' mouths.

Misanthrope Index (1-10): 1-3=Merely Disappointing, 4-5=Disappointing, 6-7=Quite Disappointing, 8-9=Approaching Full Walken, 10=Full Walken."""

    user = f"Write the Folly of the Day:\n\nTitle: {fotd['title']}\nSource: {fotd['source']}\nSummary: {fotd.get('summary', '')}\nCategory: {fotd['category']}"

    text = call_claude(system, user, max_tokens=1500)
    return extract_json(text)


# ── Step 6: Find Video of the Day ─────────────────────────────

def find_video(video_candidates):
    """Pick best YouTube video from candidates, or search for one."""
    # Filter to YouTube links
    yt_pattern = re.compile(r'(?:youtube\.com/(?:watch\?v=|embed/|shorts/)|youtu\.be/)([\w-]{11})')

    for c in video_candidates:
        if yt_pattern.search(c.get("url", "")):
            return {
                "url": c["url"],
                "title": c["title"],
                "caption": c.get("summary", "")[:200],
                "category": "Exhibit A",
            }

    # Fallback: search Google News for viral folly videos
    search_url = "https://news.google.com/rss/search?q=viral+video+man+tries+OR+woman+attempts+OR+caught+on+camera+fails+site:youtube.com&hl=en-US"
    try:
        feed = feedparser.parse(search_url)
        for entry in feed.entries[:10]:
            url = entry.get("link", "")
            if yt_pattern.search(url):
                return {
                    "url": url,
                    "title": entry.get("title", "Video of the Day"),
                    "caption": entry.get("summary", "")[:200],
                    "category": "Exhibit A",
                }
    except Exception:
        pass

    return None


# ── Step 7: Assemble stories.json ─────────────────────────────

def assemble(fotd, wire, campus, treadwell, commentary, video):
    now = datetime.now(timezone.utc)
    ct  = now - timedelta(hours=5)  # CDT
    day_names = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"]

    # Drudge-style ALL CAPS on every 3rd wire story
    for i, s in enumerate(wire):
        if i % 3 == 0:
            s["title"] = s["title"].upper()

    output = {
        "lastUpdated": now.isoformat(),
        "edition": f"Vol. I, No. {ct.timetuple().tm_yday} — {day_names[ct.weekday()]}, {ct.strftime('%B %d, %Y')}",
        "epigraph": commentary.get("epigraph", {
            "text": "Every normal man must be tempted, at times, to spit on his hands, hoist the black flag, and begin slitting throats.",
            "attribution": "H.L. Mencken"
        }),
        "follyOfTheDay": {
            "headline":   commentary.get("headline", fotd["title"]),
            "summary":    commentary.get("summary", fotd.get("summary", "")),
            "source":     fotd["source"],
            "sourceUrl":  fotd["url"],
            "category":   fotd["category"],
            "commentary": commentary.get("commentary", "No comment necessary."),
        },
        "stories": [
            {"headline": s["title"], "url": s["url"], "source": s["source"], "category": s["category"]}
            for s in wire
        ],
        "misanthropeIndex": {
            "value": commentary.get("misanthrope_index", {}).get("value", 6.5),
            "label": commentary.get("misanthrope_index", {}).get("label", "Disappointing"),
            "scale": "Disappointing — Full Walken",
        },
        "treadwellCorner": [
            {"headline": s["title"], "url": s["url"], "source": s["source"], "category": s["category"]}
            for s in treadwell
        ] if treadwell else [],
        "campusWatch": [
            {"headline": s["title"], "url": s["url"], "source": s["source"], "category": s["category"]}
            for s in campus
        ] if campus else [],
        "videoOfTheDay": video,
    }

    STORIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    STORIES_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False))
    print(f"  ✓ stories.json written — wire:{len(wire)}, campus:{len(campus)}, treadwell:{len(treadwell)}")
    return output


# ── Step 8: Deploy to Netlify ──────────────────────────────────

def netlify_deploy():
    import hashlib as _h

    def sha1(path):
        h = _h.sha1()
        with open(path, 'rb') as f: h.update(f.read())
        return h.hexdigest()

    files = {}
    for root, dirs, fnames in os.walk(str(REPO_ROOT)):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d != '__pycache__']
        for fname in fnames:
            full = os.path.join(root, fname)
            rel  = '/' + os.path.relpath(full, str(REPO_ROOT))
            files[rel] = sha1(full)

    payload = json.dumps({"files": files}).encode()
    req = urllib.request.Request(
        f"https://api.netlify.com/api/v1/sites/{NETLIFY_SITE_ID}/deploys",
        data=payload,
        headers={"Authorization": f"Bearer {NETLIFY_TOKEN}", "Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req) as r:
        deploy = json.loads(r.read())

    deploy_id = deploy['id']
    required  = deploy.get('required', [])
    sha_to_path = {v: k for k, v in files.items()}

    ext_ct = {'html':'text/html','css':'text/css','js':'application/javascript',
               'json':'application/json','jpg':'image/jpeg','png':'image/png',
               'svg':'image/svg+xml','xml':'application/xml'}

    for sha in required:
        rel = sha_to_path.get(sha)
        if not rel: continue
        full = str(REPO_ROOT) + rel
        with open(full, 'rb') as f: data = f.read()
        ct = ext_ct.get(rel.rsplit('.',1)[-1], 'application/octet-stream')
        urllib.request.urlopen(urllib.request.Request(
            f"https://api.netlify.com/api/v1/deploys/{deploy_id}/files{rel}",
            data=data, headers={"Authorization": f"Bearer {NETLIFY_TOKEN}", "Content-Type": ct},
            method='PUT'
        ))

    print(f"  ✓ Netlify deployed ({len(required)} files uploaded, deploy {deploy_id[:8]})")


# ── Step 9: Push stories.json to GitHub ───────────────────────

def github_push(message="Daily edition"):
    import base64

    path = "data/stories.json"
    url  = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/contents/{path}"
    headers = {
        "Authorization": f"Bearer {GITHUB_PAT}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "DailyMisanthrope/1.0",
    }

    # Get current SHA
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as r:
            sha = json.loads(r.read())["sha"]
    except Exception:
        sha = None

    with open(str(STORIES_PATH), 'rb') as f:
        content = base64.b64encode(f.read()).decode()

    body = {"message": message, "content": content}
    if sha: body["sha"] = sha

    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method='PUT')
    with urllib.request.urlopen(req) as r:
        result = json.loads(r.read())
    print(f"  ✓ GitHub pushed: {result['commit']['sha'][:12]}")


# ── Step 10: Post to X ────────────────────────────────────────

def post_tweet(output):
    fotd     = output.get("follyOfTheDay", {})
    epigraph = output.get("epigraph", {})

    lines = []
    headline = fotd.get("headline", "")
    if headline:
        lines.append(headline[:200] + ("..." if len(headline) > 200 else ""))

    if epigraph.get("text") and epigraph.get("attribution"):
        q = f'"{epigraph["text"]}" — {epigraph["attribution"]}'
        if len(q) <= 140:
            lines.append(q)

    lines.append(SITE_URL)
    tweet = "\n\n".join(lines)

    if len(tweet) > 280:
        tweet = f"{headline[:200]}...\n\n{SITE_URL}"

    xc = tweepy.Client(
        consumer_key=X_API_KEY, consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN, access_token_secret=X_ACCESS_SECRET
    )
    resp = xc.create_tweet(text=tweet)
    print(f"  ✓ Tweeted (ID: {resp.data['id']})")
    return resp.data["id"]


# ── Main Pipeline ──────────────────────────────────────────────

def main():
    print("═" * 55)
    print("THE DAILY MISANTHROPE — Curation Pipeline")
    print(f"Run: {datetime.now().strftime('%Y-%m-%d %H:%M:%S CDT')}")
    print("═" * 55)

    print("\n📡 Step 1: Gathering RSS candidates...")
    candidates = gather_candidates()
    if not candidates:
        print("  No candidates. Humanity gets a pass today.")
        return

    print("\n🔍 Step 2: Pre-filtering...")
    filtered = pre_filter(candidates)

    print("\n🧠 Step 3: Claude classification...")
    folly, campus, treadwell, video_cands = classify_stories(filtered)
    if not folly:
        print("  No FOLLY stories found. Suspicious.")
        return

    print("\n📊 Step 4: Ranking & selection...")
    fotd, wire, campus_sel, treadwell_sel = rank_and_select(folly, campus, treadwell)

    print("\n✍️  Step 5: Writing Folly of the Day commentary...")
    commentary = write_commentary(fotd)

    print("\n🎬 Step 6: Finding Video of the Day...")
    video = find_video(video_cands)
    if video:
        print(f"  ✓ Found: {video['title'][:60]}")
    else:
        print("  No video found today.")

    print("\n📰 Step 7: Assembling stories.json...")
    output = assemble(fotd, wire, campus_sel, treadwell_sel, commentary, video)
    print(f"  Misanthrope Index: {output['misanthropeIndex']['value']} ({output['misanthropeIndex']['label']})")

    print("\n🚀 Step 8: Deploying to Netlify...")
    netlify_deploy()

    print("\n🐙 Step 9: Pushing to GitHub...")
    github_push(f"Daily edition — {output['edition']}")

    print("\n🐦 Step 10: Posting to X...")
    try:
        post_tweet(output)
    except Exception as e:
        print(f"  ⚠ Tweet failed: {e}")

    print("\n" + "═" * 55)
    print("Done. Humanity remains disappointing.")
    print("═" * 55)


if __name__ == "__main__":
    main()
