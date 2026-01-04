import logging
from typing import Optional

import psycopg2
from psycopg2.extras import RealDictCursor
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


class RAGQuery:
    """RAG query module for juridik-ai using PostgreSQL pgvector."""

    def __init__(
        self, db_connection: psycopg2.extensions.connection, embedding_model: str = "local"
    ):
        """
        Initialize RAGQuery with database connection and embedding model.

        Args:
            db_connection: PostgreSQL connection object
            embedding_model: Embedding model to use ("local" or model name)
        """
        self.db_connection = db_connection
        self.embedding_model = embedding_model
        self.model = None

        if embedding_model == "local":
            try:
                self.model = SentenceTransformer(
                    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
                )
                logger.info("Loaded sentence-transformers model successfully")
            except Exception as e:
                logger.warning(
                    f"Failed to load embedding model: {e}. Falling back to keyword search."
                )
                self.model = None
        else:
            try:
                self.model = SentenceTransformer(embedding_model)
                logger.info(f"Loaded embedding model: {embedding_model}")
            except Exception as e:
                logger.warning(
                    f"Failed to load embedding model {embedding_model}: {e}. Falling back to keyword search."
                )
                self.model = None

    def embed_query(self, query: str) -> Optional[list[float]]:
        """
        Generate embedding for a query string.

        Args:
            query: Query text to embed

        Returns:
            List of floats representing the embedding, or None if unavailable
        """
        if self.model is None:
            return None

        try:
            embedding = self.model.encode(query, convert_to_tensor=False)
            return embedding.tolist() if hasattr(embedding, "tolist") else list(embedding)
        except Exception as e:
            logger.error(f"Error embedding query: {e}")
            return None

    def search_similar(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Search for similar documents using pgvector similarity search.
        Falls back to keyword search if embeddings unavailable.

        Args:
            query: Query text
            top_k: Number of top results to return

        Returns:
            List of result dictionaries with chunk_id, content, score, source, year
        """
        results = []
        embedding = self.embed_query(query)

        if embedding:
            try:
                with self.db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
                    cursor.execute(
                        """
                        SELECT
                            chunk_id,
                            content,
                            source,
                            year,
                            1 - (embedding <=> %s::vector) AS score
                        FROM legal_chunks
                        WHERE embedding IS NOT NULL
                        ORDER BY embedding <=> %s::vector
                        LIMIT %s
                    """,
                        (str(embedding), str(embedding), top_k),
                    )

                    rows = cursor.fetchall()
                    results = [
                        {
                            "chunk_id": row["chunk_id"],
                            "content": row["content"],
                            "score": float(row["score"]),
                            "source": row["source"],
                            "year": row["year"],
                        }
                        for row in rows
                    ]
                    logger.info(f"Found {len(results)} similar documents via pgvector")
            except Exception as e:
                logger.error(f"Error during pgvector search: {e}")
                results = []

        if not results:
            results = self._keyword_search(query, top_k)

        return results

    def _keyword_search(self, query: str, top_k: int = 5) -> list[dict]:
        """
        Fallback keyword-based search using simple string matching.

        Args:
            query: Query text
            top_k: Number of top results to return

        Returns:
            List of result dictionaries
        """
        try:
            keywords = query.lower().split()

            with self.db_connection.cursor(cursor_factory=RealDictCursor) as cursor:
                placeholders = " OR ".join(["LOWER(content) LIKE %s"] * len(keywords))
                query_params = [f"%{kw}%" for kw in keywords]

                cursor.execute(
                    f"""
                    SELECT
                        chunk_id,
                        content,
                        source,
                        year
                    FROM legal_chunks
                    WHERE {placeholders}
                    LIMIT %s
                """,
                    query_params + [top_k],
                )

                rows = cursor.fetchall()
                results = [
                    {
                        "chunk_id": row["chunk_id"],
                        "content": row["content"],
                        "score": 0.5,
                        "source": row["source"],
                        "year": row["year"],
                    }
                    for row in rows
                ]
                logger.info(f"Found {len(results)} documents via keyword search")
                return results
        except Exception as e:
            logger.error(f"Error during keyword search: {e}")
            return []

    def format_context(self, results: list[dict]) -> str:
        """
        Format search results into a context string for LLM.

        Args:
            results: List of result dictionaries

        Returns:
            Formatted context string
        """
        if not results:
            return "No relevant documents found."

        context_parts = []
        for i, result in enumerate(results, 1):
            source_info = (
                f"{result['source']} ({result['year']})" if result.get("year") else result["source"]
            )
            score_info = (
                f"[similarity: {result['score']:.2f}]" if result.get("score", 0) > 0.5 else ""
            )

            context_parts.append(f"Document {i}: {source_info} {score_info}\n{result['content']}")

        return "\n\n".join(context_parts)

    def query_with_context(self, question: str) -> str:
        """
        Execute a RAG query with context retrieval and formatting.

        Args:
            question: The question to answer

        Returns:
            Formatted context string with relevant documents
        """
        try:
            results = self.search_similar(question, top_k=5)
            context = self.format_context(results)
            logger.info(f"Generated context with {len(results)} documents for question")
            return context
        except Exception as e:
            logger.error(f"Error in query_with_context: {e}")
            return "Error retrieving context."
