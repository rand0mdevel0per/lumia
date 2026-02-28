"""
Memory Graph Operations.

This module provides CRUD operations for the memory graph.

Key features:
- Topic CRUD operations
- Instance CRUD operations
- Edge CRUD operations
- Batch operations for performance
- pgserver database integration
"""

import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg


class GraphError(Exception):
    """Base exception for graph-related errors."""

    pass


@dataclass
class Topic:
    """
    Represents a memory topic.

    Attributes:
        id: Topic ID (None for new topics)
        name: Topic name (unique)
        embedding: Embedding vector
        description: Topic description
        strength: Memory strength
        last_access: Last access timestamp
        created_at: Creation timestamp
        updated_at: Update timestamp
    """

    id: int | None
    name: str
    embedding: list[float]
    description: str | None = None
    strength: float = 1.0
    last_access: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Instance:
    """
    Represents a memory instance.

    Attributes:
        id: Instance ID (None for new instances)
        topic_id: Associated topic ID
        content: Instance content
        embedding: Embedding vector
        sender: Sender identifier
        metadata: Additional metadata
        strength: Memory strength
        last_access: Last access timestamp
        created_at: Creation timestamp
        updated_at: Update timestamp
    """

    id: int | None
    topic_id: int
    content: str
    embedding: list[float]
    sender: str | None = None
    metadata: dict[str, Any] | None = None
    strength: float = 1.0
    last_access: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass
class Edge:
    """
    Represents a topic edge.

    Attributes:
        id: Edge ID (None for new edges)
        from_topic_id: Source topic ID
        to_topic_id: Target topic ID
        weight: Edge weight
        created_at: Creation timestamp
        updated_at: Update timestamp
    """

    id: int | None
    from_topic_id: int
    to_topic_id: int
    weight: float = 1.0
    created_at: datetime | None = None
    updated_at: datetime | None = None


class MemoryGraph:
    """
    Memory graph manager with CRUD operations.

    Manages topics, instances, and edges in the memory graph.
    """

    def __init__(self, db_path: Path | None = None):
        """
        Initialize MemoryGraph.

        Args:
            db_path: Path to database directory (uses pgserver)
        """
        self.db_path = db_path or Path("data/pgdata")
        self._conn: psycopg.Connection | None = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        """
        Connect to database and initialize schema.

        Raises:
            GraphError: If connection fails
        """
        try:
            from lumia import pgserver

            # Start pgserver
            db = pgserver.get_server(str(self.db_path))
            uri = db.get_uri()

            # Connect to database
            self._conn = psycopg.connect(uri)

            # Load schema
            schema_path = Path(__file__).parent / "schema.sql"
            with open(schema_path) as f:
                schema_sql = f.read()

            with self._conn.cursor() as cur:
                cur.execute(schema_sql)
            self._conn.commit()

        except ImportError as e:
            raise GraphError(
                "pgserver not installed. Install with: pip install pgserver"
            ) from e
        except Exception as e:
            raise GraphError(f"Failed to connect to database: {e}") from e

    def close(self) -> None:
        """Close database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()

    # Topic CRUD Operations

    def create_topic(self, topic: Topic) -> int:
        """
        Create a new topic.

        Args:
            topic: Topic to create

        Returns:
            Created topic ID

        Raises:
            GraphError: If creation fails
        """
        if not self._conn:
            raise GraphError("Not connected to database")

        try:
            with self._lock, self._conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO memory_topics (name, embedding, description, strength)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (topic.name, topic.embedding, topic.description, topic.strength),
                )
                topic_id = cur.fetchone()[0]
                self._conn.commit()
                return topic_id

        except Exception as e:
            self._conn.rollback()
            raise GraphError(f"Failed to create topic: {e}") from e

    def get_topic(self, topic_id: int) -> Topic | None:
        """
        Get topic by ID.

        Args:
            topic_id: Topic ID

        Returns:
            Topic object or None if not found

        Raises:
            GraphError: If query fails
        """
        if not self._conn:
            raise GraphError("Not connected to database")

        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, name, embedding, description, strength,
                           last_access, created_at, updated_at
                    FROM memory_topics
                    WHERE id = %s
                    """,
                    (topic_id,),
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

        except Exception as e:
            raise GraphError(f"Failed to get topic: {e}") from e

    def update_topic(self, topic: Topic) -> None:
        """
        Update an existing topic.

        Args:
            topic: Topic to update (must have id)

        Raises:
            GraphError: If update fails
        """
        if not self._conn:
            raise GraphError("Not connected to database")

        if topic.id is None:
            raise GraphError("Topic must have an id to update")

        try:
            with self._lock, self._conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE memory_topics
                    SET name = %s, embedding = %s, description = %s,
                        strength = %s, updated_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        topic.name,
                        topic.embedding,
                        topic.description,
                        topic.strength,
                        topic.id,
                    ),
                )
                self._conn.commit()

        except Exception as e:
            self._conn.rollback()
            raise GraphError(f"Failed to update topic: {e}") from e

    def delete_topic(self, topic_id: int) -> None:
        """
        Delete a topic.

        Args:
            topic_id: Topic ID to delete

        Raises:
            GraphError: If deletion fails
        """
        if not self._conn:
            raise GraphError("Not connected to database")

        try:
            with self._lock, self._conn.cursor() as cur:
                cur.execute("DELETE FROM memory_topics WHERE id = %s", (topic_id,))
                self._conn.commit()

        except Exception as e:
            self._conn.rollback()
            raise GraphError(f"Failed to delete topic: {e}") from e

    # Instance CRUD Operations

    def create_instance(self, instance: Instance) -> int:
        """
        Create a new instance.

        Args:
            instance: Instance to create

        Returns:
            Created instance ID

        Raises:
            GraphError: If creation fails
        """
        if not self._conn:
            raise GraphError("Not connected to database")

        try:
            with self._lock, self._conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO memory_instances
                    (topic_id, content, embedding, sender, metadata, strength)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        instance.topic_id,
                        instance.content,
                        instance.embedding,
                        instance.sender,
                        instance.metadata,
                        instance.strength,
                    ),
                )
                instance_id = cur.fetchone()[0]
                self._conn.commit()
                return instance_id

        except Exception as e:
            self._conn.rollback()
            raise GraphError(f"Failed to create instance: {e}") from e

    def get_instance(self, instance_id: int) -> Instance | None:
        """
        Get instance by ID.

        Args:
            instance_id: Instance ID

        Returns:
            Instance object or None if not found

        Raises:
            GraphError: If query fails
        """
        if not self._conn:
            raise GraphError("Not connected to database")

        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, topic_id, content, embedding, sender, metadata,
                           strength, last_access, created_at, updated_at
                    FROM memory_instances
                    WHERE id = %s
                    """,
                    (instance_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None

                return Instance(
                    id=row[0],
                    topic_id=row[1],
                    content=row[2],
                    embedding=row[3],
                    sender=row[4],
                    metadata=row[5],
                    strength=row[6],
                    last_access=row[7],
                    created_at=row[8],
                    updated_at=row[9],
                )

        except Exception as e:
            raise GraphError(f"Failed to get instance: {e}") from e

    def delete_instance(self, instance_id: int) -> None:
        """
        Delete an instance.

        Args:
            instance_id: Instance ID to delete

        Raises:
            GraphError: If deletion fails
        """
        if not self._conn:
            raise GraphError("Not connected to database")

        try:
            with self._lock, self._conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM memory_instances WHERE id = %s", (instance_id,)
                )
                self._conn.commit()

        except Exception as e:
            self._conn.rollback()
            raise GraphError(f"Failed to delete instance: {e}") from e

    # Edge CRUD Operations

    def create_edge(self, edge: Edge) -> int:
        """
        Create a new edge between topics.

        Args:
            edge: Edge to create

        Returns:
            Created edge ID

        Raises:
            GraphError: If creation fails
        """
        if not self._conn:
            raise GraphError("Not connected to database")

        try:
            with self._lock, self._conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO topic_edges (from_topic_id, to_topic_id, weight)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (from_topic_id, to_topic_id)
                    DO UPDATE SET weight = EXCLUDED.weight, updated_at = NOW()
                    RETURNING id
                    """,
                    (edge.from_topic_id, edge.to_topic_id, edge.weight),
                )
                edge_id = cur.fetchone()[0]
                self._conn.commit()
                return edge_id

        except Exception as e:
            self._conn.rollback()
            raise GraphError(f"Failed to create edge: {e}") from e

    def get_edges_from_topic(self, topic_id: int) -> list[Edge]:
        """
        Get all edges from a topic.

        Args:
            topic_id: Source topic ID

        Returns:
            List of edges

        Raises:
            GraphError: If query fails
        """
        if not self._conn:
            raise GraphError("Not connected to database")

        try:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, from_topic_id, to_topic_id, weight, created_at, updated_at
                    FROM topic_edges
                    WHERE from_topic_id = %s
                    """,
                    (topic_id,),
                )
                rows = cur.fetchall()
                return [
                    Edge(
                        id=row[0],
                        from_topic_id=row[1],
                        to_topic_id=row[2],
                        weight=row[3],
                        created_at=row[4],
                        updated_at=row[5],
                    )
                    for row in rows
                ]

        except Exception as e:
            raise GraphError(f"Failed to get edges: {e}") from e

    def delete_edge(self, edge_id: int) -> None:
        """
        Delete an edge.

        Args:
            edge_id: Edge ID to delete

        Raises:
            GraphError: If deletion fails
        """
        if not self._conn:
            raise GraphError("Not connected to database")

        try:
            with self._lock, self._conn.cursor() as cur:
                cur.execute("DELETE FROM topic_edges WHERE id = %s", (edge_id,))
                self._conn.commit()

        except Exception as e:
            self._conn.rollback()
            raise GraphError(f"Failed to delete edge: {e}") from e

