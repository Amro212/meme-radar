# Meme Radar 🎯

A cross-platform meme detection system that monitors Twitter/X, TikTok, Instagram, and Reddit for emerging memes and viral trends.

## Features

- **Multi-Platform Monitoring**: Collects data from Twitter, TikTok, Instagram, and Reddit
- **Trend Detection**: Identifies emerging memes using frequency, acceleration, and z-score analysis
- **Comment Meme Detection**: Catches viral phrases being spammed across posts
- **Image Template Detection**: Uses perceptual hashing to find reused meme templates
- **Cross-Platform Correlation**: Boosts trends appearing on multiple platforms
- **Noise Filtering**: Filters generic phrases, evergreen hashtags, and spam
- **Scheduled Monitoring**: Run continuous monitoring with configurable intervals

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

For TikTok support, also install Playwright:
```bash
pip install playwright
playwright install
```

### 2. Configure Credentials

Edit `config/config.yaml` and add your API credentials:

```yaml
reddit:
  client_id: "your_client_id"
  client_secret: "your_client_secret"
  user_agent: "MemeRadar/1.0 by u/your_username"
```

Or use environment variables:
```bash
export REDDIT_CLIENT_ID="your_client_id"
export REDDIT_CLIENT_SECRET="your_client_secret"
```

### 3. Initialize Database

```bash
python radar.py init-db
```

### 4. Run Collection

```bash
# Collect from all platforms
python radar.py collect

# Collect from a specific platform
python radar.py collect --platform reddit
```

### 5. View Trends

```bash
# Show trends from the last 2 hours
python radar.py show

# Show trends from a specific platform
python radar.py show --platform twitter --since 4
```

### 6. Start Continuous Monitoring

```bash
# Start with default 30-minute interval
python radar.py run

# Start with custom interval
python radar.py run --interval 15
```

## CLI Commands

| Command | Description |
|---------|-------------|
| `init-db` | Initialize the database and create tables |
| `collect` | Run a single collection cycle |
| `analyze` | Run the analysis pipeline on collected data |
| `show` | Display current trending memes |
| `run` | Start the scheduler for continuous monitoring |
| `status` | Show system statistics |

## Configuration

All settings are in `config/config.yaml`:

### Platform Settings

```yaml
reddit:
  subreddits:
    - memes
    - dankmemes
    - MemeEconomy
  max_posts_per_subreddit: 50
  comments_per_post: 10

twitter:
  queries:
    - "meme"
    - "viral"
  min_likes: 50
```

### Analysis Thresholds

```yaml
analysis:
  time_window_minutes: 30
  min_frequency: 10
  z_score_threshold: 2.0
  acceleration_threshold: 3.0
```

### Noise Filtering

```yaml
noise:
  stop_phrases:
    - "lol"
    - "lmao"
    - "link in bio"
  evergreen_hashtags:
    - "love"
    - "happy"
```

## Project Structure

```
meme-radar/
├── radar.py                 # Main entry point
├── config/
│   └── config.yaml         # Configuration
├── meme_radar/
│   ├── cli.py              # CLI commands
│   ├── scheduler.py        # Orchestrator
│   ├── config.py           # Config loader
│   ├── database.py         # DB connection
│   ├── models.py           # SQLAlchemy models
│   ├── collectors/
│   │   ├── base.py         # Base collector class
│   │   ├── twitter.py      # Twitter/X collector
│   │   ├── tiktok.py       # TikTok collector
│   │   ├── instagram.py    # Instagram collector
│   │   └── reddit.py       # Reddit collector
│   └── analysis/
│       ├── trends.py       # Trend detection
│       ├── comments.py     # Comment meme detection
│       ├── images.py       # Image hashing
│       ├── cross_platform.py
│       └── noise.py        # Noise filtering
└── requirements.txt
```

## Platform Setup

### Reddit (Required: API credentials)

1. Go to https://www.reddit.com/prefs/apps
2. Create a new app (script type)
3. Copy client ID and secret to config

### Twitter/X (No credentials needed)

Uses snscrape which doesn't require API keys.

### TikTok (Playwright required)

```bash
pip install TikTokApi playwright
playwright install
```

### Instagram (No credentials needed)

Uses instaloader for public content. Rate limiting is built-in.

## Extending

### Adding a New Platform

1. Create a new collector in `meme_radar/collectors/`
2. Inherit from `BaseCollector`
3. Implement `collect()` and `is_available()`
4. Return standardized `PostEvent` and `CommentEvent` objects

### Adding AI Classification (Future)

The architecture is designed for AI integration:
- Add classification to the analysis pipeline
- Use `TrendCandidate.raw_metadata` to store AI outputs
- Integrate with OpenRouter, Tavily, etc.

## License

MIT

## Troubleshooting

### "Database locked" errors
SQLite doesn't handle concurrent writes well. For production, migrate to PostgreSQL.

### Platform collector unavailable
Check that the required library is installed and credentials are configured.

### No trends detected
1. Ensure data was collected: `python radar.py status`
2. Run analysis: `python radar.py analyze`
3. Check thresholds in config (lower min_frequency for testing)
