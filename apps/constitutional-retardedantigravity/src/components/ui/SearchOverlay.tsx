import { AnimatePresence, motion } from "framer-motion";
import { CornerDownLeft, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef } from "react";
import clsx from "clsx";
import { createPortal } from "react-dom";

import { useAppStore } from "../../stores/useAppStore";

type SearchOverlayProps = {
  isOpen: boolean;
  onClose: () => void;
};

const BACKEND_MODE_MAP: Record<
  "verify" | "summarize" | "compare",
  "auto" | "chat" | "evidence"
> = {
  verify: "evidence",
  summarize: "chat",
  compare: "auto",
};

export function SearchOverlay({ isOpen, onClose }: SearchOverlayProps) {
  const query = useAppStore((s) => s.query);
  const queries = useAppStore((s) => s.queries);
  const setQuery = useAppStore((s) => s.setQuery);
  const startSearch = useAppStore((s) => s.startSearch);
  const isSearching = useAppStore((s) => s.isSearching);

  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const t = setTimeout(() => inputRef.current?.focus(), 0);
    return () => clearTimeout(t);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isOpen, onClose]);

  const recent = useMemo(
    () =>
      queries
        .slice(-8)
        .map((q) => ({ query: q.query, mode: q.mode }))
        .reverse(),
    [queries],
  );

  const currentMode = queries[queries.length - 1]?.mode ?? "verify";

  const submit = async () => {
    if (!query.trim()) return;
    onClose();
    await startSearch(BACKEND_MODE_MAP[currentMode], currentMode);
  };

  const portalRoot = typeof document !== "undefined" ? document.body : null;
  if (!portalRoot) return null;

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <>
          <motion.div
            className="fixed inset-0 z-[90] bg-stone-900/15 backdrop-blur-[2px]"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
          />

          <motion.div
            className="fixed inset-0 z-[100] flex items-start justify-center pt-[12vh] px-6"
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 10 }}
          >
            <div
              className={clsx(
                "w-full max-w-3xl rounded-2xl border border-stone-300/70",
                "bg-gradient-to-b from-stone-50/85 to-stone-100/55 backdrop-blur-xl",
                "ring-1 ring-stone-900/5 shadow-[0_24px_60px_rgba(0,0,0,0.12)]",
              )}
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between px-6 pt-5 pb-3">
                <div className="text-[11px] font-mono uppercase tracking-wider text-stone-600">
                  New Query
                </div>
                <button
                  type="button"
                  onClick={onClose}
                  className="p-2 rounded-lg text-stone-500 hover:text-stone-800 hover:bg-stone-200/40 transition-colors"
                >
                  <X className="w-4 h-4" strokeWidth={1.5} />
                </button>
              </div>

              <div className="px-6 pb-5">
                <div className="relative bg-white/75 border border-stone-300 rounded-2xl p-2 flex items-center focus-within:bg-white focus-within:border-teal-600 focus-within:ring-1 focus-within:ring-teal-600/20 shadow-sm">
                  <Search
                    className="w-5 h-5 text-stone-700 ml-3"
                    strokeWidth={1.5}
                  />
                  <input
                    ref={inputRef}
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Type a new question…"
                    className="flex-1 bg-transparent border-none text-base text-stone-900 font-medium placeholder-stone-400 px-3 py-3 focus:ring-0 focus:outline-none"
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        submit();
                      }
                    }}
                  />
                  <div className="mr-2 flex items-center gap-2">
                    <span className="text-[10px] font-mono text-stone-500 bg-stone-100 px-2 py-1 rounded border border-stone-200 hidden sm:block">
                      Enter{" "}
                      <CornerDownLeft
                        className="w-3 h-3 inline ml-1 opacity-60"
                        strokeWidth={1.5}
                      />
                    </span>
                    <button
                      type="button"
                      disabled={!query.trim() || isSearching}
                      onClick={submit}
                      className={clsx(
                        "px-3 py-2 rounded-xl border transition-colors font-mono text-xs",
                        "bg-teal-50 border-teal-100 text-stone-800 hover:bg-teal-100",
                        (!query.trim() || isSearching) &&
                          "opacity-50 cursor-not-allowed hover:bg-teal-50",
                      )}
                    >
                      Run
                    </button>
                  </div>
                </div>

                <div className="mt-5">
                  <div className="text-[11px] font-mono uppercase tracking-wider text-stone-600 mb-2">
                    Recent
                  </div>
                  {recent.length === 0 ? (
                    <div className="text-sm text-stone-500">
                      No recent queries yet.
                    </div>
                  ) : (
                    <div className="space-y-1">
                      {recent.map(({ query: q, mode }) => (
                        <button
                          key={q}
                          type="button"
                          onClick={async () => {
                            setQuery(q);
                            onClose();
                            await startSearch(BACKEND_MODE_MAP[mode], mode);
                          }}
                          className={clsx(
                            "w-full text-left px-3 py-2 rounded-xl border border-transparent",
                            "hover:border-stone-300/60 hover:bg-white/60 transition-colors",
                          )}
                        >
                          <div className="text-sm text-stone-800 truncate">
                            {q}
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>,
    portalRoot,
  );
}
