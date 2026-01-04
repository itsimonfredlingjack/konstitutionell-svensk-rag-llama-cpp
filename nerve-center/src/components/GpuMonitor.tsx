import { Cpu, Thermometer, Zap } from 'lucide-react'
import { Card } from './Card'
import { cn } from '../lib/utils'
import type { GpuStats } from '../types'

interface GpuMonitorProps {
  gpu: GpuStats
}

function ProgressBar({ value, max, color }: { value: number; max: number; color: string }) {
  const percent = (value / max) * 100
  return (
    <div className="h-2 bg-zinc-800 rounded-full overflow-hidden">
      <div
        className={cn('h-full transition-all duration-500', color)}
        style={{ width: `${percent}%` }}
      />
    </div>
  )
}

export function GpuMonitor({ gpu }: GpuMonitorProps) {
  const memoryPercent = (gpu.memoryUsed / gpu.memoryTotal) * 100

  return (
    <Card
      title={gpu.name}
      icon={<Cpu className="w-4 h-4" />}
      className="col-span-full lg:col-span-2"
    >
      <div className="grid grid-cols-3 gap-6">
        {/* VRAM */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-zinc-400">VRAM</span>
            <span className={cn(
              'font-mono font-medium',
              memoryPercent > 90 ? 'text-red-400' :
              memoryPercent > 70 ? 'text-yellow-400' : 'text-green-400'
            )}>
              {memoryPercent.toFixed(0)}%
            </span>
          </div>
          <ProgressBar
            value={gpu.memoryUsed}
            max={gpu.memoryTotal}
            color={memoryPercent > 90 ? 'bg-red-500' : memoryPercent > 70 ? 'bg-yellow-500' : 'bg-green-500'}
          />
          <p className="text-xs text-zinc-500">
            {gpu.memoryUsed.toFixed(0)} / {gpu.memoryTotal} MiB
          </p>
        </div>

        {/* Utilization */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-sm">
            <span className="text-zinc-400">GPU Load</span>
            <span className="font-mono font-medium text-blue-400">
              {gpu.utilization.toFixed(0)}%
            </span>
          </div>
          <ProgressBar
            value={gpu.utilization}
            max={100}
            color="bg-blue-500"
          />
          <p className="text-xs text-zinc-500">
            Compute utilization
          </p>
        </div>

        {/* Temperature & Power */}
        <div className="space-y-3">
          <div className="flex items-center gap-3">
            <Thermometer className="w-4 h-4 text-orange-400" />
            <div className="flex-1">
              <span className={cn(
                'font-mono font-medium',
                gpu.temperature > 80 ? 'text-red-400' :
                gpu.temperature > 65 ? 'text-orange-400' : 'text-green-400'
              )}>
                {gpu.temperature.toFixed(0)}°C
              </span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <Zap className="w-4 h-4 text-yellow-400" />
            <div className="flex-1">
              <span className="font-mono font-medium text-yellow-400">
                {gpu.power.toFixed(0)}W
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* GPU Processes */}
      {gpu.processes.length > 0 && (
        <div className="mt-4 pt-4 border-t border-[#2a2a3a]">
          <p className="text-xs text-zinc-500 mb-2">Active Processes</p>
          <div className="space-y-1">
            {gpu.processes.map(proc => (
              <div key={proc.pid} className="flex items-center justify-between text-sm">
                <span className="text-zinc-300 font-mono">{proc.name}</span>
                <span className="text-zinc-500 font-mono text-xs">
                  PID {proc.pid} · {proc.memory} MiB
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}
