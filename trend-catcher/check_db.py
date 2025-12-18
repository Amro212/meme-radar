from db import SessionLocal, TrackedVideo, VideoStats, engine
session = SessionLocal()
videos = session.query(TrackedVideo).count()
stats_count = session.query(VideoStats).count()
print(f"Tracked Videos: {videos}")
print(f"Video Stats: {stats_count}")

# Check if link column exists in schema
from sqlalchemy import inspect
inspector = inspect(engine)
columns = [c['name'] for c in inspector.get_columns('video_stats')]
print(f"VideoStats columns: {columns}")
if 'link' in columns:
    print("VERIFIED: 'link' column exists.")
else:
    print("FAILED: 'link' column missing.")

session.close()
