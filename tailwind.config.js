/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./app/web/templates/**/*.html",
    "./app/web/static/js/**/*.js",
  ],
  darkMode: "class",
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui"],
        mono: ["JetBrains Mono", "ui-monospace", "monospace"],
      },
      colors: {
        // OKLCH-based palette via CSS variables in tailwind.input.css
        surface: "var(--color-surface)",
        "surface-2": "var(--color-surface-2)",
        ink: "var(--color-ink)",
        muted: "var(--color-muted)",
        accent: "var(--color-accent)",
        "accent-fg": "var(--color-accent-fg)",
        positive: "var(--color-positive)",
        negative: "var(--color-negative)",
      },
      borderRadius: {
        DEFAULT: "0.5rem",
        lg: "0.75rem",
        xl: "1rem",
      },
      transitionDuration: {
        DEFAULT: "150ms",
      },
    },
  },
  plugins: [],
};
