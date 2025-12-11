"""
Command-line interface for Meme Radar.

Provides commands for:
- Initializing the database
- Running collection cycles
- Viewing detected trends
- Starting the scheduler
"""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from datetime import datetime, timedelta

console = Console()


@click.group()
@click.version_option(version='1.0.0', prog_name='Meme Radar')
def cli():
    """
    Meme Radar - Cross-Platform Meme Detection System
    
    Monitors Twitter, TikTok, Instagram, and Reddit for emerging memes.
    """
    pass


@cli.command()
def init_db():
    """Initialize the database and create tables."""
    from .database import init_db as db_init
    
    console.print("[bold blue]Initializing database...[/]")
    
    try:
        db_init()
        console.print("[bold green]✓ Database initialized successfully[/]")
    except Exception as e:
        console.print(f"[bold red]✗ Error: {e}[/]")
        raise click.Abort()


@cli.command()
@click.option(
    '--platform', '-p',
    type=click.Choice(['all', 'twitter', 'tiktok', 'instagram', 'reddit']),
    default='all',
    help='Platform to collect from'
)
def collect(platform: str):
    """Run a single collection cycle."""
    from .scheduler import MemeRadarOrchestrator
    
    platforms = None if platform == 'all' else [platform]
    
    console.print(f"[bold blue]Collecting from {platform}...[/]")
    
    orchestrator = MemeRadarOrchestrator()
    results = orchestrator.run_collection(platforms)
    
    # Display results
    table = Table(title="Collection Results")
    table.add_column("Platform", style="cyan")
    table.add_column("Posts", justify="right")
    table.add_column("Comments", justify="right")
    table.add_column("Errors", justify="right", style="red")
    
    for platform_name, result in results.items():
        table.add_row(
            platform_name,
            str(len(result.posts)),
            str(len(result.comments)),
            str(len(result.errors)),
        )
    
    console.print(table)
    
    # Show errors if any
    for platform_name, result in results.items():
        if result.errors:
            console.print(f"\n[yellow]Errors from {platform_name}:[/]")
            for error in result.errors:
                console.print(f"  • {error}")


@cli.command()
def analyze():
    """Run the analysis pipeline on collected data."""
    from .scheduler import MemeRadarOrchestrator
    
    console.print("[bold blue]Running analysis pipeline...[/]")
    
    orchestrator = MemeRadarOrchestrator()
    results = orchestrator.run_analysis()
    
    # Display trends
    if results['trends']:
        table = Table(title="Top Trending Terms")
        table.add_column("Term", style="cyan")
        table.add_column("Type")
        table.add_column("Frequency", justify="right")
        table.add_column("Acceleration", justify="right")
        table.add_column("Z-Score", justify="right")
        
        for trend in results['trends'][:10]:
            table.add_row(
                trend['term'][:40],
                trend['type'],
                str(trend['frequency']),
                f"{trend['acceleration']:.2f}x",
                f"{trend['z_score']:.2f}",
            )
        
        console.print(table)
    else:
        console.print("[yellow]No trends detected[/]")
    
    # Display comment memes
    if results['comment_memes']:
        console.print("\n[bold]Comment Memes:[/]")
        for meme in results['comment_memes'][:5]:
            console.print(
                f"  • \"{meme['text']}\" "
                f"({meme['occurrences']} occurrences on {meme['posts']} posts)"
            )


@cli.command()
@click.option(
    '--platform', '-p',
    type=click.Choice(['all', 'twitter', 'tiktok', 'instagram', 'reddit']),
    default='all',
    help='Filter by platform'
)
@click.option(
    '--since', '-s',
    type=float,
    default=2.0,
    help='Hours to look back (default: 2)'
)
@click.option(
    '--limit', '-n',
    type=int,
    default=20,
    help='Maximum trends to show (default: 20)'
)
def show(platform: str, since: float, limit: int):
    """Show current trending memes and patterns."""
    from .database import get_session, get_platform_id
    from .models import TrendCandidate, Platform
    
    console.print(f"[bold blue]Showing trends from the last {since} hours...[/]\n")
    
    since_time = datetime.utcnow() - timedelta(hours=since)
    
    with get_session() as session:
        query = (
            session.query(TrendCandidate)
            .filter(TrendCandidate.detected_at >= since_time)
        )
        
        if platform != 'all':
            platform_id = get_platform_id(session, platform)
            query = query.filter(TrendCandidate.platform_id == platform_id)
        
        candidates = (
            query
            .order_by(TrendCandidate.trend_score.desc())
            .limit(limit)
            .all()
        )
        
        if not candidates:
            console.print("[yellow]No trends found. Try running 'collect' and 'analyze' first.[/]")
            return
        
        # Get platform names
        platform_names = {p.id: p.name for p in session.query(Platform).all()}
        
        # Display trends table
        table = Table(title=f"Trending Memes ({len(candidates)} found)")
        table.add_column("#", justify="right", style="dim")
        table.add_column("Term", style="cyan", max_width=40)
        table.add_column("Type")
        table.add_column("Platform")
        table.add_column("Freq", justify="right")
        table.add_column("Accel", justify="right")
        table.add_column("Score", justify="right", style="green")
        
        for i, c in enumerate(candidates, 1):
            platform_name = platform_names.get(c.platform_id, '?')
            cross = "🌐" if c.cross_platform else ""
            
            table.add_row(
                str(i),
                f"{cross}{c.term[:40]}",
                c.term_type,
                platform_name,
                str(c.current_frequency),
                f"{c.acceleration_score:.1f}x",
                f"{c.trend_score:.1f}",
            )
        
        console.print(table)
        
        # Show details for top trend
        if candidates:
            top = candidates[0]
            console.print(f"\n[bold]Top Trend Details:[/]")
            console.print(f"  Term: [cyan]{top.term}[/]")
            console.print(f"  Detected: {top.detected_at.strftime('%Y-%m-%d %H:%M')} UTC")
            console.print(f"  Baseline frequency: {top.baseline_frequency:.1f}")
            console.print(f"  Z-score: {top.z_score:.2f}")
            if top.cross_platform:
                console.print(f"  Platforms: [green]{top.platforms_seen}[/]")
            if top.example_refs:
                console.print(f"  Examples:")
                for ref in top.example_refs[:3]:
                    console.print(f"    • {ref}")


@cli.command()
@click.option(
    '--interval', '-i',
    type=int,
    default=None,
    help='Collection interval in minutes (default: from config)'
)
def run(interval: int):
    """Start the scheduler for continuous monitoring."""
    from .scheduler import Scheduler, MemeRadarOrchestrator
    from .database import init_db as db_init
    
    # Ensure database is initialized
    db_init()
    
    if interval:
        # Override config
        from .config import config
        config._config['scheduler']['interval_minutes'] = interval
    
    console.print(Panel.fit(
        "[bold green]Meme Radar[/]\n"
        f"Starting continuous monitoring...\n"
        f"Interval: {interval or 'config default'} minutes\n"
        "Press Ctrl+C to stop",
        title="🎯 Meme Radar",
    ))
    
    scheduler = Scheduler()
    
    try:
        scheduler.start(blocking=True)
    except KeyboardInterrupt:
        console.print("\n[yellow]Stopping scheduler...[/]")
        scheduler.stop()
        console.print("[green]Scheduler stopped[/]")


@cli.command()
def status():
    """Show system status and statistics."""
    from .database import get_session
    from .models import Post, Comment, TrendCandidate, Platform
    
    with get_session() as session:
        # Count records
        post_count = session.query(Post).count()
        comment_count = session.query(Comment).count()
        trend_count = session.query(TrendCandidate).count()
        
        # Posts per platform
        platforms = session.query(Platform).all()
        platform_stats = {}
        for p in platforms:
            count = session.query(Post).filter_by(platform_id=p.id).count()
            platform_stats[p.name] = count
        
        # Recent activity
        recent_posts = (
            session.query(Post)
            .order_by(Post.collected_at.desc())
            .limit(1)
            .first()
        )
        
        recent_trend = (
            session.query(TrendCandidate)
            .order_by(TrendCandidate.detected_at.desc())
            .limit(1)
            .first()
        )
    
    console.print(Panel.fit("[bold]Meme Radar Status[/]", title="📊"))
    
    console.print(f"\n[bold]Database Statistics:[/]")
    console.print(f"  Total posts: {post_count:,}")
    console.print(f"  Total comments: {comment_count:,}")
    console.print(f"  Detected trends: {trend_count:,}")
    
    console.print(f"\n[bold]Posts by Platform:[/]")
    for platform, count in platform_stats.items():
        console.print(f"  {platform}: {count:,}")
    
    console.print(f"\n[bold]Recent Activity:[/]")
    if recent_posts:
        console.print(f"  Last post collected: {recent_posts.collected_at.strftime('%Y-%m-%d %H:%M')} UTC")
    else:
        console.print("  No posts collected yet")
    
    if recent_trend:
        console.print(f"  Last trend detected: {recent_trend.detected_at.strftime('%Y-%m-%d %H:%M')} UTC")
    else:
        console.print("  No trends detected yet")


# =============================================================================
# Lowkey Creator Detection Commands
# =============================================================================

@cli.group()
def lowkey():
    """Lowkey creator detection commands."""
    pass


@lowkey.command()
def status():
    """Show lowkey detection status and watchlist summary."""
    from .database import get_session
    from .models import Creator, HotVideo, Watchlist, CommentPhrase
    
    with get_session() as session:
        # Count records
        creator_count = session.query(Creator).count()
        hot_video_count = session.query(HotVideo).count()
        watchlist_active = session.query(Watchlist).filter_by(status="active").count()
        watchlist_dropped = session.query(Watchlist).filter_by(status="dropped").count()
        phrase_count = session.query(CommentPhrase).filter(CommentPhrase.video_count >= 2).count()
        
        # Recent activity
        recent_hot = (
            session.query(HotVideo)
            .order_by(HotVideo.detected_at.desc())
            .first()
        )
    
    console.print(Panel.fit("[bold]Lowkey Creator Detection Status[/]", title="🔥"))
    
    console.print(f"\n[bold]Database:[/]")
    console.print(f"  Creators tracked: {creator_count:,}")
    console.print(f"  Hot videos detected: {hot_video_count:,}")
    console.print(f"  Trending phrases: {phrase_count:,}")
    
    console.print(f"\n[bold]Watchlist:[/]")
    console.print(f"  Active creators: [green]{watchlist_active}[/]")
    console.print(f"  Dropped creators: [dim]{watchlist_dropped}[/]")
    
    if recent_hot:
        console.print(f"\n[bold]Last Hot Video:[/]")
        console.print(f"  Detected: {recent_hot.detected_at.strftime('%Y-%m-%d %H:%M')} UTC")
        console.print(f"  Score: {recent_hot.meme_seed_score:.2f}")
        console.print(f"  Views: {recent_hot.views:,}")


@lowkey.command()
@click.option('--limit', '-n', type=int, default=10, help='Number of creators to show')
def top(limit: int):
    """Show top meme-seed creators."""
    from .database import get_session
    from .analysis.lowkey_detector import LowkeyAnalyzer
    
    with get_session() as session:
        analyzer = LowkeyAnalyzer(session)
        creators = analyzer.get_top_creators(limit=limit)
    
    if not creators:
        console.print("[yellow]No creators on watchlist yet. Run 'radar lowkey run' first.[/]")
        return
    
    table = Table(title=f"Top {len(creators)} Meme-Seed Creators")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Username", style="cyan")
    table.add_column("Followers", justify="right")
    table.add_column("Max Virality", justify="right")
    table.add_column("Max Spike", justify="right")
    table.add_column("Score", justify="right", style="green")
    table.add_column("Videos", justify="right")
    
    for i, c in enumerate(creators, 1):
        table.add_row(
            str(i),
            f"@{c['username']}",
            f"{c['followers']:,}" if c['followers'] else "?",
            f"{c['max_virality_ratio']:.1f}x",
            f"{c['max_spike_factor']:.1f}x",
            f"{c['max_meme_seed_score']:.2f}",
            str(c['qualifying_videos']),
        )
    
    console.print(table)
    
    # Show details for top creator
    if creators:
        top_creator = creators[0]
        console.print(f"\n[bold]Top Creator: @{top_creator['username']}[/]")
        console.print(f"  First qualified: {top_creator['first_qualified'].strftime('%Y-%m-%d')}")
        console.print(f"  Last qualified: {top_creator['last_qualified'].strftime('%Y-%m-%d')}")
        
        if top_creator['hot_videos']:
            console.print(f"  Hot Videos:")
            for v in top_creator['hot_videos'][:3]:
                console.print(f"    • {v['views']:,} views, score {v['score']:.2f}")


@lowkey.command(name='run')
def run_analysis():
    """Manually run lowkey creator detection."""
    from .database import get_session
    from .analysis.lowkey_detector import LowkeyAnalyzer
    
    console.print("[bold blue]Running lowkey creator detection...[/]")
    
    with get_session() as session:
        analyzer = LowkeyAnalyzer(session)
        results = analyzer.run_full_analysis()
        session.commit()
    
    console.print(f"\n[bold green]✓ Detection complete![/]")
    console.print(f"  Videos analyzed: {results['videos_analyzed']}")
    console.print(f"  Hot videos found: {results['hot_videos_found']}")
    console.print(f"  Creators updated: {results['creators_updated']}")
    console.print(f"  Watchlist additions: {results['watchlist_additions']}")
    console.print(f"  Phrases detected: {results['phrases_detected']}")


@lowkey.command()
def phrases():
    """Show trending comment phrases."""
    from .database import get_session
    from .analysis.lowkey_detector import CommentCultureAnalyzer
    from .config import config
    
    with get_session() as session:
        analyzer = CommentCultureAnalyzer(session, config)
        phrases = analyzer.get_trending_phrases(limit=20)
    
    if not phrases:
        console.print("[yellow]No trending phrases found yet.[/]")
        return
    
    table = Table(title="Trending Comment Phrases")
    table.add_column("#", justify="right", style="dim")
    table.add_column("Phrase", style="cyan", max_width=50)
    table.add_column("Videos", justify="right")
    table.add_column("Occurrences", justify="right")
    table.add_column("Avg Likes", justify="right")
    
    for i, p in enumerate(phrases, 1):
        table.add_row(
            str(i),
            p['phrase'][:50],
            str(p['video_count']),
            str(p['total_occurrences']),
            f"{p['avg_likes']:.1f}",
        )
    
    console.print(table)


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == '__main__':
    main()
