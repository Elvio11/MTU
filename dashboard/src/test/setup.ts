import '@testing-library/jest-dom/vitest';

import { cleanup } from '@testing-library/react';
import { afterEach } from 'vitest';

afterEach(() => {
  cleanup();
});

global.window = global.window || {} as Window & typeof globalThis;
global.navigator = global.navigator || { onLine: true } as Navigator;