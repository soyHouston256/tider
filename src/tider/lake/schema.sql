CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS docs (
  id          TEXT PRIMARY KEY,           -- ruta o URI del original
  doc_type    TEXT NOT NULL,              -- runbook | architecture | incident | adr
  service     TEXT,
  title       TEXT,
  updated     DATE,                       -- para penalizar fuentes viejas
  meta        JSONB DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS chunks (
  id          BIGSERIAL PRIMARY KEY,
  doc_id      TEXT REFERENCES docs(id) ON DELETE CASCADE,
  ord         INT,
  text        TEXT NOT NULL,
  embedding   vector(256),
  tsv         tsvector GENERATED ALWAYS AS (to_tsvector('simple', text)) STORED
);
CREATE INDEX IF NOT EXISTS chunks_tsv ON chunks USING gin(tsv);
CREATE INDEX IF NOT EXISTS chunks_emb ON chunks USING hnsw (embedding vector_cosine_ops);

-- Grafo de dependencias extraído de los diagramas (Mermaid)
CREATE TABLE IF NOT EXISTS edges (
  src TEXT, dst TEXT, label TEXT, doc_id TEXT REFERENCES docs(id) ON DELETE CASCADE,
  PRIMARY KEY (src, dst, doc_id)
);
