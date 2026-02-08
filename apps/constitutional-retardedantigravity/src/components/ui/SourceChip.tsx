import React, { useState } from "react";
import clsx from "clsx";
import { ChevronDown } from "lucide-react";
import type { QueryResultSource } from "../../types/queryResult";

// Load thresholds from env vars (default: 0.7)

interface SourceChipProps {
    source: QueryResultSource;
}

export const SourceChip: React.FC<SourceChipProps> = ({ source }) => {
    const [isExpanded, setIsExpanded] = useState(false);

    // Color logic
    const score = source.score;
    let colorClass = "";
    let borderClass = "";
    let textClass = "";
    let bgHoverClass = "";
    let bgExpandedClass = "";

    if (score >= 0.7) {
        // High relevance (Green)
        colorClass = "bg-emerald-50";
        borderClass = "border-emerald-300/60";
        textClass = "text-emerald-700";
        bgHoverClass = "hover:bg-emerald-100/70";
        bgExpandedClass = "bg-emerald-50/50";
    } else if (score >= 0.4) {
        // Medium relevance (Orange)
        colorClass = "bg-amber-50";
        borderClass = "border-amber-300/60";
        textClass = "text-amber-700";
        bgHoverClass = "hover:bg-amber-100/70";
        bgExpandedClass = "bg-amber-50/50";
    } else {
        // Low relevance (Red)
        colorClass = "bg-red-50";
        borderClass = "border-red-300/60";
        textClass = "text-red-700";
        bgHoverClass = "hover:bg-red-100/70";
        bgExpandedClass = "bg-red-50/50";
    }

    // Format title: shorten if too long
    const shortTitle = source.title.length > 25
        ? source.title.slice(0, 22) + "…"
        : source.title;

    return (
        <div className="inline-block align-top">
            <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                className={clsx(
                    "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-mono",
                    "border transition-all duration-200",
                    "hover:scale-[1.02] active:scale-[0.98]",
                    colorClass,
                    borderClass,
                    textClass,
                    bgHoverClass
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
                <div
                    className={clsx(
                        "mt-1.5 ml-1 p-3 rounded-xl border text-xs max-w-md shadow-sm",
                        "text-stone-800",
                        bgExpandedClass,
                        borderClass
                    )}
                >
                    <div className="flex justify-between items-start mb-2">
                        <div className="font-semibold">{source.title}</div>
                        <div className={clsx("text-[10px] font-mono px-1.5 py-0.5 rounded border", borderClass, "bg-white/50")}>
                            {source.doc_type || "DOC"}
                        </div>
                    </div>

                    {/* Inline Preview */}
                    <div className="bg-white/60 p-2 rounded-lg border border-black/5 font-serif text-stone-700 leading-relaxed italic mb-2">
                        "{source.snippet || "Ingen förhandsgranskning tillgänglig."}"
                    </div>

                    <div className="flex items-center gap-3 text-[10px] text-stone-500 font-mono opacity-80">
                        <span>Källa: {source.source || "—"}</span>
                        <span>Relevans: {(source.score * 100).toFixed(0)}%</span>
                        <span className="uppercase tracking-wider">{source.id}</span>
                    </div>
                </div>
            )}
        </div>
    );
};
