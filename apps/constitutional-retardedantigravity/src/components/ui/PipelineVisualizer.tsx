import React from "react";
import { useAppStore } from "../../stores/useAppStore";
import type { PipelineStage } from "../../stores/useAppStore";
import { STEP_TIMER_MS } from "../../constants";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useMemo, useRef, useState } from "react";
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

const stages: { id: PipelineStage; label: string; icon: LucideIcon }[] = [
  { id: "query_classification", label: "Classify", icon: Brain },
  { id: "decontextualization", label: "Decontext", icon: RefreshCw },
  { id: "retrieval", label: "Retrieval", icon: Database },
  { id: "grading", label: "Grade", icon: Filter },
  { id: "self_reflection", label: "Reflect", icon: Lightbulb },
  { id: "generation", label: "Generate", icon: Sparkles },
  { id: "guardrail_validation", label: "Validate", icon: ShieldCheck },
];

const stageMessages: Record<PipelineStage, string> = {
  idle: "",
  query_classification: "Classify: analyzing intent…",
  decontextualization: "Decontext: rewriting query…",
  retrieval: "Retrieval: fetching sources…",
  grading: "Grade: verifying relevance…",
  self_reflection: "Reflect: planning response…",
  generation: "Generate: composing answer…",
  guardrail_validation: "Validate: checking output…",
};

const runStateLabel: Record<"running" | "complete" | "error", string> = {
  running: "RUNNING",
  complete: "COMPLETE",
  error: "ERROR",
};

export interface PipelineVisualizerProps {
  isActive?: boolean;
  searchStage?: string;
  pipelineStage?: string;
  pipelineLog?: Array<{ ts: number; stage: string; message: string }>;
  selectedPipelineStage?: string | null;
  isPipelineDrawerOpen?: boolean;
  error?: string | null;
  onSelectStage?: (stage: string) => void;
  onToggleDrawer?: (force?: boolean) => void;
}

export const PipelineVisualizer: React.FC<PipelineVisualizerProps> = (
  props,
) => {
  const queries = useAppStore((state) => state.queries);
  const activeQueryId = useAppStore((state) => state.activeQueryId);
  const storeSetSelectedPipelineStage = useAppStore(
    (state) => state.setSelectedPipelineStage,
  );
  const storeTogglePipelineDrawer = useAppStore(
    (state) => state.togglePipelineDrawer,
  );
  const updateQueryResult = useAppStore((state) => state.updateQueryResult);

  const activeFromStore = activeQueryId
    ? queries.find((q) => q.id === activeQueryId)
    : null;

  const hasProps =
    props.searchStage !== undefined || props.pipelineStage !== undefined;
  const pipelineStage =
    (hasProps ? props.pipelineStage : activeFromStore?.pipelineStage) ?? "idle";
  const searchStage =
    (hasProps ? props.searchStage : activeFromStore?.searchStage) ?? "idle";
  const error = hasProps
    ? (props.error ?? null)
    : (activeFromStore?.error ?? null);
  const selectedPipelineStage = hasProps
    ? (props.selectedPipelineStage ?? "query_classification")
    : (activeFromStore?.selectedPipelineStage ?? "query_classification");
  const isPipelineDrawerOpen = hasProps
    ? (props.isPipelineDrawerOpen ?? false)
    : (activeFromStore?.isPipelineDrawerOpen ?? false);
  const pipelineLog = hasProps
    ? (props.pipelineLog ?? [])
    : (activeFromStore?.pipelineLog ?? []);

  const isActive = props.isActive !== false;
  const setSelectedPipelineStage =
    props.onSelectStage && hasProps
      ? props.onSelectStage
      : (stage: string) => {
          if (activeQueryId)
            updateQueryResult(activeQueryId, { selectedPipelineStage: stage });
          else storeSetSelectedPipelineStage(stage as PipelineStage);
        };
  const togglePipelineDrawer =
    props.onToggleDrawer && hasProps
      ? props.onToggleDrawer
      : (force?: boolean) => {
          if (activeQueryId && activeFromStore)
            updateQueryResult(activeQueryId, {
              isPipelineDrawerOpen:
                typeof force === "boolean"
                  ? force
                  : !activeFromStore.isPipelineDrawerOpen,
            });
          else storeTogglePipelineDrawer(force);
        };

  const isIdle = searchStage === "idle";

  // Determine active index for progress bar
  const runningStage: PipelineStage =
    pipelineStage === "idle"
      ? "guardrail_validation"
      : (pipelineStage as PipelineStage);
  const activeIndex = stages.findIndex((s) => s.id === runningStage);

  const selectedIndex = stages.findIndex((s) => s.id === selectedPipelineStage);
  const progressPct =
    selectedIndex >= 0
      ? `${(selectedIndex / (stages.length - 1)) * 100}%`
      : "0%";

  const runState = useMemo<"running" | "complete" | "error">(() => {
    if (!isActive) return "complete";
    if (searchStage === "error") return "error";
    if (searchStage === "complete") return "complete";
    return "running";
  }, [searchStage, isActive]);

  // Display smoothing: if backend jumps quickly, we still animate through steps so the process is legible.
  const [displayIndex, setDisplayIndex] = useState(() =>
    !isActive ? stages.length - 1 : Math.max(0, activeIndex),
  );
  const stepTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (stepTimerRef.current) clearTimeout(stepTimerRef.current);
    if (!isActive) {
      setDisplayIndex(stages.length - 1);
      return;
    }
    if (runState === "complete") {
      setDisplayIndex(stages.length - 1);
      return;
    }

    // On error, snap to current (and mark failed visually).
    if (runState === "error") {
      setDisplayIndex(Math.max(0, activeIndex));
      return;
    }

    // Running: step forward gradually if we need to catch up.
    const target = Math.max(0, activeIndex);
    setDisplayIndex((prev) => {
      if (prev > target) return target;
      return prev;
    });

    if (displayIndex < target) {
      stepTimerRef.current = setTimeout(() => {
        setDisplayIndex((prev) => Math.min(prev + 1, target));
      }, STEP_TIMER_MS);
    }

    return () => {
      if (stepTimerRef.current) clearTimeout(stepTimerRef.current);
    };
  }, [isActive, activeIndex, runState, stages.length, displayIndex]);

  const displayStage =
    stages[Math.max(0, Math.min(displayIndex, stages.length - 1))]?.id;

  // Keep selected stage following the active stage unless the drawer is open (user exploring).
  useEffect(() => {
    if (isPipelineDrawerOpen) return;
    if (displayStage && selectedPipelineStage !== displayStage) {
      setSelectedPipelineStage(displayStage);
    }
  }, [
    isPipelineDrawerOpen,
    displayStage,
    selectedPipelineStage,
    setSelectedPipelineStage,
  ]);

  const visibleLog = useMemo(() => {
    return pipelineLog
      .filter((l) => l.stage === selectedPipelineStage)
      .slice(-5);
  }, [pipelineLog, selectedPipelineStage]);

  const effectiveStageForStatus = displayStage ?? runningStage;

  const statusText =
    searchStage === "error"
      ? `Error: ${error || "Unknown error"}`
      : searchStage === "complete"
        ? "Complete: answer ready"
        : stageMessages[effectiveStageForStatus];

  const percent = Math.round((displayIndex / (stages.length - 1)) * 100);

  if (isIdle) return null;

  return (
    <div
      className={clsx(
        "w-full rounded-2xl border bg-gradient-to-b backdrop-blur-xl px-7 py-6",
        "from-stone-50/70 to-stone-100/45",
        "border-stone-300/70 ring-1 ring-stone-900/5",
        "shadow-[0_10px_30px_rgba(0,0,0,0.06)]",
      )}
    >
      {/* Subtle top accent (helps the eye find the panel) */}
      <div className="h-[2px] w-full rounded-full bg-teal-700/25 mb-4" />

      {/* Small header row */}
      <div className="flex items-center justify-between mb-3">
        <div className="text-[11px] font-mono uppercase tracking-wider text-stone-600">
          PIPELINE
        </div>
        <div
          className={clsx(
            "text-[11px] font-mono uppercase tracking-wider",
            runState === "error"
              ? "text-red-700"
              : runState === "complete"
                ? "text-teal-800"
                : "text-stone-500",
          )}
        >
          {runStateLabel[runState]} • {percent}%
        </div>
      </div>

      {/* Top row: stages */}
      <div className="relative">
        {/* Connector baseline */}
        <div
          className={clsx(
            "absolute left-0 top-[18px] w-full h-[3px] rounded-full pointer-events-none -z-10",
            runState === "error" ? "bg-red-500/25" : "bg-stone-300/70",
          )}
        />

        {/* Active Progress Bar */}
        <motion.div
          className={clsx(
            "absolute left-0 top-[18px] h-[3px] rounded-full pointer-events-none -z-10",
            runState === "error" ? "bg-red-600/80" : "bg-teal-700/85",
          )}
          initial={{ width: "0%" }}
          animate={{
            width:
              displayIndex >= 0
                ? `${(displayIndex / (stages.length - 1)) * 100}%`
                : "0%",
          }}
          transition={{ duration: 0.65, ease: "easeOut" }}
        />

        {/* Progress glow (subtle, material-like) */}
        <motion.div
          aria-hidden="true"
          className={clsx(
            "absolute left-0 top-[18px] h-[12px] -translate-y-1/2 blur-md rounded-full pointer-events-none -z-10",
            runState === "error" ? "bg-red-600/35" : "bg-teal-700/35",
          )}
          initial={{ width: "0%" }}
          animate={{
            width:
              displayIndex >= 0
                ? `${(displayIndex / (stages.length - 1)) * 100}%`
                : "0%",
          }}
          transition={{ duration: 0.65, ease: "easeOut" }}
        />

        {/* Energy flow shimmer (only while running) */}
        {runState === "running" && (
          <motion.div
            aria-hidden="true"
            className="absolute left-0 top-[18px] h-[3px] rounded-full overflow-hidden pointer-events-none -z-10"
            style={{
              width:
                displayIndex >= 0
                  ? `${(displayIndex / (stages.length - 1)) * 100}%`
                  : "0%",
            }}
          >
            <motion.div
              className="h-full w-full"
              style={{
                backgroundImage:
                  "linear-gradient(90deg, rgba(15,118,110,0) 0%, rgba(15,118,110,0.55) 45%, rgba(15,118,110,0) 80%)",
                backgroundSize: "200% 100%",
              }}
              animate={{ backgroundPositionX: ["0%", "200%"] }}
              transition={{ repeat: Infinity, duration: 1.1, ease: "linear" }}
            />
          </motion.div>
        )}

        {/* Energy pulse (only while running) */}
        {runState === "running" && displayIndex >= 0 && (
          <>
            <motion.div
              aria-hidden="true"
              className="absolute top-[18px] -translate-y-1/2 w-7 h-7 rounded-full bg-teal-700/25 blur-md pointer-events-none"
              style={{
                left: `calc(${(displayIndex / (stages.length - 1)) * 100}% - 14px)`,
              }}
              animate={{ opacity: [0.25, 0.6, 0.25] }}
              transition={{
                repeat: Infinity,
                duration: 1.15,
                ease: "easeInOut",
              }}
            />
            <motion.div
              className="absolute top-[18px] -translate-y-1/2 w-3.5 h-3.5 rounded-full bg-teal-700 shadow-sm pointer-events-none"
              style={{
                left: `calc(${(displayIndex / (stages.length - 1)) * 100}% - 7px)`,
              }}
              animate={{
                scale: [1, 1.35, 1],
                opacity: [0.65, 1, 0.65],
              }}
              transition={{
                repeat: Infinity,
                duration: 1.05,
                ease: "easeInOut",
              }}
            />
          </>
        )}

        <div className="flex items-start justify-between gap-3">
          {stages.map((stage, index) => {
            const isBefore = displayIndex >= 0 && index < displayIndex;
            const isCurrent = index === displayIndex;
            const isSelected = stage.id === selectedPipelineStage;
            const Icon = stage.icon;

            const stepState: "pending" | "active" | "done" | "failed" =
              runState === "complete"
                ? "done"
                : runState === "error"
                  ? isCurrent
                    ? "failed"
                    : isBefore
                      ? "done"
                      : "pending"
                  : isCurrent
                    ? "active"
                    : isBefore
                      ? "done"
                      : "pending";

            return (
              <button
                key={stage.id}
                type="button"
                onClick={() => {
                  setSelectedPipelineStage(stage.id);
                  togglePipelineDrawer(true);
                }}
                className={clsx(
                  "group flex flex-col items-center gap-2 text-left select-none",
                  "focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-700/30 rounded-xl px-1",
                )}
              >
                <motion.div
                  className={clsx(
                    "relative rounded-full flex items-center justify-center border",
                    "transition-colors duration-200",
                    stepState === "active"
                      ? "bg-stone-50 border-teal-700/70 ring-2 ring-teal-700/25 shadow-sm"
                      : stepState === "done"
                        ? "bg-stone-50 border-stone-300/60"
                        : stepState === "failed"
                          ? "bg-stone-50 border-red-500/50 ring-2 ring-red-500/15"
                          : "bg-stone-100/60 border-stone-300/40",
                    isSelected && "outline outline-1 outline-stone-900/5",
                  )}
                  style={{
                    width: stepState === "active" ? 44 : 40,
                    height: stepState === "active" ? 44 : 40,
                  }}
                  animate={
                    stepState === "active"
                      ? { scale: [1, 1.08, 1] }
                      : { scale: 1 }
                  }
                  transition={{
                    repeat: stepState === "active" ? Infinity : (0 as number),
                    duration: 1.8,
                  }}
                >
                  <Icon
                    size={18}
                    className={clsx(
                      "text-stone-800",
                      stepState === "pending" && "opacity-70",
                      stepState === "done" && "opacity-80",
                      stepState === "failed" && "opacity-90",
                    )}
                    strokeWidth={1.5}
                  />

                  {stepState === "done" && (
                    <span className="absolute -right-1 -top-1 w-[18px] h-[18px] rounded-full bg-stone-100 border border-stone-300/70 flex items-center justify-center">
                      <Check
                        className="w-3.5 h-3.5 text-teal-700/80"
                        strokeWidth={2}
                      />
                    </span>
                  )}

                  {stepState === "failed" && (
                    <span className="absolute -right-1 -top-1 w-[18px] h-[18px] rounded-full bg-stone-100 border border-red-500/40 flex items-center justify-center">
                      <XCircle
                        className="w-3.5 h-3.5 text-red-600/90"
                        strokeWidth={1.8}
                      />
                    </span>
                  )}
                </motion.div>
                <span
                  className={clsx(
                    "text-xs font-mono uppercase tracking-wider",
                    stepState === "active"
                      ? "text-stone-900"
                      : stepState === "done"
                        ? "text-stone-700"
                        : stepState === "failed"
                          ? "text-red-700"
                          : "text-stone-400",
                  )}
                >
                  {stage.label}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Inline status row + drawer toggle */}
      <div className="mt-4 flex items-center justify-between gap-4">
        <motion.div
          key={`${searchStage}:${pipelineStage}:${displayIndex}`}
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          className={clsx(
            "text-sm font-mono truncate flex items-center gap-2",
            runState === "error" ? "text-red-700" : "text-stone-700",
          )}
        >
          {runState === "running" ? (
            <Loader2
              className="w-4 h-4 animate-spin opacity-70"
              strokeWidth={1.8}
            />
          ) : runState === "complete" ? (
            <Check className="w-4 h-4 text-teal-700/80" strokeWidth={2} />
          ) : (
            <XCircle className="w-4 h-4" strokeWidth={1.8} />
          )}
          <span className="truncate">{statusText}</span>
          <span className="text-[11px] text-stone-400 font-mono whitespace-nowrap">
            {Math.max(1, displayIndex + 1)}/{stages.length}
          </span>
        </motion.div>

        <button
          type="button"
          onClick={() => togglePipelineDrawer()}
          className={clsx(
            "flex items-center gap-2 text-[11px] font-mono uppercase tracking-wider",
            "text-stone-500 hover:text-stone-700 transition-colors",
          )}
        >
          <span>{isPipelineDrawerOpen ? "Hide" : "Details"}</span>
          <ChevronDown
            className={clsx(
              "w-3.5 h-3.5 transition-transform",
              isPipelineDrawerOpen ? "rotate-180" : "rotate-0",
            )}
            strokeWidth={1.5}
          />
        </button>
      </div>

      {/* Slim drawer (inline) */}
      <AnimatePresence initial={false}>
        {isPipelineDrawerOpen && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="mt-3 overflow-hidden"
          >
            <div className="rounded-xl border border-stone-300/50 bg-stone-100/50 px-5 py-4">
              {/* Selected stage progress hint */}
              <div className="flex items-center justify-between mb-2">
                <div className="text-[11px] font-mono uppercase tracking-wider text-stone-600">
                  {stages.find((s) => s.id === selectedPipelineStage)?.label}{" "}
                  Logs
                </div>
                <div className="w-28 h-2 rounded-full bg-stone-200 overflow-hidden">
                  <div
                    className="h-full bg-teal-700/50"
                    style={{ width: progressPct }}
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                {visibleLog.length === 0 ? (
                  <div className="text-sm text-stone-500 font-mono">
                    No logs yet.
                  </div>
                ) : (
                  visibleLog.map((l) => (
                    <div
                      key={`${l.ts}:${l.message}`}
                      className="text-sm text-stone-700 font-mono"
                    >
                      {l.message}
                    </div>
                  ))
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
};
