import { motion } from 'framer-motion';
import { Zap, ShieldAlert, ShieldCheck, Shield } from 'lucide-react';
import { useAppStore } from '../../stores/useAppStore';
import type { EvidenceLevel } from '../../stores/useAppStore';
import { PipelineVisualizer } from './PipelineVisualizer';
import { useEffect, useMemo, useRef, useState } from 'react';
import { SourcesPanel } from './SourcesPanel';
import { AnswerWithCitations, extractCitedSourceIds } from './AnswerWithCitations';
import { QueryBar } from './QueryBar';
import { SearchOverlay } from './SearchOverlay';
import { ThoughtChain } from './ThoughtChain';


const EvidenceLevelInline = ({ level }: { level: EvidenceLevel }) => {
    if (!level) return null;

    const config = {
        HIGH: { icon: ShieldCheck, text: 'text-emerald-700' },
        MEDIUM: { icon: Shield, text: 'text-amber-700' },
        LOW: { icon: ShieldAlert, text: 'text-red-700' },
    }[level];

    if (!config) return null;
    const Icon = config.icon;

    return (
        <div className="flex items-center gap-1.5">
            <Icon className={`w-3.5 h-3.5 ${config.text}`} strokeWidth={1.5} />
            <span className={`text-[11px] font-mono uppercase tracking-wider ${config.text}`}>
                Evidence: {level}
            </span>
        </div>
    );
};

export function ResultsSection() {
    const {
        sources,
        hoveredSourceId,
        lockedSourceId,
        searchStage,
        answer,
        thoughtChain,
        evidenceLevel
    } = useAppStore();
    const answerContainerRef = useRef<HTMLDivElement>(null);
    const citedSourceIds = useMemo(() => extractCitedSourceIds(answer, sources), [answer, sources]);
    const [isHistoryOpen, setIsHistoryOpen] = useState(false);

    // Cmd/Ctrl+K opens query history overlay (Results view).
    useEffect(() => {
        const handler = (e: KeyboardEvent) => {
            if (e.key.toLowerCase() !== 'k') return;
            if (!(e.metaKey || e.ctrlKey)) return;

            const el = document.activeElement as HTMLElement | null;
            const tag = el?.tagName?.toLowerCase();
            const isTyping =
                tag === 'input' ||
                tag === 'textarea' ||
                (el instanceof HTMLElement && el.isContentEditable);
            if (isTyping) return;

            e.preventDefault();
            setIsHistoryOpen(true);
        };

        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, []);

    // Auto-scroll to bottom when answer updates during streaming
    useEffect(() => {
        if ((searchStage === 'reading' || searchStage === 'complete') && answer && answerContainerRef.current) {
            // Small delay to ensure DOM has updated
            const timeoutId = setTimeout(() => {
                if (answerContainerRef.current) {
                    const container = answerContainerRef.current;
                    const isNearBottom = container.scrollHeight - container.scrollTop - container.clientHeight < 100;

                    // Only auto-scroll if user is near bottom (hasn't scrolled up)
                    if (isNearBottom) {
                        container.scrollTo({
                            top: container.scrollHeight,
                            behavior: 'smooth'
                        });
                    }
                }
            }, 50);

            return () => clearTimeout(timeoutId);
        }
    }, [answer, searchStage]);

    return (
        <div className="flex flex-col w-full max-w-7xl mx-auto mt-6 flex-1 min-h-0 relative">
            <div className="flex gap-6 flex-1 min-h-0 overflow-hidden">
                {/* LEFT: Result Panel */}
                <motion.section
                    initial={{ opacity: 0, x: -14 }}
                    animate={{ opacity: 1, x: 0 }}
                    className="flex-1 min-h-0 overflow-hidden"
                >
                    <div className="h-full flex flex-col min-h-0 overflow-hidden rounded-2xl border border-stone-300/60 bg-stone-50/55 backdrop-blur-2xl">
                        {/* Pipeline (hero) */}
                        <div className="px-6 pt-6 pb-4">
                            <PipelineVisualizer />
                        </div>

                        <div className="h-px bg-stone-200/70" />

                        {/* Query bar (always visible in Results mode) */}
                        <div className="px-6 py-4">
                            <QueryBar onOpenHistory={() => setIsHistoryOpen(true)} />
                        </div>

                        <div className="h-px bg-stone-200/70" />

                        {/* Scrollable content */}
                        <div
                            ref={answerContainerRef}
                            className="flex-1 min-h-0 overflow-y-auto custom-scrollbar px-8 py-7"
                        >
                            {/* Header */}
                            <div className="mb-7 pb-5 border-b border-stone-200/70">
                                <div className="flex items-start justify-between gap-6">
                                    <div>
                                        <h2 className="text-[22px] font-semibold text-stone-900 tracking-tight">
                                            ANALYSIS RESULTS
                                        </h2>
                                        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-2 text-[11px] text-stone-500 font-mono">
                                            {evidenceLevel && <EvidenceLevelInline level={evidenceLevel} />}
                                        </div>
                                    </div>
                                    {/* Selection state (quiet) */}
                                    <div className="text-[10px] font-mono text-stone-400 text-right whitespace-nowrap">
                                        {lockedSourceId ? (
                                            <span>LOCKED SOURCE</span>
                                        ) : hoveredSourceId ? (
                                            <span>PREVIEWING SOURCE</span>
                                        ) : (
                                            <span>NO SOURCE SELECTED</span>
                                        )}
                                    </div>
                                </div>
                            </div>

                            {/* Body */}
                            {searchStage === 'searching' && (
                                <div className="flex items-center gap-3 text-stone-700 font-mono text-sm">
                                    <Zap className="w-4 h-4 text-stone-700" strokeWidth={1.5} />
                                    <span className="animate-pulse">Running pipeline…</span>
                                </div>
                            )}

                            {searchStage === 'error' && (
                                <div className="flex items-center gap-3 text-red-700 font-mono text-sm">
                                    <ShieldAlert className="w-4 h-4" strokeWidth={1.5} />
                                    <span>An error occurred. Check the console for details.</span>
                                </div>
                            )}

                            {(searchStage === 'reading' || searchStage === 'complete') && (
                                <div className="relative z-10">
                                    <ThoughtChain thought={thoughtChain} />
                                    {answer ? (
                                        <div
                                            className="text-stone-900 font-sans text-[15px]"
                                            style={{ lineHeight: '1.85' }}
                                        >
                                            <AnswerWithCitations
                                                answer={answer}
                                                sources={sources}
                                            />
                                        </div>
                                    ) : (
                                        <div className="text-stone-500 italic flex items-center gap-2">
                                            <span className="w-2 h-2 bg-stone-400 rounded-full animate-pulse" />
                                            Waiting for intelligence stream…
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                </motion.section>

                {/* RIGHT: Sources Panel (temporary; will be replaced by SourcesPanel) */}
                <motion.aside
                    initial={{ opacity: 0, x: 14 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: 0.1 }}
                    className="w-[360px] flex flex-col min-h-0 overflow-hidden"
                >
                    <SourcesPanel citedSourceIds={citedSourceIds} />
                </motion.aside>
            </div>

            <SearchOverlay isOpen={isHistoryOpen} onClose={() => setIsHistoryOpen(false)} />
        </div>
    );
}
