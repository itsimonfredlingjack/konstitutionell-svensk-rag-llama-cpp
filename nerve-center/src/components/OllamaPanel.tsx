import { Brain, Play, Square, HardDrive } from 'lucide-react'
import { Card } from './Card'
import { cn, formatBytes } from '../lib/utils'
import type { OllamaModel } from '../types'

interface OllamaPanelProps {
  models: OllamaModel[]
  running: string | null
}

export function OllamaPanel({ models, running }: OllamaPanelProps) {
  return (
    <Card
      title="Ollama Models"
      icon={<Brain className="w-4 h-4" />}
      headerAction={
        <span className="text-xs text-zinc-500">
          {running ? `Running: ${running.split(':')[0]}` : 'Idle'}
        </span>
      }
    >
      <div className="space-y-2">
        {models.map(model => (
          <div
            key={model.name}
            className={cn(
              'flex items-center justify-between p-3 rounded-lg border transition-all',
              model.loaded
                ? 'bg-green-500/10 border-green-500/30'
                : 'bg-zinc-800/50 border-zinc-700/50 hover:border-zinc-600'
            )}
          >
            <div className="flex items-center gap-3">
              <Brain className={cn(
                'w-5 h-5',
                model.loaded ? 'text-green-400' : 'text-zinc-500'
              )} />
              <div>
                <p className={cn(
                  'font-medium',
                  model.loaded ? 'text-green-300' : 'text-zinc-300'
                )}>
                  {model.name.split(':')[0]}
                </p>
                <p className="text-xs text-zinc-500 flex items-center gap-2">
                  <span className="flex items-center gap-1">
                    <HardDrive className="w-3 h-3" />
                    {formatBytes(model.size)}
                  </span>
                  {model.vram && (
                    <span className="text-green-400">
                      · {model.vram} MiB VRAM
                    </span>
                  )}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              {model.loaded ? (
                <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors text-sm">
                  <Square className="w-3 h-3" />
                  Unload
                </button>
              ) : (
                <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-green-500/20 text-green-400 hover:bg-green-500/30 transition-colors text-sm">
                  <Play className="w-3 h-3" />
                  Load
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </Card>
  )
}
