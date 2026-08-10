import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    setupFiles: ['./src/mocks/vitest.setup.ts'],
  },
});
