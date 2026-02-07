import React, { useMemo, useState, useEffect, useRef } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
    Brain,
    RefreshCw,
    Database,
    Sparkles,
    ShieldCheck,
    ChevronDown,
    Check,
    XCircle,
    Loader2,
    Filter,
    Lightbulb,
    type LucideIcon,
} from "lucide-react";
import clsx from "clsx";
import type { QueryResult } from "../../types/queryResult";
import type { PipelineStage } from "../../stores/useAppStore";

const stages: { id: PipelineStage; label: string; icon: LucideIcon }[] = [
    { id: "query_classification", label: "Classify", icon: Brain },
    { id: "decontextualization", label: "Decontext", icon: RefreshCw },
    { id: "retrieval", label: "Retrieval", icon: Database },
    { id: "grading", label: "Grade", icon: Filter },
    { id: "self_reflection", label: "Reflect", icon: Lightbulb },
    { id: "generation", label: "Generate", icon: Sparkles },
    { id: "guardrail_validation", label: "Validate", icon: ShieldCheck },
];

// Minimum time each stage should display (ms) for visual smoothness
const MIN_STAGE_DISPLAY_MS = 400;

interface CompactPipelineProps {
    queryResult: QueryResult;
}

export const CompactPipeline: React.FC<CompactPipelineProps> = ({
    queryResult,
}) => {
    const [isExpanded, setIsExpanded] = useState(false);
    const { searchStage, pipelineStage, pipelineLog, error } = queryResult;

    const isIdle = searchStage === "idle";
    const isComplete = searchStage === "complete";
    const isError = searchStage === "error";

    // Calculate actual stage index from backend
    const actualStageIndex = useMemo(() => {
        if (isComplete || pipelineStage === "idle") return stages.length - 1;
        const idx = stages.findIndex((s) => s.id === pipelineStage);
        return idx >= 0 ? idx : 0;
    }, [pipelineStage, isComplete]);

    // Track completed stages to avoid race conditions
    const [completedStages, setCompletedStages] = useState<Set<number>>(new Set());
    const [currentDisplayStage, setCurrentDisplayStage] = useState(0);
    const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const queryIdRef = useRef(queryResult.id);

    // Reset when query changes
    useEffect(() => {
        if (queryIdRef.current !== queryResult.id) {
            queryIdRef.current = queryResult.id;
            setCompletedStages(new Set());
            setCurrentDisplayStage(0);
        }
    }, [queryResult.id]);

    // Handle stage progression with minimum display time
    useEffect(() => {
        // Clear any pending timer
        if (timerRef.current) {
            clearTimeout(timerRef.current);
            timerRef.current = null;
        }

        // If complete, mark ALL stages as done
        if (isComplete) {
            const allStages = new Set(stages.map((_, i) => i));
            setCompletedStages(allStages);
            setCurrentDisplayStage(stages.length - 1);
            return;
        }

        // If error, mark stages up to current as done
        if (isError) {
            const doneStages = new Set<number>();
            for (let i = 0; i < actualStageIndex; i++) {
                doneStages.add(i);
            }
            setCompletedStages(doneStages);
            setCurrentDisplayStage(actualStageIndex);
            return;
        }

        // Progressive animation: step through stages one at a time
        if (currentDisplayStage < actualStageIndex) {
            timerRef.current = setTimeout(() => {
                setCompletedStages(prev => new Set([...prev, currentDisplayStage]));
                setCurrentDisplayStage(prev => prev + 1);
            }, MIN_STAGE_DISPLAY_MS);
        } else if (currentDisplayStage === actualStageIndex && actualStageIndex > 0) {
            // Mark previous stage as complete when we move to a new one
            setCompletedStages(prev => {
                const next = new Set(prev);
                for (let i = 0; i < actualStageIndex; i++) {
                    next.add(i);
                }
                return next;
            });
        }

        return () => {
            if (timerRef.current) {
                clearTimeout(timerRef.current);
            }
        };
    }, [actualStageIndex, currentDisplayStage, isComplete, isError]);

    const runState: "running" | "complete" | "error" = useMemo(() => {
        if (isError) return "error";
        if (isComplete) return "complete";
        return "running";
    }, [isComplete, isError]);

    const progressPercent = ((currentDisplayStage + 1) / stages.length) * 100;

    const visibleLogs = useMemo(() => {
        return pipelineLog.slice(-8);
    }, [pipelineLog]);

    if (isIdle) return null;

    return (
        <div className="w-full">
            {/* Compact bar */}
            <button
                type="button"
                onClick={() => setIsExpanded(!isExpanded)}
                className={clsx(
                    "w-full rounded-xl border px-4 py-2.5 flex items-center gap-3",
                    "bg-stone-100/60 backdrop-blur-sm",
                    "border-stone-300/50 hover:border-stone-400/60 transition-colors",
                    "cursor-pointer select-none"
                )}
            >
                {/* Progress indicator */}
                <div className="relative w-full flex items-center gap-1.5">
                    {stages.map((stage, index) => {
                        const isBefore = completedStages.has(index);
                        const isCurrent = index === currentDisplayStage;
                        const isDone = isComplete || isBefore;
                        const isFailed = isError && isCurrent;
                        const Icon = stage.icon;

                        return (
                            <motion.div
                                key={stage.id}
                                className="flex-1 flex flex-col items-center gap-1"
                                initial={false}
                                animate={{
                                    scale: isCurrent && runState === "running" ? 1.05 : 1,
                                }}
                                transition={{ duration: 0.2 }}
                            >
                                <motion.div
                                    className={clsx(
                                        "w-6 h-6 rounded-full flex items-center justify-center relative",
                                        "border transition-colors duration-300"
                                    )}
                                    initial={false}
                                    animate={{
                                        backgroundColor: isDone
                                            ? "rgba(15, 118, 110, 0.15)"
                                            : isCurrent && !isFailed
                                                ? "rgba(250, 250, 249, 1)"
                                                : isFailed
                                                    ? "rgba(254, 242, 242, 1)"
                                                    : "rgba(231, 229, 228, 0.5)",
                                        borderColor: isDone
                                            ? "rgba(15, 118, 110, 0.4)"
                                            : isCurrent && !isFailed
                                                ? "rgba(15, 118, 110, 0.6)"
                                                : isFailed
                                                    ? "rgba(239, 68, 68, 0.5)"
                                                    : "rgba(168, 162, 158, 0.4)",
                                    }}
                                    transition={{ duration: 0.3 }}
                                >
                                    <AnimatePresence mode="wait">
                                        {isDone ? (
                                            <motion.div
                                                key="done"
                                                initial={{ scale: 0, opacity: 0 }}
                                                animate={{ scale: 1, opacity: 1 }}
                                                exit={{ scale: 0, opacity: 0 }}
                                                transition={{ duration: 0.2 }}
                                            >
                                                <Check
                                                    className="w-3 h-3 text-teal-700"
                                                    strokeWidth={2.5}
                                                />
                                            </motion.div>
                                        ) : isFailed ? (
                                            <motion.div
                                                key="failed"
                                                initial={{ scale: 0, opacity: 0 }}
                                                animate={{ scale: 1, opacity: 1 }}
                                            >
                                                <XCircle
                                                    className="w-3 h-3 text-red-600"
                                                    strokeWidth={2}
                                                />
                                            </motion.div>
                                        ) : isCurrent ? (
                                            <motion.div
                                                key="current"
                                                initial={{ scale: 0, opacity: 0 }}
                                                animate={{ scale: 1, opacity: 1 }}
                                                exit={{ scale: 0, opacity: 0 }}
                                                transition={{ duration: 0.2 }}
                                            >
                                                <Loader2
                                                    className="w-3 h-3 text-teal-700 animate-spin"
                                                    strokeWidth={2}
                                                />
                                            </motion.div>
                                        ) : (
                                            <motion.div
                                                key="pending"
                                                initial={{ opacity: 0 }}
                                                animate={{ opacity: 1 }}
                                            >
                                                <Icon
                                                    className="w-3 h-3 text-stone-400"
                                                    strokeWidth={1.5}
                                                />
                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                </motion.div>
                                <span
                                    className={clsx(
                                        "text-[9px] font-mono uppercase tracking-wide transition-colors duration-300",
                                        isDone
                                            ? "text-teal-700"
                                            : isCurrent
                                                ? "text-stone-700 font-semibold"
                                                : "text-stone-400"
                                    )}
                                >
                                    {stage.label}
                                </span>
                            </motion.div>
                        );
                    })}
                </div>

                {/* Expand indicator */}
                <div className="flex items-center gap-2 flex-shrink-0 ml-2">
                    <motion.span
                        key={runState}
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        className={clsx(
                            "text-[10px] font-mono uppercase tracking-wider",
                            runState === "error"
                                ? "text-red-600"
                                : runState === "complete"
                                    ? "text-teal-700"
                                    : "text-stone-500"
                        )}
                    >
                        {runState === "error"
                            ? "ERROR"
                            : runState === "complete"
                                ? "DONE"
                                : `${Math.round(progressPercent)}%`}
                    </motion.span>
                    <ChevronDown
                        className={clsx(
                            "w-3.5 h-3.5 text-stone-400 transition-transform",
                            isExpanded && "rotate-180"
                        )}
                        strokeWidth={1.5}
                    />
                </div>
            </button>

            {/* Expanded logs drawer */}
            <AnimatePresence initial={false}>
                {isExpanded && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        className="overflow-hidden"
                    >
                        <div className="mt-2 rounded-xl border border-stone-300/50 bg-stone-100/50 px-4 py-3 max-h-48 overflow-y-auto">
                            {error && (
                                <div className="text-sm text-red-700 font-mono mb-2">
                                    Error: {error}
                                </div>
                            )}
                            {visibleLogs.length === 0 ? (
                                <div className="text-sm text-stone-500 font-mono">
                                    No logs yet.
                                </div>
                            ) : (
                                <div className="space-y-1">
                                    {visibleLogs.map((log, i) => (
                                        <div
                                            key={`${log.ts}-${i}`}
                                            className="text-xs text-stone-600 font-mono"
                                        >
                                            <span className="text-stone-400">
                                                {new Date(log.ts).toLocaleTimeString("sv-SE", {
                                                    hour: "2-digit",
                                                    minute: "2-digit",
                                                    second: "2-digit",
                                                })}
                                            </span>{" "}
                                            {log.message}
                                        </div>
                                    ))}
                                </div>
                            )}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
};
