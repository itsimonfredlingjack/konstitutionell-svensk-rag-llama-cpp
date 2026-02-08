import { create } from "zustand";
import {
  GRADING_WATCHDOG_MS,
  MIN_STAGE_DURATION_MS,
  METADATA_STAGE_DELAY_MS,
  GRADING_STAGE_DELAY_MS,
  MAX_PIPELINE_LOG_ENTRIES,
} from "../constants";
import type {
  QueryResult,
  QueryResultMode,
  QueryResultSource,
} from "../types/queryResult";

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || "http://localhost:8900";
const API_ENDPOINT = `${BACKEND_URL}/api/constitutional/agent/query/stream`;

// Prevent overlapping streams when user iterates quickly.
let activeAbortController: AbortController | null = null;
const createSearchId = () => {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }
  return `search-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
};
const scheduleMicrotask =
  typeof queueMicrotask === "function"
    ? queueMicrotask
    : (cb: () => void) => setTimeout(cb, 0);

// Token batching for performance - accumulate tokens and flush with RAF
let tokenBuffer: string[] = [];
let rafId: number | null = null;
let flushCallback: (() => void) | null = null;

const flushTokenBuffer = () => {
  rafId = null;
  if (tokenBuffer.length === 0 || !flushCallback) return;
  flushCallback();
  flushCallback = null;
};

const scheduleTokenFlush = (callback: () => void) => {
  flushCallback = callback;
  if (rafId === null) {
    rafId = requestAnimationFrame(flushTokenBuffer);
  }
};

// Matches backend Source response
export interface Source {
  id: string;
  title: string;
  snippet: string;
  score: number; // Backend uses "score", not "relevance"
  doc_type: string; // "prop", "mot", "sou", "bet", "sfs"
  source: string; // "riksdagen", etc.
}

// Pipeline stages matching backend flow + CRAG
export type PipelineStage =
  | "idle"
  | "query_classification"
  | "decontextualization"
  | "retrieval"
  | "grading" // NY: CRAG Grading
  | "self_reflection" // NY: CRAG Reflection
  | "generation"
  | "guardrail_validation";

export type EvidenceLevel = "HIGH" | "MEDIUM" | "LOW" | null;

export interface PipelineLogEntry {
  ts: number;
  stage: PipelineStage;
  message: string;
}

export type BackendMode = "auto" | "chat" | "assist" | "evidence";

function createQueryResultId(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }
  return `qr-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

function backendModeToUiMode(mode: BackendMode): QueryResultMode {
  if (mode === "evidence") return "verify";
  if (mode === "chat") return "summarize";
  return "compare";
}

function normalizeSources(data: unknown): QueryResultSource[] {
  if (!Array.isArray(data)) return [];
  return data.map((s: Record<string, unknown>) => ({
    id: String(s?.id ?? ""),
    title: String(s?.title ?? ""),
    snippet: String(s?.snippet ?? ""),
    score: Number(s?.score ?? 0),
    doc_type: String(s?.doc_type ?? ""),
    source: String(s?.source ?? ""),
  }));
}

interface AppState {
  viewMode: "hero" | "results";
  query: string;
  activeMode: "verify" | "summarize" | "compare";
  queries: QueryResult[];
  activeQueryId: string | null;
  focusedQueryId: string | null;
  isSearching: boolean;
  currentSearchId: string | null;
  activeSourceId: string | null;
  hoveredSourceId: string | null;
  lockedSourceId: string | null;
  citationTarget: DOMRect | null;
  connectorCoords: { x: number; y: number } | null;

  setQuery: (q: string) => void;
  setActiveMode: (mode: "verify" | "summarize" | "compare") => void;
  startSearch: (mode?: BackendMode, uiMode?: QueryResultMode) => Promise<void>;
  retryQuery: (queryResultId: string) => void;
  setFocusedQuery: (id: string | null) => void;
  setHoveredSource: (id: string | null) => void;
  toggleLockedSource: (id: string) => void;
  setActiveSource: (id: string | null) => void;
  getEffectiveActiveSourceId: () => string | null;
  setSelectedPipelineStage: (stage: PipelineStage) => void;
  togglePipelineDrawer: (force?: boolean) => void;
  setCitationTarget: (rect: DOMRect | null) => void;
  setConnectorCoords: (coords: { x: number; y: number } | null) => void;
  updateQueryResult: (id: string, patch: Partial<QueryResult>) => void;
  resetToHome: () => void;
}

const MAX = MAX_PIPELINE_LOG_ENTRIES;

export const useAppStore = create<AppState>((set, get) => ({
  viewMode: "hero",
  query: "",
  activeMode: "verify",
  queries: [],
  activeQueryId: null,
  focusedQueryId: null,
  isSearching: false,
  currentSearchId: null,
  activeSourceId: null,
  hoveredSourceId: null,
  lockedSourceId: null,
  citationTarget: null,
  connectorCoords: null,

  setQuery: (query) => set({ query }),

  setActiveMode: (mode) => set({ activeMode: mode }),

  setFocusedQuery: (id) => set({ focusedQueryId: id }),

  updateQueryResult: (id, patch) =>
    set((state) => ({
      queries: state.queries.map((q) => (q.id === id ? { ...q, ...patch } : q)),
    })),

  startSearch: async (mode = "auto", uiMode) => {
    const { query } = get();
    if (!query.trim()) return;

    const backendMode = mode;
    const resolvedUiMode = uiMode ?? backendModeToUiMode(backendMode);

    const previousAbortController = activeAbortController;
    let currentAbortController: AbortController | null = null;
    try {
      currentAbortController = new AbortController();
    } catch (abortCreateError) {
      console.warn(
        "[startSearch] AbortController unavailable, continuing without signal",
        abortCreateError,
      );
    }
    activeAbortController = currentAbortController;

    if (previousAbortController) {
      scheduleMicrotask(() => {
        try {
          if (!previousAbortController.signal.aborted) {
            previousAbortController.abort();
          }
        } catch (abortError) {
          console.warn("[startSearch] Abort threw, continuing", abortError);
        }
      });
    }

    const searchId = createSearchId();
    const queryResultId = createQueryResultId();
    const now = Date.now();

    const newResult: QueryResult = {
      id: queryResultId,
      query: query.trim(),
      mode: resolvedUiMode,
      answer: "",
      sources: [],
      pipelineLog: [
        {
          ts: now,
          stage: "query_classification",
          message: "Klassificera: startar pipeline…",
        },
      ],
      searchStage: "searching",
      pipelineStage: "query_classification",
      selectedPipelineStage: "query_classification",
      isPipelineDrawerOpen: false,
      evidenceLevel: null,
      retrievalStrategy: null,
      thoughtChain: null,
      error: null,
      timestamp: now,
      lastStageChangeTimestamp: now,
    };

    set((state) => ({
      viewMode: "results",
      isSearching: true,
      currentSearchId: searchId,
      activeQueryId: queryResultId,
      focusedQueryId: queryResultId,
      activeSourceId: null,
      hoveredSourceId: null,
      lockedSourceId: null,
      citationTarget: null,
      connectorCoords: null,
      queries: [...state.queries, newResult],
    }));

    let generationLogged = false;
    let gradingWatchdog: ReturnType<typeof setTimeout> | null = null;

    const clearGradingWatchdog = () => {
      if (gradingWatchdog) {
        clearTimeout(gradingWatchdog);
        gradingWatchdog = null;
      }
    };

    const armGradingWatchdog = () => {
      clearGradingWatchdog();
      gradingWatchdog = setTimeout(() => {
        if (get().currentSearchId !== searchId) return;
        const active = get().queries.find((q) => q.id === queryResultId);
        if (active?.pipelineStage !== "grading") return;
        get().updateQueryResult(queryResultId, {
          pipelineStage: "generation",
          searchStage: "reasoning",
          pipelineLog: [
            ...(active.pipelineLog || []),
            {
              ts: Date.now(),
              stage: "grading",
              message: "Grading: timeout, proceeding to generation",
            },
          ].slice(-MAX),
        });
      }, GRADING_WATCHDOG_MS);
    };

    const updateStageWithDelay = (
      updateFn: () => void,
      minDurationMs: number = MIN_STAGE_DURATION_MS,
    ) => {
      if (get().currentSearchId !== searchId) return;
      const active = get().queries.find((q) => q.id === queryResultId);
      if (!active) return;
      const now = Date.now();
      const elapsed = now - active.lastStageChangeTimestamp;
      const remaining = Math.max(0, minDurationMs - elapsed);

      if (remaining > 0) {
        setTimeout(() => {
          if (get().currentSearchId !== searchId) return;
          updateFn();
          get().updateQueryResult(queryResultId, {
            lastStageChangeTimestamp: Date.now(),
          });
        }, remaining);
      } else {
        updateFn();
        get().updateQueryResult(queryResultId, {
          lastStageChangeTimestamp: Date.now(),
        });
      }
    };

    try {
      const response = await fetch(API_ENDPOINT, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        ...(currentAbortController
          ? { signal: currentAbortController.signal }
          : {}),
        body: JSON.stringify({
          question: query,
          mode: mode,
          history: [],
        }),
      });

      if (!response.ok)
        throw new Error(`Backend request failed: ${response.status}`);
      if (!response.body) throw new Error("No response body");

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (get().currentSearchId !== searchId) break;
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        buffer += chunk;
        const events = buffer.split("\n\n");
        buffer = events.pop() || "";

        for (const eventBlock of events) {
          if (!eventBlock.trim()) continue;
          const dataMatch = eventBlock.match(/^data:\s*(.+)$/m);
          if (!dataMatch) continue;

          try {
            const data = JSON.parse(dataMatch[1]);

            switch (data.type) {
              case "metadata": {
                if (data.sources)
                  get().updateQueryResult(queryResultId, {
                    sources: normalizeSources(data.sources),
                  });
                if (data.evidence_level)
                  get().updateQueryResult(queryResultId, {
                    evidenceLevel: data.evidence_level,
                  });
                updateStageWithDelay(() => {
                  const active = get().queries.find(
                    (q) => q.id === queryResultId,
                  );
                  if (!active) return;
                  get().updateQueryResult(queryResultId, {
                    pipelineLog: [
                      ...active.pipelineLog,
                      {
                        ts: Date.now(),
                        stage: "retrieval",
                        message: `Retrieval: fetched ${data.sources?.length ?? 0} sources`,
                      },
                    ].slice(-MAX),
                    pipelineStage: "grading",
                    searchStage: "reading",
                  });
                  armGradingWatchdog();
                }, METADATA_STAGE_DELAY_MS);
                break;
              }

              case "grading": {
                clearGradingWatchdog();
                const relevant = data.relevant ?? data.relevant_count ?? 0;
                const total = data.total ?? data.total_count ?? 0;
                const active = get().queries.find(
                  (q) => q.id === queryResultId,
                );
                const shouldAdvance = active?.pipelineStage === "grading";
                updateStageWithDelay(() => {
                  const cur = get().queries.find((q) => q.id === queryResultId);
                  if (!cur) return;
                  get().updateQueryResult(queryResultId, {
                    pipelineLog: [
                      ...cur.pipelineLog,
                      {
                        ts: Date.now(),
                        stage: "grading",
                        message:
                          typeof data.message === "string"
                            ? data.message
                            : `Grading: ${relevant}/${total} documents relevant`,
                      },
                    ].slice(-MAX),
                    pipelineStage: shouldAdvance
                      ? "self_reflection"
                      : cur.pipelineStage,
                  });
                }, GRADING_STAGE_DELAY_MS);
                break;
              }

              case "thought_chain":
                clearGradingWatchdog();
                get().updateQueryResult(queryResultId, {
                  thoughtChain: data.content,
                });
                updateStageWithDelay(() => {
                  const active = get().queries.find(
                    (q) => q.id === queryResultId,
                  );
                  if (!active) return;
                  get().updateQueryResult(queryResultId, {
                    pipelineLog: [
                      ...active.pipelineLog,
                      {
                        ts: Date.now(),
                        stage: "self_reflection",
                        message:
                          "Reflection: analyzing evidence sufficiency...",
                      },
                    ].slice(-MAX),
                    pipelineStage: "generation",
                    searchStage: "reasoning",
                  });
                }, GRADING_STAGE_DELAY_MS);
                break;

              case "token":
                clearGradingWatchdog();
                if (data.content) {
                  if (!generationLogged) {
                    generationLogged = true;
                    const active = get().queries.find(
                      (q) => q.id === queryResultId,
                    );
                    if (active)
                      get().updateQueryResult(queryResultId, {
                        pipelineLog: [
                          ...active.pipelineLog,
                          {
                            ts: Date.now(),
                            stage: "generation",
                            message: "Generate: composing answer…",
                          },
                        ].slice(-MAX),
                      });
                  }
                  tokenBuffer.push(data.content);
                  scheduleTokenFlush(() => {
                    const buffered = tokenBuffer.join("");
                    tokenBuffer = [];
                    const active = get().queries.find(
                      (q) => q.id === queryResultId,
                    );
                    if (!active) return;
                    get().updateQueryResult(queryResultId, {
                      answer: active.answer + buffered,
                      pipelineStage: "generation",
                      searchStage: "reasoning",
                    });
                  });
                }
                break;

              case "corrections": {
                clearGradingWatchdog();
                const active = get().queries.find(
                  (q) => q.id === queryResultId,
                );
                if (active)
                  get().updateQueryResult(queryResultId, {
                    pipelineStage: "guardrail_validation",
                    pipelineLog: [
                      ...active.pipelineLog,
                      {
                        ts: Date.now(),
                        stage: "guardrail_validation",
                        message: `Validate: ${data.corrections?.length || 0} corrections applied`,
                      },
                    ].slice(-MAX),
                  });
                if (data.corrected_text) {
                  const cur = get().queries.find((q) => q.id === queryResultId);
                  if (cur)
                    get().updateQueryResult(queryResultId, {
                      answer: data.corrected_text,
                    });
                }
                break;
              }

              case "done":
                clearGradingWatchdog();
                if (tokenBuffer.length > 0) {
                  const remaining = tokenBuffer.join("");
                  tokenBuffer = [];
                  const active = get().queries.find(
                    (q) => q.id === queryResultId,
                  );
                  if (active)
                    get().updateQueryResult(queryResultId, {
                      answer: active.answer + remaining,
                    });
                }
                if (rafId !== null) {
                  cancelAnimationFrame(rafId);
                  rafId = null;
                }
                flushCallback = null;
                {
                  const active = get().queries.find(
                    (q) => q.id === queryResultId,
                  );
                  if (active)
                    get().updateQueryResult(queryResultId, {
                      searchStage: "complete",
                      pipelineStage: "idle",
                      pipelineLog: [
                        ...active.pipelineLog,
                        {
                          ts: Date.now(),
                          stage: "guardrail_validation",
                          message: `Complete: ${data.total_time_ms ? `${data.total_time_ms.toFixed(0)}ms` : "done"}`,
                        },
                      ].slice(-MAX),
                    });
                }
                set({ isSearching: false, currentSearchId: null });
                break;

              case "error":
                clearGradingWatchdog();
                tokenBuffer = [];
                if (rafId !== null) {
                  cancelAnimationFrame(rafId);
                  rafId = null;
                }
                flushCallback = null;
                {
                  const active = get().queries.find(
                    (q) => q.id === queryResultId,
                  );
                  if (active)
                    get().updateQueryResult(queryResultId, {
                      error: data.message || "Unknown error",
                      searchStage: "error",
                      pipelineStage: "idle",
                      pipelineLog: [
                        ...active.pipelineLog,
                        {
                          ts: Date.now(),
                          stage: "idle",
                          message: `Error: ${data.message}`,
                        },
                      ].slice(-MAX),
                    });
                }
                set({ isSearching: false, currentSearchId: null });
                break;
            }
          } catch (e) {
            console.error("Error parsing SSE data:", e);
          }
        }
      }

      const currentState = get();
      if (
        currentState.isSearching &&
        currentState.currentSearchId === searchId
      ) {
        clearGradingWatchdog();
        const active = get().queries.find((q) => q.id === queryResultId);
        if (active)
          get().updateQueryResult(queryResultId, {
            searchStage: "complete",
            pipelineStage: "idle",
          });
        set({ isSearching: false, currentSearchId: null });
      }
    } catch (error) {
      if (error instanceof DOMException && error.name === "AbortError") {
        return;
      }
      if (get().currentSearchId !== searchId) return;
      clearGradingWatchdog();
      const active = get().queries.find((q) => q.id === queryResultId);
      if (active)
        get().updateQueryResult(queryResultId, {
          searchStage: "error",
          pipelineStage: "idle",
          error: error instanceof Error ? error.message : "Search failed",
        });
      set({ isSearching: false, currentSearchId: null });
    } finally {
      clearGradingWatchdog();
      if (
        activeAbortController === currentAbortController &&
        currentAbortController?.signal.aborted
      ) {
        activeAbortController = null;
      }
    }
  },

  retryQuery: (queryResultId) => {
    const queryResult = get().queries.find((q) => q.id === queryResultId);
    if (!queryResult) return;
    // Remove the failed query and re-run with same parameters
    set((state) => ({
      queries: state.queries.filter((q) => q.id !== queryResultId),
      query: queryResult.query,
    }));
    // Map UI mode back to backend mode
    const modeMap: Record<QueryResultMode, BackendMode> = {
      verify: "evidence",
      summarize: "chat",
      compare: "auto",
    };
    get().startSearch(modeMap[queryResult.mode], queryResult.mode);
  },

  setHoveredSource: (id) =>
    set((state) => ({
      hoveredSourceId: id,
      activeSourceId: state.lockedSourceId ? state.lockedSourceId : id,
    })),
  toggleLockedSource: (id) =>
    set((state) => {
      const isUnlock = state.lockedSourceId === id;
      const nextLocked = isUnlock ? null : id;
      return {
        lockedSourceId: nextLocked,
        activeSourceId: nextLocked ?? state.hoveredSourceId,
      };
    }),
  setActiveSource: (id) => get().setHoveredSource(id),
  getEffectiveActiveSourceId: () => {
    const s = get();
    return s.lockedSourceId ?? s.hoveredSourceId;
  },
  setSelectedPipelineStage: (stage) => {
    const aid = get().activeQueryId;
    if (aid) get().updateQueryResult(aid, { selectedPipelineStage: stage });
  },
  togglePipelineDrawer: (force) => {
    const aid = get().activeQueryId;
    if (!aid) return;
    const active = get().queries.find((q) => q.id === aid);
    if (active)
      get().updateQueryResult(aid, {
        isPipelineDrawerOpen:
          typeof force === "boolean" ? force : !active.isPipelineDrawerOpen,
      });
  },
  setCitationTarget: (rect) => set({ citationTarget: rect }),
  setConnectorCoords: (coords) => set({ connectorCoords: coords }),

  resetToHome: () => {
    if (activeAbortController) {
      try {
        activeAbortController.abort();
      } catch {
        // ignore
      }
      activeAbortController = null;
    }
    tokenBuffer = [];
    if (rafId !== null) {
      cancelAnimationFrame(rafId);
      rafId = null;
    }
    flushCallback = null;
    set({
      viewMode: "hero",
      query: "",
      queries: [], // Clear chat history
      activeQueryId: null,
      focusedQueryId: null,
      isSearching: false,
      currentSearchId: null,
      activeSourceId: null,
      hoveredSourceId: null,
      lockedSourceId: null,
      citationTarget: null,
      connectorCoords: null,
    });
  },
}));
