import React, { useState, useRef, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ArrowUp, Shield, BookOpen, GitCompare, RotateCcw } from "lucide-react";
import clsx from "clsx";
import { useAppStore } from "../../stores/useAppStore";
import type { QueryResultMode } from "../../types/queryResult";
import type { BackendMode } from "../../stores/useAppStore";

const MODE_CONFIG: {
    id: QueryResultMode;
    icon: React.ComponentType<{ className?: string; strokeWidth?: number }>;
    label: string;
    backendMode: BackendMode;
}[] = [
        { id: "verify", icon: Shield, label: "Verifiera", backendMode: "evidence" },
        { id: "summarize", icon: BookOpen, label: "Sammanfatta", backendMode: "chat" },
        { id: "compare", icon: GitCompare, label: "Jämför", backendMode: "assist" },
    ];

export const ChatInput: React.FC = () => {
    const [input, setInput] = useState("");
    const [shake, setShake] = useState(false);
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    const activeMode = useAppStore((s) => s.activeMode);
    const setActiveMode = useAppStore((s) => s.setActiveMode);
    const setQuery = useAppStore((s) => s.setQuery);
    const startSearch = useAppStore((s) => s.startSearch);
    const isSearching = useAppStore((s) => s.isSearching);
    const queries = useAppStore((s) => s.queries);
    const resetToHome = useAppStore((s) => s.resetToHome);

    // Auto-resize textarea
    useEffect(() => {
        const textarea = textareaRef.current;
        if (textarea) {
            textarea.style.height = "auto";
            textarea.style.height = Math.min(textarea.scrollHeight, 150) + "px";
        }
    }, [input]);

    const handleSubmit = () => {
        if (isSearching) return;

        if (!input.trim()) {
            // Empty submit - shake animation
            setShake(true);
            setTimeout(() => setShake(false), 500);
            return;
        }

        const modeConfig = MODE_CONFIG.find((m) => m.id === activeMode);
        const backendMode = modeConfig?.backendMode ?? "evidence";

        setQuery(input.trim());
        startSearch(backendMode, activeMode);
        setInput("");

        // Reset textarea height
        if (textareaRef.current) {
            textareaRef.current.style.height = "auto";
        }
    };

    const handleNewConversation = () => {
        // Clear queries and stay in chat view
        resetToHome();
    };

    const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
        if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            handleSubmit();
        }
    };

    return (
        <div
            className={clsx(
                "border-t border-stone-200/60",
                "bg-stone-50/80 backdrop-blur-xl",
                "px-4 py-3"
            )}
        >
            <div className="max-w-3xl mx-auto flex items-end gap-3">
                {/* Mode selector buttons */}
                <div className="flex gap-1 flex-shrink-0">
                    {MODE_CONFIG.map((mode) => {
                        const Icon = mode.icon;
                        const isActive = activeMode === mode.id;

                        return (
                            <button
                                key={mode.id}
                                type="button"
                                onClick={() => setActiveMode(mode.id)}
                                aria-label={mode.label}
                                aria-pressed={isActive}
                                className={clsx(
                                    "min-w-[44px] min-h-[44px] rounded-xl flex items-center justify-center",
                                    "border transition-all duration-200",
                                    isActive
                                        ? "bg-teal-700 border-teal-700 text-white shadow-sm"
                                        : "bg-stone-100 border-stone-300/60 text-stone-600 hover:bg-stone-200/70 hover:border-stone-400/60"
                                )}
                                title={mode.label}
                            >
                                <Icon className="w-4 h-4" strokeWidth={1.5} />
                            </button>
                        );
                    })}
                </div>

                {/* Input textarea */}
                <div className="flex-1 relative">
                    <motion.div
                        animate={shake ? { x: [-4, 4, -4, 4, 0] } : { x: 0 }}
                        transition={{ duration: 0.4 }}
                    >
                        <textarea
                            ref={textareaRef}
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder="Ställ en fråga..."
                            rows={1}
                            disabled={isSearching}
                            className={clsx(
                                "w-full resize-none rounded-xl px-4 py-3 pr-12",
                                "bg-white border",
                                shake
                                    ? "border-red-400 ring-2 ring-red-200"
                                    : "border-stone-300/60",
                                "text-stone-900 text-[15px] placeholder:text-stone-400",
                                "focus:outline-none focus:ring-2 focus:ring-teal-700/20 focus:border-teal-700/40",
                                "transition-all duration-200",
                                "disabled:opacity-60 disabled:cursor-not-allowed"
                            )}
                            style={{
                                minHeight: "48px",
                                maxHeight: "150px",
                            }}
                        />
                    </motion.div>
                </div>

                {/* Send button */}
                <button
                    type="button"
                    onClick={handleSubmit}
                    disabled={isSearching}
                    aria-label="Skicka"
                    className={clsx(
                        "min-w-[44px] min-h-[44px] rounded-xl flex items-center justify-center flex-shrink-0",
                        "transition-all duration-200",
                        !isSearching
                            ? "bg-teal-700 text-white hover:bg-teal-800 shadow-sm"
                            : "bg-stone-200 text-stone-400 cursor-not-allowed"
                    )}
                >
                    <ArrowUp className="w-5 h-5" strokeWidth={2} />
                </button>

                {/* New conversation button - only show if there are queries */}
                <AnimatePresence>
                    {queries.length > 0 && (
                        <motion.button
                            initial={{ opacity: 0, scale: 0.8 }}
                            animate={{ opacity: 1, scale: 1 }}
                            exit={{ opacity: 0, scale: 0.8 }}
                            type="button"
                            onClick={handleNewConversation}
                            aria-label="Ny konversation"
                            className={clsx(
                                "min-w-[44px] min-h-[44px] rounded-xl flex items-center justify-center flex-shrink-0",
                                "border border-stone-300/60 bg-stone-100",
                                "text-stone-500 hover:text-stone-700 hover:bg-stone-200/70",
                                "transition-all duration-200"
                            )}
                            title="Ny konversation"
                        >
                            <RotateCcw className="w-4 h-4" strokeWidth={1.5} />
                        </motion.button>
                    )}
                </AnimatePresence>
            </div>

            {/* Hint text */}
            <div className="max-w-3xl mx-auto mt-2 px-1">
                <span className="text-[10px] text-stone-400 font-mono">
                    Enter = skicka • Shift+Enter = ny rad
                </span>
            </div>
        </div>
    );
};
