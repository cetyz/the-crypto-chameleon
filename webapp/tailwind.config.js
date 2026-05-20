/** @type {import('tailwindcss').Config} */
export default {
  content: ['./src/**/*.{html,svelte,ts}'],
  theme: {
    extend: {
      colors: {
        ink: {
          deep: 'oklch(18% 0.012 60)',
          settled: 'oklch(94% 0.008 80)',
          faded: 'oklch(68% 0.012 70)',
          rule: 'oklch(34% 0.012 60)'
        },
        chameleon: 'oklch(74% 0.13 130)'
      },
      fontFamily: {
        serif: ['Newsreader', 'ui-serif', 'Georgia', 'serif'],
        sans: ['Inter', 'ui-sans-serif', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'ui-monospace', 'SFMono-Regular', 'monospace']
      }
    }
  },
  plugins: []
};
