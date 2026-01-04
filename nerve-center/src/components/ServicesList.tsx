import { Server, Container, Network, RefreshCw, Square, Play } from 'lucide-react'
import { Card } from './Card'
import { StatusBadge } from './StatusBadge'
import { formatUptime } from '../lib/utils'
import type { ServiceStatus } from '../types'

interface ServicesListProps {
  services: ServiceStatus[]
}

function ServiceIcon({ type }: { type: ServiceStatus['type'] }) {
  const icons = {
    systemd: <Server className="w-4 h-4" />,
    docker: <Container className="w-4 h-4" />,
    port: <Network className="w-4 h-4" />,
    ollama: <Server className="w-4 h-4" />
  }
  return <span className="text-zinc-500">{icons[type]}</span>
}

export function ServicesList({ services }: ServicesListProps) {
  const grouped = {
    systemd: services.filter(s => s.type === 'systemd'),
    docker: services.filter(s => s.type === 'docker'),
    port: services.filter(s => s.type === 'port')
  }

  const runningCount = services.filter(s => s.status === 'running').length
  const totalCount = services.length

  return (
    <Card
      title={`Services (${runningCount}/${totalCount})`}
      icon={<Server className="w-4 h-4" />}
      headerAction={
        <button className="p-1.5 rounded-lg hover:bg-zinc-800 transition-colors">
          <RefreshCw className="w-4 h-4 text-zinc-400" />
        </button>
      }
    >
      <div className="space-y-4">
        {/* Systemd Services */}
        {grouped.systemd.length > 0 && (
          <div>
            <p className="text-xs text-zinc-500 mb-2 uppercase tracking-wider">Systemd</p>
            <div className="space-y-1">
              {grouped.systemd.map(service => (
                <ServiceRow key={service.name} service={service} />
              ))}
            </div>
          </div>
        )}

        {/* Docker Containers */}
        {grouped.docker.length > 0 && (
          <div>
            <p className="text-xs text-zinc-500 mb-2 uppercase tracking-wider">Docker</p>
            <div className="space-y-1">
              {grouped.docker.map(service => (
                <ServiceRow key={service.name} service={service} />
              ))}
            </div>
          </div>
        )}

        {/* Port Listeners */}
        {grouped.port.length > 0 && (
          <div>
            <p className="text-xs text-zinc-500 mb-2 uppercase tracking-wider">Ports</p>
            <div className="space-y-1">
              {grouped.port.map(service => (
                <ServiceRow key={service.name} service={service} />
              ))}
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}

function ServiceRow({ service }: { service: ServiceStatus }) {
  return (
    <div className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-zinc-800/50 transition-colors group">
      <div className="flex items-center gap-3">
        <ServiceIcon type={service.type} />
        <div>
          <p className="text-sm font-medium text-zinc-200">{service.name}</p>
          <p className="text-xs text-zinc-500">
            {service.port && `Port ${service.port}`}
            {service.port && service.uptime && ' · '}
            {service.uptime && formatUptime(service.uptime)}
          </p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <StatusBadge status={service.status} size="sm" />
        <div className="opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
          {service.status === 'running' ? (
            <button className="p-1 rounded hover:bg-red-500/20 text-red-400">
              <Square className="w-3 h-3" />
            </button>
          ) : (
            <button className="p-1 rounded hover:bg-green-500/20 text-green-400">
              <Play className="w-3 h-3" />
            </button>
          )}
          <button className="p-1 rounded hover:bg-blue-500/20 text-blue-400">
            <RefreshCw className="w-3 h-3" />
          </button>
        </div>
      </div>
    </div>
  )
}
