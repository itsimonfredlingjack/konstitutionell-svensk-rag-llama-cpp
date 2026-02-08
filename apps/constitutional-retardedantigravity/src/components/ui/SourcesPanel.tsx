import { AnimatePresence, motion } from "framer-motion";
import clsx from "clsx";
import { ChevronDown, FileSearch } from "lucide-react";
import { useMemo, useState } from "react";

import type { Source } from "../../stores/useAppStore";
import { useAppStore } from "../../stores/useAppStore";

// Load thresholds from env vars (default: 0.7, 0.5)
const SCORE_THRESHOLD_GOOD =
  Number(import.meta.env.VITE_SCORE_THRESHOLD_GOOD) || 0.7;
const SCORE_THRESHOLD_OK =
  Number(import.meta.env.VITE_SCORE_THRESHOLD_OK) || 0.5;

const getScoreColor = (score: number): string => {
  if (score >= SCORE_THRESHOLD_GOOD) return "bg-emerald-500";
  if (score >= SCORE_THRESHOLD_OK) return "bg-amber-500";
  return "bg-red-500/50"; // Röd/Grå för låg relevans
};

const getScoreBadgeColor = (score: number): string => {
  if (score >= SCORE_THRESHOLD_GOOD) return "text-emerald-700 bg-emerald-50";
  if (score >= SCORE_THRESHOLD_OK) return "text-amber-700 bg-amber-50";
  return "text-red-700 bg-red-50";
};

const getScoreLabel = (score: number): string => {
  if (score >= SCORE_THRESHOLD_GOOD) return "Hög relevans";
  if (score >= SCORE_THRESHOLD_OK) return "Möjlig relevans";
  return "Låg relevans";
};

type SourcesPanelProps = {
  sources: Source[];
  className?: string;
  citedSourceIds?: Set<string>;
};

export function SourcesPanel({
  sources,
  className,
  citedSourceIds,
}: SourcesPanelProps) {
  const activeSourceId = useAppStore((s) => s.activeSourceId);
  const hoveredSourceId = useAppStore((s) => s.hoveredSourceId);
  const lockedSourceId = useAppStore((s) => s.lockedSourceId);
  const setHoveredSource = useAppStore((s) => s.setHoveredSource);
  const toggleLockedSource = useAppStore((s) => s.toggleLockedSource);

  const [isPreviewExpanded, setIsPreviewExpanded] = useState(false);

  const previewSourceId = lockedSourceId ?? hoveredSourceId;
  const previewSource = useMemo(
    () => sources.find((src) => src.id === previewSourceId) || null,
    [sources, previewSourceId],
  );

  const showHint = !previewSource;
  const isLockedPreview = Boolean(
    previewSource && lockedSourceId === previewSource.id,
  );

  return (
    <div
      className={clsx(
        "h-full bg-stone-50/55 border border-stone-300/60 rounded-2xl px-5 py-5",
        "flex-1 min-h-0 overflow-hidden flex flex-col backdrop-blur-2xl",
        className,
      )}
      onMouseLeave={() => setHoveredSource(null)}
    >
      <div className="flex items-baseline justify-between pb-4 border-b border-stone-200/70">
        <h4 className="text-[11px] font-mono uppercase tracking-wider text-stone-700">
          Sources ({sources.length})
        </h4>
        <div className="text-[10px] font-mono text-stone-400">
          {lockedSourceId ? "LOCKED" : hoveredSourceId ? "PREVIEW" : ""}
        </div>
      </div>

      {/* List */}
      <div className="flex-1 min-h-0 overflow-y-auto custom-scrollbar pt-2">
        {sources.length === 0 && (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <FileSearch
              className="w-8 h-8 text-stone-400 mb-3"
              strokeWidth={1.2}
            />
            <div className="text-sm text-stone-500 font-mono">
              Inga källor matchade din fråga
            </div>
          </div>
        )}
        <AnimatePresence>
          {sources.map((source, i) => {
            const isActive = activeSourceId === source.id;
            const isLocked = lockedSourceId === source.id;
            const isCited = citedSourceIds
              ? citedSourceIds.has(source.id)
              : false;

            // Micro-indicator with color coding
            const scoreWidth = Math.max(10, Math.round(source.score * 46)); // 10–46px
            const scoreColor = getScoreColor(source.score);
            const scoreBadgeColor = getScoreBadgeColor(source.score);
            const scoreLabel = getScoreLabel(source.score);

            return (
              <motion.div
                key={source.id}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0, transition: { delay: i * 0.02 } }}
                className={clsx(
                  "group relative w-full text-left cursor-pointer select-none",
                  "px-2 py-3 transition-colors",
                  i < sources.length - 1 && "border-b border-stone-200/60",
                  isActive ? "bg-stone-100/70" : "hover:bg-stone-100/50",
                )}
                onMouseEnter={() => setHoveredSource(source.id)}
                onClick={() => {
                  toggleLockedSource(source.id);
                  setIsPreviewExpanded(false);
                }}
              >
                <div className="grid grid-cols-[1fr_auto] gap-3 items-start">
                  <div className="min-w-0">
                    <div className="flex items-start gap-2">
                      {isCited && (
                        <span
                          className="mt-1 inline-block w-1.5 h-1.5 rounded-full bg-teal-700/60 flex-shrink-0"
                          aria-label="Cited"
                        />
                      )}
                      <div
                        className={clsx(
                          "text-[13px] font-semibold leading-snug",
                          isActive ? "text-stone-900" : "text-stone-800",
                        )}
                        style={{
                          display: "-webkit-box",
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: "vertical",
                          overflow: "hidden",
                        }}
                      >
                        {source.title}
                      </div>
                    </div>
                    <div className="mt-1 text-[11px] text-stone-500">
                      {source.source} •{" "}
                      <span className="font-mono text-[10px]">
                        {source.doc_type.toUpperCase()}
                      </span>
                    </div>
                  </div>

                  <div className="flex flex-col items-end gap-2 pt-0.5">
                    {/* Relevance Badge med Label */}
                    <div
                      className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${scoreBadgeColor}`}
                    >
                      {scoreLabel}
                    </div>

                    {/* Numeriskt Score */}
                    <div className="text-[10px] font-mono text-stone-500">
                      {source.score.toFixed(3)}
                    </div>

                    {/* Color-coded Indicator Bar */}
                    <div className="h-1.5 w-12 rounded-full bg-stone-200 overflow-hidden">
                      <div
                        className={`h-full rounded-full ${scoreColor}`}
                        style={{ width: `${scoreWidth}px` }}
                      />
                    </div>

                    {/* Lock Indicator */}
                    {isLocked && (
                      <div className="text-[10px] font-mono text-stone-500 uppercase tracking-wider">
                        Locked
                      </div>
                    )}
                  </div>
                </div>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      {/* Preview */}
      <div className="pt-4 mt-3 border-t border-stone-200/70">
        {showHint ? (
          <div className="text-xs text-stone-500 font-mono">
            Select a source to preview.
          </div>
        ) : (
          <div>
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <div className="text-[10px] font-mono uppercase tracking-wider text-stone-500">
                  Source Preview
                </div>
                <div
                  className="mt-1 text-[13px] font-semibold text-stone-900 leading-snug"
                  style={{
                    display: "-webkit-box",
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: "vertical",
                    overflow: "hidden",
                  }}
                >
                  {previewSource.title}
                </div>
                <div className="mt-1 text-[11px] text-stone-500">
                  {previewSource.source} •{" "}
                  <span className="font-mono text-[10px]">
                    {previewSource.doc_type.toUpperCase()}
                  </span>{" "}
                  •{" "}
                  <span
                    className={`font-mono text-[10px] ${getScoreBadgeColor(previewSource.score)}`}
                  >
                    Score: {previewSource.score.toFixed(3)}
                  </span>
                </div>
              </div>

              {isLockedPreview && (
                <button
                  type="button"
                  onClick={() => setIsPreviewExpanded((v) => !v)}
                  className="flex items-center gap-2 text-[10px] font-mono uppercase tracking-wider text-stone-500 hover:text-stone-700 transition-colors"
                >
                  <span>{isPreviewExpanded ? "Less" : "More"}</span>
                  <ChevronDown
                    className={clsx(
                      "w-3 h-3 transition-transform",
                      isPreviewExpanded ? "rotate-180" : "rotate-0",
                    )}
                    strokeWidth={1.5}
                  />
                </button>
              )}
            </div>

            <div
              className={clsx(
                "mt-3 text-xs text-stone-700 leading-relaxed",
                !isPreviewExpanded && "line-clamp-3",
              )}
            >
              {previewSource.snippet}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
