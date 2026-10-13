module.exports = {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: { 'dark-bg': '#030712', neon: { cyan: '#22d3ee', violet: '#a78bfa', green: '#34d399' } },
      fontFamily: { mono: ['"JetBrains Mono"', 'ui-monospace', 'monospace'], sans: ['Inter', 'system-ui', 'sans-serif'] },
      boxShadow: {
        'glow-cyan': '0 0 24px rgba(34,211,238,0.18), inset 0 0 0 1px rgba(34,211,238,0.18)',
        'glow-green': '0 0 24px rgba(52,211,153,0.2)',
      },
    },
  },
  plugins: [],
};
