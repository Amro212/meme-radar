"""Debug script to analyze why no hot videos are being detected."""
from meme_radar.database import get_session
from meme_radar.models import Post, Creator, CreatorStats, HotVideo, Platform

with get_session() as session:
    print("=" * 60)
    print("DIAGNOSIS: WHY NO HOT VIDEOS?")
    print("=" * 60)
    
    # 1. Check if posts have views in raw_metadata
    print("\n1. CHECKING POST VIEW DATA")
    print("-" * 40)
    posts_with_views = 0
    posts_total = session.query(Post).count()
    
    sample_posts = session.query(Post).limit(10).all()
    for p in sample_posts:
        if p.raw_metadata:
            views = p.raw_metadata.get('views', 0)
            play_count = p.raw_metadata.get('playCount', 0)
            stats = p.raw_metadata.get('stats', {})
            stats_views = stats.get('playCount', 0) if isinstance(stats, dict) else 0
            
            print(f"Post {p.id} @{p.author}:")
            print(f"  raw_metadata keys: {list(p.raw_metadata.keys())}")
            print(f"  views={views}, playCount={play_count}, stats.playCount={stats_views}")
            print(f"  likes={p.likes}, comments={p.comments_count}, shares={p.shares}")
            
            if views > 0 or play_count > 0 or stats_views > 0:
                posts_with_views += 1
    
    print(f"\nTotal posts: {posts_total}")
    print(f"Sample with view data: {posts_with_views}/10")
    
    # 2. Check creator stats  
    print("\n2. TOP CREATOR STATS")
    print("-" * 40)
    stats = session.query(CreatorStats).order_by(CreatorStats.avg_views.desc()).limit(5).all()
    for s in stats:
        creator = session.query(Creator).get(s.creator_id)
        username = creator.username if creator else "?"
        followers = creator.follower_count if creator else 0
        print(f"@{username}: avg_views={s.avg_views:,.0f}, avg_likes={s.avg_likes:,.0f}, followers={followers}")
    
    # 3. Check what's in raw_metadata for TikTok
    print("\n3. TIKTOK RAW METADATA STRUCTURE")
    print("-" * 40)
    tiktok = session.query(Platform).filter_by(name="tiktok").first()
    if tiktok:
        tiktok_post = session.query(Post).filter_by(platform_id=tiktok.id).first()
        if tiktok_post and tiktok_post.raw_metadata:
            import json
            print(json.dumps(tiktok_post.raw_metadata, indent=2, default=str)[:2000])
    
    # 4. Test detection logic manually
    print("\n4. MANUAL DETECTION TEST")
    print("-" * 40)
    # Get a post with high likes
    top_post = session.query(Post).order_by(Post.likes.desc()).first()
    if top_post:
        print(f"Testing top post: @{top_post.author}")
        print(f"  likes={top_post.likes:,}, comments={top_post.comments_count}, shares={top_post.shares}")
        
        # Check raw_metadata for views
        if top_post.raw_metadata:
            views = top_post.raw_metadata.get('views', 0)
            play_count = top_post.raw_metadata.get('playCount', 0)
            stats = top_post.raw_metadata.get('stats', {})
            if isinstance(stats, dict):
                stats_play = stats.get('playCount', 0)
            else:
                stats_play = 0
            print(f"  Views options: views={views}, playCount={play_count}, stats.playCount={stats_play}")
            
            # Try all possible view fields
            actual_views = views or play_count or stats_play
            print(f"  ACTUAL VIEWS: {actual_views:,}")
            
            # Check creator
            creator = session.query(Creator).filter_by(username=top_post.author).first()
            if creator:
                print(f"  Creator: @{creator.username}, followers={creator.follower_count}")
                
                # Calculate metrics
                if actual_views > 0:
                    virality = actual_views / max(creator.follower_count, 1)
                    engagement = (top_post.likes + top_post.comments_count + top_post.shares) / max(actual_views, 1)
                    comment_intensity = top_post.comments_count / max(actual_views, 1)
                    
                    print(f"  Computed metrics:")
                    print(f"    virality_ratio = {virality:.2f}x")
                    print(f"    engagement_rate = {engagement:.2%}")
                    print(f"    comment_intensity = {comment_intensity:.4%}")
                    
                    # Config thresholds
                    print(f"  Thresholds (from config):")
                    print(f"    min_views = 250000")
                    print(f"    min_virality_ratio = 10.0")
                    print(f"    min_engagement_rate = 0.08 (8%)")
                    print(f"    min_comment_intensity = 0.02 (2%)")
                    
                    # Why it fails
                    print(f"  PASS/FAIL:")
                    print(f"    views >= 250000? {actual_views:,} >= 250000 = {actual_views >= 250000}")
                    print(f"    virality >= 10? {virality:.2f} >= 10 = {virality >= 10}")
                    print(f"    engagement >= 8%? {engagement:.2%} >= 8% = {engagement >= 0.08}")
                    print(f"    comment_intensity >= 2%? {comment_intensity:.4%} >= 2% = {comment_intensity >= 0.02}")
