/**
 * NeonChartWrapper
 * Provides SVG definitions for neon gradients and glow effects
 * Used across all Recharts visualizations
 */

import type { ReactNode } from 'react';

interface NeonChartWrapperProps {
  children: ReactNode;
  className?: string;
}

export function NeonChartWrapper({ children, className = '' }: NeonChartWrapperProps) {
  return (
    <div className={`relative ${className}`}>
      {/* Hidden SVG with all defs for glow effects */}
      <svg width="0" height="0" className="absolute">
        <defs>
          {/* Cyan Gradient */}
          <linearGradient id="neon-cyan-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.1" />
            <stop offset="50%" stopColor="#06b6d4" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#06b6d4" stopOpacity="0.1" />
          </linearGradient>

          {/* Purple Gradient */}
          <linearGradient id="neon-purple-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#7c3aed" stopOpacity="0.1" />
            <stop offset="50%" stopColor="#7c3aed" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#7c3aed" stopOpacity="0.1" />
          </linearGradient>

          {/* Emerald Gradient */}
          <linearGradient id="neon-emerald-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#10b981" stopOpacity="0.1" />
            <stop offset="50%" stopColor="#10b981" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#10b981" stopOpacity="0.1" />
          </linearGradient>

          {/* Amber Gradient */}
          <linearGradient id="neon-amber-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#f59e0b" stopOpacity="0.1" />
            <stop offset="50%" stopColor="#f59e0b" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#f59e0b" stopOpacity="0.1" />
          </linearGradient>

          {/* Rose Gradient */}
          <linearGradient id="neon-rose-gradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#f43f5e" stopOpacity="0.1" />
            <stop offset="50%" stopColor="#f43f5e" stopOpacity="0.8" />
            <stop offset="100%" stopColor="#f43f5e" stopOpacity="0.1" />
          </linearGradient>

          {/* Vertical Gradient for Area Charts */}
          <linearGradient id="neon-cyan-area" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#06b6d4" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#06b6d4" stopOpacity="0" />
          </linearGradient>

          <linearGradient id="neon-emerald-area" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#10b981" stopOpacity="0.4" />
            <stop offset="100%" stopColor="#10b981" stopOpacity="0" />
          </linearGradient>

          {/* Glow Filters */}
          <filter id="glow-cyan" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          <filter id="glow-cyan-strong" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="5" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          <filter id="glow-purple" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          <filter id="glow-emerald" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>

          <filter id="glow-amber" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="3" result="coloredBlur" />
            <feMerge>
              <feMergeNode in="coloredBlur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>
      </svg>

      {/* Chart Content */}
      {children}
    </div>
  );
}

/**
 * Helper to get gradient URL
 */
export const getGradientUrl = (color: 'cyan' | 'purple' | 'emerald' | 'amber' | 'rose') => {
  return `url(#neon-${color}-gradient)`;
};

/**
 * Helper to get area gradient URL
 */
export const getAreaGradientUrl = (color: 'cyan' | 'emerald') => {
  return `url(#neon-${color}-area)`;
};

/**
 * Helper to get glow filter URL
 */
export const getGlowFilterUrl = (color: 'cyan' | 'purple' | 'emerald' | 'amber' | 'rose', strength: 'normal' | 'strong' = 'normal') => {
  return `url(#glow-${color}${strength === 'strong' ? '-strong' : ''})`;
};
