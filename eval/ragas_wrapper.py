"""
RAGAS Metrics Wrapper - Kapslad implementation
===============================================

Abstraherar RAGAS-mått så vi kan byta till lightweight senare.

Användning:
    from ragas_wrapper import get_metrics_provider

    metrics = get_metrics_provider("ragas")  # eller "lightweight"
    score = metrics.faithfulness(answer, contexts)
"""

import logging
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class MetricsProvider(ABC):
    """Abstract base för metrics - möjliggör byte från RAGAS till lightweight"""

    @abstractmethod
    def faithfulness(self, answer: str, contexts: list[str], question: str = "") -> float:
        """
        Mäter om svaret stöds av kontext (ingen hallucination).

        Returns:
            float: 0.0-1.0, där 1.0 = alla claims stöds av kontext
        """
        pass

    @abstractmethod
    def context_precision(
        self, question: str, contexts: list[str], ground_truth: str = ""
    ) -> float:
        """
        Mäter om relevanta chunks rankas högt.

        Returns:
            float: 0.0-1.0, där 1.0 = alla relevanta chunks är i toppen
        """
        pass

    @abstractmethod
    def context_recall(self, contexts: list[str], ground_truth: str) -> float:
        """
        Mäter om alla relevanta chunks hittades.

        Returns:
            float: 0.0-1.0, där 1.0 = alla relevanta chunks hittade
        """
        pass

    @abstractmethod
    def answer_relevancy(self, question: str, answer: str) -> float:
        """
        Mäter om svaret är relevant för frågan.

        Returns:
            float: 0.0-1.0, där 1.0 = perfekt relevans
        """
        pass


class RagasProvider(MetricsProvider):
    """RAGAS-baserad implementation (P0-P1)"""

    def __init__(self):
        try:
            from datasets import Dataset
            from ragas import evaluate
            from ragas.metrics import (
                answer_relevancy as ragas_answer_relevancy,
            )
            from ragas.metrics import (
                context_precision as ragas_context_precision,
            )
            from ragas.metrics import (
                context_recall as ragas_context_recall,
            )
            from ragas.metrics import (
                faithfulness as ragas_faithfulness,
            )

            self._faithfulness_metric = ragas_faithfulness
            self._context_precision_metric = ragas_context_precision
            self._context_recall_metric = ragas_context_recall
            self._answer_relevancy_metric = ragas_answer_relevancy
            self._evaluate = evaluate
            self._Dataset = Dataset

            logger.info("RAGAS provider initialized successfully")

        except ImportError as e:
            logger.error(f"RAGAS not installed: {e}")
            logger.error("Install with: pip install ragas datasets")
            raise RuntimeError(
                "RAGAS not available. Install with: pip install ragas datasets"
            ) from e

    def faithfulness(self, answer: str, contexts: list[str], question: str = "") -> float:
        """
        RAGAS faithfulness: Mäter om svaret stöds av kontext.

        RAGAS använder LLM för att:
        1. Extrahera claims från answer
        2. Verifiera varje claim mot contexts
        """
        try:
            # RAGAS kräver Dataset-format
            data = {
                "question": [question or "N/A"],
                "answer": [answer],
                "contexts": [contexts],
            }
            dataset = self._Dataset.from_dict(data)

            # Kör RAGAS evaluate
            result = self._evaluate(
                dataset,
                metrics=[self._faithfulness_metric],
            )

            return float(result["faithfulness"])

        except Exception as e:
            logger.error(f"RAGAS faithfulness error: {e}")
            return 0.0

    def context_precision(
        self, question: str, contexts: list[str], ground_truth: str = ""
    ) -> float:
        """
        RAGAS context precision: Mäter om relevanta chunks rankas högt.

        Kräver ground_truth för att veta vilka chunks som är relevanta.
        """
        try:
            if not ground_truth:
                logger.warning("context_precision requires ground_truth, returning 0.0")
                return 0.0

            data = {
                "question": [question],
                "contexts": [contexts],
                "ground_truth": [ground_truth],
            }
            dataset = self._Dataset.from_dict(data)

            result = self._evaluate(
                dataset,
                metrics=[self._context_precision_metric],
            )

            return float(result["context_precision"])

        except Exception as e:
            logger.error(f"RAGAS context_precision error: {e}")
            return 0.0

    def context_recall(self, contexts: list[str], ground_truth: str) -> float:
        """
        RAGAS context recall: Mäter om alla relevanta chunks hittades.
        """
        try:
            if not ground_truth:
                logger.warning("context_recall requires ground_truth, returning 0.0")
                return 0.0

            data = {
                "question": ["N/A"],  # RAGAS kräver question även om vi inte använder den
                "contexts": [contexts],
                "ground_truth": [ground_truth],
            }
            dataset = self._Dataset.from_dict(data)

            result = self._evaluate(
                dataset,
                metrics=[self._context_recall_metric],
            )

            return float(result["context_recall"])

        except Exception as e:
            logger.error(f"RAGAS context_recall error: {e}")
            return 0.0

    def answer_relevancy(self, question: str, answer: str) -> float:
        """
        RAGAS answer relevancy: Mäter om svaret är relevant för frågan.
        """
        try:
            data = {
                "question": [question],
                "answer": [answer],
                "contexts": [["N/A"]],  # RAGAS kräver contexts även om vi inte använder dem
            }
            dataset = self._Dataset.from_dict(data)

            result = self._evaluate(
                dataset,
                metrics=[self._answer_relevancy_metric],
            )

            return float(result["answer_relevancy"])

        except Exception as e:
            logger.error(f"RAGAS answer_relevancy error: {e}")
            return 0.0


class LightweightProvider(MetricsProvider):
    """
    Lightweight implementation för CI/offline (framtida P2).

    Använder enkla heuristiker utan LLM-calls:
    - Faithfulness: Overlap mellan answer och contexts
    - Context precision: Keyword-baserad relevans
    - Context recall: Keyword coverage
    - Answer relevancy: Semantic similarity (sentence-transformers)
    """

    def __init__(self):
        logger.info("Lightweight provider initialized (heuristic-based)")
        self._stopwords = {
            "och",
            "i",
            "att",
            "en",
            "ett",
            "det",
            "som",
            "av",
            "för",
            "med",
            "till",
            "på",
            "är",
            "om",
            "har",
            "de",
            "den",
            "vara",
            "vad",
            "var",
        }

    def _extract_keywords(self, text: str) -> set:
        """Extrahera keywords (enkelt, utan NLP)"""
        words = text.lower().split()
        return {w for w in words if len(w) > 3 and w not in self._stopwords}

    def faithfulness(self, answer: str, contexts: list[str], question: str = "") -> float:
        """
        Lightweight faithfulness: Mäter overlap mellan answer och contexts.

        Heuristik: Om alla keywords i answer finns i contexts → hög faithfulness.
        """
        if not answer or not contexts:
            return 0.0

        answer_keywords = self._extract_keywords(answer)
        if not answer_keywords:
            return 0.5  # Tomt svar, neutral score

        # Kombinera alla contexts
        all_context = " ".join(contexts).lower()

        # Räkna hur många answer-keywords som finns i context
        supported = sum(1 for kw in answer_keywords if kw in all_context)

        return supported / len(answer_keywords)

    def context_precision(
        self, question: str, contexts: list[str], ground_truth: str = ""
    ) -> float:
        """
        Lightweight context precision: Keyword-baserad relevans.

        Heuristik: Rankar contexts efter keyword-overlap med question.
        """
        if not question or not contexts:
            return 0.0

        question_keywords = self._extract_keywords(question)
        if not question_keywords:
            return 0.5

        # Beräkna relevans för varje context
        relevance_scores = []
        for ctx in contexts:
            ctx_keywords = self._extract_keywords(ctx)
            overlap = len(question_keywords & ctx_keywords)
            relevance_scores.append(overlap / len(question_keywords) if question_keywords else 0)

        # Precision: Är de mest relevanta contexts i toppen?
        # Enkel heuristik: Medelvärde av top-3 scores
        top_scores = sorted(relevance_scores, reverse=True)[:3]
        return sum(top_scores) / len(top_scores) if top_scores else 0.0

    def context_recall(self, contexts: list[str], ground_truth: str) -> float:
        """
        Lightweight context recall: Keyword coverage.

        Heuristik: Hur många ground_truth-keywords finns i contexts?
        """
        if not ground_truth or not contexts:
            return 0.0

        gt_keywords = self._extract_keywords(ground_truth)
        if not gt_keywords:
            return 0.5

        all_context = " ".join(contexts).lower()
        found = sum(1 for kw in gt_keywords if kw in all_context)

        return found / len(gt_keywords)

    def answer_relevancy(self, question: str, answer: str) -> float:
        """
        Lightweight answer relevancy: Keyword overlap.

        Heuristik: Hur många question-keywords finns i answer?
        """
        if not question or not answer:
            return 0.0

        q_keywords = self._extract_keywords(question)
        a_keywords = self._extract_keywords(answer)

        if not q_keywords:
            return 0.5

        overlap = len(q_keywords & a_keywords)
        return overlap / len(q_keywords)


# ═══════════════════════════════════════════════════════════════════════════
# FACTORY
# ═══════════════════════════════════════════════════════════════════════════


def get_metrics_provider(provider: str = "ragas") -> MetricsProvider:
    """
    Factory för att skapa metrics provider.

    Args:
        provider: "ragas" (default) eller "lightweight"

    Returns:
        MetricsProvider instance

    Raises:
        ValueError: Om provider är okänd
        RuntimeError: Om RAGAS inte är installerad (när provider="ragas")
    """
    if provider == "ragas":
        return RagasProvider()
    elif provider == "lightweight":
        return LightweightProvider()
    else:
        raise ValueError(f"Unknown provider: {provider}. Use 'ragas' or 'lightweight'")


# ═══════════════════════════════════════════════════════════════════════════
# CLI TEST
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Test both providers
    print("Testing RAGAS provider...")
    try:
        ragas = get_metrics_provider("ragas")
        score = ragas.faithfulness(
            answer="Regeringsformen skyddar yttrandefrihet enligt 2 kap. 1 §.",
            contexts=["RF 2 kap. 1 § säger att var och en är tillförsäkrad yttrandefrihet."],
            question="Vad säger RF om yttrandefrihet?",
        )
        print(f"✅ RAGAS faithfulness: {score:.2f}")
    except RuntimeError as e:
        print(f"❌ RAGAS not available: {e}")

    print("\nTesting Lightweight provider...")
    lightweight = get_metrics_provider("lightweight")
    score = lightweight.faithfulness(
        answer="Regeringsformen skyddar yttrandefrihet enligt 2 kap. 1 §.",
        contexts=["RF 2 kap. 1 § säger att var och en är tillförsäkrad yttrandefrihet."],
    )
    print(f"✅ Lightweight faithfulness: {score:.2f}")
