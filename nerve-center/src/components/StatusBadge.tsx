import { cn } from '../lib/utils'

interface StatusBadgeProps {
  status: 'running' | 'stopped' | 'error' | 'unhealthy'
  size?: 'sm' | 'md'
}

export function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const colors = {
    running: 'bg-green-500',
    stopped: 'bg-zinc-500',
    error: 'bg-red-500',
    unhealthy: 'bg-yellow-500'
  }

  return (
    <span className="relative flex items-center gap-2">
      <span className={cn(
        'rounded-full',
        size === 'sm' ? 'w-2 h-2' : 'w-2.5 h-2.5',
        colors[status]
      )}>
        {status === 'running' && (
          <span className={cn(
            'absolute inset-0 rounded-full animate-ping opacity-75',
            colors[status]
          )} />
        )}
      </span>
      <span className={cn(
        'capitalize font-medium',
        size === 'sm' ? 'text-xs' : 'text-sm',
        status === 'running' && 'text-green-400',
        status === 'stopped' && 'text-zinc-400',
        status === 'error' && 'text-red-400',
        status === 'unhealthy' && 'text-yellow-400'
      )}>
        {status}
      </span>
    </span>
  )
}
