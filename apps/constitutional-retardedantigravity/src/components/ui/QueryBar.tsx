import { AnimatePresence, motion } from 'framer-motion';
import { Clock, CornerDownLeft, History, Pencil, Play, X, Loader2 } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import clsx from 'clsx';

import { useAppStore } from '../../stores/useAppStore';

type QueryBarProps = {
    onOpenHistory?: () => void;
    className?: string;
};

export function QueryBar({ onOpenHistory, className }: QueryBarProps) {
    const submittedQuery = useAppStore((s) => s.submittedQuery);
    const queryHistory = useAppStore((s) => s.queryHistory);
    const isSearching = useAppStore((s) => s.isSearching);
    const setQuery = useAppStore((s) => s.setQuery);
    const startSearch = useAppStore((s) => s.startSearch);

    const [isEditing, setIsEditing] = useState(false);
    const [draft, setDraft] = useState(submittedQuery);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    useEffect(() => {
        // Keep draft in sync when not editing.
        if (!isEditing) setDraft(submittedQuery);
    }, [submittedQuery, isEditing]);

    useEffect(() => {
        if (!isEditing) return;
        const t = setTimeout(() => {
            if (textareaRef.current) {
                textareaRef.current.focus();
                // Auto-resize on open
                textareaRef.current.style.height = 'auto';
                textareaRef.current.style.height = textareaRef.current.scrollHeight + 'px';
            }
        }, 0);
        return () => clearTimeout(t);
    }, [isEditing]);

    // Auto-resize on typing
    useEffect(() => {
        if (isEditing && textareaRef.current) {
            textareaRef.current.style.height = 'auto';
            textareaRef.current.style.height = textareaRef.current.scrollHeight + 'px';
        }
    }, [draft, isEditing]);

    const recent = useMemo(() => queryHistory.slice(0, 6), [queryHistory]);

    const run = async (q: string) => {
        const trimmed = q.trim();
        if (!trimmed) return;
        setQuery(trimmed);
        setIsEditing(false);
        await startSearch();
    };

    return (
        <div className={clsx("w-full", className)}>
            <div className="flex items-center justify-between gap-4">
                <div className="flex items-center gap-3 min-w-0">
                    <div className="text-[11px] font-mono uppercase tracking-wider text-stone-600">
                        Query
                    </div>

                    {/* Chip / inline editor */}
                    <div className="min-w-0">
                        <AnimatePresence initial={false} mode="wait">
                            {!isEditing ? (
                                <motion.button
                                    key="chip"
                                    type="button"
                                    onClick={() => setIsEditing(true)}
                                    className={clsx(
                                        "group inline-flex items-center gap-2 max-w-[680px]",
                                        "px-3 py-1.5 rounded-full border",
                                        "bg-white/60 border-stone-300/70 text-stone-800",
                                        "hover:bg-white hover:border-teal-700/35 transition-colors",
                                        "focus:outline-none focus-visible:ring-2 focus-visible:ring-teal-700/20"
                                    )}
                                    title="Click to edit"
                                    initial={{ opacity: 0, y: 3 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, y: -3 }}
                                >
                                    <span
                                        className={clsx(
                                            "text-[12px] font-mono truncate",
                                            !submittedQuery && "text-stone-400"
                                        )}
                                    >
                                        {submittedQuery || 'Click to enter a new query…'}
                                    </span>
                                    <span className="text-[10px] font-mono text-stone-400 group-hover:text-stone-500">
                                        Click to edit
                                    </span>
                                </motion.button>
                            ) : (
                                <motion.div
                                    key="input"
                                    initial={{ opacity: 0, y: 3 }}
                                    animate={{ opacity: 1, y: 0 }}
                                    exit={{ opacity: 0, y: -3 }}
                                    className="flex items-center gap-2"
                                >
                                    <div className="flex items-center gap-2 px-3 py-1.5 rounded-2xl border bg-white/80 border-teal-700/30">
                                        <textarea
                                            ref={textareaRef}
                                            value={draft}
                                            onChange={(e) => setDraft(e.target.value)}
                                            placeholder="Type a new query…"
                                            rows={1}
                                            className="w-[420px] max-w-[52vw] bg-transparent text-[13px] font-mono text-stone-900 placeholder-stone-400 outline-none resize-none overflow-hidden"
                                            onKeyDown={(e) => {
                                                if (e.key === 'Escape') {
                                                    setIsEditing(false);
                                                    setDraft(submittedQuery);
                                                }
                                                if (e.key === 'Enter' && !e.shiftKey) {
                                                    e.preventDefault();
                                                    run(draft);
                                                }
                                            }}
                                        />
                                        <span className="text-[10px] font-mono text-stone-500 hidden md:inline-flex items-center gap-1 self-end mb-1">
                                            Enter <CornerDownLeft className="w-3 h-3 opacity-60" strokeWidth={1.5} />
                                        </span>
                                    </div>
                                    <button
                                        type="button"
                                        onClick={() => run(draft)}
                                        disabled={!draft.trim() || isSearching}
                                        className={clsx(
                                            "px-3 py-1.5 rounded-full border font-mono text-[11px] uppercase tracking-wider h-[32px] flex items-center justify-center min-w-[50px]",
                                            "bg-teal-50 border-teal-100 text-stone-800 hover:bg-teal-100 transition-colors",
                                            (!draft.trim() || isSearching) && "opacity-50 cursor-not-allowed hover:bg-teal-50"
                                        )}
                                    >
                                        {isSearching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : 'Run'}
                                    </button>
                                    <button
                                        type="button"
                                        onClick={() => {
                                            setIsEditing(false);
                                            setDraft(submittedQuery);
                                        }}
                                        className="p-2 rounded-full border border-transparent text-stone-500 hover:text-stone-800 hover:bg-stone-200/40 transition-colors"
                                        title="Cancel"
                                    >
                                        <X className="w-4 h-4" strokeWidth={1.5} />
                                    </button>
                                </motion.div>
                            )}
                        </AnimatePresence>
                    </div>
                </div>

                {/* Right actions */}
                <div className={clsx("flex items-center gap-2 flex-shrink-0", isEditing && "hidden")}>
                    <button
                        type="button"
                        onClick={() => setIsEditing(true)}
                        className="hidden md:inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-stone-300/70 bg-white/40 hover:bg-white/60 transition-colors text-stone-700"
                        title="Edit"
                    >
                        <Pencil className="w-4 h-4" strokeWidth={1.5} />
                        <span className="text-[11px] font-mono uppercase tracking-wider">Edit</span>
                    </button>

                    <button
                        type="button"
                        onClick={() => run(submittedQuery)}
                        disabled={!submittedQuery.trim() || isSearching}
                        className={clsx(
                            "inline-flex items-center gap-2 px-3 py-2 rounded-xl border transition-colors",
                            "border-teal-100 bg-teal-50 hover:bg-teal-100 text-stone-800",
                            (!submittedQuery.trim() || isSearching) && "opacity-50 cursor-not-allowed hover:bg-teal-50"
                        )}
                        title="Run again"
                    >
                        {isSearching ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" strokeWidth={1.6} />}
                        <span className="text-[11px] font-mono uppercase tracking-wider">Run</span>
                    </button>

                    {onOpenHistory && (
                        <button
                            type="button"
                            onClick={onOpenHistory}
                            className="inline-flex items-center gap-2 px-3 py-2 rounded-xl border border-stone-300/70 bg-white/40 hover:bg-white/60 transition-colors text-stone-700"
                            title="Recent queries"
                        >
                            <History className="w-4 h-4" strokeWidth={1.5} />
                            <span className="text-[11px] font-mono uppercase tracking-wider">Recent</span>
                            <span className="hidden sm:inline-flex items-center gap-1 text-[10px] font-mono text-stone-500 bg-stone-100/70 px-2 py-0.5 rounded-lg border border-stone-200/70">
                                Cmd/Ctrl <span className="text-stone-400">K</span>
                            </span>
                        </button>
                    )}
                </div>
            </div>

            {/* Compact recent list (visible only when editing and history exists) */}
            {isEditing && recent.length > 0 && (
                <div className="mt-3 flex items-start gap-3">
                    <div className="text-[11px] font-mono uppercase tracking-wider text-stone-600 flex items-center gap-1 pt-1">
                        <Clock className="w-3.5 h-3.5 text-stone-500" strokeWidth={1.5} />
                        Recent
                    </div>
                    <div className="flex flex-wrap gap-2">
                        {recent.map((q) => (
                            <button
                                key={q}
                                type="button"
                                onClick={() => run(q)}
                                className={clsx(
                                    "px-3 py-1.5 rounded-full border border-stone-300/70",
                                    "bg-white/50 hover:bg-white hover:border-teal-700/30 transition-colors",
                                    "text-[12px] font-mono text-stone-800 max-w-[520px] truncate"
                                )}
                                title={q}
                            >
                                {q}
                            </button>
                        ))}
                    </div>
                </div>
            )}
        </div>
    );
}
