/**
 * NeonBadge
 * Status badges with neon glow effects
 */

import { motion, type HTMLMotionProps } from 'framer-motion';
import { cn } from '../lib/utils';

export type BadgeVariant = 'success' | 'warning' | 'error' | 'info' | 'neutral';
export type BadgeSize = 'sm' | 'md' | 'lg';

interface NeonBadgeProps extends Omit<HTMLMotionProps<'span'>, 'variant'> {
  variant?: BadgeVariant;
  size?: BadgeSize;
  children: React.ReactNode;
  icon?: React.ReactNode;
  pulse?: boolean;
}

const variantStyles: Record<BadgeVariant, string> = {
  success: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20 shadow-[0_0_10px_rgba(16,185,129,0.2)]',
  warning: 'bg-amber-500/10 text-amber-400 border-amber-500/20 shadow-[0_0_10px_rgba(245,158,11,0.2)]',
  error: 'bg-rose-500/10 text-rose-400 border-rose-500/20 shadow-[0_0_10px_rgba(244,63,94,0.2)]',
  info: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20 shadow-[0_0_10px_rgba(6,182,212,0.2)]',
  neutral: 'bg-gray-500/10 text-gray-400 border-gray-500/20',
};

const sizeStyles: Record<BadgeSize, string> = {
  sm: 'px-2 py-0.5 text-[10px]',
  md: 'px-3 py-1 text-xs',
  lg: 'px-4 py-1.5 text-sm',
};

const dotStyles: Record<BadgeVariant, string> = {
  success: 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]',
  warning: 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]',
  error: 'bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.5)]',
  info: 'bg-cyan-500 shadow-[0_0_8px_rgba(6,182,212,0.5)]',
  neutral: 'bg-gray-500',
};

export function NeonBadge({
  variant = 'neutral',
  size = 'md',
  children,
  icon,
  pulse = false,
  className = '',
  ...props
}: NeonBadgeProps) {
  return (
    <motion.span
      className={cn(
        'inline-flex items-center gap-2 rounded-full border backdrop-blur-sm font-medium uppercase tracking-wider transition-all duration-300',
        variantStyles[variant],
        sizeStyles[size],
        pulse && 'animate-pulse-neon-cyan',
        className
      )}
      initial={{ opacity: 0, scale: 0.8 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3 }}
      {...props}
    >
      {pulse && (
        <span
          className={cn(
            'w-2 h-2 rounded-full animate-pulse',
            dotStyles[variant]
          )}
        />
      )}
      {icon && <span className="flex-shrink-0">{icon}</span>}
      <span>{children}</span>
    </motion.span>
  );
}

/**
 * StatusDot - Simple pulsing dot for inline status
 */
interface StatusDotProps {
  status: 'online' | 'offline' | 'syncing';
  size?: 'sm' | 'md' | 'lg';
}

export function StatusDot({ status, size = 'md' }: StatusDotProps) {
  const sizeStyles: Record<string, string> = {
    sm: 'w-1.5 h-1.5',
    md: 'w-2 h-2',
    lg: 'w-3 h-3',
  };

  const statusStyles: Record<string, string> = {
    online: 'bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]',
    offline: 'bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.5)]',
    syncing: 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.5)]',
  };

  return (
    <span
      className={cn(
        'rounded-full inline-block animate-pulse',
        sizeStyles[size],
        statusStyles[status]
      )}
    />
  );
}
