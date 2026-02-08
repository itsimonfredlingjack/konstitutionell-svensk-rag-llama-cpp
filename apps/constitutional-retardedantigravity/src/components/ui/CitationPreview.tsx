import { createPortal } from "react-dom";
import { motion } from "framer-motion";
import { useAppStore } from "../../stores/useAppStore";
import { useMemo } from "react";

import type { Source } from "../../stores/useAppStore";

const EMPTY_SOURCES: Source[] = [];

export function CitationPreview() {
  const activeSourceId = useAppStore((s) => s.activeSourceId);
  const hoveredSourceId = useAppStore((s) => s.hoveredSourceId);
  const citationTarget = useAppStore((s) => s.citationTarget);
  const queries = useAppStore((s) => s.queries);
  const focusedQueryId = useAppStore((s) => s.focusedQueryId);
  const sources = useMemo(() => {
    const q = queries.find((x) => x.id === focusedQueryId);
    return q?.sources ?? EMPTY_SOURCES;
  }, [queries, focusedQueryId]);

  const focusSourceId =
    citationTarget && hoveredSourceId ? hoveredSourceId : activeSourceId;
  if (!focusSourceId || !citationTarget) return null;

  const source = sources.find((s: Source) => s.id === focusSourceId);
  if (!source) return null;

  // Calculate position: standard tooltip logic (right of pill, or below)
  const left = citationTarget.right + 10;
  const top = citationTarget.top;

  return createPortal(
    <motion.div
      initial={{ opacity: 0, scale: 0.9, x: -10 }}
      animate={{ opacity: 1, scale: 1, x: 0 }}
      exit={{ opacity: 0, scale: 0.9 }}
      style={{
        position: "fixed",
        left: left,
        top: top,
        zIndex: 60,
      }}
      className="w-72 bg-stone-950/75 backdrop-blur-xl border border-teal-700/20 rounded-xl p-4 shadow-2xl pointer-events-none"
    >
      <div className="text-[10px] uppercase font-mono text-teal-300 mb-1">
        Source Preview
      </div>
      <h4 className="text-sm font-medium text-white mb-2 leading-tight">
        {source.title}
      </h4>
      <p className="text-xs text-white/60 line-clamp-3 leading-relaxed">
        {source.snippet}
      </p>
    </motion.div>,
    document.body,
  );
}
