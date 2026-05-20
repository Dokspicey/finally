import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: {
          base: '#0d1117',
          panel: '#1a1a2e',
          elevated: '#161b22',
        },
        border: {
          subtle: '#2a2f3a',
          muted: '#3a3f4a',
        },
        accent: '#ecad0a',
        primary: '#209dd7',
        submit: '#753991',
        up: '#22c55e',
        down: '#ef4444',
        flat: '#a1a1aa',
      },
      fontFamily: {
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      animation: {
        'flash-up': 'flashUp 500ms ease-out',
        'flash-down': 'flashDown 500ms ease-out',
      },
      keyframes: {
        flashUp: {
          '0%': { backgroundColor: 'rgba(34, 197, 94, 0.45)' },
          '100%': { backgroundColor: 'transparent' },
        },
        flashDown: {
          '0%': { backgroundColor: 'rgba(239, 68, 68, 0.45)' },
          '100%': { backgroundColor: 'transparent' },
        },
      },
    },
  },
  plugins: [],
};

export default config;
