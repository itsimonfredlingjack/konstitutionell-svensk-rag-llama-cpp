import React, { useState } from "react";
import clsx from "clsx";
import { ChevronDown } from "lucide-react";
import type { QueryResultSource } from "../../types/queryResult";

// Load thresholds from env vars (default: 0.7)
const SCORE_THRESHOLD_HIGH =
    Number(import.meta.env.VITE_SCORE_THRESHOLD_GOOD) || 0.7;

interface SourceChipProps {
    source: QueryResultSource;
}

export const SourceChip: React.FC<SourceChipProps> = ({ source }) => {
    const [isExpanded, setIsExpanded] = useState(false);

    const isHighRelevance = source.score >= SCORE_THRESHOLD_HIGH;

    // Format title: shorten if too long
    const shortTitle = source.title.length > 25
        ? source.title.slice(0, 22) + "…"
        : source.title;

    return (
        <div className="inline-block">
            <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                className={clsx(
                    "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono",
                    "border transition-all duration-200",
                    "hover:scale-[1.02] active:scale-[0.98]",
                    isHighRelevance
                        ? "bg-emerald-50 border-emerald-300/60 text-emerald-700 hover:bg-emerald-100/70"
                        : "bg-amber-50 border-amber-300/60 text-amber-700 hover:bg-amber-100/70"
                )}
            >
                <span>{shortTitle}</span>
                <span className="opacity-70">{source.score.toFixed(2)}</span>
                <ChevronDown
                    className={clsx(
                        "w-3 h-3 transition-transform",
                        isExpanded && "rotate-180"
                    )}
                    strokeWidth={1.5}
                />
            </button>

            {isExpanded && (
                <div className="mt-1.5 ml-1 p-3 rounded-lg bg-stone-100/80 border border-stone-200/60 text-xs max-w-sm">
                    <div className="font-medium text-stone-800 mb-1">{source.title}</div>
                    <div className="text-stone-600 leading-relaxed">
                        {source.snippet || "Ingen förhandsgranskning tillgänglig."}
                    </div>
                    <div className="mt-2 pt-2 border-t border-stone-200/50 flex items-center gap-3 text-[10px] text-stone-500 font-mono">
                        <span>Typ: {source.doc_type || "—"}</span>
                        <span>Källa: {source.source || "—"}</span>
                        <span>Score: {source.score.toFixed(3)}</span>
                    </div>
                </div>
            )}
        </div>
    );
};
