import { serve } from '@hono/node-server';
import { config } from './app.config.js';
import { app } from './app.js';

const port = config.port;

serve({ fetch: app.fetch, port }, (info) => {
  console.log(`[server] listening on http://localhost:${info.port}`);
});
