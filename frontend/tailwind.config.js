import defaultTheme from 'tailwindcss/defaultTheme.js'

// Every text size is larger in the same proportion, so that text-sm (0.875rem) becomes 1rem and the rest follows
// (text-xs 0.857rem, text-base 1.143rem, text-lg 1.286rem, ...). Only the text grows: spacing and widths stay as they were.
const SCALE = 1 / 0.875
const grow = (value) => (typeof value === 'string' && value.endsWith('rem') ? `${+(parseFloat(value) * SCALE).toFixed(4)}rem` : value)
const fontSize = Object.fromEntries(
  Object.entries(defaultTheme.fontSize).map(([name, [size, options]]) => [
    name,
    [grow(size), typeof options === 'string' ? options : { ...options, lineHeight: grow(options.lineHeight) }],
  ]),
)

/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: { fontSize },
  },
  plugins: [],
}
