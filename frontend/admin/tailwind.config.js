/** Midnight Aurora — colours are driven by CSS variables set by ThemeProvider,
 *  so a theme change from the panel restyles the app with no rebuild. */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  // classes composed at runtime ('badge-' + tone) that the content scan can't see
  safelist: ['badge-success', 'badge-danger', 'badge-warning', 'badge-primary'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: 'var(--c-bg)',
        surface: 'var(--c-surface)',
        primary: 'var(--c-primary)',
        secondary: 'var(--c-secondary)',
        success: 'var(--c-success)',
        danger: 'var(--c-danger)',
        warning: 'var(--c-warning)',
        text: 'var(--c-text)',
        muted: 'var(--c-text-muted)',
        border: 'var(--c-border)',
      },
      fontFamily: {
        sans: ['Vazirmatn', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
      borderRadius: { glass: '16px' },
      backdropBlur: { glass: '16px' },
    },
  },
  plugins: [],
}
