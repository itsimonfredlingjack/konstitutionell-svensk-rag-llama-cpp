import React from "react";
import { motion } from "framer-motion";
import { Shield, BookOpen, GitCompare, ShieldAlert } from "lucide-react";
import clsx from "clsx";
import type { QueryResult } from "../../types/queryResult";
import { CompactPipeline } from "./CompactPipeline";
import { SourceChip } from "./SourceChip";
import { AnswerWithCitations } from "./AnswerWithCitations";
import { ThoughtChain } from "./ThoughtChain";

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
    const {
        query,
        mode,
        answer,
        sources,
        searchStage,
        evidenceLevel,
        thoughtChain,
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
            {/* User's question - right aligned */}
            <div className="flex justify-end">
                <div
                    className={clsx(
                        "relative max-w-[85%] rounded-2xl px-5 py-3",
                        "bg-stone-200/70 backdrop-blur-sm",
                        "border border-stone-300/50"
                    )}
                >
                    <p className="text-stone-900 text-[15px] leading-relaxed">{query}</p>
                    <div className="flex items-center gap-1.5 mt-2">
                        <ModeIcon className="w-3 h-3 text-stone-500" strokeWidth={1.5} />
                        <span className="text-[10px] font-mono uppercase tracking-wider text-stone-500">
                            {MODE_LABELS[mode]}
                        </span>
                    </div>
                </div>
            </div>

            {/* Pipeline visualization */}
            <CompactPipeline queryResult={queryResult} />

            {/* AI Response */}
            <div
                className={clsx(
                    "rounded-2xl px-6 py-5",
                    "bg-white/60 backdrop-blur-xl",
                    "border border-stone-200/60",
                    "shadow-sm"
                )}
            >
                {/* Evidence level badge */}
                {evidenceLevel && (
                    <div className="flex items-center gap-1.5 mb-3">
                        {evidenceLevel === "HIGH" ? (
                            <Shield className="w-3.5 h-3.5 text-emerald-600" strokeWidth={1.5} />
                        ) : evidenceLevel === "LOW" ? (
                            <ShieldAlert className="w-3.5 h-3.5 text-red-600" strokeWidth={1.5} />
                        ) : (
                            <Shield className="w-3.5 h-3.5 text-amber-600" strokeWidth={1.5} />
                        )}
                        <span
                            className={clsx(
                                "text-[10px] font-mono uppercase tracking-wider",
                                evidenceLevel === "HIGH"
                                    ? "text-emerald-600"
                                    : evidenceLevel === "LOW"
                                        ? "text-red-600"
                                        : "text-amber-600"
                            )}
                        >
                            Evidens: {evidenceLevel}
                        </span>
                    </div>
                )}

                {/* Loading state */}
                {isSearching && (
                    <div className="flex items-center gap-3 text-stone-500">
                        <span className="w-2 h-2 bg-teal-600 rounded-full animate-pulse" />
                        <span className="text-sm font-mono">Kör pipeline…</span>
                    </div>
                )}

                {/* Error state */}
                {isError && (
                    <div className="flex items-center gap-3 text-red-700">
                        <ShieldAlert className="w-4 h-4" strokeWidth={1.5} />
                        <span className="text-sm font-mono">Ett fel uppstod.</span>
                    </div>
                )}

                {/* Answer content */}
                {hasAnswer && (
                    <div>
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
                            <div className="flex items-center gap-2 text-stone-500 italic">
                                <span className="w-2 h-2 bg-stone-400 rounded-full animate-pulse" />
                                Väntar på svar…
                            </div>
                        )}
                    </div>
                )}

                {/* Source chips */}
                {sources.length > 0 && (
                    <div className="mt-5 pt-4 border-t border-stone-200/50">
                        <div className="text-[10px] font-mono uppercase tracking-wider text-stone-500 mb-2">
                            Källor ({sources.length})
                        </div>
                        <div className="flex flex-wrap gap-2">
                            {sources.map((source) => (
                                <SourceChip key={source.id} source={source} />
                            ))}
                        </div>
                    </div>
                )}
            </div>
        </motion.div>
    );
};
