-- Lumia Memory System Database Schema
-- PostgreSQL + pgvector for semantic memory graph

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Memory Topics Table
-- Stores high-level concepts and their embeddings
CREATE TABLE IF NOT EXISTS memory_topics (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL UNIQUE,
    embedding vector(384) NOT NULL,  -- all-MiniLM-L6-v2 embeddings
    description TEXT,
    strength REAL NOT NULL DEFAULT 1.0,  -- Memory strength for decay
    last_access TIMESTAMP NOT NULL DEFAULT NOW(),  -- Last access time
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Memory Instances Table
-- Stores specific instances/examples of topics
CREATE TABLE IF NOT EXISTS memory_instances (
    id SERIAL PRIMARY KEY,
    topic_id INTEGER NOT NULL REFERENCES memory_topics(id) ON DELETE CASCADE,
    content TEXT NOT NULL,
    embedding vector(384) NOT NULL,
    sender TEXT,  -- Sender identifier for filtering
    metadata JSONB,  -- Additional metadata
    strength REAL NOT NULL DEFAULT 1.0,
    last_access TIMESTAMP NOT NULL DEFAULT NOW(),
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

-- Topic Edges Table
-- Stores relationships between topics for spreading activation
CREATE TABLE IF NOT EXISTS topic_edges (
    id SERIAL PRIMARY KEY,
    from_topic_id INTEGER NOT NULL REFERENCES memory_topics(id) ON DELETE CASCADE,
    to_topic_id INTEGER NOT NULL REFERENCES memory_topics(id) ON DELETE CASCADE,
    weight REAL NOT NULL DEFAULT 1.0,  -- Edge weight for spreading activation
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
    UNIQUE(from_topic_id, to_topic_id)
);

-- Indexes for performance optimization

-- HNSW indexes for vector similarity search
-- m=16: number of connections per layer (trade-off between recall and speed)
-- ef_construction=64: size of dynamic candidate list during construction
CREATE INDEX IF NOT EXISTS idx_topics_embedding_hnsw
    ON memory_topics USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_instances_embedding_hnsw
    ON memory_instances USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- B-tree indexes for filtering and sorting
CREATE INDEX IF NOT EXISTS idx_topics_name ON memory_topics(name);
CREATE INDEX IF NOT EXISTS idx_topics_strength ON memory_topics(strength);
CREATE INDEX IF NOT EXISTS idx_topics_last_access ON memory_topics(last_access);

CREATE INDEX IF NOT EXISTS idx_instances_topic_id ON memory_instances(topic_id);
CREATE INDEX IF NOT EXISTS idx_instances_sender ON memory_instances(sender);
CREATE INDEX IF NOT EXISTS idx_instances_strength ON memory_instances(strength);
CREATE INDEX IF NOT EXISTS idx_instances_last_access ON memory_instances(last_access);

CREATE INDEX IF NOT EXISTS idx_edges_from_topic ON topic_edges(from_topic_id);
CREATE INDEX IF NOT EXISTS idx_edges_to_topic ON topic_edges(to_topic_id);
CREATE INDEX IF NOT EXISTS idx_edges_weight ON topic_edges(weight);

-- GIN index for JSONB metadata search
CREATE INDEX IF NOT EXISTS idx_instances_metadata ON memory_instances USING GIN(metadata);
