import { motion } from "framer-motion";
import {
  Search,
  Map,
  Shield,
  Zap,
  ChevronRight,
  CornerDownLeft,
  Loader2,
  Sparkles,
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
  verify: "Klistra in ett påstående för att verifiera...",
  summarize: "Ange text eller dokument att sammanfatta...",
  compare: "Ange vad du vill jämföra...",
};

const GLASS_CARDS = [
  {
    id: "verify",
    title: "Snabbverifiering",
    text: "Klistra in ett påstående, få styrkta källor + osäkerheter.",
    icon: Shield,
    color: "cyan" as const,
    mode: "verify" as const,
    example: "Är det grundlagsskyddat att demonstrera utan tillstånd?",
  },
  {
    id: "summarize",
    title: "Källspårning",
    text: "Visa var varje mening kommer ifrån med detaljerade citat.",
    icon: Map,
    color: "emerald" as const,
    mode: "summarize" as const, // Using summarize for trace intent for now based on backend map
    example: "Sammanfatta SOU 2023:25 om AI-förordningen.",
  },
  {
    id: "compare",
    title: "Risk & Bevis",
    text: "Jämför dokument och flagga tveksamma slutsatser.",
    icon: Zap,
    color: "orange" as const,
    mode: "compare" as const,
    example: "Jämför RF 2 kap. med EKMR artikel 10.",
  },
];

const EXAMPLE_QUESTIONS = [
  "Är det tillåtet att bränna koranen enligt svensk lag?",
  "Vad krävs för att ändra en grundlag?",
  "Jämför yttrandefriheten i RF med USA:s First Amendment."
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

  const handleSubmit = (e?: React.FormEvent) => {
    e?.preventDefault();
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

  const handleCardClick = (card: typeof GLASS_CARDS[0]) => {
    setActiveMode(card.mode);
    setQuery(card.example);
    // Optional: focus textarea
    setTimeout(() => textareaRef.current?.focus(), 50);
  };

  const handleExampleClick = (q: string) => {
    setQuery(q);
    // Auto-submit or just fill? Let's just fill for now to let user confirm.
    // But user requested "onramp", so maybe just filling is safer.
    setTimeout(() => textareaRef.current?.focus(), 50);
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
      className="flex flex-col items-center justify-start w-full max-w-4xl mx-auto pt-[min(10vh,4rem)] px-4 sm:px-6"
      animate={{
        opacity: isSearching ? 0.4 : 1,
        scale: isSearching ? 0.98 : 1,
        filter: isSearching ? "blur(2px)" : "blur(0px)"
      }}
      transition={{ duration: 0.15 }}
    >
      {/* 1. Hero Search */}
      <div className="w-full relative z-20 group">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between mb-4 gap-3 px-1">
          {/* Brand with subtle gradient accent */}
          <h1 className="text-xl sm:text-2xl font-light tracking-widest text-stone-900">
            <span className="bg-gradient-to-r from-stone-900 via-teal-800 to-stone-900 bg-clip-text text-transparent animate-gradient">KONSTITUTIONELLA SWERAG</span>{" "}
            <span className="text-teal-700 font-mono text-[10px] sm:text-xs ml-1 sm:ml-2">v3.0</span>
          </h1>

          {/* Mode Selector - Touch-friendly */}
          <div className="flex items-center gap-1 bg-white/40 rounded-lg p-1 border border-stone-300 shadow-sm backdrop-blur-sm self-start sm:self-auto">
            {(["verify", "summarize", "compare"] as const).map((mode) => {
              const labels: Record<typeof mode, string> = {
                verify: "Verifiera",
                summarize: "Sammanfatta",
                compare: "Jämför",
              };
              return (
                <button
                  key={mode}
                  onClick={() => setActiveMode(mode)}
                  className={`min-h-[44px] px-3 py-2 text-xs font-mono rounded-md transition-all focus-ring ${activeMode === mode
                    ? "bg-stone-100 shadow-sm text-teal-800 border border-stone-200 font-medium"
                    : "text-text-muted hover:text-stone-900"
                    }`}
                >
                  {labels[mode]}
                </button>
              );
            })}
          </div>
        </div>

        {/* Input Area */}
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
              className="flex-1 bg-transparent border-none text-base sm:text-lg text-stone-900 font-medium placeholder-text-muted p-4 focus:ring-0 focus:outline-none tracking-wide resize-none overflow-hidden"
              style={{ minHeight: "56px" }}
            />
            <div className="mr-2 sm:mr-4 flex items-center gap-2 sm:gap-3 self-start mt-2 sm:mt-3">
              <span className="text-[10px] font-mono text-text-muted bg-stone-100 px-2 py-1 rounded border border-stone-200 hidden md:block">
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
                aria-label="Skicka fråga"
                className="min-w-[44px] min-h-[44px] p-2.5 bg-teal-50 rounded-xl text-stone-700 hover:bg-teal-100 transition-colors active:scale-95 border border-teal-100 disabled:opacity-50 disabled:cursor-not-allowed focus-ring"
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

        {/* Example Questions (Replaces Pulse) */}
        {!query && (
          <>
            <h2 className="sr-only">Exempelfrågor</h2>
            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {EXAMPLE_QUESTIONS.map((q, i) => (
                <button
                  key={i}
                  onClick={() => handleExampleClick(q)}
                  className="flex items-center gap-1.5 px-3 py-2.5 min-h-[44px] rounded-full bg-stone-100/50 hover:bg-white border border-stone-200 hover:border-teal-300 text-xs text-text-muted hover:text-teal-800 transition-colors cursor-pointer focus-ring"
                >
                  <Sparkles className="w-3 h-3 opacity-60" />
                  <span className="hidden sm:inline">{q}</span>
                  <span className="sm:hidden">{q.length > 35 ? q.slice(0, 35) + "…" : q}</span>
                </button>
              ))}
            </div>
          </>
        )}
      </div>

      {/* 2. Quick Actions / Interactive Cards */}
      <h2 className="sr-only">Kom igång</h2>
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4 sm:gap-6 w-full mt-8 sm:mt-12">
        {GLASS_CARDS.map((card, i) => (
          <motion.button
            key={card.id}
            type="button"
            onClick={() => handleCardClick(card)}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.05 + i * 0.05, duration: 0.2 }}
            className="group relative bg-white/70 hover:bg-white border border-stone-200 hover:border-teal-500/30 p-6 rounded-2xl backdrop-blur-md transition-all cursor-pointer hover:-translate-y-1 shadow-sm hover:shadow-lg text-left w-full"
          >
            {/* Top Shine */}
            <div className="absolute inset-x-0 top-0 h-[1px] bg-gradient-to-r from-transparent via-stone-400/20 to-transparent opacity-0 group-hover:opacity-100 transition-opacity" />

            <div className="flex items-start justify-between mb-4">
              <div
                className={`w-10 h-10 rounded-xl ${COLOR_CLASSES[card.color].bg} flex items-center justify-center group-hover:scale-110 transition-transform duration-300 border border-white/50`}
              >
                <card.icon className="w-5 h-5 text-stone-700" strokeWidth={1.5} />
              </div>
              <div className="opacity-0 group-hover:opacity-100 transition-opacity transform translate-x-2 group-hover:translate-x-0">
                <ChevronRight
                  className="w-4 h-4 text-stone-400"
                  strokeWidth={1.5}
                />
              </div>
            </div>

            <h3 className="text-stone-900 font-medium mb-2 group-hover:text-teal-800 transition-colors">
              {card.title}
            </h3>
            <p className="text-sm text-text-muted leading-relaxed font-light mb-3">
              {card.text}
            </p>
            <div className="text-[10px] font-mono text-text-muted bg-stone-50 inline-block px-2 py-1 rounded border border-stone-100">
              Ex: {card.example.slice(0, 30)}…
            </div>
          </motion.button>
        ))}
      </div>
    </motion.div>
  );
}
