// Admin page types
export interface EmbeddingJob {
  id: string;
  status: 'pending' | 'running' | 'completed' | 'failed' | 'paused';
  source: string;
  doc_type?: string;
  progress: number;
  total: number;
  speed?: number;
  started_at: string;
  completed_at?: string;
  error?: string;
  errors_count?: number;
  duration?: number;
}

export interface CreateJobRequest {
  source: 'Riksdagen' | 'Kommuner' | 'All';
  doc_type?: string;
  date_from?: string;
  date_to?: string;
}

export interface LogEntry {
  timestamp: string;
  level: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';
  source: string;
  message: string;
  details?: string;
}

export interface Workflow {
  id: string;
  name: string;
  active: boolean;
  last_run_status: 'success' | 'error' | 'running' | null;
  last_run_at: string | null;
  execution_count_today: number;
  error_count: number;
}

export interface WorkflowExecution {
  id: string;
  workflow_name: string;
  started_at: string;
  duration: number;
  status: 'success' | 'error' | 'running';
  error_message?: string;
  n8n_url?: string;
}

export const API_BASE = 'http://localhost:8000';
