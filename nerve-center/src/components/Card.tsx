import { cn } from '../lib/utils'
import type { ReactNode } from 'react'

interface CardProps {
  title: string
  icon?: ReactNode
  children: ReactNode
  className?: string
  headerAction?: ReactNode
}

export function Card({ title, icon, children, className, headerAction }: CardProps) {
  return (
    <div className={cn(
      'bg-[#1a1a24] rounded-xl border border-[#2a2a3a] overflow-hidden',
      className
    )}>
      <div className="flex items-center justify-between px-4 py-3 border-b border-[#2a2a3a]">
        <div className="flex items-center gap-2">
          {icon && <span className="text-zinc-400">{icon}</span>}
          <h3 className="font-semibold text-sm text-zinc-200">{title}</h3>
        </div>
        {headerAction}
      </div>
      <div className="p-4">
        {children}
      </div>
    </div>
  )
}
