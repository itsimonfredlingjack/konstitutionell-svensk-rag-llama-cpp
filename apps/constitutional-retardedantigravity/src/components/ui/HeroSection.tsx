import { motion } from 'framer-motion';
import { Search, Map, Shield, FileText, Zap, ChevronRight, CornerDownLeft, Loader2 } from 'lucide-react';
import { useAppStore } from '../../stores/useAppStore';
import { useState, useRef, useEffect } from 'react';

// Color mapping for Tailwind classes (must be explicit for build-time)
const COLOR_CLASSES = {
    cyan: {
        bg: 'bg-teal-100', // Stone Theme: Teal
        text: 'text-teal-800'
    },
    emerald: {
        bg: 'bg-emerald-100',
        text: 'text-emerald-800'
    },
    orange: {
        bg: 'bg-amber-100', // Stone Theme: Amber
        text: 'text-amber-800'
    }
} as const;

const GLASS_CARDS = [
    {
        id: 'verify',
        title: 'Snabbverifiering',
        text: 'Klistra in ett påstående, få styrkta källor + osäkerheter.',
        icon: Shield,
        color: 'cyan' as const
    },
    {
        id: 'trace',
        title: 'Källspårning',
        text: 'Visa var varje mening kommer ifrån (citations + hover preview).',
        icon: Map,
        color: 'emerald' as const
    },
    {
        id: 'bias',
        title: 'Risk & bias-check',
        text: 'Flagga tveksamma slutsatser och saknade motkällor.',
        icon: Zap,
        color: 'orange' as const
    }
];

export function HeroSection() {
    const { query, setQuery, startSearch, isSearching } = useAppStore();
    const [activeMode, setActiveMode] = useState<'verify' | 'summarize' | 'compare'>('verify');
    const textareaRef = useRef<HTMLTextAreaElement>(null);

    const handleSubmit = (e: React.FormEvent) => {
        e.preventDefault();
        if (query.trim()) startSearch();
    };

    const handleKeyDown = (e: React.KeyboardEvent) => {
        if (e.key === 'Enter' && !e.shiftKey) {
            e.preventDefault();
            if (query.trim()) startSearch();
        }
    };

    useEffect(() => {
        if (textareaRef.current) {
            textareaRef.current.style.height = 'auto';
            textareaRef.current.style.height = textareaRef.current.scrollHeight + 'px';
        }
    }, [query]);

    return (
        <div className="flex flex-col items-center justify-center w-full max-w-4xl mx-auto mt-[10vh]">
            {/* 1. Hero Search */}
            <div className="w-full relative z-20 group">
                <div className="flex items-center justify-between mb-4 px-2">
                    <h1 className="text-2xl font-light tracking-widest text-stone-900">
                        CONSTITUTIONAL AI <span className="text-teal-700 font-mono text-xs ml-2">v3.0</span>
                    </h1>

                    {/* Mode Selector */}
                    <div className="flex items-center gap-1 bg-white/40 rounded-lg p-1 border border-stone-300 shadow-sm backdrop-blur-sm">
                        {(['verify', 'summarize', 'compare'] as const).map(mode => (
                            <button
                                key={mode}
                                onClick={() => setActiveMode(mode)}
                                className={`px-3 py-1 text-xs font-mono rounded-md transition-all ${activeMode === mode
                                    ? 'bg-stone-100 shadow-sm text-teal-800 border border-stone-200 font-medium'
                                    : 'text-stone-500 hover:text-stone-900'
                                    }`}
                            >
                                {mode.charAt(0).toUpperCase() + mode.slice(1)}
                            </button>
                        ))}
                    </div>
                </div>

                <form onSubmit={handleSubmit} className="relative">
                    <div className="absolute inset-0 bg-teal-500/10 blur-xl rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />

                    <div className="relative bg-white/80 border border-stone-300 backdrop-blur-xl rounded-2xl p-2 flex items-center transition-all focus-within:bg-white focus-within:border-teal-600 focus-within:ring-1 focus-within:ring-teal-600/20 shadow-lg hover:border-stone-400">
                        <Search className="w-6 h-6 text-slate-700 ml-4 self-start mt-4" strokeWidth={1.5} />
                        <textarea
                            ref={textareaRef}
                            value={query}
                            onChange={(e) => setQuery(e.target.value)}
                            onKeyDown={handleKeyDown}
                            disabled={isSearching}
                            placeholder="Enter query to verify against constitutional framework..."
                            rows={1}
                            className="flex-1 bg-transparent border-none text-lg text-stone-900 font-medium placeholder-stone-400 p-4 focus:ring-0 focus:outline-none tracking-wide resize-none overflow-hidden"
                            style={{ minHeight: '60px' }}
                        />
                        <div className="mr-4 flex items-center gap-3 self-start mt-3">
                            <span className="text-[10px] font-mono text-stone-500 bg-stone-100 px-2 py-1 rounded border border-stone-200 hidden md:block">
                                Enter <CornerDownLeft className="w-3 h-3 inline ml-1 text-slate-700 opacity-50" strokeWidth={1.5} />
                            </span>
                            <button
                                type="submit"
                                disabled={isSearching}
                                className="p-2 bg-teal-50 rounded-xl text-slate-700 hover:bg-teal-100 transition-all hover:scale-105 active:scale-95 border border-teal-100 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                                {isSearching ? (
                                    <Loader2 className="w-5 h-5 animate-spin" />
                                ) : (
                                    <ChevronRight className="w-5 h-5" strokeWidth={1.5} />
                                )}
                            </button>
                        </div>
                    </div>
                </form>
            </div>

            {/* 2. Quick Actions */}
            <div className="flex gap-4 my-8">
                {[
                    { label: 'Verifiera påstående', icon: Shield },
                    { label: 'Sammanfatta källa', icon: FileText },
                    { label: 'Jämför dokument', icon: Map }
                ].map((action, i) => (
                    <button key={i} className="flex items-center gap-2 text-xs font-mono text-stone-600 hover:text-teal-800 transition-colors px-4 py-2 rounded-lg hover:bg-white/60 border border-transparent hover:border-stone-300">
                        <action.icon className="w-3 h-3 text-slate-700" strokeWidth={1.5} />
                        {action.label}
                    </button>
                ))}
            </div>

            {/* 3. Glass Card Grid */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full mt-4">
                {GLASS_CARDS.map((card, i) => (
                    <motion.div
                        key={card.id}
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                        transition={{ delay: 0.2 + i * 0.1 }}
                        className="group relative bg-white/70 hover:bg-white border border-stone-200 hover:border-teal-500/30 p-6 rounded-2xl backdrop-blur-md transition-all cursor-pointer hover:-translate-y-1 shadow-sm hover:shadow-lg"
                    >
                        {/* Top Shine */}
                        <div className="absolute inset-x-0 top-0 h-[1px] bg-gradient-to-r from-transparent via-stone-400/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />

                        <div className={`w-10 h-10 rounded-xl ${COLOR_CLASSES[card.color].bg} flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300 border border-white/50`}>
                            <card.icon className="w-5 h-5 text-slate-700" strokeWidth={1.5} />
                        </div>

                        <h3 className="text-stone-900 font-medium mb-2 group-hover:text-teal-800 transition-colors">{card.title}</h3>
                        <p className="text-sm text-stone-600 leading-relaxed font-light">{card.text}</p>

                        <div className="absolute bottom-6 right-6 opacity-0 group-hover:opacity-100 transition-all transform translate-x-2 group-hover:translate-x-0">
                            <ChevronRight className="w-4 h-4 text-slate-700" strokeWidth={1.5} />
                        </div>
                    </motion.div>
                ))}
            </div>
        </div>
    );
}
