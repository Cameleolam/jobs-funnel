-- Migration 0003: pgvector extension + embedding columns + HNSW indexes
-- Templates {{TABLE}} via run_migration.py.
-- Idempotent: IF NOT EXISTS / ADD COLUMN IF NOT EXISTS guard repeated runs.

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE {{TABLE}}
    ADD COLUMN IF NOT EXISTS embedding              vector(1024),
    ADD COLUMN IF NOT EXISTS embedding_calibration  vector(1024),
    ADD COLUMN IF NOT EXISTS embedded_at            TIMESTAMPTZ,
    ADD COLUMN IF NOT EXISTS embed_model            TEXT,
    ADD COLUMN IF NOT EXISTS embed_attempts         INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS scored_uncalibrated    BOOLEAN NOT NULL DEFAULT FALSE;

CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_embedding
    ON {{TABLE}} USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_embedding_calibration
    ON {{TABLE}} USING hnsw (embedding_calibration vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_calibration_pool
    ON {{TABLE}} (user_status)
    WHERE embedding_calibration IS NOT NULL
      AND user_status IN ('interested','applied','in_process','offer','dismissed','rejected');

CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_rescore
    ON {{TABLE}} (status)
    WHERE scored_uncalibrated = TRUE AND embedding_calibration IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_{{TABLE}}_embed_failed
    ON {{TABLE}} (id) WHERE error_code = 'EMBED_FAILED';
