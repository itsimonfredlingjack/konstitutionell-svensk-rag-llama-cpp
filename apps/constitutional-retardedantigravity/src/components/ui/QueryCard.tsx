import { motion } from "framer-motion";
import {
  Shield,
  BookOpen,
  GitCompare,
  ChevronUp,
  Zap,
  ShieldAlert,
} from "lucide-react";
import { useMemo, type MouseEvent } from "react";
import type { QueryResult } from "../../types/queryResult";
import { useAppStore } from "../../stores/useAppStore";
import type { EvidenceLevel } from "../../stores/useAppStore";
import { PipelineVisualizer } from "./PipelineVisualizer";
import { QueryBar } from "./QueryBar";
import { AnswerWithCitations } from "./AnswerWithCitations";
import { ThoughtChain } from "./ThoughtChain";

function formatRelativeTime(ts: number): string {
  const d = Date.now() - ts;
  if (d < 60_000) return "nyss";
  if (d < 3600_000) return `${Math.floor(d / 60_000)} min sedan`;
  if (d < 86400_000) return `${Math.floor(d / 3600_000)} h sedan`;
  return `${Math.floor(d / 86400_000)} d sedan`;
}

const MODE_ICONS = {
  verify: Shield,
  summarize: BookOpen,
  compare: GitCompare,
} as const;

const EvidenceLevelInline = ({ level }: { level: EvidenceLevel }) => {
  if (!level) return null;
  const config = {
    HIGH: { icon: Shield, text: "text-emerald-700" },
    MEDIUM: { icon: Shield, text: "text-amber-700" },
    LOW: { icon: ShieldAlert, text: "text-red-700" },
  }[level];
  if (!config) return null;
  const Icon = config.icon;
  return (
    <div className="flex items-center gap-1.5">
      <Icon className={`w-3.5 h-3.5 ${config.text}`} strokeWidth={1.5} />
      <span
        className={`text-[11px] font-mono uppercase tracking-wider ${config.text}`}
      >
        Evidence: {level}
      </span>
    </div>
  );
};

export interface QueryCardProps {
  queryResult: QueryResult;
  isActive: boolean;
  isCollapsed: boolean;
  isFocused: boolean;
  onToggleCollapse: () => void;
  onFocus: () => void;
  onOpenHistory?: () => void;
}

const COLLAPSED_TLDR_LEN = 100;

export function QueryCard({
  queryResult,
  isActive,
  isCollapsed,
  isFocused,
  onToggleCollapse,
  onFocus,
  onOpenHistory,
}: QueryCardProps) {
  const { id, query, mode, answer, sources, searchStage, evidenceLevel } =
    queryResult;
  const activeQueryId = useAppStore((s) => s.activeQueryId);
  const updateQueryResult = useAppStore((s) => s.updateQueryResult);

  const ModeIcon = MODE_ICONS[mode];
  const tldr = useMemo(() => {
    const t = answer.trim();
    if (!t) return "—";
    return t.length <= COLLAPSED_TLDR_LEN
      ? t
      : t.slice(0, COLLAPSED_TLDR_LEN) + "…";
  }, [answer]);

  const handleCardClick = () => {
    if (isCollapsed) {
      onToggleCollapse();
      onFocus();
    }
  };

  if (isCollapsed) {
    return (
      <motion.button
        type="button"
        layout
        initial={false}
        onClick={handleCardClick}
        className="w-full text-left rounded-2xl border border-stone-300/60 bg-stone-50/55 backdrop-blur-xl px-5 py-3 flex items-center gap-4 hover:bg-stone-100/60 hover:border-stone-400/50 transition-colors"
      >
        <div className="flex-shrink-0 w-9 h-9 rounded-xl bg-stone-200/60 flex items-center justify-center">
          <ModeIcon className="w-4 h-4 text-stone-700" strokeWidth={1.5} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="text-[13px] font-medium text-stone-900 truncate">
            {query}
          </div>
          <div className="text-[11px] text-stone-500 truncate mt-0.5">
            {tldr}
          </div>
        </div>
        <div className="flex-shrink-0 flex items-center gap-3 text-[11px] font-mono text-stone-500">
          <span>{sources.length} källor</span>
          <span>{formatRelativeTime(queryResult.timestamp)}</span>
        </div>
      </motion.button>
    );
  }

  const pipelineProps = {
    isActive: isActive && activeQueryId === id,
    searchStage: queryResult.searchStage,
    pipelineStage: queryResult.pipelineStage,
    pipelineLog: queryResult.pipelineLog,
    selectedPipelineStage: queryResult.selectedPipelineStage,
    isPipelineDrawerOpen: queryResult.isPipelineDrawerOpen,
    error: queryResult.error,
    onSelectStage: (stage: string) =>
      updateQueryResult(id, { selectedPipelineStage: stage }),
    onToggleDrawer: (force?: boolean) =>
      updateQueryResult(id, {
        isPipelineDrawerOpen:
          typeof force === "boolean"
            ? force
            : !queryResult.isPipelineDrawerOpen,
      }),
  };

  const handleExpandedClick = (e: MouseEvent<HTMLElement>): void => {
    const target = e.target as HTMLElement | null;
    if (
      target?.closest(
        "button, a, input, textarea, [role='button'], [data-ignore-focus]",
      )
    ) {
      return;
    }
    onFocus();
  };

  return (
    <motion.article
      layout
      initial={false}
      onClick={handleExpandedClick}
      className={`rounded-2xl border bg-stone-50/55 backdrop-blur-2xl flex flex-col ${
        isFocused
          ? "border-teal-700/40 ring-1 ring-teal-700/20"
          : "border-stone-300/60"
      }`}
    >
      <div className="px-6 pt-6 pb-4">
        <div className="flex items-center justify-end mb-2">
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onToggleCollapse();
            }}
            className="p-2 rounded-lg text-stone-500 hover:text-stone-800 hover:bg-stone-200/40 transition-colors"
            aria-label="Kollapsa"
          >
            <ChevronUp className="w-4 h-4" strokeWidth={1.5} />
          </button>
        </div>
        <PipelineVisualizer {...pipelineProps} />
      </div>

      <div className="h-px bg-stone-200/70" />
      <div className="px-6 py-4">
        <QueryBar
          queryText={queryResult.query}
          mode={queryResult.mode}
          onOpenHistory={onOpenHistory}
        />
      </div>

      <div className="h-px bg-stone-200/70" />
      <div className="px-8 py-7 flex flex-col">
        <div className="mb-7 pb-5 border-b border-stone-200/70">
          <div className="flex items-start justify-between gap-6">
            <div>
              <h2 className="text-[22px] font-semibold text-stone-900 tracking-tight">
                ANALYSIS RESULTS
              </h2>
              <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-[11px] text-stone-500 font-mono">
                {evidenceLevel && (
                  <EvidenceLevelInline level={evidenceLevel as EvidenceLevel} />
                )}
              </div>
            </div>
          </div>
        </div>

        {searchStage === "searching" && (
          <div className="flex items-center gap-3 text-stone-700 font-mono text-sm">
            <Zap className="w-4 h-4 text-stone-700" strokeWidth={1.5} />
            <span className="animate-pulse">Running pipeline…</span>
          </div>
        )}

        {searchStage === "error" && (
          <div className="flex items-center gap-3 text-red-700 font-mono text-sm">
            <ShieldAlert className="w-4 h-4" strokeWidth={1.5} />
            <span>Ett fel uppstod.</span>
          </div>
        )}

        {(searchStage === "reading" || searchStage === "complete") && (
          <div className="relative z-10">
            <ThoughtChain
              thought={(queryResult.thoughtChain as string | null) ?? null}
            />
            {answer ? (
              <div
                className="text-stone-900 font-sans text-[15px]"
                style={{ lineHeight: "1.85" }}
              >
                <AnswerWithCitations answer={answer} sources={sources} />
              </div>
            ) : (
              <div className="text-stone-500 italic flex items-center gap-2">
                <span className="w-2 h-2 bg-stone-400 rounded-full animate-pulse" />
                Waiting for stream…
              </div>
            )}
          </div>
        )}
      </div>
    </motion.article>
  );
}
