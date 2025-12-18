from datetime import datetime
from typing import List, Dict, Optional
import statistics

class TrendScorer:
    """
    Scoring engine to detect trending videos based on velocity and acceleration.
    """
    
    def calculate_velocity(self, play_count: int, created_at: datetime, current_time: datetime) -> float:
        """
        Calculate initial velocity (views per hour).
        Avoid div/0 by ensuring at least 0.1 hour age.
        """
        age_hours = (current_time - created_at).total_seconds() / 3600.0
        if age_hours < 0.1:
            age_hours = 0.1
            
        return play_count / age_hours

    def calculate_acceleration(self, 
                             v1: float, t1: datetime,
                             v2: float, t2: datetime) -> float:
        """
        Calculate acceleration (change in velocity per hour).
        """
        time_diff_hours = (t2 - t1).total_seconds() / 3600.0
        if time_diff_hours < 0.01:
            return 0.0
            
        return (v2 - v1) / time_diff_hours

    def is_potential_trend(self, 
                         velocity: float, 
                         batch_velocities: List[float], 
                         percentile_threshold: float = 90.0) -> bool:
        """
        Determine if a video is a potential trend based on its velocity
        relative to the current batch of videos.
        """
        if not batch_velocities:
            return False
            
        threshold_velocity = statistics.quantiles(batch_velocities, n=100)[int(percentile_threshold)-1]
        
        # Also enforce a hard minimum just in case the whole batch is low quality
        # This prevents "trending" in a batch of 10-view videos
        HARD_MIN_VELOCITY = 1000.0 # 1000 views/hour minimum
        
        return velocity >= threshold_velocity and velocity > HARD_MIN_VELOCITY

    def is_accelerating_trend(self, acceleration: float, velocity: float) -> bool:
        """
        Determine if an existing video is legitimately trending up.
        """
        # Tunable constants
        MIN_ACCELERATION = 100.0 # increasing by 100 views/hour per hour
        MIN_VELOCITY = 5000.0    # sustaining 5000 views/hour
        
        return acceleration > MIN_ACCELERATION and velocity > MIN_VELOCITY
