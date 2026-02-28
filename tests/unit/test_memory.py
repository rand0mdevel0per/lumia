"""
Tests for Memory System.

Tests cover:
- Graph operations (Topic, Instance, Edge CRUD)
- Embedding service
- Retrieval engine (vector search + spreading activation)
- Decay system
- Memory API
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from lumia.memory import (
    DecayConfig,
    MemorySystem,
    RetrievalConfig,
)
from lumia.memory.decay import MemoryDecay
from lumia.memory.embedding import (
    cosine_similarity,
    embed_batch,
    embed_text,
    get_embedding_dim,
)
from lumia.memory.graph import Edge, Instance, MemoryGraph, Topic
from lumia.memory.retrieval import MemoryRetrieval


@pytest.fixture
def temp_db():
    """Create temporary database directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def graph(temp_db):
    """Create and connect MemoryGraph."""
    g = MemoryGraph(temp_db)
    g.connect()
    yield g
    g.close()


@pytest.fixture
def sample_embedding():
    """Generate sample embedding."""
    return embed_text("test content")


# Graph Operations Tests


def test_create_topic(graph, sample_embedding):
    """Test topic creation."""
    topic = Topic(
        id=None,
        name="test_topic",
        embedding=sample_embedding,
        description="Test topic",
        strength=1.0,
    )
    topic_id = graph.create_topic(topic)
    assert topic_id > 0


def test_get_topic(graph, sample_embedding):
    """Test topic retrieval."""
    topic = Topic(
        id=None,
        name="test_topic",
        embedding=sample_embedding,
        description="Test topic",
    )
    topic_id = graph.create_topic(topic)

    retrieved = graph.get_topic(topic_id)
    assert retrieved is not None
    assert retrieved.id == topic_id
    assert retrieved.name == "test_topic"
    assert retrieved.description == "Test topic"


def test_update_topic(graph, sample_embedding):
    """Test topic update."""
    topic = Topic(
        id=None,
        name="test_topic",
        embedding=sample_embedding,
        description="Original description",
    )
    topic_id = graph.create_topic(topic)

    # Update topic
    topic.id = topic_id
    topic.description = "Updated description"
    graph.update_topic(topic)

    # Verify update
    retrieved = graph.get_topic(topic_id)
    assert retrieved.description == "Updated description"


def test_delete_topic(graph, sample_embedding):
    """Test topic deletion."""
    topic = Topic(
        id=None,
        name="test_topic",
        embedding=sample_embedding,
    )
    topic_id = graph.create_topic(topic)

    # Delete topic
    graph.delete_topic(topic_id)

    # Verify deletion
    retrieved = graph.get_topic(topic_id)
    assert retrieved is None


def test_create_instance(graph, sample_embedding):
    """Test instance creation."""
    # Create topic first
    topic = Topic(
        id=None,
        name="test_topic",
        embedding=sample_embedding,
    )
    topic_id = graph.create_topic(topic)

    # Create instance
    instance = Instance(
        id=None,
        topic_id=topic_id,
        content="Test instance content",
        embedding=sample_embedding,
        sender="test_sender",
        metadata={"key": "value"},
        strength=1.0,
    )
    instance_id = graph.create_instance(instance)
    assert instance_id > 0


def test_get_instance(graph, sample_embedding):
    """Test instance retrieval."""
    # Create topic
    topic = Topic(
        id=None,
        name="test_topic",
        embedding=sample_embedding,
    )
    topic_id = graph.create_topic(topic)

    # Create instance
    instance = Instance(
        id=None,
        topic_id=topic_id,
        content="Test content",
        embedding=sample_embedding,
        sender="test_sender",
    )
    instance_id = graph.create_instance(instance)

    # Retrieve instance
    retrieved = graph.get_instance(instance_id)
    assert retrieved is not None
    assert retrieved.id == instance_id
    assert retrieved.topic_id == topic_id
    assert retrieved.content == "Test content"
    assert retrieved.sender == "test_sender"


def test_delete_instance(graph, sample_embedding):
    """Test instance deletion."""
    # Create topic
    topic = Topic(
        id=None,
        name="test_topic",
        embedding=sample_embedding,
    )
    topic_id = graph.create_topic(topic)

    # Create instance
    instance = Instance(
        id=None,
        topic_id=topic_id,
        content="Test content",
        embedding=sample_embedding,
    )
    instance_id = graph.create_instance(instance)

    # Delete instance
    graph.delete_instance(instance_id)

    # Verify deletion
    retrieved = graph.get_instance(instance_id)
    assert retrieved is None


def test_create_edge(graph, sample_embedding):
    """Test edge creation."""
    # Create two topics
    topic1 = Topic(id=None, name="topic1", embedding=sample_embedding)
    topic2 = Topic(id=None, name="topic2", embedding=sample_embedding)
    topic1_id = graph.create_topic(topic1)
    topic2_id = graph.create_topic(topic2)

    # Create edge
    edge = Edge(id=None, from_topic_id=topic1_id, to_topic_id=topic2_id, weight=0.8)
    edge_id = graph.create_edge(edge)
    assert edge_id > 0


def test_get_edges_from_topic(graph, sample_embedding):
    """Test edge retrieval."""
    # Create topics
    topic1 = Topic(id=None, name="topic1", embedding=sample_embedding)
    topic2 = Topic(id=None, name="topic2", embedding=sample_embedding)
    topic3 = Topic(id=None, name="topic3", embedding=sample_embedding)
    topic1_id = graph.create_topic(topic1)
    topic2_id = graph.create_topic(topic2)
    topic3_id = graph.create_topic(topic3)

    # Create edges
    edge1 = Edge(id=None, from_topic_id=topic1_id, to_topic_id=topic2_id, weight=0.8)
    edge2 = Edge(id=None, from_topic_id=topic1_id, to_topic_id=topic3_id, weight=0.6)
    graph.create_edge(edge1)
    graph.create_edge(edge2)

    # Get edges
    edges = graph.get_edges_from_topic(topic1_id)
    assert len(edges) == 2
    assert all(e.from_topic_id == topic1_id for e in edges)


def test_delete_edge(graph, sample_embedding):
    """Test edge deletion."""
    # Create topics
    topic1 = Topic(id=None, name="topic1", embedding=sample_embedding)
    topic2 = Topic(id=None, name="topic2", embedding=sample_embedding)
    topic1_id = graph.create_topic(topic1)
    topic2_id = graph.create_topic(topic2)

    # Create edge
    edge = Edge(id=None, from_topic_id=topic1_id, to_topic_id=topic2_id)
    edge_id = graph.create_edge(edge)

    # Delete edge
    graph.delete_edge(edge_id)

    # Verify deletion
    edges = graph.get_edges_from_topic(topic1_id)
    assert len(edges) == 0


# Embedding Service Tests


def test_embed_text():
    """Test text embedding."""
    text = "This is a test sentence"
    embedding = embed_text(text)

    assert isinstance(embedding, list)
    assert len(embedding) == 384  # all-MiniLM-L6-v2 dimension
    assert all(isinstance(x, float) for x in embedding)


def test_embed_text_empty():
    """Test embedding empty text raises error."""
    from lumia.memory.embedding import EmbeddingError

    with pytest.raises(EmbeddingError):
        embed_text("")

    with pytest.raises(EmbeddingError):
        embed_text("   ")


def test_embed_batch():
    """Test batch embedding."""
    texts = ["First sentence", "Second sentence", "Third sentence"]
    embeddings = embed_batch(texts)

    assert len(embeddings) == 3
    assert all(len(emb) == 384 for emb in embeddings)


def test_embed_batch_empty():
    """Test batch embedding with empty list."""
    embeddings = embed_batch([])
    assert embeddings == []


def test_get_embedding_dim():
    """Test getting embedding dimension."""
    dim = get_embedding_dim()
    assert dim == 384


def test_cosine_similarity():
    """Test cosine similarity calculation."""
    emb1 = embed_text("Python programming")
    emb2 = embed_text("Python programming")
    emb3 = embed_text("Cooking recipes")

    # Same text should have high similarity
    sim_same = cosine_similarity(emb1, emb2)
    assert sim_same > 0.99

    # Different text should have lower similarity
    sim_diff = cosine_similarity(emb1, emb3)
    assert sim_diff < sim_same


# Retrieval Engine Tests


def test_vector_search_topics(graph):
    """Test vector search for topics."""
    # Create topics with different content
    topics_data = [
        ("Python", "Python is a programming language"),
        ("Java", "Java is a programming language"),
        ("Cooking", "Cooking is the art of preparing food"),
    ]

    for name, content in topics_data:
        embedding = embed_text(content)
        topic = Topic(id=None, name=name, embedding=embedding)
        graph.create_topic(topic)

    # Search for programming-related topics
    retrieval = MemoryRetrieval(graph)
    query_embedding = embed_text("programming languages")
    results = retrieval.vector_search_topics(query_embedding, top_k=2)

    assert len(results) == 2
    # Results should be sorted by similarity
    assert results[0][1] >= results[1][1]


def test_spreading_activation(graph):
    """Test spreading activation algorithm."""
    # Create a small graph: A -> B -> C
    #                        A -> D
    emb = embed_text("test")
    topic_a = Topic(id=None, name="A", embedding=emb)
    topic_b = Topic(id=None, name="B", embedding=emb)
    topic_c = Topic(id=None, name="C", embedding=emb)
    topic_d = Topic(id=None, name="D", embedding=emb)

    id_a = graph.create_topic(topic_a)
    id_b = graph.create_topic(topic_b)
    id_c = graph.create_topic(topic_c)
    id_d = graph.create_topic(topic_d)

    # Create edges
    graph.create_edge(Edge(None, id_a, id_b, 0.8))
    graph.create_edge(Edge(None, id_b, id_c, 0.6))
    graph.create_edge(Edge(None, id_a, id_d, 0.5))

    # Run spreading activation from A
    retrieval = MemoryRetrieval(graph)
    seed_topics = [(id_a, 1.0)]
    activation = retrieval.spreading_activation(seed_topics)

    # Check activation scores
    assert id_a in activation
    assert id_b in activation
    assert id_c in activation
    assert id_d in activation

    # A should have highest activation (seed)
    assert activation[id_a] == 1.0


# Decay System Tests


def test_calculate_decay():
    """Test decay calculation."""
    graph = MemoryGraph()
    decay = MemoryDecay(graph, DecayConfig(half_life_days=30.0))

    # Test no decay at t=0
    strength = decay.calculate_decay(1.0, 0.0)
    assert strength == 1.0

    # Test decay at half-life
    strength = decay.calculate_decay(1.0, 30.0)
    assert abs(strength - 0.5) < 0.01

    # Test decay at 2x half-life
    strength = decay.calculate_decay(1.0, 60.0)
    assert abs(strength - 0.25) < 0.01


def test_should_evict(graph, sample_embedding):
    """Test eviction criteria."""
    decay = MemoryDecay(graph, DecayConfig(half_life_days=30.0, min_strength=0.1))

    # Create topic with old last_access
    topic = Topic(
        id=None,
        name="old_topic",
        embedding=sample_embedding,
        strength=0.5,
    )
    topic_id = graph.create_topic(topic)

    # Get topic to check last_access
    retrieved = graph.get_topic(topic_id)

    # Simulate old access (100 days ago)
    old_access = datetime.now() - timedelta(days=100)

    # Should evict (strength decayed below threshold)
    assert decay.should_evict(0.5, old_access) is True

    # Should not evict (recent access)
    assert decay.should_evict(1.0, datetime.now()) is False


def test_strengthen_topic(graph, sample_embedding):
    """Test topic strengthening."""
    decay = MemoryDecay(graph, DecayConfig())

    # Create topic
    topic = Topic(id=None, name="test_topic", embedding=sample_embedding, strength=0.5)
    topic_id = graph.create_topic(topic)

    # Strengthen topic
    decay.strengthen_topic(topic_id, boost_amount=0.2)

    # Verify strength increased
    retrieved = graph.get_topic(topic_id)
    assert retrieved.strength > 0.5


# Memory API Tests


def test_memory_system_context_manager(temp_db):
    """Test MemorySystem context manager."""
    with MemorySystem(db_path=temp_db) as memory:
        assert memory.graph._conn is not None


def test_upsert_topic_create(temp_db):
    """Test creating new topic via Memory API."""
    with MemorySystem(db_path=temp_db) as memory:
        topic_id = memory.upsert_topic(
            name="Python",
            content="Python is a programming language",
            description="High-level language",
        )
        assert topic_id > 0

        # Verify topic was created
        topic = memory.graph.get_topic(topic_id)
        assert topic.name == "Python"
        assert topic.description == "High-level language"


def test_upsert_topic_update(temp_db):
    """Test updating existing topic via Memory API."""
    with MemorySystem(db_path=temp_db) as memory:
        # Create topic
        topic_id1 = memory.upsert_topic(
            name="Python", content="Python is a language", description="Original"
        )

        # Update same topic
        topic_id2 = memory.upsert_topic(
            name="Python", content="Python is a language", description="Updated"
        )

        # Should return same ID
        assert topic_id1 == topic_id2

        # Verify description was updated
        topic = memory.graph.get_topic(topic_id1)
        assert topic.description == "Updated"


def test_upsert_instance(temp_db):
    """Test creating instance via Memory API."""
    with MemorySystem(db_path=temp_db) as memory:
        # Create topic first
        topic_id = memory.upsert_topic(
            name="Python", content="Python is a language"
        )

        # Create instance
        instance_id = memory.upsert_instance(
            topic_name="Python",
            content="Python has dynamic typing",
            sender="user123",
            metadata={"source": "chat"},
        )
        assert instance_id > 0

        # Verify instance
        instance = memory.graph.get_instance(instance_id)
        assert instance.topic_id == topic_id
        assert instance.content == "Python has dynamic typing"
        assert instance.sender == "user123"


def test_query(temp_db):
    """Test querying memory via Memory API."""
    with MemorySystem(db_path=temp_db) as memory:
        # Create topics
        memory.upsert_topic("Python", "Python is a programming language")
        memory.upsert_topic("Java", "Java is a programming language")
        memory.upsert_topic("Cooking", "Cooking is preparing food")

        # Query
        results = memory.query("programming languages")
        assert len(results) > 0
        assert any("Python" in r.topic_name or "Java" in r.topic_name for r in results)


def test_strengthen(temp_db):
    """Test strengthening memory via Memory API."""
    with MemorySystem(db_path=temp_db) as memory:
        # Create topic
        topic_id = memory.upsert_topic("Python", "Python is a language")

        # Strengthen
        memory.strengthen(topic_id=topic_id, boost_amount=0.2)

        # Verify strength increased
        topic = memory.graph.get_topic(topic_id)
        assert topic.strength > 1.0


def test_create_edge(temp_db):
    """Test creating edge via Memory API."""
    with MemorySystem(db_path=temp_db) as memory:
        # Create topics
        memory.upsert_topic("Python", "Python is a language")
        memory.upsert_topic("Java", "Java is a language")

        # Create edge
        edge_id = memory.create_edge("Python", "Java", weight=0.8)
        assert edge_id > 0


def test_run_decay_job(temp_db):
    """Test running decay job via Memory API."""
    with MemorySystem(db_path=temp_db) as memory:
        # Create some topics
        memory.upsert_topic("Python", "Python is a language")
        memory.upsert_topic("Java", "Java is a language")

        # Run decay job
        stats = memory.run_decay_job()
        assert "topics_evicted" in stats
        assert "instances_evicted" in stats
        assert isinstance(stats["topics_evicted"], int)
        assert isinstance(stats["instances_evicted"], int)
