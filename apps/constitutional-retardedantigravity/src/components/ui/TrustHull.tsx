import { AnimatePresence, motion } from "framer-motion";
import { useAppStore } from "../../stores/useAppStore";
import { HeroSection } from "./HeroSection";
import { ChatView } from "./ChatView";
import { CitationPreview } from "./CitationPreview";
import { ConnectorOverlay } from "./ConnectorOverlay";
import { Shield, ArrowLeft } from "lucide-react";

export function TrustHull() {
  const { viewMode, resetToHome } = useAppStore();
  const isHeroMode = viewMode === "hero";

  return (
    <div className="w-full h-full flex flex-col p-4 sm:p-6 pointer-events-none bg-transparent">
      {/* GLOBAL HEADER (Minimal) */}
      <header className="flex items-center justify-between text-stone-500 mb-4 pointer-events-auto z-50 bg-transparent">
        <div className="flex items-center gap-3">
          <AnimatePresence>
            {!isHeroMode && (
              <motion.button
                key="back-btn"
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: -8 }}
                transition={{ duration: 0.15 }}
                onClick={() => resetToHome()}
                className="min-w-[44px] min-h-[44px] flex items-center justify-center text-stone-700 hover:text-teal-700 transition-colors cursor-pointer rounded-lg hover:bg-stone-200/50 focus-ring"
                aria-label="Tillbaka till startsidan"
              >
                <ArrowLeft className="w-5 h-5" strokeWidth={1.5} />
              </motion.button>
            )}
          </AnimatePresence>
          <Shield className="w-5 h-5 text-teal-700" strokeWidth={1.5} />
          {!isHeroMode && (
            <span className="text-sm font-medium tracking-wider">
              <span className="bg-gradient-to-r from-stone-800 via-teal-700 to-stone-800 bg-clip-text text-transparent animate-gradient">KONSTITUTIONELLA SWERAG</span>{" "}
              <span className="text-text-muted font-mono text-xs">v3.0</span>
            </span>
          )}
        </div>
        {/* Premium Status Indicator */}
        <div
          className="flex items-center gap-2 px-3 py-1.5 rounded-full bg-emerald-50/80 border border-emerald-200/50 backdrop-blur-sm"
          title="Alla systemtjänster körs normalt"
          role="status"
          aria-label="System online"
        >
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
          <span className="text-xs font-medium text-emerald-700">Live</span>
        </div>
      </header>

      {/* MAIN CONTENT ORCHESTRATOR */}
      <main id="main-content" className="flex-1 flex flex-col relative pointer-events-auto bg-transparent min-h-0">
        <AnimatePresence mode="wait" initial={false}>
          {isHeroMode ? (
            <motion.div
              key="hero"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="flex-1 flex flex-col min-h-0"
            >
              <HeroSection />
            </motion.div>
          ) : (
            <motion.div
              key="results"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.15 }}
              className="flex-1 flex flex-col min-h-0"
            >
              <ChatView />
            </motion.div>
          )}
        </AnimatePresence>

        {/* Floating Portal for Hover Previews */}
        <CitationPreview />

        {/* Connector Lines Overlay */}
        <ConnectorOverlay />
      </main>
    </div>
  );
}
