// API Types for Constitutional Dashboard

export interface SystemStatus {
  name: string;
  status: 'online' | 'offline';
  latency?: number;
  lastChecked: string;
}

export interface HarvestProgress {
  documentsProcessed: number;
  currentSource: string;
  progress: number;
  eta?: string;
  totalDocuments?: number;
}

export interface SearchResult {
  id: string;
  title: string;
  source: string;
  doc_type: string;
  relevance_score: number;
  snippet: string;
  date: string;
  url?: string;
  excerpt?: string;
  score?: number;
}

export interface BenchmarkData {
  date: string;
  queriesPerDay: number;
  avgLatency: number;
  accuracy: number;
}

export interface HealthResponse {
  status: string;
  timestamp: string;
  [key: string]: any;
}

// Search page specific types
export interface SearchFilters {
  source?: string;
  sources?: string[];
  doc_types?: string[];
  municipality?: string;
  date_from?: string;
  date_to?: string;
  category?: string[];
}

export interface GemmaAnswer {
  text: string;
  sources: string[];
  generating?: boolean;
}

export interface SearchResponse {
  results: SearchResult[];
  total: number;
  query_time_ms: number;
  gemma_answer?: GemmaAnswer;
}

export interface Municipality {
  id: string;
  name: string;
  count?: number;
}

export interface SearchRequest {
  query: string;
  filters: SearchFilters;
  page: number;
  sort: 'relevance' | 'date_desc' | 'date_asc';
}

// Use relative URL or detect host automatically
export const API_BASE = typeof window !== 'undefined'
  ? `http://${window.location.hostname}:8000`
  : 'http://localhost:8000';
