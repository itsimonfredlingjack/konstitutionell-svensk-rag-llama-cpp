import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Brain, ChevronDown, Sparkles } from 'lucide-react';
import clsx from 'clsx';

interface ThoughtChainProps {
    thought: string | null;
}

export function ThoughtChain({ thought }: ThoughtChainProps) {
    const [isOpen, setIsOpen] = useState(false);

    if (!thought) return null;

    return (
        <div className="mb-8 rounded-xl border border-teal-700/20 bg-teal-50/20 overflow-hidden">
            <button
                onClick={() => setIsOpen(!isOpen)}
                className="w-full flex items-center justify-between px-4 py-2.5 bg-teal-50/40 hover:bg-teal-100/40 transition-colors text-left group"
            >
                <div className="flex items-center gap-2.5">
                    <div className="p-1.5 rounded-md bg-teal-700/5 text-teal-700/70 group-hover:text-teal-700 group-hover:bg-teal-700/10 transition-colors">
                        <Brain size={14} strokeWidth={2} />
                    </div>
                    <div>
                        <div className="text-[11px] font-bold text-teal-800/80 uppercase tracking-wider group-hover:text-teal-900 transition-colors">
                            System Self-Reflection
                        </div>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    {!isOpen && (
                        <span className="text-[10px] text-teal-700/50 font-mono truncate max-w-[200px]">
                            {thought.slice(0, 40)}...
                        </span>
                    )}
                    <ChevronDown
                        size={14}
                        className={clsx(
                            "text-teal-700/40 group-hover:text-teal-700/60 transition-transform duration-200",
                            isOpen && "rotate-180"
                        )}
                    />
                </div>
            </button>

            <AnimatePresence initial={false}>
                {isOpen && (
                    <motion.div
                        initial={{ height: 0, opacity: 0 }}
                        animate={{ height: 'auto', opacity: 1 }}
                        exit={{ height: 0, opacity: 0 }}
                        transition={{ duration: 0.3, ease: "easeInOut" }}
                    >
                        <div className="px-5 py-4 border-t border-teal-700/10 bg-white/40">
                            <div className="prose prose-sm max-w-none text-stone-600 font-mono text-[12px] leading-relaxed whitespace-pre-wrap">
                                {thought}
                            </div>

                            <div className="mt-3 flex items-center gap-1.5 text-[10px] text-teal-600/50 font-mono uppercase tracking-widest border-t border-teal-700/5 pt-2">
                                <Sparkles size={10} />
                                CRAG Verification Complete
                            </div>
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>
        </div>
    );
}
