/**
 * GlassMetricCard
 * Metric display with neon accent and icon
 */

import { motion } from 'framer-motion';
import { LucideIcon, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { cn } from '../lib/utils';

export type TrendDirection = 'up' | 'down' | 'neutral';
export type AccentColor = 'cyan' | 'purple' | 'emerald' | 'amber' | 'rose';

interface GlassMetricCardProps {
  title: string;
  value: string | number;
  icon: LucideIcon;
  trend?: {
    value: string;
    direction: TrendDirection;
  };
  accent?: AccentColor;
  className?: string;
  onClick?: () => void;
}

const accentClasses: Record<AccentColor, string> = {
  cyan: 'text-neon-cyan',
  purple: 'text-neon-purple',
  emerald: 'text-neon-emerald',
  amber: 'text-neon-amber',
  rose: 'text-neon-rose',
};

const TrendIcon = ({ direction }: { direction: TrendDirection }) => {
  switch (direction) {
    case 'up':
      return <TrendingUp className="w-4 h-4 text-neon-emerald" />;
    case 'down':
      return <TrendingDown className="w-4 h-4 text-neon-rose" />;
    case 'neutral':
      return <Minus className="w-4 h-4 text-gray-400" />;
  }
};

const trendColorClasses: Record<TrendDirection, string> = {
  up: 'text-neon-emerald',
  down: 'text-neon-rose',
  neutral: 'text-gray-400',
};

export function GlassMetricCard({
  title,
  value,
  icon: Icon,
  trend,
  accent = 'cyan',
  className = '',
  onClick,
}: GlassMetricCardProps) {
  return (
    <motion.div
      className={cn(
        'glass-card glass-card-hover metric-card p-6',
        onClick && 'cursor-pointer',
        className
      )}
      whileHover={onClick ? { scale: 1.02 } : undefined}
      whileTap={onClick ? { scale: 0.98 } : undefined}
      onClick={onClick}
      layout
    >
      {/* Glow Border at Bottom */}
      <div
        className={cn(
          'absolute bottom-0 left-0 h-[2px]',
          accentClasses[accent]
        )}
        style={{
          width: '0%',
          boxShadow: `var(--shadow-glow-${accent})`,
        }}
      />

      {/* Header with Icon */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div
            className={cn(
              'w-10 h-10 rounded-lg flex items-center justify-center',
              accentClasses[accent],
              'bg-opacity-10 border border-current',
              `bg-${accent}-500/10`
            )}
            style={{
              boxShadow: `var(--shadow-glow-${accent})`,
            }}
          >
            <Icon className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm text-gray-400 uppercase tracking-wider font-medium">
              {title}
            </h3>
          </div>
        </div>
      </div>

      {/* Value */}
      <div className="mb-3">
        <div className="text-3xl font-bold text-white tabular-nums">
          {typeof value === 'number' ? value.toLocaleString('sv-SE') : value}
        </div>
      </div>

      {/* Trend Indicator */}
      {trend && (
        <div className="flex items-center gap-2">
          <TrendIcon direction={trend.direction} />
          <span
            className={cn(
              'text-sm font-semibold tabular-nums',
              trendColorClasses[trend.direction]
            )}
          >
            {trend.value}
          </span>
          <span className="text-xs text-gray-500">senaste perioden</span>
        </div>
      )}
    </motion.div>
  );
}
