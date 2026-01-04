import { useState, useEffect, useCallback } from 'react'
import type { AgentLoopStatus, ComponentHealth, ModelStatus } from '../types'

// API response types (snake_case from Python backend)
interface ApiComponentHealth {
  name: string
  status: 'ok' | 'degraded' | 'error' | 'offline'
  latency_ms: number | null
  message: string | null
  last_check: number
}

interface ApiModelStatus {
  name: string
  loaded: boolean
  responsive: boolean
  latency_ms: number | null
}

interface ApiAgentLoopStatus {
  timestamp: number
  overall_status: 'healthy' | 'degraded' | 'critical'
  chat: ApiComponentHealth
  assist: ApiComponentHealth
  evidence: ApiComponentHealth
  guardian: ApiComponentHealth
  ollama: ApiComponentHealth
  qdrant: ApiComponentHealth
  models: ApiModelStatus[]
  active_model: string | null
}

// Transform snake_case API response to camelCase
function transformComponentHealth(api: ApiComponentHealth): ComponentHealth {
  return {
    name: api.name,
    status: api.status,
    latencyMs: api.latency_ms,
    message: api.message,
    lastCheck: api.last_check,
  }
}

function transformModelStatus(api: ApiModelStatus): ModelStatus {
  return {
    name: api.name,
    loaded: api.loaded,
    responsive: api.responsive,
    latencyMs: api.latency_ms,
  }
}

function transformAgentLoopStatus(api: ApiAgentLoopStatus): AgentLoopStatus {
  return {
    timestamp: api.timestamp,
    overallStatus: api.overall_status,
    chat: transformComponentHealth(api.chat),
    assist: transformComponentHealth(api.assist),
    evidence: transformComponentHealth(api.evidence),
    guardian: transformComponentHealth(api.guardian),
    ollama: transformComponentHealth(api.ollama),
    qdrant: transformComponentHealth(api.qdrant),
    models: api.models.map(transformModelStatus),
    activeModel: api.active_model,
  }
}

// Mock data for development/demo
function getMockData(): AgentLoopStatus {
  const now = Date.now()
  return {
    timestamp: now,
    overallStatus: 'healthy',
    chat: {
      name: 'Chat Interface',
      status: 'ok',
      latencyMs: 45,
      message: null,
      lastCheck: now,
    },
    assist: {
      name: 'AI Assistant',
      status: 'ok',
      latencyMs: 120,
      message: null,
      lastCheck: now,
    },
    evidence: {
      name: 'Evidence Retrieval',
      status: 'degraded',
      latencyMs: 890,
      message: 'High latency detected',
      lastCheck: now,
    },
    guardian: {
      name: 'Constitutional Guardian',
      status: 'ok',
      latencyMs: 35,
      message: null,
      lastCheck: now,
    },
    ollama: {
      name: 'Ollama LLM',
      status: 'ok',
      latencyMs: 15,
      message: '4 models available',
      lastCheck: now,
    },
    qdrant: {
      name: 'Qdrant Vector DB',
      status: 'ok',
      latencyMs: 8,
      message: '230K documents indexed',
      lastCheck: now,
    },
    models: [
      { name: 'ministral-3:14b', loaded: true, responsive: true, latencyMs: 120 },
      { name: 'qwen3:14b', loaded: false, responsive: false, latencyMs: null },
      { name: 'devstral:24b', loaded: false, responsive: false, latencyMs: null },
      { name: 'gpt-oss:20b', loaded: true, responsive: true, latencyMs: 85 },
    ],
    activeModel: 'ministral-3:14b',
  }
}

export function useAgentLoop(pollInterval = 3000) {
  const [status, setStatus] = useState<AgentLoopStatus | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/agent-loop')
      if (!res.ok) {
        // Use mock data if API not available
        if (res.status === 404) {
          setStatus(getMockData())
          setError(null)
          return
        }
        throw new Error(`HTTP ${res.status}: ${res.statusText}`)
      }
      const data: ApiAgentLoopStatus = await res.json()
      setStatus(transformAgentLoopStatus(data))
      setError(null)
    } catch (e) {
      // Fallback to mock data for demo purposes
      setStatus(getMockData())
      setError(null)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchStatus()
    const interval = setInterval(fetchStatus, pollInterval)
    return () => clearInterval(interval)
  }, [fetchStatus, pollInterval])

  return { status, error, loading, refresh: fetchStatus }
}
