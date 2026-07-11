/**
 * Design Tokens exported as JavaScript constants
 * Source of truth for all design system values
 * Used in CVA variants and component props
 */

// Color tokens (from CSS variables in index.css and Tailwind config)
export const colors = {
  // Brand colors
  primary: {
    50: '#f8fafc',
    100: '#f1f5f9',
    200: '#e2e8f0',
    300: '#cbd5e1',
    400: '#94a3b8',
    500: '#64748b',
    600: '#475569',
    700: '#334155',
    800: '#1e293b',
    900: '#0f172a', // Deep Navy (primary)
    950: '#020617',
  },
  accent: '#D97706', // Warm Ochre
  
  // Semantic colors
  success: '#059669', // Green
  warning: '#F59E0B', // Amber
  error: '#DC2626', // Red
  info: '#0EA5E9', // Blue
  
  // Neutrals
  foreground: 'var(--foreground)',
  background: 'var(--background)',
  muted: 'var(--muted)',
  mutedForeground: 'var(--muted-foreground)',
  border: 'var(--border)',
};

// Spacing scale (8px base grid)
export const spacing = {
  0: '0',
  1: '0.25rem', // 4px
  2: '0.5rem', // 8px
  3: '0.75rem', // 12px
  4: '1rem', // 16px
  6: '1.5rem', // 24px
  8: '2rem', // 32px
  12: '3rem', // 48px
  16: '4rem', // 64px
  20: '5rem', // 80px
  24: '6rem', // 96px
};

// Border radius scale
export const radius = {
  xs: '0.25rem', // 4px
  sm: '0.5rem', // 8px
  md: '0.75rem', // 12px
  lg: '1rem', // 16px
  xl: '1.5rem', // 24px
  full: '9999px',
};

// Shadow scale (using rgba(15, 23, 42, opacity))
export const shadows = {
  none: 'none',
  xs: '0 1px 2px 0 rgba(15, 23, 42, 0.05)',
  sm: '0 1px 3px 0 rgba(15, 23, 42, 0.1), 0 1px 2px 0 rgba(15, 23, 42, 0.06)',
  md: '0 4px 6px -1px rgba(15, 23, 42, 0.1), 0 2px 4px -1px rgba(15, 23, 42, 0.06)',
  lg: '0 10px 15px -3px rgba(15, 23, 42, 0.1), 0 4px 6px -2px rgba(15, 23, 42, 0.05)',
  xl: '0 20px 25px -5px rgba(15, 23, 42, 0.1), 0 10px 10px -5px rgba(15, 23, 42, 0.04)',
};

// Typography scale (px sizes)
export const typography = {
  scale: {
    'display-xl': { size: '4.5rem', lineHeight: '5.4rem' }, // 72px
    'display-lg': { size: '3.75rem', lineHeight: '4.5rem' }, // 60px
    'display-md': { size: '3rem', lineHeight: '3.6rem' }, // 48px
    'display-sm': { size: '2.25rem', lineHeight: '2.7rem' }, // 36px
    'heading-lg': { size: '2rem', lineHeight: '2.4rem' }, // 32px
    'heading-md': { size: '1.5rem', lineHeight: '1.8rem' }, // 24px
    'heading-sm': { size: '1.25rem', lineHeight: '1.5rem' }, // 20px
    'body-lg': { size: '1.125rem', lineHeight: '1.75rem' }, // 18px
    'body-md': { size: '1rem', lineHeight: '1.5rem' }, // 16px
    'body-sm': { size: '0.875rem', lineHeight: '1.375rem' }, // 14px
    'label-lg': { size: '0.875rem', lineHeight: '1.375rem' }, // 14px (same as body-sm, used contextually)
    'label-md': { size: '0.75rem', lineHeight: '1.125rem' }, // 12px
    'label-sm': { size: '0.75rem', lineHeight: '1.125rem' }, // 12px
    'label-xs': { size: '0.6875rem', lineHeight: '1rem' }, // 11px
  },
  fontFamily: {
    display: '"Cabinet Grotesk", system-ui, sans-serif', // Headlines, nav
    body: '"Manrope", system-ui, sans-serif', // Body, labels
    mono: '"JetBrains Mono", monospace', // Codes, IDs
  },
  fontWeight: {
    light: 300,
    normal: 400,
    medium: 500,
    semibold: 600,
    bold: 700,
    extrabold: 800,
    black: 900,
  },
};

// Breakpoints (mobile-first: base, sm, lg only)
export const breakpoints = {
  base: '0px',
  sm: '640px',
  lg: '1024px',
};

// Container widths
export const containers = {
  xs: '20rem', // 320px
  sm: '24rem', // 384px
  md: '28rem', // 448px
  lg: '32rem', // 512px
  xl: '36rem', // 576px
  '2xl': '42rem', // 672px
  '3xl': '48rem', // 768px
  '4xl': '56rem', // 896px
  '5xl': '64rem', // 1024px
  '6xl': '72rem', // 1152px
  '7xl': '80rem', // 1280px
  full: '100%',
};

// Animation durations
export const animation = {
  fast: '150ms',
  base: '200ms', // Default transition
  slow: '300ms',
  slower: '500ms',
};

// Easing functions
export const easing = {
  linear: 'linear',
  in: 'cubic-bezier(0.4, 0, 1, 1)',
  out: 'cubic-bezier(0, 0, 0.2, 1)',
  inOut: 'cubic-bezier(0.4, 0, 0.2, 1)',
};

export default {
  colors,
  spacing,
  radius,
  shadows,
  typography,
  breakpoints,
  containers,
  animation,
  easing,
};
