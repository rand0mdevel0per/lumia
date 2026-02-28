"""
Memory Retrieval Engine.

This module provides retrieval functionality combining RAG and spreading activation.

Key features:
- Vector search with HNSW index
- Spreading activation algorithm
- Sender filtering
- Result ranking and deduplication
"""

from dataclasses import dataclass
from typing import Any

from lumia.memory.graph import MemoryGraph


class RetrievalError(Exception):
    """Base exception for retrieval-related errors."""

    pass


@dataclass
class RetrievalConfig:
    """
    Configuration for retrieval.

    Attributes:
        max_depth: Maximum depth for spreading activation
        min_edge_weight: Minimum edge weight to follow
        decay_factor: Decay factor for spreading activation
        top_k_seeds: Number of seed topics from vector search
        top_k_final: Number of final results to return
    """

    max_depth: int = 2
    min_edge_weight: float = 0.3
    decay_factor: float = 0.5
    top_k_seeds: int = 20
    top_k_final: int = 10


@dataclass
class RetrievalResult:
    """
    Retrieval result.

    Attributes:
        topic_id: Topic ID
        topic_name: Topic name
        score: Relevance score
        instances: Related instances
    """

    topic_id: int
    topic_name: str
    score: float
    instances: list[dict[str, Any]]


class MemoryRetrieval:
    """
    Memory retrieval engine.

    Combines vector search and spreading activation for semantic retrieval.
    """

    def __init__(self, graph: MemoryGraph, config: RetrievalConfig | None = None):
        """
        Initialize MemoryRetrieval.

        Args:
            graph: Memory graph instance
            config: Retrieval configuration
        """
        self.graph = graph
        self.config = config or RetrievalConfig()

    def vector_search_topics(
        self, query_embedding: list[float], top_k: int, sender_filter: str | None = None
    ) -> list[tuple[int, float]]:
        """
        Search topics using vector similarity.

        Args:
            query_embedding: Query embedding vector
            top_k: Number of results to return
            sender_filter: Optional sender filter

        Returns:
            List of (topic_id, similarity_score) tuples

        Raises:
            RetrievalError: If search fails
        """
        if not self.graph._conn:
            raise RetrievalError("Graph not connected to database")

        try:
            with self.graph._conn.cursor() as cur:
                # Vector similarity search using cosine distance
                cur.execute(
                    """
                    SELECT id, 1 - (embedding <=> %s::vector) as similarity
                    FROM memory_topics
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """,
                    (query_embedding, query_embedding, top_k),
                )
                results = cur.fetchall()
                return [(row[0], row[1]) for row in results]

        except Exception as e:
            raise RetrievalError(f"Failed to search topics: {e}") from e

    def vector_search_instances(
        self,
        query_embedding: list[float],
        top_k: int,
        sender_filter: str | None = None,
        topic_ids: list[int] | None = None,
    ) -> list[tuple[int, float]]:
        """
        Search instances using vector similarity.

        Args:
            query_embedding: Query embedding vector
            top_k: Number of results to return
            sender_filter: Optional sender filter
            topic_ids: Optional list of topic IDs to filter by

        Returns:
            List of (instance_id, similarity_score) tuples

        Raises:
            RetrievalError: If search fails
        """
        if not self.graph._conn:
            raise RetrievalError("Graph not connected to database")

        try:
            with self.graph._conn.cursor() as cur:
                # Build query with optional filters
                query = """
                    SELECT id, 1 - (embedding <=> %s::vector) as similarity
                    FROM memory_instances
                    WHERE 1=1
                """
                params: list[Any] = [query_embedding]

                if sender_filter:
                    query += " AND sender = %s"
                    params.append(sender_filter)

                if topic_ids:
                    query += " AND topic_id = ANY(%s)"
                    params.append(topic_ids)

                query += " ORDER BY embedding <=> %s::vector LIMIT %s"
                params.extend([query_embedding, top_k])

                cur.execute(query, params)
                results = cur.fetchall()
                return [(row[0], row[1]) for row in results]

        except Exception as e:
            raise RetrievalError(f"Failed to search instances: {e}") from e

    def spreading_activation(
        self, seed_topics: list[tuple[int, float]]
    ) -> dict[int, float]:
        """
        Perform spreading activation from seed topics.

        Args:
            seed_topics: List of (topic_id, initial_activation) tuples

        Returns:
            Dictionary mapping topic_id to activation score

        Raises:
            RetrievalError: If spreading activation fails
        """
        if not self.graph._conn:
            raise RetrievalError("Graph not connected to database")

        # Initialize activation scores
        activation: dict[int, float] = {}
        for topic_id, score in seed_topics:
            activation[topic_id] = score

        # Spreading activation with BFS
        visited = set()
        current_layer = [(tid, score, 0) for tid, score in seed_topics]

        while current_layer:
            next_layer = []

            for topic_id, current_activation, depth in current_layer:
                if topic_id in visited:
                    continue

                visited.add(topic_id)

                # Stop if max depth reached
                if depth >= self.config.max_depth:
                    continue

                # Get outgoing edges
                edges = self.graph.get_edges_from_topic(topic_id)

                for edge in edges:
                    # Skip weak edges
                    if edge.weight < self.config.min_edge_weight:
                        continue

                    # Calculate activation for neighbor
                    neighbor_id = edge.to_topic_id
                    propagated_activation = (
                        current_activation * edge.weight * self.config.decay_factor
                    )

                    # Update activation (accumulate)
                    if neighbor_id in activation:
                        activation[neighbor_id] = max(
                            activation[neighbor_id], propagated_activation
                        )
                    else:
                        activation[neighbor_id] = propagated_activation

                    # Add to next layer
                    next_layer.append((neighbor_id, propagated_activation, depth + 1))

            current_layer = next_layer

        return activation

    def query(
        self,
        query_text: str,
        query_embedding: list[float],
        sender_filter: str | None = None,
    ) -> list[RetrievalResult]:
        """
        Query memory using RAG + spreading activation.

        Args:
            query_text: Query text
            query_embedding: Query embedding vector
            sender_filter: Optional sender filter

        Returns:
            List of retrieval results

        Raises:
            RetrievalError: If query fails
        """
        try:
            # Step 1: Vector search for seed topics
            seed_topics = self.vector_search_topics(
                query_embedding, self.config.top_k_seeds, sender_filter
            )

            if not seed_topics:
                return []

            # Step 2: Spreading activation
            activation_scores = self.spreading_activation(seed_topics)

            # Step 3: Rank topics by activation score
            ranked_topics = sorted(
                activation_scores.items(), key=lambda x: x[1], reverse=True
            )[: self.config.top_k_final]

            # Step 4: Retrieve instances for top topics
            results = []
            for topic_id, score in ranked_topics:
                topic = self.graph.get_topic(topic_id)
                if not topic:
                    continue

                # Get instances for this topic
                instances = self.vector_search_instances(
                    query_embedding,
                    top_k=5,
                    sender_filter=sender_filter,
                    topic_ids=[topic_id],
                )

                # Fetch instance details
                instance_details = []
                for inst_id, inst_score in instances:
                    instance = self.graph.get_instance(inst_id)
                    if instance:
                        instance_details.append(
                            {
                                "id": instance.id,
                                "content": instance.content,
                                "sender": instance.sender,
                                "score": inst_score,
                            }
                        )

                results.append(
                    RetrievalResult(
                        topic_id=topic_id,
                        topic_name=topic.name,
                        score=score,
                        instances=instance_details,
                    )
                )

            return results

        except Exception as e:
            raise RetrievalError(f"Failed to query memory: {e}") from e

