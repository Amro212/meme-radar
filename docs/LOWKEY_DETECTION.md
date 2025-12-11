# Lowkey Creator Detection

Detects "lowkey but juicy" TikTok creators: small/mid-size accounts with viral outlier videos and strong comment culture.

## Quick Start

```bash
# Run detection manually
python radar.py lowkey run

# Check status
python radar.py lowkey status

# View top creators
python radar.py lowkey top

# View trending phrases
python radar.py lowkey phrases
```

## How It Works

### Detection Pipeline

1. **Collect** - TikTok scraper fetches trending videos
2. **Analyze** - Score each video against thresholds
3. **Track** - Add qualifying creators to watchlist
4. **Monitor** - Check watchlisted creators for new content

### Metrics

| Metric | Formula | Default Threshold |
|--------|---------|-------------------|
| Virality Ratio | views / followers | ≥ 10x |
| Engagement Rate | (likes+comments+shares) / views | ≥ 8% |
| Comment Intensity | comments / views | ≥ 2% |
| Spike Factor | views / avg_views | ≥ 3x |

### Qualification Criteria

A video qualifies as "hot" if **ALL** conditions are met:
- Creator has 5k-300k followers
- Video has ≥ 200k views
- Virality ratio ≥ 10x
- Engagement rate ≥ 8%
- Comment intensity ≥ 2%
- Spike factor ≥ 3x (significantly beats their own average)

## Configuration

Edit `config/config.yaml`:

```yaml
lowkey_detection:
  enabled: true
  
  # Creator selection
  min_followers: 5000
  max_followers: 300000
  min_views: 200000
  
  # Metric thresholds
  min_virality_ratio: 10.0
  min_engagement_rate: 0.08
  min_comment_intensity: 0.02
  min_spike_factor: 3.0
  
  # Rolling stats
  history_video_count: 10
  
  # Watchlist
  watchlist_drop_days: 30
  
  # Processing limits
  max_creators_per_run: 100
  max_videos_per_run: 500
```

## Database Tables

| Table | Purpose |
|-------|---------|
| `creators` | TikTok creator profiles |
| `creator_stats` | Rolling stats per creator |
| `hot_videos` | Videos that triggered detection |
| `watchlist` | Tracked creators |
| `comment_phrases` | Repeated comment patterns |

## CLI Commands

### `radar lowkey status`
Shows database stats and watchlist summary.

### `radar lowkey run`
Manually triggers detection pipeline.

### `radar lowkey top [--limit N]`
Shows top N meme-seed creators.

### `radar lowkey phrases`
Shows trending comment phrases.

## Integration

Lowkey detection runs automatically after each collection cycle if `lowkey_detection.enabled: true` in config.

The scheduler calls it after cross-platform trend analysis.

## Meme-Seed Score

Composite score (0-1) combining:
- Virality ratio (25%)
- Engagement rate (20%)
- Comment intensity (20%)
- Spike factor (20%)
- Repeated phrases (15%)

Higher score = stronger meme potential.
