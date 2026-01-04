export interface ServiceStatus {
  name: string
  type: 'systemd' | 'docker' | 'port' | 'ollama'
  status: 'running' | 'stopped' | 'error' | 'unhealthy'
  port?: number
  pid?: number
  uptime?: number
  memory?: number
  cpu?: number
}

export interface GpuStats {
  name: string
  temperature: number
  utilization: number
  memoryUsed: number
  memoryTotal: number
  power: number
  processes: GpuProcess[]
}

export interface GpuProcess {
  pid: number
  name: string
  memory: number
}

export interface OllamaModel {
  name: string
  size: number
  loaded: boolean
  vram?: number
}

export interface SystemMetrics {
  timestamp: number
  gpu: GpuStats
  services: ServiceStatus[]
  ollama: {
    models: OllamaModel[]
    running: string | null
  }
}

// Agent Loop Types (Constitutional AI Pipeline)
export interface ComponentHealth {
  name: string
  status: 'ok' | 'degraded' | 'error' | 'offline'
  latencyMs: number | null
  message: string | null
  lastCheck: number
}

export interface ModelStatus {
  name: string
  loaded: boolean
  responsive: boolean
  latencyMs: number | null
}

export interface AgentLoopStatus {
  timestamp: number
  overallStatus: 'healthy' | 'degraded' | 'critical'

  // Pipeline stages
  chat: ComponentHealth
  assist: ComponentHealth
  evidence: ComponentHealth
  guardian: ComponentHealth

  // Core services
  ollama: ComponentHealth
  qdrant: ComponentHealth

  // Models
  models: ModelStatus[]
  activeModel: string | null
}
