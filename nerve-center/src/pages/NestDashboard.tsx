import { useAgentLoop } from '../hooks/useAgentLoop'
import type { ComponentHealth } from '../types'
import {
  MessageSquare,
  Brain,
  Database,
  Shield,
  Server,
  Cpu,
  AlertTriangle,
  Activity,
  ArrowRight,
  Zap
} from 'lucide-react'

// Status color mapping
const statusColors = {
  ok: { bg: 'bg-emerald-500', glow: 'shadow-emerald-500/50', text: 'text-emerald-400', ring: 'ring-emerald-500' },
  degraded: { bg: 'bg-amber-500', glow: 'shadow-amber-500/50', text: 'text-amber-400', ring: 'ring-amber-500' },
  error: { bg: 'bg-red-500', glow: 'shadow-red-500/50', text: 'text-red-400', ring: 'ring-red-500' },
  offline: { bg: 'bg-zinc-600', glow: '', text: 'text-zinc-500', ring: 'ring-zinc-600' },
}

const overallStatusColors = {
  healthy: { bg: 'bg-emerald-500', text: 'text-emerald-400', label: 'ALL SYSTEMS GO' },
  degraded: { bg: 'bg-amber-500', text: 'text-amber-400', label: 'DEGRADED' },
  critical: { bg: 'bg-red-500', text: 'text-red-400', label: 'CRITICAL' },
}

// Pipeline stage icons
const stageIcons = {
  chat: MessageSquare,
  assist: Brain,
  evidence: Database,
  guardian: Shield,
}

// Status indicator with glow effect
function StatusDot({ status, size = 'md' }: { status: ComponentHealth['status']; size?: 'sm' | 'md' | 'lg' }) {
  const colors = statusColors[status]
  const sizes = {
    sm: 'w-3 h-3',
    md: 'w-4 h-4',
    lg: 'w-5 h-5',
  }

  return (
    <div className="relative">
      <div
        className={`${sizes[size]} rounded-full ${colors.bg} ${colors.glow} shadow-lg
          ${status === 'degraded' ? 'animate-pulse-slow' : ''}
          ${status === 'error' ? 'animate-blink' : ''}
        `}
      />
      {status === 'ok' && (
        <div className={`absolute inset-0 ${sizes[size]} rounded-full ${colors.bg} opacity-40 animate-ping-slow`} />
      )}
    </div>
  )
}

// Pipeline node component
function PipelineNode({
  stage,
  health,
  isActive
}: {
  stage: keyof typeof stageIcons
  health: ComponentHealth
  isActive?: boolean
}) {
  const Icon = stageIcons[stage]
  const colors = statusColors[health.status]

  return (
    <div
      className={`
        relative flex flex-col items-center gap-2 p-4 rounded-2xl
        bg-zinc-900/60 backdrop-blur-sm border border-zinc-800/50
        transition-all duration-300
        ${isActive ? 'ring-2 ring-cyan-500/50 shadow-lg shadow-cyan-500/20' : ''}
        ${health.status === 'error' ? 'animate-shake' : ''}
      `}
    >
      {/* Icon */}
      <div className={`p-3 rounded-xl bg-zinc-800/80 ${colors.text}`}>
        <Icon className="w-7 h-7" strokeWidth={1.5} />
      </div>

      {/* Name */}
      <span className="text-base font-semibold text-zinc-200 tracking-tight">
        {stage.toUpperCase()}
      </span>

      {/* Status */}
      <StatusDot status={health.status} size="lg" />

      {/* Latency */}
      {health.latencyMs !== null && (
        <span className={`text-sm font-mono ${colors.text}`}>
          {health.latencyMs}ms
        </span>
      )}
    </div>
  )
}

// Animated arrow between pipeline stages
function PipelineArrow({ active }: { active?: boolean }) {
  return (
    <div className="flex items-center justify-center px-2">
      <div className={`relative ${active ? 'animate-flow' : ''}`}>
        <ArrowRight
          className={`w-6 h-6 ${active ? 'text-cyan-400' : 'text-zinc-600'}`}
          strokeWidth={2}
        />
        {active && (
          <div className="absolute inset-0 animate-pulse">
            <ArrowRight className="w-6 h-6 text-cyan-400 opacity-50" strokeWidth={2} />
          </div>
        )}
      </div>
    </div>
  )
}

// Service card component
function ServiceCard({
  name,
  health,
  icon: Icon,
  detail
}: {
  name: string
  health: ComponentHealth
  icon: typeof Server
  detail?: string
}) {
  const colors = statusColors[health.status]

  return (
    <div className={`
      flex items-center gap-4 p-4 rounded-xl
      bg-zinc-900/60 backdrop-blur-sm border border-zinc-800/50
      ${health.status === 'error' ? 'border-red-500/30' : ''}
    `}>
      <div className={`p-2 rounded-lg bg-zinc-800/80 ${colors.text}`}>
        <Icon className="w-6 h-6" strokeWidth={1.5} />
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="text-base font-semibold text-zinc-200">{name}</span>
          <StatusDot status={health.status} size="sm" />
        </div>
        <p className={`text-sm ${colors.text} truncate`}>
          {health.message || (health.status === 'ok' ? 'Operational' : health.status)}
        </p>
      </div>

      {detail && (
        <span className="text-lg font-mono text-zinc-400">{detail}</span>
      )}
    </div>
  )
}

// Critical alert banner
function CriticalBanner() {
  return (
    <div className="absolute inset-x-0 top-0 z-50 animate-slide-down">
      <div className="bg-red-600/90 backdrop-blur-sm py-3 px-6 flex items-center justify-center gap-3">
        <AlertTriangle className="w-6 h-6 text-white animate-pulse" />
        <span className="text-xl font-bold text-white tracking-wide">
          CRITICAL SYSTEM FAILURE
        </span>
        <AlertTriangle className="w-6 h-6 text-white animate-pulse" />
      </div>
    </div>
  )
}

// Main dashboard component
export function NestDashboard() {
  const { status, loading } = useAgentLoop(3000)

  if (loading || !status) {
    return (
      <div className="w-[1024px] h-[600px] bg-[#0a0a0f] flex items-center justify-center">
        <div className="flex flex-col items-center gap-4">
          <Activity className="w-12 h-12 text-cyan-400 animate-pulse" />
          <span className="text-xl text-zinc-400">Connecting to pipeline...</span>
        </div>
      </div>
    )
  }

  const overallColors = overallStatusColors[status.overallStatus]
  const formattedTime = new Date(status.timestamp).toLocaleTimeString('sv-SE', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })

  // Check if pipeline is active (all stages ok)
  const pipelineActive = status.chat.status === 'ok' &&
                         status.assist.status === 'ok' &&
                         status.evidence.status === 'ok' &&
                         status.guardian.status === 'ok'

  return (
    <div className="w-[1024px] h-[600px] bg-[#0a0a0f] overflow-hidden relative">
      {/* Critical banner */}
      {status.overallStatus === 'critical' && <CriticalBanner />}

      {/* Background gradient */}
      <div className="absolute inset-0 bg-gradient-to-br from-purple-900/10 via-transparent to-cyan-900/10" />

      {/* Content */}
      <div className="relative z-10 h-full flex flex-col p-5 gap-4">

        {/* HEADER */}
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-4">
            <div className="p-2 rounded-xl bg-gradient-to-br from-purple-500/20 to-cyan-500/20 border border-purple-500/30">
              <Zap className="w-7 h-7 text-purple-400" />
            </div>
            <div>
              <h1 className="text-2xl font-black tracking-tight bg-gradient-to-r from-purple-400 via-cyan-400 to-purple-400 bg-clip-text text-transparent">
                NERVE CENTER
              </h1>
              <p className="text-sm text-zinc-500">Agent Loop Pipeline Monitor</p>
            </div>
          </div>

          <div className="flex items-center gap-6">
            <span className="text-lg font-mono text-zinc-400">{formattedTime}</span>
            <div className="flex items-center gap-2">
              <div className={`w-3 h-3 rounded-full ${overallColors.bg} ${
                status.overallStatus === 'healthy' ? 'animate-pulse-slow' :
                status.overallStatus === 'critical' ? 'animate-blink' : 'animate-pulse'
              }`} />
              <span className={`text-base font-bold ${overallColors.text}`}>
                {overallColors.label}
              </span>
            </div>
          </div>
        </header>

        {/* PIPELINE VISUALIZATION - Main feature */}
        <section className="flex-1 flex items-center justify-center">
          <div className="flex items-center gap-1">
            <PipelineNode stage="chat" health={status.chat} isActive={pipelineActive} />
            <PipelineArrow active={pipelineActive && status.chat.status === 'ok'} />
            <PipelineNode stage="assist" health={status.assist} isActive={pipelineActive} />
            <PipelineArrow active={pipelineActive && status.assist.status === 'ok'} />
            <PipelineNode stage="evidence" health={status.evidence} isActive={pipelineActive} />
            <PipelineArrow active={pipelineActive && status.evidence.status === 'ok'} />
            <PipelineNode stage="guardian" health={status.guardian} isActive={pipelineActive} />
          </div>
        </section>

        {/* SERVICE CARDS - Bottom strip */}
        <section className="grid grid-cols-3 gap-4">
          <ServiceCard
            name="OLLAMA"
            health={status.ollama}
            icon={Server}
            detail={`${status.models.filter(m => m.loaded).length} models`}
          />
          <ServiceCard
            name="QDRANT"
            health={status.qdrant}
            icon={Database}
          />
          <ServiceCard
            name="ACTIVE MODEL"
            health={{
              name: 'Model',
              status: status.activeModel ? 'ok' : 'offline',
              latencyMs: status.models.find(m => m.name === status.activeModel)?.latencyMs ?? null,
              message: status.activeModel || 'No model loaded',
              lastCheck: status.timestamp,
            }}
            icon={Cpu}
            detail={status.activeModel?.split(':')[0] || '—'}
          />
        </section>
      </div>

      {/* Custom styles for animations */}
      <style>{`
        @keyframes pulse-slow {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.6; }
        }

        @keyframes ping-slow {
          0% { transform: scale(1); opacity: 0.4; }
          75%, 100% { transform: scale(2); opacity: 0; }
        }

        @keyframes blink {
          0%, 50%, 100% { opacity: 1; }
          25%, 75% { opacity: 0.3; }
        }

        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          10%, 30%, 50%, 70%, 90% { transform: translateX(-2px); }
          20%, 40%, 60%, 80% { transform: translateX(2px); }
        }

        @keyframes flow {
          0%, 100% { opacity: 1; transform: translateX(0); }
          50% { opacity: 0.5; transform: translateX(4px); }
        }

        @keyframes slide-down {
          from { transform: translateY(-100%); }
          to { transform: translateY(0); }
        }

        .animate-pulse-slow {
          animation: pulse-slow 2s ease-in-out infinite;
        }

        .animate-ping-slow {
          animation: ping-slow 2s cubic-bezier(0, 0, 0.2, 1) infinite;
        }

        .animate-blink {
          animation: blink 1s ease-in-out infinite;
        }

        .animate-shake {
          animation: shake 0.5s ease-in-out;
        }

        .animate-flow {
          animation: flow 1.5s ease-in-out infinite;
        }

        .animate-slide-down {
          animation: slide-down 0.3s ease-out;
        }
      `}</style>
    </div>
  )
}

export default NestDashboard
