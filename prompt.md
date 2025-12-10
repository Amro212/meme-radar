# Project Prompt: Cross-Platform Meme Radar (Internal Tool)

You are an expert backend and data engineer. Your job is to design and implement a **cross-platform “meme radar”** that detects emerging memes and meme-like trends as early as possible using **only free or open tools**.

The output of your work will be:
- A clear architecture and data model.
- Code to ingest data from multiple social platforms.
- A trend detection engine that flags likely memes.
- A simple interface (CLI or lightweight dashboard) to inspect “what’s trending”.

AI models (OpenRouter, Tavily etc.) are **out of scope for v1**. Design the system so they can be plugged in later, but do not implement that part now.

---

## 1. High-Level Goal

Build an internal tool that:
- Monitors **Twitter / X, TikTok, Instagram, and Reddit**.
- Focuses on:
  - **Hashtags / keywords**
  - **Images / meme templates**
  - **Comments / repeated phrases**
- Runs a **scan at least every 30–60 minutes**.
- Detects **rising engagement patterns** (frequency and acceleration) so we can spot:
  - New meme phrases.
  - New meme images/templates.
  - “Comment memes” that people start spamming across posts.

The goal is **earliest possible detection**, not perfect coverage.

---

## 2. Scope and Non-Goals

**In scope for v1**

- Data collection from:
  - Twitter / X (public tweets).
  - TikTok (trending videos and their metadata).
  - Instagram (posts by hashtag and/or selected accounts).
  - Reddit (meme subreddits, comments).
- Storage of normalized data (posts, comments, media, hashtags, metrics).
- Trend detection algorithm based on:
  - Frequency.
  - Acceleration / bursts.
  - Cross-platform duplication (same term or comment or image).
- Noise filtering rules to avoid obvious garbage.
- A minimal interface to:
  - List top candidates for “emerging memes” per platform and cross-platform.
  - Show supporting examples (posts/comments/images).

**Out of scope for v1**

- Any paid APIs or tools.
- Third-party SaaS scrapers like Apify.
- Heavy AI / LLM post-processing (classification, summarization, explanation).
- Full UX polish or public-facing product.

---

## 3. Tech Stack and General Constraints

Propose and implement using:

- **Language**: Python preferred.
- **Data fetching**: Official free APIs where possible, otherwise **open-source scraping libraries**.
- **Storage**: Start with **PostgreSQL** or **SQLite** plus a lightweight ORM. Design schema so we can scale up later.
- **Scheduler**: Cron-style or a simple Python scheduler (e.g. `APScheduler`) for 30–60 minute runs.
- **Environment**:
  - Must be runnable locally.
  - Easy to containerize later (Docker is a bonus, but not mandatory for v1).

Design everything so it is **modular**:
- One “collector” module per platform.
- A shared “analysis” module.
- A thin UI layer.

---

## 4. Platform-Specific Data Collection

For each platform, use **only free tools** (API or scraping libraries) and design a **collector** module.

### 4.1 Twitter / X

**Goal:** Approximate “what is trending” by scraping recent high-engagement tweets and extracting recurring hashtags, phrases, and media.

**Tools:**

- `snscrape`  
  - A free social media scraping library for multiple platforms, including Twitter, that works without API keys. It supports scraping tweets by search queries, hashtags, users, etc. :contentReference[oaicite:0]{index=0}  

**Strategy:**

- Use `snscrape` to:
  - Fetch tweets from the last 30–60 minutes using broad search queries.
  - Prioritize:
    - High like/retweet counts.
    - Tweets containing images or GIFs.
  - Extract:
    - Hashtags.
    - N-gram phrases from tweet text.
    - Media URLs (images/GIFs).
- Approximate “trends” by:
  - Aggregating hashtag frequencies in the last time window.
  - Aggregating phrase frequencies.
  - Tracking which media URLs or image hashes repeat.

Implementation details for this module:

- Accept parameters:
  - Time window (e.g. last 60 minutes).
  - Minimum engagement thresholds (likes/retweets).
- Return a standardized list of “events”:
  - `post_id`, `platform = "twitter"`, `author`, `timestamp`, `text`, `hashtags[]`, `engagement`, `media[]`.

### 4.2 TikTok

**Goal:** Capture trending or high-engagement TikTok videos, their captions, and especially **top comments**, then derive repeated comment phrases and hashtags.

**Tools:**

- `TikTokApi` (unofficial Python wrapper)  
  - An open-source Python wrapper for TikTok.com. It can fetch **trending videos** and other data like user info. :contentReference[oaicite:1]{index=1}  
- If needed, fall back to simple HTTP + reverse-engineered endpoints used by `TikTokApi`, but prefer the library for v1.

**Strategy:**

- Use `TikTokApi` to:
  - Fetch the **current trending feed** (e.g. 100 videos).
  - For each video, collect:
    - Video id, author, caption, hashtags, creation timestamp.
    - View count, like count, share count (engagement).
    - Top N comments (text + like counts).
- Extract:
  - Hashtags from captions.
  - N-gram phrases from captions.
  - Comment text for comment-meme detection.

Implementation details for this module:

- Provide a function that:
  - Fetches trending videos.
  - For each video, optionally fetches top comments.
  - Returns standardized “post” and “comment” events with metrics.

### 4.3 Instagram

**Goal:** Track meme-ish content via posts and comments on **selected hashtags and accounts**, and detect repeated comment phrases and image templates.

**Tools:**

- `Instaloader` (Python library)  
  - Free, open-source tool to download Instagram media and metadata. It can access **hashtags, profiles, feeds, and comments** for public content. :contentReference[oaicite:2]{index=2}  

**Strategy:**

- Use `Instaloader` as a Python module to:
  - Scrape posts for selected hashtags (e.g. `#memes`, `#dankmemes`, any other meme-oriented tags).
  - Optionally monitor a curated list of large meme accounts.
  - For each post:
    - Save caption, timestamp, like count, comment count, media URLs.
    - Extract hashtags from captions.
  - Fetch **top N comments** per post where possible (Instaloader supports comment metadata).
- We cannot get a global “trending” list, so v1 will:
  - Monitor a **fixed set of meme-heavy hashtags and accounts** that are likely to surface new memes quickly.
  - Later, we can expand the heuristic list.

Implementation details for this module:

- Create configuration for:
  - List of hashtags to monitor.
  - List of accounts to monitor.
- The collector should:
  - Fetch recent posts since the last run.
  - Extract captions, hashtags, comments, and image URLs.
  - Return standardized events.

### 4.4 Reddit

**Goal:** Track rising meme posts and copypasta-style comments from meme-centric subreddits.

**Tools:**

- **Reddit API + PRAW**  
  - PRAW (Python Reddit API Wrapper) is a free library providing simple access to Reddit’s API and supports reading posts and comments. :contentReference[oaicite:3]{index=3}  

**Hot spots to monitor:**

- Subreddits like:
  - `r/memes`
  - `r/dankmemes`
  - `r/wholesomememes`
  - `r/AdviceAnimals`
  - `r/MemeEconomy` (meta about upcoming memes)
  - `r/copypasta` (for viral text)

**Strategy:**

- For each target subreddit:
  - Poll **rising** and **new** feeds to catch early memes.
  - For each post:
    - Store title, subreddit, timestamp, score, upvote ratio, media URLs, and text.
  - For each post, fetch **top N comments** and store comment text and score.
- Extract:
  - Keywords and phrases from titles and comments.
  - Image URLs from posts.
- Use this data for:
  - Meme image detection (via image hashing).
  - Copypasta / comment-meme detection (duplicate comments across posts).

Implementation details for this module:

- Implement a `reddit_collector` using PRAW with proper API credentials.
- Configure:
  - List of subreddits.
  - Maximum posts per run.
  - Maximum comments per post.

---

## 5. Shared Data Model

Design a **normalized schema** that can handle all platforms.

At minimum, define tables (or models) like:

- `platforms`  
  - `id`, `name` ("twitter", "tiktok", "instagram", "reddit").

- `posts`  
  - `id` (internal).
  - `platform_id`.
  - `platform_post_id` (string).
  - `author`.
  - `created_at`.
  - `text` (full text or caption).
  - `permalink` or URL.
  - `engagement_score` (normalized metric, or separate fields for likes, shares, comments).
  - `media_present` (bool).
  - `raw_metadata` (JSON).

- `media`  
  - `id`, `post_id`, `media_url`, `media_type` (image, video, gif), `image_hash` (perceptual hash).

- `comments`  
  - `id`, `post_id`, `platform_comment_id`, `author`, `created_at`, `text`, `score` (likes/upvotes), `raw_metadata`.

- `hashtags`  
  - `id`, `tag` (string, lowercased).

- `post_hashtags`  
  - `post_id`, `hashtag_id`.

- `term_stats` (for trend detection, can also be materialized views)  
  - `term` (hashtag or phrase).
  - `platform_id`.
  - `time_bucket` (e.g. 30-minute window).
  - `count_posts`.
  - `count_comments`.
  - `sum_engagement`.

Structure does not need to be perfect, but make it easy to:
- Count occurrences of a term per time window.
- Track how many distinct posts/comments a term appears in.
- Track image reuse via `image_hash`.

---

## 6. Trend Detection Algorithm

Implement a **trend analyzer** module that runs after each collection cycle.

### 6.1 Units of analysis

Detect trends on:

- **Hashtags** (e.g. `#skibidi`, `#ohio`).
- **Text phrases** from posts and comments (e.g. “we do a little trolling”).
- **Image hashes** from media (same meme template reused).

### 6.2 Frequency and acceleration

For each unit (term or image hash):

1. Bucket data into time windows (e.g. 30 minutes).
2. For each window, compute:
   - `count_posts`
   - `count_comments`
   - `sum_engagement`
3. Maintain a short history per unit:
   - Last N windows (for example, last 6 windows for the past 3 hours).

Then compute:

- **Current frequency**: counts in the most recent window.
- **Baseline frequency**: mean and standard deviation across previous windows.
- **Acceleration score**: ratio `(current + 1) / (baseline + 1)`, plus z-score style anomaly detection.

Flag a unit as a **trend candidate** if:

- It appears in at least a minimum number of posts/comments in the last window (e.g. ≥ 10).
- Its frequency or engagement is significantly higher than baseline (e.g. z-score > 2 or 3, or acceleration ratio above a threshold).
- Optionally, engagement-weighted: many small appearances are less important than fewer, highly engaged ones.

### 6.3 Comment-meme detection

Special handling for **comments**:

- Normalize comment text:
  - Lowercase.
  - Strip punctuation.
  - Normalize whitespace.
  - Possibly remove trailing emojis or treat them separately.
- Maintain a mapping:
  - `normalized_comment_text -> set of (post_id, platform, window)` and frequency.
- A comment phrase is a strong candidate meme if:
  - It appears in comments on many **distinct posts** within a short time.
  - Each occurrence has non-trivial engagement (likes/upvotes on the comment).

Implement threshold logic, for example:

- At least 5 distinct posts on a platform in a single 30-minute window.
- Or at least 3 platforms seeing the same or very similar comment across posts within 1–2 hours.

### 6.4 Image meme detection

Implement **perceptual image hashing** for images:

- Use a library like `imagehash` or OpenCV to generate a hash that is robust to small changes (resize, slight crop).
- For each new image:
  - Compute hash.
  - Store in `media` table.
- To detect reuse of the same meme template:
  - Count frequency of identical or near-identical hashes per window.
  - A template is trending if it appears in many posts across time windows with rising count.

We do not need sophisticated CV here, just enough to detect identical or very similar images.

### 6.5 Cross-platform correlation

After per-platform detection, implement a simple correlation step:

- If the **same term** (hashtag or normalized phrase) is flagged as trending on more than one platform in adjacent windows, **boost its score**.
- For image hashes, if the same or similar hash appears on multiple platforms, **boost score**.
- Use this to prioritize a **global “meme radar” list** over platform-specific lists.

---

## 7. Noise Reduction

Implement aggressive noise filtering:

- Maintain stop-lists of:
  - Extremely generic phrases (e.g. “lol”, “omg”, “this is so funny”), which are always present.
  - Platform-specific boilerplate (“link in bio”, “subscribe”, etc).
- For hashtags:
  - Filter out generic or evergreen tags (`#love`, `#happy`, `#fashion`, etc.) unless their short-term spike is extreme.
- Require **engagement minimums**:
  - Ignore comments with zero engagement if they look like spam.
  - Deprioritize posts with very low engagement relative to the norm.
- Ignore units that are:
  - Only triggered by a single high-volume account (e.g. one influencer spamming a phrase).
  - Purely promotional or clearly non-meme topics, where possible (basic heuristics like presence of links, discount codes).

Make these rules configurable so they can be tuned over time.

---

## 8. Scheduling and Execution Model

Design a simple orchestrator:

1. **Every 30–60 minutes**:
   - Run collectors for Twitter, TikTok, Instagram, Reddit.
   - Insert new posts, media, hashtags, comments into the database.
2. After ingestion:
   - Run the analysis pipeline:
     - Update term and image statistics for the latest time bucket.
     - Compute trend scores.
     - Persist “trend candidates” with their metrics.
3. Expose results through:
   - A CLI command (e.g. `python radar.py show --platform all --since 2h`).
   - Optionally, a simple web dashboard (Flask or FastAPI) listing:
     - Top N trending terms by platform.
     - Global cross-platform meme candidates.
     - Example posts/comments/images for each candidate.

Keep the execution logic simple and clearly separated:
- `collect_*` modules only fetch and normalize data.
- `analyze` module only uses database state.
- `ui` module only reads from analysis outputs.

---

## 9. Configuration and Extensibility

Provide a clear configuration structure (YAML, JSON, or `.env`) for:

- Subreddits to monitor.
- TikTok limits (number of trending videos per run).
- Instagram hashtags and accounts.
- Time window for trend analysis.
- Thresholds for:
  - Minimum frequency.
  - Minimum acceleration.
  - Minimum engagement.

Make sure the architecture is easy to extend later with:

- AI-based classification and explanation.
- Additional platforms (YouTube, Discord, 4chan archives, etc.).
- Integration with Tavily or other research tools.

---

## 10. Deliverables

For this project, produce:

1. **Architecture documentation**  
   - `architecture.md` explaining:
     - Platform collectors.
     - Data model.
     - Trend detection logic and thresholds.
     - Execution flow.

2. **Working codebase**  
   - Python package or repo with:
     - `collect_twitter.py` (using snscrape).
     - `collect_tiktok.py` (using TikTokApi).
     - `collect_instagram.py` (using Instaloader).
     - `collect_reddit.py` (using PRAW).
     - `models.py` / migrations for the database schema.
     - `analyze_trends.py` for trend detection.
     - `cli.py` or similar for basic interaction.
   - Clear instructions in `README.md` on:
     - Setup and installing dependencies.
     - Configuring API keys where needed (Reddit).
     - Running scheduled jobs.
     - Reading outputs.

3. **Example outputs**  
   - At least one sample run that:
     - Ingests a small batch of real data.
     - Produces a list of **candidate meme trends** with:
       - Term / image hash.
       - Platform(s).
       - Frequencies and acceleration metrics.
       - Example references (post IDs or URLs).

Focus on robustness, clear structure, and making the trend detection logic explicit and tunable.
