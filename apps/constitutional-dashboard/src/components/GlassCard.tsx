/**
 * GlassCard
 * Base glassmorphic card component with hover effects
 */

import { motion, type HTMLMotionProps, type Variants } from 'framer-motion';
import type { ReactNode } from 'react';
import { cn } from '../lib/utils';

interface GlassCardProps extends HTMLMotionProps<'div'> {
  children: ReactNode;
  className?: string;
  variant?: 'default' | 'hover' | 'interactive';
}

const cardVariants: Variants = {
  hidden: { opacity: 0, y: 20, scale: 0.95 },
  visible: {
    opacity: 1,
    y: 0,
    scale: 1,
    transition: {
      duration: 0.4,
      ease: [0.25, 0.1, 0.25, 1],
    },
  },
};

export function GlassCard({
  children,
  className = '',
  variant = 'default',
  ...props
}: GlassCardProps) {
  const baseClasses = cn(
    'glass-card',
    variant === 'hover' && 'glass-card-hover',
    variant === 'interactive' && 'cursor-pointer hover:scale-[1.02]',
    className
  );

  return (
    <motion.div
      variants={cardVariants}
      initial="hidden"
      animate="visible"
      className={baseClasses}
      {...props}
    >
      {children}
    </motion.div>
  );
}
