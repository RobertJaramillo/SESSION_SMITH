import { afterAll, afterEach, beforeAll } from 'vitest';
import { setApiBase } from '../api/client';
import { resetStore } from './handlers';
import { server } from './server';

// Node's fetch needs absolute URLs; point the client at a stub origin the
// MSW node server intercepts.
setApiBase('http://localhost');

beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => {
  server.resetHandlers();
  resetStore();
});
afterAll(() => server.close());
