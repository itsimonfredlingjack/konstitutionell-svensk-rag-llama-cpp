import React, { useEffect, useState } from 'react';
import { useAppStore } from '../../stores/useAppStore';
import { motion } from 'framer-motion';
import { Terminal, Cpu, Network, Database, Sparkles, ShieldCheck, Clock, FileText } from 'lucide-react';
import clsx from 'clsx';

export const QueryProcessor: React.FC<{ className?: string }> = ({ className }) => {
    const { query, pipelineStage, retrievalStrategy, searchStage } = useAppStore();
    const [elapsed, setElapsed] = useState(0);

    // Timer for metrics
    useEffect(() => {
        let interval: ReturnType<typeof setInterval>;

        if (searchStage === 'searching' || searchStage === 'reading') {
            const start = Date.now();
            interval = setInterval(() => {
                setElapsed((Date.now() - start) / 1000);
            }, 100);
        }

        return () => {
            if (interval) clearInterval(interval);
        };
    }, [searchStage]);

    if (!pipelineStage || pipelineStage === 'idle') return null;

    const stages = [
        { id: 'query_classification', icon: Cpu, label: 'Classification' },
        { id: 'retrieval', icon: Database, label: 'Retrieval' },
        { id: 'generation', icon: Sparkles, label: 'Generation' },
        { id: 'guardrail_validation', icon: ShieldCheck, label: 'Validation' }
    ];

    const currentStageIndex = stages.findIndex(s => s.id === pipelineStage);

    return (
        <motion.div
            initial={{ opacity: 0, y: -20 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            className={clsx("w-full", className)}
        >
            {/* Unified Header */}
            <div className="flex items-center justify-between mb-6">
                <h3 className="text-sm font-semibold text-slate-900">Query Operations</h3>
                <div className="flex items-center gap-4 text-xs text-slate-400 font-mono">
                    <span className="flex items-center gap-1">
                        <Clock className="w-3 h-3" strokeWidth={1.5} /> {elapsed.toFixed(1)}s
                    </span>
                    <span className="flex items-center gap-1">
                        <Terminal className="w-3 h-3" strokeWidth={1.5} /> v3.0
                    </span>
                </div>
            </div>

            {/* Unified Content - Two Columns */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Left Column: Active Pipeline */}
                <div className="space-y-3">
                    <div className="flex items-center gap-2 mb-3">
                        <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">Active Pipeline</span>
                        <div className="flex-1 h-px bg-slate-200" />
                    </div>

                    <div className="flex flex-col gap-2">
                        {stages.map((stage, i) => {
                            const isCurrent = i === currentStageIndex;

                            return (
                                <div key={stage.id} className={clsx(
                                    "flex items-center gap-3 py-2 px-2 transition-all duration-200",
                                    isCurrent ? "bg-slate-50 rounded border border-slate-200" : "opacity-40"
                                )}>
                                    <stage.icon className={clsx("w-4 h-4 text-slate-700", isCurrent && "animate-pulse")} strokeWidth={1.5} />
                                    <div className="flex flex-col flex-1">
                                        <span className={clsx("text-xs font-medium", isCurrent ? "text-slate-900" : "text-slate-500")}>
                                            {stage.label}
                                        </span>
                                        {isCurrent && (
                                            <span className="text-[10px] text-slate-400 font-mono mt-0.5">Processing...</span>
                                        )}
                                    </div>
                                    {isCurrent && (
                                        <motion.div
                                            className="w-2 h-2 rounded-full bg-slate-400"
                                            animate={{ scale: [1, 1.3, 1], opacity: [1, 0.6, 1] }}
                                            transition={{ repeat: Infinity, duration: 1 }}
                                        />
                                    )}
                                </div>
                            );
                        })}
                    </div>
                </div>

                {/* Right Column: Strategy Context */}
                <div className="space-y-3 md:border-l md:border-slate-200 md:pl-6">
                    <div className="flex items-center gap-2 mb-3">
                        <span className="text-xs font-medium text-slate-500 uppercase tracking-wide">Strategy Context</span>
                        <div className="flex-1 h-px bg-slate-200" />
                    </div>

                    <div className="space-y-2">
                        <div className="py-2 px-3 bg-slate-50 rounded border border-slate-200">
                            <span className="block text-[10px] text-slate-500 mb-1.5 uppercase tracking-wide">Retrieval Mode</span>
                            <div className="flex items-center gap-2">
                                <Network className="w-3 h-3 text-slate-700" strokeWidth={1.5} />
                                <span className="text-xs text-slate-700 font-mono">
                                    {retrievalStrategy || 'Analyzing...'}
                                </span>
                            </div>
                        </div>

                        <div className="py-2 px-3 bg-slate-50 rounded border border-slate-200">
                            <span className="block text-[10px] text-slate-500 mb-1.5 uppercase tracking-wide">Input Vector</span>
                            <div className="flex items-center gap-2">
                                <FileText className="w-3 h-3 text-slate-700" strokeWidth={1.5} />
                                <span className="text-xs text-slate-600 font-mono truncate max-w-[150px]">
                                    "{query}"
                                </span>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </motion.div>
    );
};
