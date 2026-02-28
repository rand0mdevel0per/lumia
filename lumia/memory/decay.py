"""
Memory Decay System.

This module provides memory decay and forgetting mechanisms.

Key features:
- Exponential decay formula
- Eviction criteria evaluation
- Strengthen memory on access
- Configurable decay parameters
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from lumia.memory.graph import MemoryGraph


class DecayError(Exception):
    """Base exception for decay-related errors."""

    pass


@dataclass
class DecayConfig:
    """
    Configuration for memory decay.

    Attributes:
        half_life_days: Half-life for exponential decay (in days)
        min_strength: Minimum strength threshold for eviction
        eviction_batch_size: Number of memories to check per decay job
    """

    half_life_days: float = 30.0
    min_strength: float = 0.1
    eviction_batch_size: int = 100


class MemoryDecay:
    """
    Memory decay manager.

    Implements exponential decay and forgetting for memory system.
    """

    def __init__(self, graph: MemoryGraph, config: DecayConfig | None = None):
        """
        Initialize MemoryDecay.

        Args:
            graph: Memory graph instance
            config: Decay configuration
        """
        self.graph = graph
        self.config = config or DecayConfig()

    def calculate_decay(
        self, initial_strength: float, time_elapsed_days: float
    ) -> float:
        """
        Calculate decayed strength using exponential decay formula.

        Formula: S(t) = S₀ × (0.5)^(t / half_life_days)

        Args:
            initial_strength: Initial strength value
            time_elapsed_days: Time elapsed in days

        Returns:
            Decayed strength value
        """
        if time_elapsed_days < 0:
            raise DecayError("Time elapsed cannot be negative")

        if initial_strength < 0:
            raise DecayError("Initial strength cannot be negative")

        # Exponential decay formula
        decay_factor = 0.5 ** (time_elapsed_days / self.config.half_life_days)
        return initial_strength * decay_factor

    def get_current_strength(
        self, initial_strength: float, last_access: datetime
    ) -> float:
        """
        Get current strength based on last access time.

        Args:
            initial_strength: Initial strength value
            last_access: Last access timestamp

        Returns:
            Current strength value
        """
        now = datetime.now()
        time_elapsed = now - last_access
        time_elapsed_days = time_elapsed.total_seconds() / 86400.0

        return self.calculate_decay(initial_strength, time_elapsed_days)

    def should_evict(self, initial_strength: float, last_access: datetime) -> bool:
        """
        Check if a memory should be evicted based on current strength.

        Args:
            initial_strength: Initial strength value
            last_access: Last access timestamp

        Returns:
            True if memory should be evicted, False otherwise
        """
        current_strength = self.get_current_strength(initial_strength, last_access)
        return current_strength < self.config.min_strength

    def evict_weak_topics(self) -> int:
        """
        Evict weak topics based on decay criteria.

        Returns:
            Number of topics evicted

        Raises:
            DecayError: If eviction fails
        """
        if not self.graph._conn:
            raise DecayError("Graph not connected to database")

        try:
            with self.graph._conn.cursor() as cur:
                # Get candidate topics for eviction
                cur.execute(
                    """
                    SELECT id, strength, last_access
                    FROM memory_topics
                    ORDER BY last_access ASC
                    LIMIT %s
                    """,
                    (self.config.eviction_batch_size,),
                )
                candidates = cur.fetchall()

                # Check which topics should be evicted
                to_evict = []
                for topic_id, strength, last_access in candidates:
                    if self.should_evict(strength, last_access):
                        to_evict.append(topic_id)

                # Delete evicted topics
                if to_evict:
                    cur.execute(
                        "DELETE FROM memory_topics WHERE id = ANY(%s)", (to_evict,)
                    )
                    self.graph._conn.commit()

                return len(to_evict)

        except Exception as e:
            self.graph._conn.rollback()
            raise DecayError(f"Failed to evict weak topics: {e}") from e

    def evict_weak_instances(self) -> int:
        """
        Evict weak instances based on decay criteria.

        Returns:
            Number of instances evicted

        Raises:
            DecayError: If eviction fails
        """
        if not self.graph._conn:
            raise DecayError("Graph not connected to database")

        try:
            with self.graph._conn.cursor() as cur:
                # Get candidate instances for eviction
                cur.execute(
                    """
                    SELECT id, strength, last_access
                    FROM memory_instances
                    ORDER BY last_access ASC
                    LIMIT %s
                    """,
                    (self.config.eviction_batch_size,),
                )
                candidates = cur.fetchall()

                # Check which instances should be evicted
                to_evict = []
                for instance_id, strength, last_access in candidates:
                    if self.should_evict(strength, last_access):
                        to_evict.append(instance_id)

                # Delete evicted instances
                if to_evict:
                    cur.execute(
                        "DELETE FROM memory_instances WHERE id = ANY(%s)", (to_evict,)
                    )
                    self.graph._conn.commit()

                return len(to_evict)

        except Exception as e:
            self.graph._conn.rollback()
            raise DecayError(f"Failed to evict weak instances: {e}") from e

    def strengthen_topic(
        self, topic_id: int, boost_amount: float = 0.1, max_strength: float = 2.0
    ) -> None:
        """
        Strengthen a topic on access.

        Args:
            topic_id: Topic ID to strengthen
            boost_amount: Amount to boost strength by
            max_strength: Maximum strength cap

        Raises:
            DecayError: If strengthening fails
        """
        if not self.graph._conn:
            raise DecayError("Graph not connected to database")

        if boost_amount < 0:
            raise DecayError("Boost amount cannot be negative")

        try:
            with self.graph._conn.cursor() as cur:
                # Get current topic
                cur.execute(
                    """
                    SELECT strength, last_access
                    FROM memory_topics
                    WHERE id = %s
                    """,
                    (topic_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise DecayError(f"Topic {topic_id} not found")

                initial_strength, last_access = row

                # Calculate current decayed strength
                current_strength = self.get_current_strength(
                    initial_strength, last_access
                )

                # Apply boost and cap at max_strength
                new_strength = min(current_strength + boost_amount, max_strength)

                # Update topic with new strength and last_access
                cur.execute(
                    """
                    UPDATE memory_topics
                    SET strength = %s, last_access = NOW(), updated_at = NOW()
                    WHERE id = %s
                    """,
                    (new_strength, topic_id),
                )
                self.graph._conn.commit()

        except Exception as e:
            self.graph._conn.rollback()
            raise DecayError(f"Failed to strengthen topic: {e}") from e

    def strengthen_instance(
        self, instance_id: int, boost_amount: float = 0.1, max_strength: float = 2.0
    ) -> None:
        """
        Strengthen an instance on access.

        Args:
            instance_id: Instance ID to strengthen
            boost_amount: Amount to boost strength by
            max_strength: Maximum strength cap

        Raises:
            DecayError: If strengthening fails
        """
        if not self.graph._conn:
            raise DecayError("Graph not connected to database")

        if boost_amount < 0:
            raise DecayError("Boost amount cannot be negative")

        try:
            with self.graph._conn.cursor() as cur:
                # Get current instance
                cur.execute(
                    """
                    SELECT strength, last_access
                    FROM memory_instances
                    WHERE id = %s
                    """,
                    (instance_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise DecayError(f"Instance {instance_id} not found")

                initial_strength, last_access = row

                # Calculate current decayed strength
                current_strength = self.get_current_strength(
                    initial_strength, last_access
                )

                # Apply boost and cap at max_strength
                new_strength = min(current_strength + boost_amount, max_strength)

                # Update instance with new strength and last_access
                cur.execute(
                    """
                    UPDATE memory_instances
                    SET strength = %s, last_access = NOW(), updated_at = NOW()
                    WHERE id = %s
                    """,
                    (new_strength, instance_id),
                )
                self.graph._conn.commit()

        except Exception as e:
            self.graph._conn.rollback()
            raise DecayError(f"Failed to strengthen instance: {e}") from e

    def run_decay_job(self) -> dict[str, int]:
        """
        Run scheduled decay job to evict weak memories.

        This should be called periodically (e.g., daily via cron.1d event).

        Returns:
            Dictionary with eviction statistics

        Raises:
            DecayError: If decay job fails
        """
        try:
            topics_evicted = self.evict_weak_topics()
            instances_evicted = self.evict_weak_instances()

            return {
                "topics_evicted": topics_evicted,
                "instances_evicted": instances_evicted,
            }

        except Exception as e:
            raise DecayError(f"Failed to run decay job: {e}") from e
