import { useState, useEffect } from 'react'
import { useSystemMetrics } from './hooks/useSystemMetrics'
import { Header } from './components/Header'
import { GpuMonitor } from './components/GpuMonitor'
import { ServicesList } from './components/ServicesList'
import { OllamaPanel } from './components/OllamaPanel'
import { NestDashboard } from './pages/NestDashboard'
import { Activity, AlertTriangle } from 'lucide-react'

// Simple hash-based routing
function useRoute() {
  const [route, setRoute] = useState(window.location.hash.slice(1) || '/')

  useEffect(() => {
    const handleHashChange = () => setRoute(window.location.hash.slice(1) || '/')
    window.addEventListener('hashchange', handleHashChange)
    return () => window.removeEventListener('hashchange', handleHashChange)
  }, [])

  return route
}

function App() {
  const route = useRoute()

  // Route: #nest → Nest Hub Dashboard
  if (route === 'nest' || route === '/nest') {
    return <NestDashboard />
  }

  // Default route: Main dashboard
  return <MainDashboard />
}

function MainDashboard() {
  const { metrics, error, loading, refresh } = useSystemMetrics(2000)

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <Activity className="w-8 h-8 text-purple-400 animate-pulse mx-auto mb-4" />
          <p className="text-zinc-400">Connecting to server...</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <AlertTriangle className="w-8 h-8 text-red-400 mx-auto mb-4" />
          <p className="text-red-400 mb-2">Connection Error</p>
          <p className="text-zinc-500 text-sm">{error}</p>
          <button
            onClick={refresh}
            className="mt-4 px-4 py-2 rounded-lg bg-zinc-800 text-zinc-200 hover:bg-zinc-700 transition-colors"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (!metrics) return null

  return (
    <div className="min-h-screen bg-[#0a0a0f]">
      <Header lastUpdate={metrics.timestamp} onRefresh={refresh} />

      <main className="max-w-7xl mx-auto px-4 py-6">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* GPU Monitor - Full width on mobile, 2/3 on desktop */}
          <GpuMonitor gpu={metrics.gpu} />

          {/* Services - 1/3 on desktop */}
          <div className="lg:col-span-1">
            <ServicesList services={metrics.services} />
          </div>

          {/* Ollama Panel - Full width */}
          <div className="col-span-full">
            <OllamaPanel
              models={metrics.ollama.models}
              running={metrics.ollama.running}
            />
          </div>
        </div>

        {/* Quick Stats */}
        <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-4">
          <QuickStat
            label="GPU Memory"
            value={`${((metrics.gpu.memoryUsed / metrics.gpu.memoryTotal) * 100).toFixed(0)}%`}
            color="purple"
          />
          <QuickStat
            label="Services Running"
            value={`${metrics.services.filter(s => s.status === 'running').length}/${metrics.services.length}`}
            color="green"
          />
          <QuickStat
            label="GPU Temp"
            value={`${metrics.gpu.temperature.toFixed(0)}°C`}
            color="orange"
          />
          <QuickStat
            label="Active Model"
            value={metrics.ollama.running?.split(':')[0] || 'None'}
            color="blue"
          />
        </div>
      </main>
    </div>
  )
}

function QuickStat({ label, value, color }: { label: string; value: string; color: string }) {
  const colors = {
    purple: 'from-purple-500/20 to-purple-500/5 border-purple-500/30',
    green: 'from-green-500/20 to-green-500/5 border-green-500/30',
    orange: 'from-orange-500/20 to-orange-500/5 border-orange-500/30',
    blue: 'from-blue-500/20 to-blue-500/5 border-blue-500/30',
  }

  return (
    <div className={`p-4 rounded-xl bg-gradient-to-br ${colors[color as keyof typeof colors]} border`}>
      <p className="text-xs text-zinc-400 mb-1">{label}</p>
      <p className="text-xl font-bold text-zinc-100 font-mono">{value}</p>
    </div>
  )
}

export { MainDashboard }
export default App
