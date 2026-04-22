/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        mono: ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
        display: ['"Barlow Condensed"', 'sans-serif'],
        ui: ['"DM Sans"', 'sans-serif'],
      },
      colors: {
        // Core dark system palette
        slate: {
          950: '#020817',
          900: '#0f172a',
          850: '#131f35',
          800: '#1e293b',
          750: '#243347',
          700: '#334155',
        },
        // Status colors
        safe: { DEFAULT: '#10b981', dim: '#064e3b', glow: '#34d39966' },
        warn: { DEFAULT: '#f59e0b', dim: '#451a03', glow: '#fbbf2466' },
        danger: { DEFAULT: '#ef4444', dim: '#450a0a', glow: '#f8717166' },
        // Accent
        cyan: { DEFAULT: '#06b6d4', dim: '#164e63', glow: '#22d3ee55' },
        // Grid / border
        grid: '#1e293b',
      },
      animation: {
        'pulse-danger': 'pulse-danger 0.8s ease-in-out infinite',
        'fade-in': 'fade-in 0.3s ease-out',
        'slide-up': 'slide-up 0.25s ease-out',
        'scan-line': 'scan-line 2s linear infinite',
        'blink': 'blink 1s step-end infinite',
      },
      keyframes: {
        'pulse-danger': {
          '0%, 100%': { boxShadow: '0 0 0 0 rgba(239,68,68,0)' },
          '50%': { boxShadow: '0 0 0 12px rgba(239,68,68,0.35)' },
        },
        'fade-in': {
          from: { opacity: '0' },
          to: { opacity: '1' },
        },
        'slide-up': {
          from: { opacity: '0', transform: 'translateY(8px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'scan-line': {
          '0%': { top: '0%' },
          '100%': { top: '100%' },
        },
        'blink': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0' },
        },
      },
      backgroundImage: {
        'grid-pattern': `
          linear-gradient(rgba(6,182,212,0.04) 1px, transparent 1px),
          linear-gradient(90deg, rgba(6,182,212,0.04) 1px, transparent 1px)
        `,
      },
      backgroundSize: {
        'grid-sm': '24px 24px',
      },
    },
  },
  plugins: [],
}
