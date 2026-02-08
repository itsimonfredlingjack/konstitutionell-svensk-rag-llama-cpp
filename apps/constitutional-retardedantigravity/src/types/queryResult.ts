/**
 * One question + full RAG result. Used in the chat-like flow (queries array).
 */
export interface QueryResultSource {
  id: string;
  title: string;
  snippet: string;
  score: number;
  doc_type: string;
  source: string;
}

export interface QueryResultPipelineLogEntry {
  ts: number;
  stage: string;
  message: string;
}

export type QueryResultMode = "verify" | "summarize" | "compare";

export interface QueryResult {
  id: string;
  query: string;
  mode: QueryResultMode;
  answer: string;
  sources: QueryResultSource[];
  pipelineLog: QueryResultPipelineLogEntry[];
  searchStage: string;
  pipelineStage: string;
  selectedPipelineStage: string | null;
  isPipelineDrawerOpen: boolean;
  evidenceLevel: string | null;
  retrievalStrategy: string | null;
  thoughtChain: unknown | null;
  error: string | null;
  timestamp: number;
  lastStageChangeTimestamp: number;
}
