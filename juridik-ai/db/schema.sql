-- Swedish Government Documents Schema
-- For storing JO ämbetsberättelser and other government documents
-- with vector embeddings support for semantic search

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS pgvector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ============================================================================
-- AGENCIES TABLE
-- ============================================================================
-- Stores information about Swedish government agencies

CREATE TABLE IF NOT EXISTS agencies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name VARCHAR(255) NOT NULL UNIQUE,
    abbreviation VARCHAR(20) NOT NULL UNIQUE,
    website VARCHAR(500),
    description TEXT,
    organization_number VARCHAR(20),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_agencies_abbreviation ON agencies(abbreviation);
CREATE INDEX idx_agencies_name ON agencies(name);

-- ============================================================================
-- DOCUMENTS TABLE
-- ============================================================================
-- Main table for government documents (primarily JO ämbetsberättelser)

CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    agency_id UUID REFERENCES agencies(id) ON DELETE SET NULL,
    source_agency VARCHAR(255),
    year INTEGER NOT NULL,
    title VARCHAR(500) NOT NULL,
    url VARCHAR(500),
    pdf_path VARCHAR(500),
    document_type VARCHAR(100) DEFAULT 'ämbetsberättelse',
    language VARCHAR(10) DEFAULT 'sv',
    pages INTEGER,
    file_size_bytes INTEGER,
    extraction_method VARCHAR(100),
    extraction_status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_documents_agency_id ON documents(agency_id);
CREATE INDEX idx_documents_year ON documents(year);
CREATE INDEX idx_documents_source_agency ON documents(source_agency);
CREATE INDEX idx_documents_document_type ON documents(document_type);
CREATE INDEX idx_documents_extraction_status ON documents(extraction_status);
CREATE INDEX idx_documents_url ON documents(url);
CREATE INDEX idx_documents_created_at ON documents(created_at DESC);

-- ============================================================================
-- CHUNKS TABLE
-- ============================================================================
-- Stores text chunks from documents for semantic search with embeddings

CREATE TABLE IF NOT EXISTS chunks (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    section_header VARCHAR(500),
    content TEXT NOT NULL,
    token_count INTEGER,
    embedding vector(1536),
    embedding_model VARCHAR(50) DEFAULT 'openai-text-embedding-3-large',
    embedding_created_at TIMESTAMP,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_chunks_document_id ON chunks(document_id);
CREATE INDEX idx_chunks_document_chunk_idx ON chunks(document_id, chunk_index);
CREATE INDEX idx_chunks_token_count ON chunks(token_count);
CREATE INDEX idx_chunks_embedding_created_at ON chunks(embedding_created_at);
-- Vector similarity search index (IVFFlat for faster approximate nearest neighbor search)
CREATE INDEX idx_chunks_embedding_ivf ON chunks USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);
-- Alternative: HNSW index for better quality (requires pgvector >= 0.5.0)
-- CREATE INDEX idx_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops)
--     WITH (m = 16, ef_construction = 64);

-- ============================================================================
-- DECISIONS TABLE
-- ============================================================================
-- Stores individual JO decisions extracted from ämbetsberättelser

CREATE TABLE IF NOT EXISTS decisions (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    case_number VARCHAR(100) NOT NULL,
    complaint_date DATE,
    decision_date DATE NOT NULL,
    agency_complained_about VARCHAR(255) NOT NULL,
    agency_id UUID REFERENCES agencies(id) ON DELETE SET NULL,
    complainant_type VARCHAR(100),
    complaint_basis VARCHAR(500),
    outcome VARCHAR(100) NOT NULL,
    summary TEXT,
    criticism VARCHAR(1000),
    recommendations TEXT,
    case_status VARCHAR(50) DEFAULT 'closed',
    chapter_reference VARCHAR(100),
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_decisions_document_id ON decisions(document_id);
CREATE INDEX idx_decisions_case_number ON decisions(case_number);
CREATE INDEX idx_decisions_decision_date ON decisions(decision_date DESC);
CREATE INDEX idx_decisions_agency_complained_about ON decisions(agency_complained_about);
CREATE INDEX idx_decisions_agency_id ON decisions(agency_id);
CREATE INDEX idx_decisions_outcome ON decisions(outcome);
CREATE INDEX idx_decisions_case_status ON decisions(case_status);

-- ============================================================================
-- EMBEDDINGS_LOG TABLE
-- ============================================================================
-- Track embedding operations for monitoring and debugging

CREATE TABLE IF NOT EXISTS embeddings_log (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    chunk_id UUID REFERENCES chunks(id) ON DELETE CASCADE,
    model_name VARCHAR(100) NOT NULL,
    embedding_dimensions INTEGER NOT NULL,
    execution_time_ms INTEGER,
    status VARCHAR(50) DEFAULT 'success',
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_embeddings_log_chunk_id ON embeddings_log(chunk_id);
CREATE INDEX idx_embeddings_log_status ON embeddings_log(status);
CREATE INDEX idx_embeddings_log_created_at ON embeddings_log(created_at DESC);

-- ============================================================================
-- SEARCH_QUERIES TABLE
-- ============================================================================
-- Track user search queries for analytics and UX improvements

CREATE TABLE IF NOT EXISTS search_queries (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    query_text TEXT NOT NULL,
    embedding vector(1536),
    result_count INTEGER,
    execution_time_ms INTEGER,
    user_session_id VARCHAR(255),
    filters JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_search_queries_created_at ON search_queries(created_at DESC);
CREATE INDEX idx_search_queries_result_count ON search_queries(result_count);
CREATE INDEX idx_search_queries_user_session_id ON search_queries(user_session_id);

-- ============================================================================
-- VIEWS FOR COMMON QUERIES
-- ============================================================================

-- View: Documents with their agency information
CREATE OR REPLACE VIEW documents_with_agencies AS
SELECT
    d.id,
    d.title,
    d.year,
    d.document_type,
    d.url,
    d.pdf_path,
    d.pages,
    d.extraction_status,
    d.created_at,
    a.abbreviation,
    a.name as agency_name,
    COUNT(c.id) as chunk_count,
    COUNT(dec.id) as decision_count
FROM documents d
LEFT JOIN agencies a ON d.agency_id = a.id
LEFT JOIN chunks c ON d.id = c.document_id
LEFT JOIN decisions dec ON d.id = dec.document_id
GROUP BY d.id, d.title, d.year, d.document_type, d.url, d.pdf_path,
         d.pages, d.extraction_status, d.created_at, a.abbreviation, a.name;

-- View: Decisions with their agency information
CREATE OR REPLACE VIEW decisions_with_agencies AS
SELECT
    d.id,
    d.case_number,
    d.decision_date,
    d.complaint_date,
    d.outcome,
    d.summary,
    d.agency_complained_about,
    a.abbreviation,
    a.name as agency_name,
    doc.title as document_title,
    doc.year as document_year
FROM decisions d
LEFT JOIN agencies a ON d.agency_id = a.id
LEFT JOIN documents doc ON d.document_id = doc.id;

-- ============================================================================
-- INITIAL DATA: Common Swedish Agencies
-- ============================================================================

INSERT INTO agencies (name, abbreviation, website, description) VALUES
    ('Justitieombudsmannen', 'JO', 'https://www.jo.se', 'Swedish Parliamentary Ombudsman'),
    ('Diskrimineringsombudsmannen', 'DO', 'https://www.do.se', 'Swedish Equality Ombudsman'),
    ('Statsrevisionen', 'RiR', 'https://www.riksrevisionen.se', 'Swedish National Audit Office'),
    ('Myndigheten för samhällsskydd och beredskap', 'MSB', 'https://www.msb.se', 'Swedish Civil Contingencies Agency'),
    ('Arbetsmiljöverket', 'AV', 'https://www.av.se', 'Swedish Work Environment Authority'),
    ('Skatteverket', 'SKV', 'https://www.skatteverket.se', 'Swedish Tax Agency'),
    ('Migrationsverket', 'MI', 'https://www.migrationsverket.se', 'Swedish Migration Agency'),
    ('Skolverket', 'SV', 'https://www.skolverket.se', 'Swedish National Agency for Education'),
    ('Socialstyrelsen', 'SOL', 'https://www.socialstyrelsen.se', 'National Board of Health and Welfare'),
    ('Folkhälsomyndigheten', 'FHM', 'https://www.folkhalsomyndigheten.se', 'Swedish Public Health Agency')
ON CONFLICT (abbreviation) DO NOTHING;

-- ============================================================================
-- FUNCTIONS FOR COMMON OPERATIONS
-- ============================================================================

-- Function: Search chunks by embedding similarity
CREATE OR REPLACE FUNCTION search_chunks_by_embedding(
    query_embedding vector(1536),
    similarity_threshold FLOAT DEFAULT 0.3,
    limit_results INT DEFAULT 10
)
RETURNS TABLE (
    chunk_id UUID,
    document_id UUID,
    document_title VARCHAR,
    content TEXT,
    similarity FLOAT,
    chunk_index INTEGER
) AS $$
SELECT
    c.id,
    c.document_id,
    d.title,
    c.content,
    (1 - (c.embedding <=> query_embedding))::FLOAT as similarity,
    c.chunk_index
FROM chunks c
JOIN documents d ON c.document_id = d.id
WHERE c.embedding IS NOT NULL
    AND (1 - (c.embedding <=> query_embedding)) >= similarity_threshold
ORDER BY c.embedding <=> query_embedding
LIMIT limit_results;
$$ LANGUAGE SQL STABLE;

-- Function: Get document statistics
CREATE OR REPLACE FUNCTION get_document_statistics(
    p_year INT DEFAULT NULL
)
RETURNS TABLE (
    total_documents INT,
    total_chunks INT,
    total_decisions INT,
    avg_chunks_per_document FLOAT,
    docs_with_embeddings INT,
    documents_by_type JSONB
) AS $$
SELECT
    COUNT(DISTINCT d.id)::INT,
    COUNT(DISTINCT c.id)::INT,
    COUNT(DISTINCT dec.id)::INT,
    (COUNT(c.id)::FLOAT / NULLIF(COUNT(DISTINCT d.id), 0))::FLOAT,
    COUNT(DISTINCT CASE WHEN c.embedding IS NOT NULL THEN c.document_id END)::INT,
    jsonb_object_agg(
        COALESCE(d.document_type, 'unknown'),
        COUNT(DISTINCT d.id)
    )
FROM documents d
LEFT JOIN chunks c ON d.id = c.document_id
LEFT JOIN decisions dec ON d.id = dec.document_id
WHERE (p_year IS NULL OR d.year = p_year);
$$ LANGUAGE SQL STABLE;

-- ============================================================================
-- COMMENTS FOR DOCUMENTATION
-- ============================================================================

COMMENT ON TABLE documents IS 'Main table for Swedish government documents, primarily JO ämbetsberättelser (annual reports)';
COMMENT ON TABLE chunks IS 'Text chunks from documents with vector embeddings for semantic search';
COMMENT ON TABLE decisions IS 'Individual JO decisions extracted from ämbetsberättelser';
COMMENT ON TABLE agencies IS 'Swedish government agencies';
COMMENT ON TABLE embeddings_log IS 'Log of embedding operations for monitoring and debugging';
COMMENT ON COLUMN chunks.embedding IS 'Vector embedding (1536 dimensions for OpenAI, 384 for local models)';
COMMENT ON COLUMN chunks.embedding_model IS 'Model used to generate the embedding';
COMMENT ON FUNCTION search_chunks_by_embedding(vector, FLOAT, INT) IS 'Search chunks by cosine similarity to a query embedding';
COMMENT ON FUNCTION get_document_statistics(INT) IS 'Get statistics about stored documents and chunks';
