import clsx from 'clsx';
import { useMemo } from 'react';

import type { Source } from '../../stores/useAppStore';
import { useAppStore } from '../../stores/useAppStore';

const CITATION_RE = /\[(?:Källa\s+)?(\d+)\]/g;

export function extractCitedSourceIds(answer: string, sources: Source[]): Set<string> {
    const cited = new Set<string>();
    if (!answer) return cited;

    for (const match of answer.matchAll(CITATION_RE)) {
        const n = Number(match[1]);
        if (!Number.isFinite(n) || n < 1) continue;
        const src = sources[n - 1];
        if (src?.id) cited.add(src.id);
    }

    return cited;
}

type AnswerWithCitationsProps = {
    answer: string;
    sources: Source[];
    className?: string;
};

export function AnswerWithCitations({ answer, sources, className }: AnswerWithCitationsProps) {
    const activeSourceId = useAppStore((s) => s.activeSourceId);
    const setHoveredSource = useAppStore((s) => s.setHoveredSource);
    const toggleLockedSource = useAppStore((s) => s.toggleLockedSource);
    const setCitationTarget = useAppStore((s) => s.setCitationTarget);

    const parts = useMemo(() => {
        const nodes: Array<
            | { type: 'text'; value: string }
            | { type: 'citation'; n: number; sourceId: string | null }
        > = [];

        if (!answer) return nodes;

        let lastIndex = 0;
        for (const match of answer.matchAll(CITATION_RE)) {
            const idx = match.index ?? 0;
            if (idx > lastIndex) {
                nodes.push({ type: 'text', value: answer.slice(lastIndex, idx) });
            }

            const n = Number(match[1]);
            const src = Number.isFinite(n) ? sources[n - 1] : undefined;
            nodes.push({ type: 'citation', n, sourceId: src?.id ?? null });
            lastIndex = idx + match[0].length;
        }

        if (lastIndex < answer.length) {
            nodes.push({ type: 'text', value: answer.slice(lastIndex) });
        }

        return nodes;
    }, [answer, sources]);

    return (
        <div className={clsx("whitespace-pre-wrap break-words", className)}>
            {parts.map((p, i) => {
                if (p.type === 'text') {
                    return <span key={`t:${i}`}>{p.value}</span>;
                }

                const isKnown = Boolean(p.sourceId);
                const isActive = p.sourceId && activeSourceId === p.sourceId;

                return (
                    <button
                        key={`c:${i}`}
                        type="button"
                        disabled={!isKnown}
                        onMouseEnter={(e) => {
                            if (!p.sourceId) return;
                            setHoveredSource(p.sourceId);
                            setCitationTarget(e.currentTarget.getBoundingClientRect());
                        }}
                        onMouseLeave={() => {
                            setCitationTarget(null);
                            setHoveredSource(null);
                        }}
                        onClick={(e) => {
                            if (!p.sourceId) return;
                            toggleLockedSource(p.sourceId);
                            setCitationTarget(e.currentTarget.getBoundingClientRect());
                        }}
                        className={clsx(
                            "inline-flex items-center align-baseline mx-1",
                            "px-2 py-0.5 rounded-full border",
                            "text-[11px] font-mono tracking-wider",
                            isKnown
                                ? "bg-stone-100/70 border-stone-300/70 text-stone-700 hover:bg-stone-100"
                                : "bg-stone-100/40 border-stone-200/70 text-stone-400 cursor-not-allowed",
                            isActive && "ring-2 ring-teal-700/20"
                        )}
                        aria-label={isKnown ? `Citation ${p.n}` : 'Unknown citation'}
                    >
                        [{p.n}]
                    </button>
                );
            })}
        </div>
    );
}
