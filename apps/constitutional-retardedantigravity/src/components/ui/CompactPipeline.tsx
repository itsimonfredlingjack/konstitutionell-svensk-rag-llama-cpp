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
import { EVIDENCE_COLORS, DEFAULT_STAGE_COLORS } from "../../theme/colors";

const stages: { id: PipelineStage; label: string; icon: LucideIcon }[] = [
    { id: "query_classification", label: "Tolka", icon: Brain },
    { id: "decontextualization", label: "Förenkla", icon: RefreshCw },
    { id: "retrieval", label: "Sök", icon: Database },
    { id: "grading", label: "Bedöm", icon: Filter },
    { id: "self_reflection", label: "Granska", icon: Lightbulb },
    { id: "generation", label: "Generera", icon: Sparkles },
    { id: "guardrail_validation", label: "Validera", icon: ShieldCheck },
];

// Minimum time each stage should display (ms) - snappier feel
const MIN_STAGE_DISPLAY_MS = 250;

interface CompactPipelineProps {
    queryResult: QueryResult;
}

export const CompactPipeline: React.FC<CompactPipelineProps> = ({
    queryResult,
}) => {
    const [isExpanded, setIsExpanded] = useState(false);

    // Track which stage is selected for detailed view. Null means default view (all/recent logs).
    const [activeDetailStage, setActiveDetailStage] = useState<PipelineStage | null>(null);

    const { searchStage, pipelineStage, pipelineLog, error, evidenceLevel } = queryResult;

    const isIdle = searchStage === "idle";
    const isComplete = searchStage === "complete";
    const isError = searchStage === "error";

    // Resolve accent colors based on evidence level
    const stageColors = useMemo(() => {
        const level = evidenceLevel as keyof typeof EVIDENCE_COLORS | null;
        if (level && EVIDENCE_COLORS[level]) return EVIDENCE_COLORS[level];
        return DEFAULT_STAGE_COLORS;
    }, [evidenceLevel]);

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
            setActiveDetailStage(null);
            setIsExpanded(false);
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

    // Filter logs based on selection
    const visibleLogs = useMemo(() => {
        if (activeDetailStage) {
            return pipelineLog.filter(l => l.stage === activeDetailStage);
        }
        return pipelineLog.slice(-8);
    }, [pipelineLog, activeDetailStage]);

    const handleStageClick = (e: React.MouseEvent, stageId: PipelineStage) => {
        e.stopPropagation(); // Prevent toggling the main drawer if we click a specific stage
        if (activeDetailStage === stageId) {
            // Toggle off if clicking same
            setActiveDetailStage(null);
            setIsExpanded(false);
        } else {
            setActiveDetailStage(stageId);
            setIsExpanded(true); // Auto-open drawer to show details
        }
    };

    if (isIdle) return null;

    return (
        <div className="w-full">
            {/* Compact bar */}
            <div
                className={clsx(
                    "w-full rounded-xl border px-4 py-2.5 flex items-center gap-3",
                    "bg-stone-100/60 backdrop-blur-sm",
                    "border-stone-300/50 transition-colors",
                    "select-none"
                )}
            >
                {/* Progress indicator */}
                <div className="relative w-full flex items-center gap-1.5">
                    {stages.map((stage, index) => {
                        const isBefore = completedStages.has(index);
                        const isCurrent = index === currentDisplayStage;
                        const isDone = isComplete || isBefore;
                        const isFailed = isError && isCurrent;
                        const isActiveDetail = activeDetailStage === stage.id;
                        const Icon = stage.icon;

                        return (
                            <motion.button
                                key={stage.id}
                                onClick={(e) => handleStageClick(e, stage.id)}
                                className={clsx(
                                    "flex-1 flex flex-col items-center justify-center gap-1 cursor-pointer group",
                                    "min-h-[44px] min-w-[44px] sm:min-w-0 rounded-lg py-1 transition-colors hover:bg-stone-200/50",
                                    "focus-ring",
                                    isActiveDetail && "bg-stone-200/80 ring-1 ring-stone-300"
                                )}
                                initial={false}
                                animate={{
                                    scale: isCurrent && runState === "running" ? 1.05 : 1,
                                }}
                                transition={{ duration: 0.15 }}
                            >
                                <motion.div
                                    className={clsx(
                                        "w-6 h-6 rounded-full flex items-center justify-center relative",
                                        "border transition-colors duration-300"
                                    )}
                                    initial={false}
                                    animate={{
                                        backgroundColor: isDone
                                            ? stageColors.bgRgba
                                            : isCurrent && !isFailed
                                                ? "rgba(250, 250, 249, 1)"
                                                : isFailed
                                                    ? "rgba(254, 242, 242, 1)"
                                                    : "rgba(231, 229, 228, 0.5)",
                                        borderColor: isDone
                                            ? stageColors.borderRgba
                                            : isCurrent && !isFailed
                                                ? stageColors.activeRgba
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
                                                    className={clsx("w-3 h-3", stageColors.text)}
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
                                                    className={clsx("w-3 h-3 animate-spin", stageColors.text)}
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
                                                    className="w-3 h-3 text-text-muted group-hover:text-stone-600 transition-colors"
                                                    strokeWidth={1.5}
                                                />
                                            </motion.div>
                                        )}
                                    </AnimatePresence>
                                </motion.div>
                                <span
                                    className={clsx(
                                        "text-[9px] font-mono uppercase tracking-wide transition-colors duration-300",
                                        "hidden sm:inline",
                                        isDone
                                            ? stageColors.text
                                            : isCurrent
                                                ? "text-stone-700 font-semibold"
                                                : "text-text-muted group-hover:text-stone-600"
                                    )}
                                >
                                    {stage.label}
                                </span>
                            </motion.button>
                        );
                    })}
                </div>

                {/* Expand indicator (General click to toggle drawer) */}
                <div
                    className="flex items-center gap-2 shrink-0 ml-2 cursor-pointer hover:opacity-70 transition-opacity"
                    onClick={() => {
                        setIsExpanded(!isExpanded);
                        setActiveDetailStage(null); // Reset detail filter when toggling general view
                    }}
                >
                    <motion.span
                        key={runState}
                        initial={{ opacity: 0, y: -4 }}
                        animate={{ opacity: 1, y: 0 }}
                        className={clsx(
                            "text-[10px] font-mono uppercase tracking-wider",
                            runState === "error"
                                ? "text-red-600"
                                : runState === "complete"
                                    ? stageColors.text
                                    : "text-text-muted"
                        )}
                    >
                        {runState === "error"
                            ? "FEL"
                            : runState === "complete"
                                ? "KLART"
                                : <><span className="sm:hidden">{stages[currentDisplayStage]?.label} </span>{`${Math.round(progressPercent)}%`}</>}
                    </motion.span>
                    <ChevronDown
                        className={clsx(
                            "w-3.5 h-3.5 text-text-muted transition-transform",
                            isExpanded && "rotate-180"
                        )}
                        strokeWidth={1.5}
                    />
                </div>
            </div>

            {/* Expanded logs drawer */}
            <AnimatePresence initial={false}>
                {isExpanded && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: "auto", opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.15 }}
                        className="overflow-hidden"
                    >
                        <div className="mt-2 rounded-xl border border-stone-300/50 bg-stone-100/50 px-4 py-3 max-h-48 overflow-y-auto">
                            {/* Header for detail view */}
                            {activeDetailStage && (
                                <div className="flex items-center justify-between mb-2 pb-2 border-b border-stone-200/50">
                                    <span className="text-xs font-semibold text-stone-700 uppercase tracking-wider font-mono">
                                        Detaljer: {stages.find(s => s.id === activeDetailStage)?.label}
                                    </span>
                                    <button
                                        onClick={() => setActiveDetailStage(null)}
                                        className="text-[10px] text-text-muted hover:text-stone-600 focus-ring rounded px-1"
                                    >
                                        RENSA FILTER
                                    </button>
                                </div>
                            )}

                            {error && (
                                <div className="text-sm text-red-700 font-mono mb-2">
                                    Fel: {error}
                                </div>
                            )}
                            {visibleLogs.length === 0 ? (
                                <div className="text-sm text-text-muted font-mono">
                                    {activeDetailStage ? "Inga loggar för detta steg." : "Inga loggar än."}
                                </div>
                            ) : (
                                <div className="space-y-1">
                                    {visibleLogs.map((log, i) => (
                                        <div
                                            key={`${log.ts}-${i}`}
                                            className="text-xs text-stone-600 font-mono"
                                        >
                                            <span className="text-text-muted">
                                                {new Date(log.ts).toLocaleTimeString("sv-SE", {
                                                    hour: "2-digit",
                                                    minute: "2-digit",
                                                    second: "2-digit"
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
