import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useAppStore } from "../../stores/useAppStore";
import { QueryCard } from "./QueryCard";
import { SourcesPanel } from "./SourcesPanel";
import { SearchOverlay } from "./SearchOverlay";
import { extractCitedSourceIds } from "./citations";

export function ResultsSection() {
  const queries = useAppStore((s) => s.queries);
  const activeQueryId = useAppStore((s) => s.activeQueryId);
  const focusedQueryId = useAppStore((s) => s.focusedQueryId);
  const setFocusedQuery = useAppStore((s) => s.setFocusedQuery);

  const scrollRef = useRef<HTMLDivElement>(null);
  const [collapsedIds, setCollapsedIds] = useState<Set<string>>(new Set());
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);

  const focusedQuery = queries.find((q) => q.id === focusedQueryId);
  const citedSourceIds = focusedQuery
    ? extractCitedSourceIds(focusedQuery.answer, focusedQuery.sources)
    : new Set<string>();

  useEffect(() => {
    if (activeQueryId) {
      setCollapsedIds((prev) => {
        const next = new Set(prev);
        queries.forEach((q) => {
          if (q.id !== activeQueryId) next.add(q.id);
        });
        return next;
      });
      setTimeout(() => {
        scrollRef.current?.scrollTo({
          top: scrollRef.current.scrollHeight,
          behavior: "smooth",
        });
      }, 100);
    }
  }, [activeQueryId, queries.length]);

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key.toLowerCase() !== "k") return;
      if (!(e.metaKey || e.ctrlKey)) return;
      const el = document.activeElement as HTMLElement | null;
      const tag = el?.tagName?.toLowerCase();
      const isTyping =
        tag === "input" ||
        tag === "textarea" ||
        (el instanceof HTMLElement && el.isContentEditable);
      if (isTyping) return;
      e.preventDefault();
      setIsHistoryOpen(true);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, []);

  return (
    <div className="flex flex-col w-full max-w-7xl mx-auto mt-6 flex-1 min-h-0 relative">
      <div className="flex gap-6 flex-1 min-h-0 overflow-hidden">
        <motion.section
          initial={{ opacity: 0, x: -14 }}
          animate={{ opacity: 1, x: 0 }}
          ref={scrollRef}
          className="flex-1 min-h-0 overflow-y-auto overflow-x-hidden custom-scrollbar flex flex-col gap-6 pb-6"
        >
          {queries.map((q) => (
            <QueryCard
              key={q.id}
              queryResult={q}
              isActive={q.id === activeQueryId}
              isCollapsed={collapsedIds.has(q.id)}
              isFocused={q.id === focusedQueryId}
              onToggleCollapse={() => {
                setCollapsedIds((prev) => {
                  const next = new Set(prev);
                  if (next.has(q.id)) next.delete(q.id);
                  else next.add(q.id);
                  return next;
                });
              }}
              onFocus={() => setFocusedQuery(q.id)}
              onOpenHistory={() => setIsHistoryOpen(true)}
            />
          ))}
        </motion.section>

        <motion.aside
          initial={{ opacity: 0, x: 14 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: 0.1 }}
          className="w-[360px] flex-shrink-0 flex flex-col min-h-0 overflow-hidden"
        >
          <SourcesPanel
            sources={focusedQuery?.sources ?? []}
            citedSourceIds={citedSourceIds}
          />
        </motion.aside>
      </div>

      <SearchOverlay
        isOpen={isHistoryOpen}
        onClose={() => setIsHistoryOpen(false)}
      />
    </div>
  );
}
