import { Activity, RefreshCw, Clock } from 'lucide-react'

interface HeaderProps {
  lastUpdate: number
  onRefresh: () => void
}

export function Header({ lastUpdate, onRefresh }: HeaderProps) {
  const formattedTime = new Date(lastUpdate).toLocaleTimeString('sv-SE', {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit'
  })

  return (
    <header className="sticky top-0 z-50 bg-[#0a0a0f]/80 backdrop-blur-xl border-b border-[#2a2a3a]">
      <div className="max-w-7xl mx-auto px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-gradient-to-br from-purple-500/20 to-blue-500/20 border border-purple-500/30">
            <Activity className="w-5 h-5 text-purple-400" />
          </div>
          <div>
            <h1 className="text-lg font-bold tracking-tight bg-gradient-to-r from-purple-400 to-blue-400 bg-clip-text text-transparent">
              NERVE CENTER
            </h1>
            <p className="text-xs text-zinc-500">Server Monitoring Dashboard</p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center gap-2 text-sm text-zinc-400">
            <Clock className="w-4 h-4" />
            <span className="font-mono">{formattedTime}</span>
          </div>
          <button
            onClick={onRefresh}
            className="p-2 rounded-lg hover:bg-zinc-800 transition-colors"
          >
            <RefreshCw className="w-4 h-4 text-zinc-400" />
          </button>
        </div>
      </div>
    </header>
  )
}
