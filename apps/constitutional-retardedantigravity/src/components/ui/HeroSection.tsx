import { motion } from "framer-motion";
import {
  Search,
  Map,
  Shield,
  FileText,
  Zap,
  ChevronRight,
  CornerDownLeft,
  Loader2,
} from "lucide-react";
import { useAppStore } from "../../stores/useAppStore";
import { useState, useRef, useEffect } from "react";

// Color mapping for Tailwind classes (must be explicit for build-time)
const COLOR_CLASSES = {
  cyan: {
    bg: "bg-teal-100", // Stone Theme: Teal
    text: "text-teal-800",
  },
  emerald: {
    bg: "bg-emerald-100",
    text: "text-emerald-800",
  },
  orange: {
    bg: "bg-amber-100", // Stone Theme: Amber
    text: "text-amber-800",
  },
} as const;

const PLACEHOLDER_BY_MODE: Record<"verify" | "summarize" | "compare", string> =
{
  verify: "Enter query to verify against constitutional framework...",
  summarize: "Enter text to summarize...",
  compare: "Enter documents to compare...",
};

const GLASS_CARDS = [
  {
    id: "verify",
    title: "Snabbverifiering",
    text: "Klistra in ett påstående, få styrkta källor + osäkerheter.",
    icon: Shield,
    color: "cyan" as const,
  },
  {
    id: "trace",
    title: "Källspårning",
    text: "Visa var varje mening kommer ifrån (citations + hover preview).",
    icon: Map,
    color: "emerald" as const,
  },
  {
    id: "bias",
    title: "Risk & bias-check",
    text: "Flagga tveksamma slutsatser och saknade motkällor.",
    icon: Zap,
    color: "orange" as const,
  },
];

export function HeroSection() {
  const { query, setQuery, startSearch, isSearching } = useAppStore();
  const [activeMode, setActiveMode] = useState<
    "verify" | "summarize" | "compare"
  >("verify");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Map UI modes to backend modes
  const BACKEND_MODE_MAP: Record<
    typeof activeMode,
    "auto" | "chat" | "assist" | "evidence"
  > = {
    verify: "evidence",
    summarize: "chat",
    compare: "auto",
  };

  // Use DOM value as source of truth so click-submit always sees latest (fixes IME/stale state)
  const getValueToSubmit = (): string => {
    const fromDom = textareaRef.current?.value;
    const value = (
      fromDom !== undefined && fromDom !== null ? fromDom : query
    ).trim();
    return value;
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const valueToSubmit = getValueToSubmit();
    if (!valueToSubmit) return;
    if (
      textareaRef.current?.value !== undefined &&
      textareaRef.current.value !== query
    ) {
      setQuery(textareaRef.current.value);
    }
    startSearch(BACKEND_MODE_MAP[activeMode], activeMode);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      const valueToSubmit = getValueToSubmit();
      if (valueToSubmit) startSearch(BACKEND_MODE_MAP[activeMode], activeMode);
    }
  };

  // Blur textarea before submit so IME/composition commits; then submit uses DOM value
  const handleSubmitButtonMouseDown = () => {
    textareaRef.current?.blur();
  };

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height =
        textareaRef.current.scrollHeight + "px";
    }
  }, [query]);

  return (
    <motion.div
      className="flex flex-col items-center justify-center w-full max-w-4xl mx-auto mt-[10vh]"
      animate={{
        opacity: isSearching ? 0.4 : 1,
        scale: isSearching ? 0.98 : 1,
        filter: isSearching ? "blur(2px)" : "blur(0px)"
      }}
      transition={{ duration: 0.2 }}
    >
      {/* 1. Hero Search */}
      <div className="w-full relative z-20 group">
        <div className="flex items-center justify-between mb-4 px-2">
          <h1 className="text-2xl font-light tracking-widest text-stone-900">
            CONSTITUTIONAL AI{" "}
            <span className="text-teal-700 font-mono text-xs ml-2">v3.0</span>
          </h1>

          {/* Mode Selector */}
          <div className="flex items-center gap-1 bg-white/40 rounded-lg p-1 border border-stone-300 shadow-sm backdrop-blur-sm">
            {(["verify", "summarize", "compare"] as const).map((mode) => (
              <button
                key={mode}
                onClick={() => setActiveMode(mode)}
                className={`px-3 py-1 text-xs font-mono rounded-md transition-all ${activeMode === mode
                  ? "bg-stone-100 shadow-sm text-teal-800 border border-stone-200 font-medium"
                  : "text-stone-500 hover:text-stone-900"
                  }`}
              >
                {mode.charAt(0).toUpperCase() + mode.slice(1)}
              </button>
            ))}
          </div>
        </div>

        <form onSubmit={handleSubmit} className="relative">
          <div className="absolute inset-0 bg-teal-500/10 blur-xl rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-500" />

          <div className="relative bg-white/80 border border-stone-300 backdrop-blur-xl rounded-2xl p-2 flex items-center transition-all focus-within:bg-white focus-within:border-teal-600 focus-within:border-1 focus-within:ring-1 focus-within:ring-teal-600/20 shadow-lg hover:border-stone-400">
            <Search
              className="w-6 h-6 text-stone-700 ml-4 self-start mt-4"
              strokeWidth={1.5}
            />
            <textarea
              ref={textareaRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={isSearching}
              aria-label="Search query"
              placeholder={PLACEHOLDER_BY_MODE[activeMode]}
              rows={1}
              className="flex-1 bg-transparent border-none text-lg text-stone-900 font-medium placeholder-stone-400 p-4 focus:ring-0 focus:outline-none tracking-wide resize-none overflow-hidden"
              style={{ minHeight: "60px" }}
            />
            <div className="mr-4 flex items-center gap-3 self-start mt-3">
              <span className="text-[10px] font-mono text-stone-500 bg-stone-100 px-2 py-1 rounded border border-stone-200 hidden md:block">
                Enter{" "}
                <CornerDownLeft
                  className="w-3 h-3 inline ml-1 text-stone-700 opacity-50"
                  strokeWidth={1.5}
                />
              </span>
              <button
                type="submit"
                disabled={isSearching}
                onMouseDown={handleSubmitButtonMouseDown}
                className="p-2 bg-teal-50 rounded-xl text-stone-700 hover:bg-teal-100 transition-all hover:scale-105 active:scale-95 border border-teal-100 disabled:opacity-50 disabled:cursor-not-allowed"
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
          { label: "Verifiera påstående", icon: Shield },
          { label: "Sammanfatta källa", icon: FileText },
          { label: "Jämför dokument", icon: Map },
        ].map((action, i) => (
          <button
            key={i}
            className="flex items-center gap-2 text-xs font-mono text-stone-600 hover:text-teal-800 transition-colors px-4 py-2 rounded-lg hover:bg-white/60 border border-transparent hover:border-stone-300"
          >
            <action.icon className="w-3 h-3 text-stone-700" strokeWidth={1.5} />
            {action.label}
          </button>
        ))}
      </div>

      {/* 3. Glass Card Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 w-full mt-4">
        {GLASS_CARDS.map((card, i) => (
          <motion.button
            key={card.id}
            type="button"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 + i * 0.1 }}
            className="group relative bg-white/70 hover:bg-white border border-stone-200 hover:border-teal-500/30 p-6 rounded-2xl backdrop-blur-md transition-all cursor-pointer hover:-translate-y-1 shadow-sm hover:shadow-lg text-left w-full"
          >
            {/* Top Shine */}
            <div className="absolute inset-x-0 top-0 h-[1px] bg-gradient-to-r from-transparent via-stone-400/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />

            <div
              className={`w-10 h-10 rounded-xl ${COLOR_CLASSES[card.color].bg} flex items-center justify-center mb-4 group-hover:scale-110 transition-transform duration-300 border border-white/50`}
            >
              <card.icon className="w-5 h-5 text-stone-700" strokeWidth={1.5} />
            </div>

            <h3 className="text-stone-900 font-medium mb-2 group-hover:text-teal-800 transition-colors">
              {card.title}
            </h3>
            <p className="text-sm text-stone-600 leading-relaxed font-light">
              {card.text}
            </p>

            <div className="absolute bottom-6 right-6 opacity-0 group-hover:opacity-100 transition-all transform translate-x-2 group-hover:translate-x-0">
              <ChevronRight
                className="w-4 h-4 text-stone-700"
                strokeWidth={1.5}
              />
            </div>
          </motion.button>
        ))}
      </div>
    </motion.div>
  );
}
