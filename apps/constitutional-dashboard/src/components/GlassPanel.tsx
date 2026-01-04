/**
 * GlassPanel
 * Large glassmorphic panel for sections and containers
 */

import { motion, type HTMLMotionProps, type Variants } from 'framer-motion';
import type { ReactNode } from 'react';
import { cn } from '../lib/utils';

interface GlassPanelProps extends HTMLMotionProps<'div'> {
  children: ReactNode;
  className?: string;
  variant?: 'default' | 'elevated' | 'border';
}

export function GlassPanel({
  children,
  className = '',
  variant = 'default',
  ...props
}: GlassPanelProps) {
  const variantClasses = {
    default: 'glass-panel',
    elevated: 'glass-panel shadow-glass-lg',
    border: 'glass-panel border-glass-highlight',
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20, scale: 0.98 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.5, ease: 'easeOut' }}
      className={cn(variantClasses[variant], className)}
      {...props}
    >
      {children}
    </motion.div>
  );
}

/**
 * StaggeredContainer - Parent component for staggered child animations
 */
interface StaggeredContainerProps extends HTMLMotionProps<'div'> {
  children: ReactNode;
  staggerDelay?: number;
  className?: string;
}

export const containerVariants: Variants = {
  hidden: { opacity: 0 },
  visible: {
    opacity: 1,
    transition: {
      staggerChildren: 0.1,
      delayChildren: 0.2,
    },
  },
};

export const itemVariants: Variants = {
  hidden: { opacity: 0, y: 20 },
  visible: {
    opacity: 1,
    y: 0,
    transition: {
      duration: 0.4,
      ease: [0.25, 0.1, 0.25, 1],
    },
  },
};

export function StaggeredContainer({
  children,
  staggerDelay = 0.1,
  className = '',
  ...props
}: StaggeredContainerProps) {
  return (
    <motion.div
      variants={{
        hidden: { opacity: 0 },
        visible: {
          opacity: 1,
          transition: {
            staggerChildren: staggerDelay,
            delayChildren: 0.1,
          },
        },
      }}
      initial="hidden"
      animate="visible"
      className={cn('', className)}
      {...props}
    >
      {children}
    </motion.div>
  );
}
