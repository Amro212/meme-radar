# Meme Radar - Architecture Documentation

## System Overview

```mermaid
flowchart TD
    subgraph Collectors
        TW[Twitter Collector]
        TK[TikTok Collector]
        IG[Instagram Collector]
        RD[Reddit Collector]
    end

    subgraph Orchestrator
        SCH[Scheduler]
        ORC[Orchestrator]
    end

    subgraph Storage
        DB[(SQLite/PostgreSQL)]
    end

    subgraph Analysis
        TA[Trend Analyzer]
        CM[Comment Meme Detector]
        IH[Image Hasher]
        CP[Cross-Platform Analyzer]
        NF[Noise Filter]
    end

    subgraph Interface
        CLI[CLI]
        API[API - Future]
    end

    SCH --> ORC
    ORC --> TW & TK & IG & RD
    TW & TK & IG & RD --> DB
    ORC --> TA
    TA --> CM & IH & CP
    CP --> NF
    NF --> DB
    CLI --> ORC
    CLI --> DB
```

## Data Flow

### 1. Collection Phase

```
Scheduler (every 30 min)
    ↓
Orchestrator.run_collection()
    ↓
┌─────────────────────────────────────────┐
│ For each enabled platform:              │
│   1. Collector.collect()                │
│   2. Returns CollectionResult with:     │
│      - PostEvent[]                      │
│      - CommentEvent[]                   │
│   3. Orchestrator._persist_result()     │
│      - Upsert posts                     │
│      - Link hashtags                    │
│      - Store media URLs                 │
│      - Store comments                   │
└─────────────────────────────────────────┘
```

### 2. Analysis Phase

```
Orchestrator.run_analysis()
    ↓
TrendAnalyzer.update_term_stats()
    ↓ Aggregate into TermStat records
TrendAnalyzer.detect_trends()
    ↓ Calculate frequency, acceleration, z-score
NoiseFilter.filter_trends()
    ↓ Remove stop phrases, evergreen hashtags
TrendAnalyzer.save_trend_candidates()
    ↓
CommentMemeDetector.detect()
    ↓ Find repeated phrases across posts
TemplateDetector.detect_templates()
    ↓ Find repeated image hashes
CrossPlatformAnalyzer.analyze()
    ↓ Boost multi-platform trends
    ↓
Results stored in TrendCandidate table
```

## Data Model

```mermaid
erDiagram
    PLATFORM ||--o{ POST : has
    POST ||--o{ MEDIA : contains
    POST ||--o{ COMMENT : has
    POST }o--o{ HASHTAG : tagged
    PLATFORM ||--o{ TERM_STAT : tracks
    PLATFORM ||--o{ TREND_CANDIDATE : detects

    PLATFORM {
        int id PK
        string name
    }

    POST {
        int id PK
        int platform_id FK
        string platform_post_id
        string author
        datetime created_at
        text text
        string permalink
        int likes
        int shares
        int comments_count
        float engagement_score
    }

    MEDIA {
        int id PK
        int post_id FK
        string media_url
        string media_type
        string image_hash
    }

    COMMENT {
        int id PK
        int post_id FK
        string author
        text text
        text normalized_text
        int score
    }

    HASHTAG {
        int id PK
        string tag
    }

    TERM_STAT {
        int id PK
        string term
        string term_type
        int platform_id FK
        datetime time_bucket
        int count_posts
        int count_comments
        float sum_engagement
    }

    TREND_CANDIDATE {
        int id PK
        string term
        string term_type
        int platform_id FK
        datetime detected_at
        int current_frequency
        float baseline_frequency
        float acceleration_score
        float z_score
        float trend_score
    }
```

## Trend Detection Algorithm

### Frequency Analysis

For each term (hashtag, phrase, or image hash):

1. **Bucket** data into 30-minute windows
2. **Count** occurrences in current window
3. **Calculate baseline** from previous N windows (mean + std)

### Acceleration Score

```
acceleration = (current_frequency + 1) / (baseline_frequency + 1)
```

- > 3.0 = Strong acceleration (potential trend)
- > 10.0 = Viral spike

### Z-Score

```
z_score = (current - baseline_mean) / baseline_std
```

- > 2.0 = Statistically significant
- > 3.0 = Strong anomaly

### Trend Criteria

A term is flagged as trending if:
- `frequency >= min_frequency` (default: 10)
- `z_score >= threshold` (default: 2.0) OR `acceleration >= threshold` (default: 3.0)
- `engagement >= min_engagement` (default: 5)

## Platform Collectors

| Platform | Library | Data Collected |
|----------|---------|----------------|
| Twitter/X | snscrape | Tweets, hashtags, media, engagement |
| TikTok | TikTokApi | Trending videos, comments, engagement |
| Instagram | Instaloader | Posts by hashtag/account, comments |
| Reddit | PRAW | Rising/new posts, comments, scores |

### Standardized Output

All collectors return:

```python
@dataclass
class PostEvent:
    platform: str
    platform_post_id: str
    author: str
    created_at: datetime
    text: str
    hashtags: list[str]
    media_urls: list[tuple[str, str]]
    likes: int
    shares: int
    comments_count: int
    engagement_score: float
```

## Image Hashing

Uses **pHash (perceptual hash)** from the `imagehash` library:

1. Resize image to 32x32
2. Convert to grayscale
3. Apply DCT (Discrete Cosine Transform)
4. Extract top-left 8x8 of DCT
5. Compute median and generate binary hash

### Similarity Detection

- Identical hashes = Same image
- Hamming distance ≤ 10 = Same meme template

## Noise Filtering

### Stop Phrases
Generic reactions filtered out:
- "lol", "lmao", "omg"
- "link in bio", "subscribe"

### Evergreen Hashtags

Always-popular tags (filtered unless extreme spike):
- #love, #happy, #fashion

### Spam Detection

- Single-author content
- Promotional patterns (discount, sale, etc.)
- Very short phrases

## Future Extensions

### AI Integration Points

1. **Classification**: Add LLM classification to `TrendCandidate`
2. **Explanation**: Generate meme explanations
3. **Prediction**: Predict viral potential

### Additional Platforms

- YouTube (comments on trending videos)
- Discord (public server messages)
- 4chan archives

### Scaling

- Migrate SQLite → PostgreSQL
- Add Redis for caching
- Distribute collectors
