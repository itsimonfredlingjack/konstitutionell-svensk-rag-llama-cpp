import React from "react";
import { motion } from "framer-motion";
import { Shield, BookOpen, GitCompare, User, RefreshCw, AlertCircle, FileQuestion } from "lucide-react";
import clsx from "clsx";
import type { QueryResult } from "../../types/queryResult";
import { CompactPipeline } from "./CompactPipeline";
import { SourceChip } from "./SourceChip";
import { AnswerWithCitations } from "./AnswerWithCitations";
import { ThoughtChain } from "./ThoughtChain";
import { ConfidenceBadge } from "./ConfidenceBadge";
import { useAppStore } from "../../stores/useAppStore";

const MODE_ICONS = {
    verify: Shield,
    summarize: BookOpen,
    compare: GitCompare,
} as const;

const MODE_LABELS = {
    verify: "Verifiera",
    summarize: "Sammanfatta",
    compare: "Jämför",
} as const;

interface ChatMessageProps {
    queryResult: QueryResult;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({ queryResult }) => {
    const retryQuery = useAppStore((s) => s.retryQuery);
    const {
        id,
        query,
        mode,
        answer,
        sources,
        searchStage,
        thoughtChain,
        error,
    } = queryResult;

    const ModeIcon = MODE_ICONS[mode];
    const isSearching = searchStage === "searching";
    const isError = searchStage === "error";
    const hasAnswer = searchStage === "reading" || searchStage === "complete" || searchStage === "reasoning";

    return (
        <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            className="w-full max-w-3xl mx-auto space-y-4"
        >
            {/* User's question - right aligned with teal tint and avatar */}
            <div className="flex justify-end gap-3">
                <div
                    className={clsx(
                        "relative max-w-[85%] rounded-2xl px-5 py-3",
                        "bg-user-bubble-bg backdrop-blur-sm",
                        "border border-user-bubble-border"
                    )}
                >
                    <p className="text-stone-900 text-[15px] leading-relaxed">{query}</p>
                    <div className="flex items-center gap-1.5 mt-2">
                        <ModeIcon className="w-3 h-3 text-text-muted" strokeWidth={1.5} />
                        <span className="text-[10px] font-mono uppercase tracking-wider text-text-muted">
                            {MODE_LABELS[mode]}
                        </span>
                    </div>
                </div>
                {/* User Avatar */}
                <div className="w-8 h-8 rounded-full bg-teal-700 flex items-center justify-center shrink-0">
                    <User className="w-4 h-4 text-white" strokeWidth={2} />
                </div>
            </div>

            {/* Pipeline visualization */}
            <CompactPipeline queryResult={queryResult} />

            {/* AI Response - with floating confidence badge */}
            <div
                className={clsx(
                    "relative rounded-2xl px-5 sm:px-6 pt-6 pb-5",
                    "bg-white/70 backdrop-blur-xl",
                    "border border-stone-200/60",
                    "shadow-sm"
                )}
                role="region"
                aria-label="AI-svar"
                aria-live="polite"
            >
                {/* Floating Confidence Badge */}
                <div className="absolute -top-3 left-5 sm:left-6">
                    <ConfidenceBadge queryResult={queryResult} />
                </div>


                {/* Loading state with skeleton */}
                {
                    isSearching && (
                        <div className="mt-4 space-y-3">
                            <div className="flex items-center gap-3 text-text-muted">
                                <span className="w-2 h-2 bg-teal-600 rounded-full animate-pulse" />
                                <span className="text-sm font-mono">Kör pipeline…</span>
                            </div>
                            {/* Skeleton lines */}
                            <div className="space-y-2.5 animate-pulse">
                                <div className="h-3.5 bg-stone-200 rounded w-3/4" />
                                <div className="h-3.5 bg-stone-200 rounded w-1/2" />
                                <div className="h-3.5 bg-stone-200 rounded w-5/6" />
                            </div>
                        </div>
                    )
                }

                {/* Error state with recovery action */}
                {
                    isError && (
                        <div className="mt-4 p-4 rounded-xl bg-red-50 border border-red-200">
                            <div className="flex items-start gap-3">
                                <AlertCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" strokeWidth={1.5} />
                                <div className="flex-1">
                                    <p className="text-sm font-medium text-red-800">Något gick fel</p>
                                    <p className="text-sm text-red-700 mt-1">
                                        {error || "Ett oväntat fel uppstod vid bearbetning av din fråga."}
                                    </p>
                                    <button
                                        onClick={() => retryQuery(id)}
                                        className="mt-3 inline-flex items-center gap-2 px-3 py-1.5 text-xs font-medium text-red-700 bg-red-100 hover:bg-red-200 rounded-lg transition-colors focus-ring"
                                    >
                                        <RefreshCw className="w-3.5 h-3.5" />
                                        Försök igen
                                    </button>
                                </div>
                            </div>
                        </div>
                    )
                }

                {/* Answer content */}
                {
                    hasAnswer && (
                        <div className="mt-4">
                            {/* Thought chain (if present) */}
                            <ThoughtChain thought={(thoughtChain as string | null) ?? null} />

                            {/* Main answer */}
                            {answer ? (
                                <div
                                    className="text-stone-900 text-[15px] leading-relaxed"
                                    style={{ lineHeight: "1.85" }}
                                >
                                    <AnswerWithCitations answer={answer} sources={sources} />
                                </div>
                            ) : (
                                <div className="flex items-center gap-2 text-text-muted italic">
                                    <span className="w-2 h-2 bg-stone-400 rounded-full animate-pulse" />
                                    Väntar på svar…
                                </div>
                            )}
                        </div>
                    )
                }

                {/* Source chips or empty state */}
                {
                    hasAnswer && (
                        <div className="mt-5 pt-4 border-t border-stone-200/50">
                            {sources.length > 0 ? (
                                <>
                                    <div className="text-[10px] font-mono uppercase tracking-wider text-text-muted mb-2">
                                        Källor ({sources.length})
                                    </div>
                                    <div className="flex flex-wrap gap-2">
                                        {sources.map((source) => (
                                            <SourceChip key={source.id} source={source} />
                                        ))}
                                    </div>
                                </>
                            ) : (
                                <div className="flex items-start gap-3 p-3 rounded-lg bg-stone-100/50">
                                    <FileQuestion className="w-4 h-4 text-text-muted shrink-0 mt-0.5" />
                                    <div>
                                        <p className="text-xs font-medium text-stone-700">Inga källor hämtade</p>
                                        <p className="text-xs text-text-muted mt-0.5">
                                            Svaret baseras på modellens resonemang. Försök omformulera frågan för att hitta relevanta källor.
                                        </p>
                                    </div>
                                </div>
                            )}
                        </div>
                    )
                }
            </div >
        </motion.div >
    );
};
