"""
Image hashing and meme template detection for Meme Radar.

Uses perceptual hashing to detect when the same meme template
is being reused across posts, even with minor modifications.
"""

import io
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional

import requests
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..config import config
from ..models import Media, Post, Platform


@dataclass
class ImageTemplate:
    """A detected meme image template."""
    image_hash: str
    platforms: list[str] = field(default_factory=list)
    occurrences: int = 0
    distinct_posts: int = 0
    total_engagement: float = 0
    example_urls: list[str] = field(default_factory=list)
    first_seen: Optional[datetime] = None
    
    @property
    def cross_platform(self) -> bool:
        return len(self.platforms) > 1
    
    @property
    def template_score(self) -> float:
        """Score based on reuse pattern."""
        platform_bonus = 2.0 if self.cross_platform else 1.0
        return (self.occurrences * self.total_engagement * platform_bonus) ** 0.5


class ImageHasher:
    """
    Perceptual image hashing for meme template detection.
    
    Uses pHash (perceptual hash) which is robust to:
    - Resizing
    - Minor cropping
    - Color adjustments
    - Compression artifacts
    """
    
    def __init__(self):
        self._imagehash = None
        self._pil = None
    
    def _ensure_imports(self) -> bool:
        """Lazy import imagehash and PIL."""
        if self._imagehash is None:
            try:
                import imagehash
                from PIL import Image
                self._imagehash = imagehash
                self._pil = Image
                return True
            except ImportError:
                return False
        return True
    
    def hash_from_url(self, url: str, timeout: int = 10) -> Optional[str]:
        """
        Download an image from URL and compute its perceptual hash.
        
        Returns:
            String hash or None if failed
        """
        if not self._ensure_imports():
            return None
        
        try:
            response = requests.get(url, timeout=timeout, stream=True)
            response.raise_for_status()
            
            # Read image data
            image_data = io.BytesIO(response.content)
            image = self._pil.open(image_data)
            
            # Convert to RGB if necessary
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            # Compute perceptual hash
            phash = self._imagehash.phash(image)
            
            return str(phash)
            
        except Exception:
            return None
    
    def hash_from_file(self, filepath: str) -> Optional[str]:
        """
        Compute perceptual hash from a local file.
        """
        if not self._ensure_imports():
            return None
        
        try:
            image = self._pil.open(filepath)
            
            if image.mode != 'RGB':
                image = image.convert('RGB')
            
            phash = self._imagehash.phash(image)
            return str(phash)
            
        except Exception:
            return None
    
    def are_similar(self, hash1: str, hash2: str, threshold: int = 10) -> bool:
        """
        Check if two hashes are similar (same meme template).
        
        Args:
            hash1: First hash string
            hash2: Second hash string
            threshold: Hamming distance threshold (lower = stricter)
            
        Returns:
            True if hashes are similar
        """
        if not self._ensure_imports():
            return False
        
        try:
            h1 = self._imagehash.hex_to_hash(hash1)
            h2 = self._imagehash.hex_to_hash(hash2)
            
            distance = h1 - h2
            return distance <= threshold
            
        except Exception:
            return False


class TemplateDetector:
    """
    Detects trending meme templates by analyzing image hash frequency.
    """
    
    def __init__(self, session: Session):
        self.session = session
        self.config = config
        self.hasher = ImageHasher()
    
    def detect_templates(
        self,
        since_hours: float = 2.0,
        min_occurrences: int = 3,
    ) -> list[ImageTemplate]:
        """
        Detect trending image templates.
        
        Args:
            since_hours: How far back to look
            min_occurrences: Minimum times a template must appear
            
        Returns:
            List of trending ImageTemplate objects
        """
        since_time = datetime.utcnow() - timedelta(hours=since_hours)
        
        # Query for repeated image hashes
        results = (
            self.session.query(
                Media.image_hash,
                func.count(Media.id).label('occurrences'),
                func.count(func.distinct(Media.post_id)).label('distinct_posts'),
                func.min(Post.collected_at).label('first_seen'),
            )
            .join(Post, Media.post_id == Post.id)
            .filter(Post.collected_at >= since_time)
            .filter(Media.image_hash.isnot(None))
            .filter(Media.image_hash != '')
            .group_by(Media.image_hash)
            .having(func.count(Media.id) >= min_occurrences)
            .order_by(func.count(Media.id).desc())
            .limit(50)
            .all()
        )
        
        templates = []
        for row in results:
            template = self._build_template(row, since_time)
            if template:
                templates.append(template)
        
        # Sort by template score
        templates.sort(key=lambda x: x.template_score, reverse=True)
        
        return templates
    
    def _build_template(self, row, since_time: datetime) -> Optional[ImageTemplate]:
        """Build an ImageTemplate with additional details."""
        image_hash = row.image_hash
        
        # Get platform distribution and engagement
        details = (
            self.session.query(
                Post.platform_id,
                func.sum(Post.engagement_score).label('engagement'),
            )
            .join(Media, Media.post_id == Post.id)
            .filter(Media.image_hash == image_hash)
            .filter(Post.collected_at >= since_time)
            .group_by(Post.platform_id)
            .all()
        )
        
        platform_ids = [d[0] for d in details]
        total_engagement = sum(d[1] or 0 for d in details)
        
        # Get platform names
        platforms = (
            self.session.query(Platform.name)
            .filter(Platform.id.in_(platform_ids))
            .all()
        )
        platform_names = [p[0] for p in platforms]
        
        # Get example media URLs
        example_urls = (
            self.session.query(Media.media_url)
            .filter(Media.image_hash == image_hash)
            .limit(5)
            .all()
        )
        
        return ImageTemplate(
            image_hash=image_hash,
            platforms=platform_names,
            occurrences=row.occurrences,
            distinct_posts=row.distinct_posts,
            total_engagement=total_engagement,
            example_urls=[u[0] for u in example_urls],
            first_seen=row.first_seen,
        )
    
    def hash_pending_media(self, limit: int = 100) -> int:
        """
        Compute hashes for media items that don't have one yet.
        
        Returns:
            Number of items successfully hashed
        """
        pending = (
            self.session.query(Media)
            .filter(Media.image_hash.is_(None))
            .filter(Media.media_type == 'image')
            .limit(limit)
            .all()
        )
        
        hashed_count = 0
        for media in pending:
            if media.media_url:
                hash_value = self.hasher.hash_from_url(media.media_url)
                if hash_value:
                    media.image_hash = hash_value
                    hashed_count += 1
        
        self.session.commit()
        return hashed_count
