import { create } from 'zustand';

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || 'http://localhost:8000';
const API_ENDPOINT = `${BACKEND_URL}/api/constitutional/agent/query/stream`;

// Prevent overlapping streams when user iterates quickly.
let activeAbortController: AbortController | null = null;

// Matches backend Source response
export interface Source {
    id: string;
    title: string;
    snippet: string;
    score: number;         // Backend uses "score", not "relevance"
    doc_type: string;      // "prop", "mot", "sou", "bet", "sfs"
    source: string;        // "riksdagen", etc.
}

// Pipeline stages matching backend flow
export type PipelineStage =
    | 'idle'
    | 'query_classification'
    | 'decontextualization'
    | 'retrieval'
    | 'generation'
    | 'guardrail_validation';

export type EvidenceLevel = 'HIGH' | 'MEDIUM' | 'LOW' | null;

export interface PipelineLogEntry {
    ts: number;
    stage: PipelineStage;
    message: string;
}

interface AppState {
    query: string;
    submittedQuery: string;
    queryHistory: string[];
    isSearching: boolean;
    searchStage: 'idle' | 'searching' | 'reading' | 'reasoning' | 'complete' | 'error';
    pipelineStage: PipelineStage;
    selectedPipelineStage: PipelineStage;
    isPipelineDrawerOpen: boolean;
    pipelineLog: PipelineLogEntry[];
    evidenceLevel: EvidenceLevel;
    retrievalStrategy: string | null;
    sources: Source[];
    activeSourceId: string | null;
    hoveredSourceId: string | null;
    lockedSourceId: string | null;
    citationTarget: DOMRect | null;
    connectorCoords: { x: number; y: number } | null;
    answer: string;
    error: string | null;
    currentSearchId: string | null;
    lastStageChangeTimestamp: number;

    setQuery: (q: string) => void;
    startSearch: (mode?: 'auto' | 'chat' | 'assist' | 'evidence') => Promise<void>;
    addQueryToHistory: (q: string) => void;
    // Hover = preview/highlight (unless locked)
    setHoveredSource: (id: string | null) => void;
    // Click = lock/unlock selection
    toggleLockedSource: (id: string) => void;
    // Back-compat (used by older components): acts like hover
    setActiveSource: (id: string | null) => void;
    // Derived helper
    getEffectiveActiveSourceId: () => string | null;
    // Pipeline UI controls
    setSelectedPipelineStage: (stage: PipelineStage) => void;
    togglePipelineDrawer: (force?: boolean) => void;
    setSearchStage: (stage: AppState['searchStage']) => void;
    setCitationTarget: (rect: DOMRect | null) => void;
    setConnectorCoords: (coords: { x: number; y: number } | null) => void;
}

export const useAppStore = create<AppState>((set, get) => ({
    query: '',
    submittedQuery: '',
    queryHistory: [],
    isSearching: false,
    searchStage: 'idle',
    pipelineStage: 'idle',
    selectedPipelineStage: 'query_classification',
    isPipelineDrawerOpen: false,
    pipelineLog: [],
    evidenceLevel: null,
    retrievalStrategy: null,
    sources: [],
    activeSourceId: null,
    hoveredSourceId: null,
    lockedSourceId: null,
    citationTarget: null,
    connectorCoords: null,
    answer: '',
    error: null,
    currentSearchId: null,
    lastStageChangeTimestamp: 0,

    setQuery: (query) => set({ query }),

    addQueryToHistory: (q) =>
        set((state) => {
            const trimmed = q.trim();
            if (!trimmed) return state;
            const next = [trimmed, ...state.queryHistory.filter((x) => x !== trimmed)].slice(0, 12);
            return { queryHistory: next };
        }),

    startSearch: async (mode = 'auto') => {
        const { query } = get();
        if (!query.trim()) return;

        // Abort any in-flight stream before starting a new run.
        if (activeAbortController) {
            activeAbortController.abort();
        }
        activeAbortController = new AbortController();
        const searchId = crypto.randomUUID();

        let generationLogged = false;

        get().addQueryToHistory(query);

        set({
            isSearching: true,
            searchStage: 'searching',
            pipelineStage: 'query_classification',
            submittedQuery: query,
            selectedPipelineStage: 'query_classification',
            isPipelineDrawerOpen: false,
            pipelineLog: [
                {
                    ts: Date.now(),
                    stage: 'query_classification',
                    message: 'Classify: starting pipeline…',
                },
            ],
            activeSourceId: null,
            hoveredSourceId: null,
            lockedSourceId: null,
            citationTarget: null,
            connectorCoords: null,
            sources: [],
            answer: '',
            error: null,
            evidenceLevel: null,
            currentSearchId: searchId,
            lastStageChangeTimestamp: Date.now(),
        });

        // Helper to enforce minimum visual duration for stages
        const updateStageWithDelay = (
            updateFn: () => void,
            minDurationMs: number = 500
        ) => {
            const { lastStageChangeTimestamp, currentSearchId } = get();

            // If search was aborted/changed, don't update
            if (currentSearchId !== searchId) return;

            const now = Date.now();
            const elapsed = now - lastStageChangeTimestamp;
            const remaining = Math.max(0, minDurationMs - elapsed);

            if (remaining > 0) {
                setTimeout(() => {
                    if (get().currentSearchId !== searchId) return;
                    updateFn();
                    set({ lastStageChangeTimestamp: Date.now() });
                }, remaining);
            } else {
                updateFn();
                set({ lastStageChangeTimestamp: Date.now() });
            }
        };

        try {
            const response = await fetch(API_ENDPOINT, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                signal: activeAbortController.signal,
                body: JSON.stringify({
                    question: query,  // Backend expects "question", not "query"
                    mode: mode,
                    history: []       // Empty history for now
                }),
            });

            if (!response.ok) {
                throw new Error(`Backend request failed: ${response.status}`);
            }
            if (!response.body) {
                throw new Error('No response body');
            }

            const reader = response.body.getReader();
            const decoder = new TextDecoder();
            let buffer = '';

            while (true) {
                const { done, value } = await reader.read();
                // Check if we've been superseded by a new search
                if (get().currentSearchId !== searchId) break;

                if (done) break;

                const chunk = decoder.decode(value, { stream: true });
                buffer += chunk;

                // Process SSE lines (events are separated by double newlines)
                const events = buffer.split('\n\n');
                buffer = events.pop() || ''; // Keep incomplete last event

                for (const eventBlock of events) {
                    if (!eventBlock.trim()) continue;

                    // Parse SSE format: "data: {...}"
                    const dataMatch = eventBlock.match(/^data:\s*(.+)$/m);
                    if (!dataMatch) continue;

                    const jsonStr = dataMatch[1];

                    try {
                        const data = JSON.parse(jsonStr);

                        // Handle different event types from backend
                        switch (data.type) {
                            case 'metadata':
                                // Contains mode, sources, evidence_level
                                if (data.sources) {
                                    set({ sources: data.sources });
                                }
                                if (data.evidence_level) {
                                    set({ evidenceLevel: data.evidence_level });
                                }

                                updateStageWithDelay(() => {
                                    set((state) => {
                                        const nextLog: PipelineLogEntry[] = [
                                            ...state.pipelineLog,
                                            {
                                                ts: Date.now(),
                                                stage: 'retrieval',
                                                message: `Retrieval: fetched ${data.sources?.length ?? 0} sources`,
                                            },
                                        ];
                                        return {
                                            pipelineLog: nextLog.slice(-50),
                                            pipelineStage: 'generation',
                                            searchStage: 'reading',
                                        };
                                    });
                                }, 600); // Ensure retrieval takes a bit of time visually
                                break;

                            case 'decontextualized':
                                // Query was rewritten for context
                                updateStageWithDelay(() => {
                                    set((state) => {
                                        const rewritten = typeof data.rewritten === 'string' ? data.rewritten : '';
                                        const nextLog: PipelineLogEntry[] = [
                                            ...state.pipelineLog,
                                            {
                                                ts: Date.now(),
                                                stage: 'decontextualization',
                                                message: rewritten
                                                    ? `Decontext: “${rewritten}”`
                                                    : 'Decontext: query rewritten',
                                            },
                                        ];
                                        return {
                                            pipelineLog: nextLog.slice(-50),
                                            pipelineStage: 'decontextualization',
                                        };
                                    });
                                }, 400); // Ensure decontextualization is visible
                                break;

                            case 'token':
                                // Streaming token content
                                if (data.content) {
                                    if (!generationLogged) {
                                        generationLogged = true;
                                        set((state) => ({
                                            pipelineLog: [
                                                ...state.pipelineLog,
                                                { ts: Date.now(), stage: 'generation' as PipelineStage, message: 'Generate: composing answer…' },
                                            ].slice(-50),
                                        }));
                                    }
                                    set((state) => ({
                                        answer: state.answer + data.content,
                                        pipelineStage: state.pipelineStage === 'generation' ? state.pipelineStage : 'generation',
                                        searchStage: state.searchStage === 'reading' ? state.searchStage : 'reading',
                                    }));
                                }
                                break;

                            case 'corrections':
                                // Guardrail corrections applied
                                set((state) => {
                                    const correctionsCount = Array.isArray(data.corrections)
                                        ? data.corrections.length
                                        : 0;
                                    const nextLog: PipelineLogEntry[] = [
                                        ...state.pipelineLog,
                                        {
                                            ts: Date.now(),
                                            stage: 'guardrail_validation',
                                            message:
                                                correctionsCount > 0
                                                    ? `Validate: ${correctionsCount} corrections applied`
                                                    : 'Validate: corrections applied',
                                        },
                                    ];
                                    return {
                                        pipelineStage: 'guardrail_validation',
                                        pipelineLog: nextLog.slice(-50),
                                    };
                                });
                                if (data.corrected_text) {
                                    set({ answer: data.corrected_text });
                                }
                                break;

                            case 'done':
                                // Stream complete
                                set((state) => ({
                                    searchStage: 'complete',
                                    pipelineStage: 'idle',
                                    isSearching: false,
                                    pipelineLog: [
                                        ...state.pipelineLog,
                                        {
                                            ts: Date.now(),
                                            stage: 'guardrail_validation' as PipelineStage,
                                            message: `Complete: ${typeof data.total_time_ms === 'number' ? `${data.total_time_ms}ms` : 'done'}`,
                                        },
                                    ].slice(-50),
                                }));
                                break;

                            case 'error':
                                // Backend error
                                set((state) => ({
                                    error: data.message || 'Unknown error',
                                    searchStage: 'error',
                                    pipelineStage: 'idle',
                                    isSearching: false,
                                    pipelineLog: [
                                        ...state.pipelineLog,
                                        {
                                            ts: Date.now(),
                                            stage: state.pipelineStage === 'idle' ? 'query_classification' : state.pipelineStage,
                                            message: `Error: ${data.message || 'Unknown error'}`,
                                        },
                                    ].slice(-50),
                                }));
                                break;

                            default:
                            // Unknown event type, log for debugging
                            // console.warn('Unknown SSE event type:', data.type, data);
                        }

                    } catch (e) {
                        console.error('Error parsing SSE data:', e, jsonStr);
                    }
                }
            }

            // Ensure we mark as complete if stream ended without 'done' event
            const currentState = get();
            if (currentState.isSearching && currentState.currentSearchId === searchId) {
                set((state) => ({
                    searchStage: 'complete',
                    pipelineStage: 'idle',
                    isSearching: false,
                    pipelineLog: [
                        ...state.pipelineLog,
                        { ts: Date.now(), stage: 'guardrail_validation' as PipelineStage, message: 'Complete: stream ended' },
                    ].slice(-50),
                }));
            }

        } catch (error) {
            // Ignore aborts (expected when user starts a new query).
            if (error instanceof DOMException && error.name === 'AbortError') {
                return;
            }
            // Check if this error belongs to the current search
            if (get().currentSearchId !== searchId) {
                return;
            }
            console.error('Search failed:', error);
            set({
                isSearching: false,
                searchStage: 'error',
                pipelineStage: 'idle',
                error: error instanceof Error ? error.message : 'Search failed'
            });
        } finally {
            if (activeAbortController?.signal.aborted) {
                // Keep controller cleared on abort
                activeAbortController = null;
            }
        }
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
            const nextActive = nextLocked ?? state.hoveredSourceId;
            return {
                lockedSourceId: nextLocked,
                activeSourceId: nextActive,
            };
        }),

    setActiveSource: (id) => {
        // Back-compat: treat as hover behavior
        get().setHoveredSource(id);
    },

    getEffectiveActiveSourceId: () => {
        const state = get();
        return state.lockedSourceId ?? state.hoveredSourceId;
    },

    setSelectedPipelineStage: (stage) => set({ selectedPipelineStage: stage }),
    togglePipelineDrawer: (force) =>
        set((state) => ({
            isPipelineDrawerOpen: typeof force === 'boolean' ? force : !state.isPipelineDrawerOpen,
        })),

    setSearchStage: (stage) => set({ searchStage: stage }),
    setCitationTarget: (rect) => set({ citationTarget: rect }),
    setConnectorCoords: (coords) => set({ connectorCoords: coords }),
}));
