"""
Observability Metrics Module
In-memory metrics collection for monitoring saknas_underlag and parse_errors rates.

Design Goals:
- Zero external dependencies (no Prometheus client needed)
- Thread-safe counters with time-windowed tracking
- Easy integration with existing logging
- Exportable via REST endpoint
"""

import json
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Deque, Dict, List, Optional


@dataclass
class MetricEvent:
    """Single metric event with timestamp and context."""

    timestamp: float
    question: str
    mode: str
    saknas_underlag: Optional[bool]
    parse_errors: bool
    latency_ms: float
    model_used: str = ""
    retrieval_count: int = 0


class RAGMetrics:
    """
    Thread-safe metrics collector for RAG pipeline events.

    Tracks:
    - saknas_underlag=True rate (evidence refusals)
    - parse_errors=True rate (JSON parsing failures)
    - Questions that trigger these conditions most often
    """

    # Time windows for rate calculation (seconds)
    WINDOW_1MIN = 60
    WINDOW_5MIN = 300
    WINDOW_1HOUR = 3600

    # Maximum events to store (prevents unbounded memory growth)
    MAX_EVENTS = 10000

    def __init__(self):
        self._lock = threading.Lock()
        self._events: Deque[MetricEvent] = deque(maxlen=self.MAX_EVENTS)
        self._start_time = time.time()

        # Counters for total lifetime stats
        self._total_requests = 0
        self._total_saknas_underlag = 0
        self._total_parse_errors = 0

        # Question frequency tracking (limited to top N)
        self._saknas_questions: Dict[str, int] = {}
        self._parse_error_questions: Dict[str, int] = {}
        self._max_tracked_questions = 100

    def record_event(
        self,
        question: str,
        mode: str,
        saknas_underlag: Optional[bool],
        parse_errors: bool,
        latency_ms: float,
        model_used: str = "",
        retrieval_count: int = 0,
    ) -> None:
        """
        Record a RAG pipeline completion event.

        Args:
            question: The user's question (truncated for privacy)
            mode: Response mode (EVIDENCE, ASSIST, CHAT)
            saknas_underlag: Whether evidence was lacking
            parse_errors: Whether JSON parsing failed
            latency_ms: Total pipeline latency
            model_used: LLM model identifier
            retrieval_count: Number of documents retrieved
        """
        # Truncate question for privacy/memory
        truncated_question = question[:200] if question else ""

        event = MetricEvent(
            timestamp=time.time(),
            question=truncated_question,
            mode=mode,
            saknas_underlag=saknas_underlag,
            parse_errors=parse_errors,
            latency_ms=latency_ms,
            model_used=model_used,
            retrieval_count=retrieval_count,
        )

        with self._lock:
            self._events.append(event)
            self._total_requests += 1

            if saknas_underlag:
                self._total_saknas_underlag += 1
                self._track_question(self._saknas_questions, truncated_question)

            if parse_errors:
                self._total_parse_errors += 1
                self._track_question(self._parse_error_questions, truncated_question)

    def _track_question(self, tracker: Dict[str, int], question: str) -> None:
        """Track question frequency, evicting least common if at limit."""
        if not question:
            return

        if question in tracker:
            tracker[question] += 1
        elif len(tracker) < self._max_tracked_questions:
            tracker[question] = 1
        else:
            # Evict least common question
            min_key = min(tracker, key=tracker.get)
            if tracker[min_key] == 1:
                del tracker[min_key]
                tracker[question] = 1

    def _filter_events_by_window(self, window_seconds: float) -> List[MetricEvent]:
        """Get events within the specified time window."""
        cutoff = time.time() - window_seconds
        with self._lock:
            return [e for e in self._events if e.timestamp >= cutoff]

    def _calculate_rates(self, events: List[MetricEvent]) -> Dict[str, float]:
        """Calculate rates from a list of events."""
        if not events:
            return {
                "total_requests": 0,
                "saknas_underlag_count": 0,
                "saknas_underlag_rate": 0.0,
                "parse_errors_count": 0,
                "parse_errors_rate": 0.0,
                "avg_latency_ms": 0.0,
            }

        total = len(events)
        saknas_count = sum(1 for e in events if e.saknas_underlag)
        parse_count = sum(1 for e in events if e.parse_errors)
        avg_latency = sum(e.latency_ms for e in events) / total

        return {
            "total_requests": total,
            "saknas_underlag_count": saknas_count,
            "saknas_underlag_rate": round(saknas_count / total * 100, 2) if total > 0 else 0.0,
            "parse_errors_count": parse_count,
            "parse_errors_rate": round(parse_count / total * 100, 2) if total > 0 else 0.0,
            "avg_latency_ms": round(avg_latency, 1),
        }

    def get_rates_1min(self) -> Dict[str, float]:
        """Get rates for the last 1 minute."""
        events = self._filter_events_by_window(self.WINDOW_1MIN)
        return self._calculate_rates(events)

    def get_rates_5min(self) -> Dict[str, float]:
        """Get rates for the last 5 minutes."""
        events = self._filter_events_by_window(self.WINDOW_5MIN)
        return self._calculate_rates(events)

    def get_rates_1hour(self) -> Dict[str, float]:
        """Get rates for the last 1 hour."""
        events = self._filter_events_by_window(self.WINDOW_1HOUR)
        return self._calculate_rates(events)

    def get_top_saknas_questions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get questions that most often trigger saknas_underlag=True."""
        with self._lock:
            sorted_questions = sorted(
                self._saknas_questions.items(), key=lambda x: x[1], reverse=True
            )[:limit]

        return [{"question": q, "count": c} for q, c in sorted_questions]

    def get_top_parse_error_questions(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Get questions that most often trigger parse_errors=True."""
        with self._lock:
            sorted_questions = sorted(
                self._parse_error_questions.items(), key=lambda x: x[1], reverse=True
            )[:limit]

        return [{"question": q, "count": c} for q, c in sorted_questions]

    def get_mode_breakdown(self, window_seconds: float = 3600) -> Dict[str, Dict[str, float]]:
        """Get rates broken down by response mode."""
        events = self._filter_events_by_window(window_seconds)

        modes = {}
        for event in events:
            mode = event.mode or "unknown"
            if mode not in modes:
                modes[mode] = {"total": 0, "saknas": 0, "parse_errors": 0}
            modes[mode]["total"] += 1
            if event.saknas_underlag:
                modes[mode]["saknas"] += 1
            if event.parse_errors:
                modes[mode]["parse_errors"] += 1

        # Calculate rates per mode
        for mode, counts in modes.items():
            total = counts["total"]
            counts["saknas_rate"] = round(counts["saknas"] / total * 100, 2) if total > 0 else 0.0
            counts["parse_errors_rate"] = (
                round(counts["parse_errors"] / total * 100, 2) if total > 0 else 0.0
            )

        return modes

    def get_full_metrics(self) -> Dict[str, Any]:
        """Get comprehensive metrics snapshot."""
        uptime_seconds = time.time() - self._start_time

        with self._lock:
            lifetime_stats = {
                "total_requests": self._total_requests,
                "total_saknas_underlag": self._total_saknas_underlag,
                "total_parse_errors": self._total_parse_errors,
                "saknas_rate_lifetime": round(
                    self._total_saknas_underlag / self._total_requests * 100, 2
                )
                if self._total_requests > 0
                else 0.0,
                "parse_errors_rate_lifetime": round(
                    self._total_parse_errors / self._total_requests * 100, 2
                )
                if self._total_requests > 0
                else 0.0,
            }

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime_seconds": round(uptime_seconds, 1),
            "events_in_buffer": len(self._events),
            "lifetime": lifetime_stats,
            "last_1min": self.get_rates_1min(),
            "last_5min": self.get_rates_5min(),
            "last_1hour": self.get_rates_1hour(),
            "by_mode": self.get_mode_breakdown(),
            "top_saknas_questions": self.get_top_saknas_questions(10),
            "top_parse_error_questions": self.get_top_parse_error_questions(10),
        }

    def to_prometheus_format(self) -> str:
        """Export metrics in Prometheus text format for scraping."""
        metrics = self.get_full_metrics()
        lifetime = metrics["lifetime"]
        last_5min = metrics["last_5min"]

        lines = [
            "# HELP constitutional_requests_total Total number of RAG requests",
            "# TYPE constitutional_requests_total counter",
            f"constitutional_requests_total {lifetime['total_requests']}",
            "",
            "# HELP constitutional_saknas_underlag_total Total saknas_underlag=True responses",
            "# TYPE constitutional_saknas_underlag_total counter",
            f"constitutional_saknas_underlag_total {lifetime['total_saknas_underlag']}",
            "",
            "# HELP constitutional_parse_errors_total Total parse_errors=True responses",
            "# TYPE constitutional_parse_errors_total counter",
            f"constitutional_parse_errors_total {lifetime['total_parse_errors']}",
            "",
            "# HELP constitutional_saknas_rate_5min Rate of saknas_underlag in last 5 minutes",
            "# TYPE constitutional_saknas_rate_5min gauge",
            f"constitutional_saknas_rate_5min {last_5min['saknas_underlag_rate']}",
            "",
            "# HELP constitutional_parse_errors_rate_5min Rate of parse_errors in last 5 minutes",
            "# TYPE constitutional_parse_errors_rate_5min gauge",
            f"constitutional_parse_errors_rate_5min {last_5min['parse_errors_rate']}",
            "",
            "# HELP constitutional_avg_latency_ms_5min Average latency in last 5 minutes",
            "# TYPE constitutional_avg_latency_ms_5min gauge",
            f"constitutional_avg_latency_ms_5min {last_5min['avg_latency_ms']}",
        ]

        # Add per-mode metrics
        for mode, stats in metrics.get("by_mode", {}).items():
            mode_label = mode.lower().replace(" ", "_")
            lines.extend(
                [
                    "",
                    "# HELP constitutional_requests_by_mode Requests by mode",
                    "# TYPE constitutional_requests_by_mode counter",
                    f'constitutional_requests_by_mode{{mode="{mode_label}"}} {stats["total"]}',
                    f'constitutional_saknas_by_mode{{mode="{mode_label}"}} {stats["saknas"]}',
                    f'constitutional_parse_errors_by_mode{{mode="{mode_label}"}} {stats["parse_errors"]}',
                ]
            )

        return "\n".join(lines) + "\n"


# Singleton instance
_metrics_instance: Optional[RAGMetrics] = None
_metrics_lock = threading.Lock()


def get_rag_metrics() -> RAGMetrics:
    """Get the singleton RAGMetrics instance."""
    global _metrics_instance

    if _metrics_instance is None:
        with _metrics_lock:
            if _metrics_instance is None:
                _metrics_instance = RAGMetrics()

    return _metrics_instance


def log_structured_metric(
    logger,
    event_type: str,
    question: str,
    mode: str,
    saknas_underlag: Optional[bool],
    parse_errors: bool,
    latency_ms: float,
    **extra_fields,
) -> None:
    """
    Log a structured metric event as JSON for easy parsing by log aggregators.

    This logs in a consistent JSON format that can be:
    - Parsed by Loki/Grafana
    - Indexed by Elasticsearch
    - Queried with CloudWatch Insights
    - Aggregated by Splunk

    Args:
        logger: Logger instance
        event_type: Event classification (e.g., "rag_completion")
        question: User's question (will be truncated)
        mode: Response mode
        saknas_underlag: Evidence lacking flag
        parse_errors: JSON parsing failure flag
        latency_ms: Pipeline latency
        **extra_fields: Additional fields to include
    """
    # Truncate question for log safety (no PII, bounded size)
    safe_question = (question or "")[:150].replace("\n", " ").replace('"', "'")

    metric_data = {
        "event": event_type,
        "question_preview": safe_question,
        "mode": mode,
        "saknas_underlag": saknas_underlag,
        "parse_errors": parse_errors,
        "latency_ms": round(latency_ms, 1),
        **extra_fields,
    }

    # Log as JSON string with marker for easy grep/filter
    logger.info(f"[METRIC] {json.dumps(metric_data)}")
