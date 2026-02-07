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
    <div className="w-full h-full flex flex-col p-6 pointer-events-none bg-transparent">
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
                transition={{ duration: 0.2 }}
                onClick={() => resetToHome()}
                className="text-stone-700 hover:text-teal-700 transition-colors cursor-pointer"
                aria-label="Tillbaka till startsidan"
              >
                <ArrowLeft className="w-5 h-5" strokeWidth={1.5} />
              </motion.button>
            )}
          </AnimatePresence>
          <Shield className="w-5 h-5 text-stone-700" strokeWidth={1.5} />
          {!isHeroMode && (
            <span className="text-sm font-medium tracking-wider text-stone-700">
              CONSTITUTIONAL AI{" "}
              <span className="text-stone-600 font-mono text-xs">v3.0</span>
            </span>
          )}
        </div>
        <div className="flex items-center gap-6 text-[10px] font-mono opacity-60">
          <span>MEM: 24GB</span>
          <span>LATENCY: 12ms</span>
        </div>
      </header>

      {/* MAIN CONTENT ORCHESTRATOR */}
      <main className="flex-1 flex flex-col relative pointer-events-auto bg-transparent min-h-0">
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
