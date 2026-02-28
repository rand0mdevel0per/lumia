"""
Lumia Memory System - Topic-Instance-Edge graph with RAG and spreading activation.

This module provides:
- PostgreSQL + pgvector integration
- Topic-Instance-Edge graph operations
- RAG + spreading activation retrieval
- Decay/forgetting mechanism
- Embedding service

Example usage:
    from lumia.memory import MemorySystem

    # Initialize memory system
    memory = MemorySystem()
    memory.connect()

    # Upsert topic
    topic_id = memory.upsert_topic(
        name="Python",
        content="Python is a programming language",
        description="High-level programming language"
    )

    # Query memory
    results = memory.query("What is Python?")
    for result in results:
        print(f"Topic: {result.topic_name}, Score: {result.score}")
"""

from pathlib import Path
from typing import Any

from lumia.memory.decay import DecayConfig, MemoryDecay
from lumia.memory.embedding import embed_text
from lumia.memory.graph import Edge, Instance, MemoryGraph, Topic
from lumia.memory.retrieval import MemoryRetrieval, RetrievalConfig, RetrievalResult

__all__ = [
    "MemorySystem",
    "Topic",
    "Instance",
    "Edge",
    "RetrievalResult",
    "RetrievalConfig",
    "DecayConfig",
]


class MemoryError(Exception):
    """Base exception for memory system errors."""

    pass


class MemorySystem:
    """
    High-level memory system API.

    Provides unified interface for memory operations.
    """

    def __init__(
        self,
        db_path: Path | None = None,
        retrieval_config: RetrievalConfig | None = None,
        decay_config: DecayConfig | None = None,
    ):
        """
        Initialize MemorySystem.

        Args:
            db_path: Path to database directory
            retrieval_config: Retrieval configuration
            decay_config: Decay configuration
        """
        self.graph = MemoryGraph(db_path)
        self.retrieval = MemoryRetrieval(self.graph, retrieval_config)
        self.decay = MemoryDecay(self.graph, decay_config)

    def connect(self) -> None:
        """Connect to database and initialize schema."""
        self.graph.connect()

    def close(self) -> None:
        """Close database connection."""
        self.graph.close()

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    def _get_topic_by_name(self, name: str) -> Topic | None:
        """
        Get topic by name.

        Args:
            name: Topic name

        Returns:
            Topic object or None if not found
        """
        if not self.graph._conn:
            return None

        try:
            with self.graph._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, embedding, description, strength,
                           last_access, created_at, updated_at
                    FROM memory_topics
                    WHERE name = %s
                    """,
                    (name,),
                )
                row = cur.fetchone()
                if not row:
                    return None

                return Topic(
                    id=row[0],
                    name=row[1],
                    embedding=row[2],
                    description=row[3],
                    strength=row[4],
                    last_access=row[5],
                    created_at=row[6],
                    updated_at=row[7],
                )
        except Exception:
            return None

    def upsert_topic(
        self,
        name: str,
        content: str,
        description: str | None = None,
        strength: float = 1.0,
    ) -> int:
        """
        Create or update a topic.

        Args:
            name: Topic name (unique identifier)
            content: Content to embed
            description: Optional description
            strength: Initial strength

        Returns:
            Topic ID

        Raises:
            MemoryError: If operation fails
        """
        try:
            # Generate embedding
            embedding = embed_text(content)

            # Check if topic exists
            existing = self._get_topic_by_name(name)
            if existing:
                # Update existing topic
                existing.embedding = embedding
                existing.description = description
                existing.strength = strength
                self.graph.update_topic(existing)
                return existing.id

            # Create new topic
            topic = Topic(
                id=None,
                name=name,
                embedding=embedding,
                description=description,
                strength=strength,
            )
            return self.graph.create_topic(topic)

        except Exception as e:
            raise MemoryError(f"Failed to upsert topic: {e}") from e

    def upsert_instance(
        self,
        topic_name: str,
        content: str,
        sender: str | None = None,
        metadata: dict[str, Any] | None = None,
        strength: float = 1.0,
    ) -> int:
        """
        Create or update an instance.

        Args:
            topic_name: Name of the topic
            content: Instance content
            sender: Sender identifier
            metadata: Additional metadata
            strength: Initial strength

        Returns:
            Instance ID

        Raises:
            MemoryError: If operation fails
        """
        try:
            # Get or create topic
            topic = self._get_topic_by_name(topic_name)
            if not topic:
                raise MemoryError(f"Topic '{topic_name}' not found")

            # Generate embedding
            embedding = embed_text(content)

            # Create instance
            instance = Instance(
                id=None,
                topic_id=topic.id,
                content=content,
                embedding=embedding,
                sender=sender,
                metadata=metadata,
                strength=strength,
            )
            return self.graph.create_instance(instance)

        except Exception as e:
            raise MemoryError(f"Failed to upsert instance: {e}") from e

    def query(
        self,
        query_text: str,
        sender_filter: str | None = None,
    ) -> list[RetrievalResult]:
        """
        Query memory using RAG + spreading activation.

        Args:
            query_text: Query text
            sender_filter: Optional sender filter

        Returns:
            List of retrieval results

        Raises:
            MemoryError: If query fails
        """
        try:
            # Generate query embedding
            query_embedding = embed_text(query_text)

            # Query using retrieval engine
            return self.retrieval.query(query_text, query_embedding, sender_filter)

        except Exception as e:
            raise MemoryError(f"Failed to query memory: {e}") from e

    def strengthen(
        self,
        topic_id: int | None = None,
        instance_id: int | None = None,
        boost_amount: float = 0.1,
    ) -> None:
        """
        Strengthen a memory on access.

        Args:
            topic_id: Topic ID to strengthen (optional)
            instance_id: Instance ID to strengthen (optional)
            boost_amount: Amount to boost strength by

        Raises:
            MemoryError: If strengthening fails
        """
        if topic_id is None and instance_id is None:
            raise MemoryError("Must specify either topic_id or instance_id")

        try:
            if topic_id is not None:
                self.decay.strengthen_topic(topic_id, boost_amount)

            if instance_id is not None:
                self.decay.strengthen_instance(instance_id, boost_amount)

        except Exception as e:
            raise MemoryError(f"Failed to strengthen memory: {e}") from e

    def create_edge(
        self, from_topic_name: str, to_topic_name: str, weight: float = 1.0
    ) -> int:
        """
        Create an edge between two topics.

        Args:
            from_topic_name: Source topic name
            to_topic_name: Target topic name
            weight: Edge weight

        Returns:
            Edge ID

        Raises:
            MemoryError: If edge creation fails
        """
        try:
            # Get topics
            from_topic = self._get_topic_by_name(from_topic_name)
            to_topic = self._get_topic_by_name(to_topic_name)

            if not from_topic:
                raise MemoryError(f"Topic '{from_topic_name}' not found")
            if not to_topic:
                raise MemoryError(f"Topic '{to_topic_name}' not found")

            # Create edge
            edge = Edge(
                id=None,
                from_topic_id=from_topic.id,
                to_topic_id=to_topic.id,
                weight=weight,
            )
            return self.graph.create_edge(edge)

        except Exception as e:
            raise MemoryError(f"Failed to create edge: {e}") from e

    def run_decay_job(self) -> dict[str, int]:
        """
        Run scheduled decay job to evict weak memories.

        Returns:
            Dictionary with eviction statistics

        Raises:
            MemoryError: If decay job fails
        """
        try:
            return self.decay.run_decay_job()

        except Exception as e:
            raise MemoryError(f"Failed to run decay job: {e}") from e
