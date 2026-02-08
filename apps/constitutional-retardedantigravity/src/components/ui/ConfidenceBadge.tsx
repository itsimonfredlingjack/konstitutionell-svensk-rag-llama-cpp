import React, { useState } from "react";
import { Shield, ShieldAlert, Info } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";
import clsx from "clsx";
import type { QueryResult } from "../../types/queryResult";

interface ConfidenceBadgeProps {
    queryResult: QueryResult;
}

export const ConfidenceBadge: React.FC<ConfidenceBadgeProps> = ({
    queryResult,
}) => {
    const [showTooltip, setShowTooltip] = useState(false);
    const { evidenceLevel: backendLevel, sources, answer, searchStage } = queryResult;

    // Don't render if no answer yet or still searching
    if (!answer || searchStage === "searching") return null;

    const sourceCount = sources.length;
    // Calculate avg score if possible
    const avgScore =
        sourceCount > 0
            ? sources.reduce((acc, s) => acc + s.score, 0) / sourceCount
            : 0;

    // Compute fallback evidence level if backend doesn't provide one
    const computedLevel = (): "HIGH" | "MEDIUM" | "LOW" => {
        if (sourceCount >= 3 && avgScore >= 0.6) return "HIGH";
        if (sourceCount >= 1 && avgScore >= 0.4) return "MEDIUM";
        return "LOW";
    };

    const evidenceLevel = backendLevel || computedLevel();

    // Configuration based on level
    const config = {
        HIGH: {
            label: "Hög tillförlitlighet",
            icon: Shield,
            color: "text-emerald-700",
            bg: "bg-emerald-50",
            border: "border-emerald-200",
        },
        MEDIUM: {
            label: "Medel tillförlitlighet",
            icon: Shield,
            color: "text-amber-700",
            bg: "bg-amber-50",
            border: "border-amber-200",
        },
        LOW: {
            label: "Låg tillförlitlighet",
            icon: ShieldAlert,
            color: "text-red-700",
            bg: "bg-red-50",
            border: "border-red-200",
        },
    }[evidenceLevel || "LOW"]; // Fallback to LOW if null (shouldn't happen with check above)

    // Default to LOW if undefined (should be covered by check but TS safety)
    const activeConfig = config || {
        label: "Okänd status",
        icon: Info,
        color: "text-stone-500",
        bg: "bg-stone-50",
        border: "border-stone-200",
    };

    const Icon = activeConfig.icon;

    return (
        <div className="relative inline-block">
            <button
                type="button"
                onMouseEnter={() => setShowTooltip(true)}
                onMouseLeave={() => setShowTooltip(false)}
                onClick={() => setShowTooltip(!showTooltip)}
                className={clsx(
                    "flex items-center gap-1.5 px-3 py-1 rounded-full border cursor-help transition-colors shadow-sm",
                    activeConfig.bg,
                    activeConfig.border,
                    activeConfig.color
                )}
            >
                <Icon className="w-3.5 h-3.5" strokeWidth={2} />
                <span className="text-[11px] font-semibold uppercase tracking-wide">
                    {activeConfig.label.split(" ")[0]}
                </span>
            </button>

            <AnimatePresence>
                {showTooltip && (
                    <motion.div
                        initial={{ opacity: 0, y: 4, scale: 0.95 }}
                        animate={{ opacity: 1, y: 0, scale: 1 }}
                        exit={{ opacity: 0, y: 4, scale: 0.95 }}
                        transition={{ duration: 0.15 }}
                        className="absolute bottom-full left-0 mb-2 w-64 p-3 bg-white rounded-xl shadow-xl border border-stone-200/60 z-50 text-left pointer-events-none"
                    >
                        <div className="flex items-center gap-2 mb-2 pb-2 border-b border-stone-100">
                            <Icon className={clsx("w-4 h-4", activeConfig.color)} />
                            <span className={clsx("text-xs font-semibold", activeConfig.color)}>
                                {activeConfig.label}
                            </span>
                        </div>

                        <div className="space-y-1.5">
                            <div className="flex justify-between text-xs">
                                <span className="text-stone-500">Antal källor:</span>
                                <span className="font-mono text-stone-700">{sourceCount}</span>
                            </div>
                            <div className="flex justify-between text-xs">
                                <span className="text-stone-500">Snittrelevans:</span>
                                <span className="font-mono text-stone-700">
                                    {avgScore.toFixed(2)}
                                </span>
                            </div>
                            <div className="mt-2 text-[10px] text-stone-400 leading-tight">
                                Bedömning baserad på källornas kvalitet och relevans för frågan.
                            </div>
                        </div>

                        {/* Arrow */}
                        <div className="absolute bottom-[-5px] left-4 w-2.5 h-2.5 bg-white border-b border-r border-stone-200/60 transform rotate-45" />
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};
