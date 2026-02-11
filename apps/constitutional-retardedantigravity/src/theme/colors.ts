export const COLORS = {
  background: '#E7E5E4', // Stone-200
  text: '#1C1917',       // Stone-900
  accentPrimary: '#0F766E',   // Teal-700
  accentSecondary: '#B45309', // Amber-700
  glassBorder: 'rgba(28, 25, 23, 0.1)',
  glassBg: 'rgba(250, 250, 249, 0.6)',
  // WCAG AA semantic text colors
  textMuted: '#57534e',   // Stone-600: 5.2:1 contrast
  textSubtle: '#44403c',  // Stone-700: 7.1:1 contrast
  textDisabled: '#78716c', // Stone-500: 4.5:1 minimum AA
  // User message differentiation
  userBubbleBg: 'rgba(15, 118, 110, 0.08)',
  userBubbleBorder: 'rgba(15, 118, 110, 0.2)',
} as const;

/** Evidence-level color tokens — shared across 2D (Tailwind / framer-motion) and 3D (Three.js hex). */
export const EVIDENCE_COLORS = {
  HIGH: {
    // Tailwind (2D)
    text: 'text-emerald-700',
    textAccent: 'text-emerald-600',
    // Framer-motion rgba (2D animated values)
    bgRgba: 'rgba(5, 150, 105, 0.15)',
    borderRgba: 'rgba(5, 150, 105, 0.4)',
    activeRgba: 'rgba(5, 150, 105, 0.6)',
    // Hex (3D materials)
    emissive: '#059669',
    wireframe: '#34d399',
    accentBar: '#059669',
    label: '#059669',
  },
  MEDIUM: {
    text: 'text-amber-700',
    textAccent: 'text-amber-600',
    bgRgba: 'rgba(217, 119, 6, 0.15)',
    borderRgba: 'rgba(217, 119, 6, 0.4)',
    activeRgba: 'rgba(217, 119, 6, 0.6)',
    emissive: '#B45309',
    wireframe: '#f59e0b',
    accentBar: '#d97706',
    label: '#d97706',
  },
  LOW: {
    text: 'text-red-700',
    textAccent: 'text-red-600',
    bgRgba: 'rgba(220, 38, 38, 0.15)',
    borderRgba: 'rgba(220, 38, 38, 0.4)',
    activeRgba: 'rgba(220, 38, 38, 0.6)',
    emissive: '#dc2626',
    wireframe: '#f87171',
    accentBar: '#dc2626',
    label: '#dc2626',
  },
} as const;

/** Default teal palette used while evidence level is still unknown. */
export const DEFAULT_STAGE_COLORS = {
  bgRgba: 'rgba(15, 118, 110, 0.15)',
  borderRgba: 'rgba(15, 118, 110, 0.4)',
  activeRgba: 'rgba(15, 118, 110, 0.6)',
  text: 'text-teal-700',
  textAccent: 'text-teal-600',
  // 3D defaults (teal)
  emissive: '#0e7490',
  wireframe: '#0891b2',
  accentBar: '#0891b2',
  label: '#0891b2',
} as const;

export type EvidenceLevel = keyof typeof EVIDENCE_COLORS;
