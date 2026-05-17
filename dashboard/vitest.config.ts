import { defineConfig } from 'vitest/config';
import path from 'path';

export default defineConfig({
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
    include: ['src/**/*.{test,spec}.{ts,tsx}'],
    coverage: {
      provider: 'v8',
      reporter: ['text', 'json', 'html'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: [
        'src/app/history/page.tsx',
        'src/app/settings/page.tsx',
        'src/app/positions/page.tsx',
        'src/app/agents/page.tsx',
        'src/app/layout.tsx',
        'src/**/*.test.*',
        'src/**/*.spec.*',
        'src/test/**',
      ],
    },
  },
});