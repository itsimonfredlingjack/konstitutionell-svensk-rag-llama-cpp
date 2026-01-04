import { useState, useEffect, useCallback } from 'react'
import type { SystemMetrics, ServiceStatus, OllamaModel } from '../types'

// API response types (snake_case from Python backend)
interface ApiGpuStats {
  name: string
  temperature: number
  utilization: number
  memory_used: number
  memory_total: number
  power: number
  processes: Array<{ pid: number; name: string; memory: number }>
}

interface ApiServiceStatus {
  name: string
  type: string
  status: string
  port: number | null
  pid: number | null
  uptime: number | null
}

interface ApiOllamaModel {
  name: string
  size: number
  loaded: boolean
  vram: number | null
}

interface ApiSystemMetrics {
  timestamp: number
  gpu: ApiGpuStats
  services: ApiServiceStatus[]
  ollama: {
    models: ApiOllamaModel[]
    running: string | null
  }
}

// Transform API response from snake_case to camelCase
function transformMetrics(api: ApiSystemMetrics): SystemMetrics {
  return {
    timestamp: api.timestamp,
    gpu: {
      name: api.gpu.name,
      temperature: api.gpu.temperature,
      utilization: api.gpu.utilization,
      memoryUsed: api.gpu.memory_used,
      memoryTotal: api.gpu.memory_total,
      power: api.gpu.power,
      processes: api.gpu.processes,
    },
    services: api.services.map((s): ServiceStatus => ({
      name: s.name,
      type: s.type as ServiceStatus['type'],
      status: s.status as ServiceStatus['status'],
      port: s.port ?? undefined,
      pid: s.pid ?? undefined,
      uptime: s.uptime ?? undefined,
    })),
    ollama: {
      models: api.ollama.models.map((m): OllamaModel => ({
        name: m.name,
        size: m.size,
        loaded: m.loaded,
        vram: m.vram ?? undefined,
      })),
      running: api.ollama.running,
    },
  }
}

export function useSystemMetrics(pollInterval = 2000) {
  const [metrics, setMetrics] = useState<SystemMetrics | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchMetrics = useCallback(async () => {
    try {
      const res = await fetch('/api/metrics')
      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`)
      }
      const data: ApiSystemMetrics = await res.json()
      setMetrics(transformMetrics(data))
      setError(null)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to fetch metrics')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchMetrics()
    const interval = setInterval(fetchMetrics, pollInterval)
    return () => clearInterval(interval)
  }, [fetchMetrics, pollInterval])

  return { metrics, error, loading, refresh: fetchMetrics }
}
