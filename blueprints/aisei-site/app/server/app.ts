import { Hono } from 'hono';
import { logger } from 'hono/logger';
// import { requestId } from 'hono/request-id';
import { secureHeaders } from 'hono/secure-headers';
import { serveStatic } from '@hono/node-server/serve-static';

export const app = new Hono();

// Middleware
app.use('*', logger());
app.use('*', secureHeaders({ xFrameOptions: false }));
// app.use('*', requestId());

// API routes
app.get('/health', (c) => {
  return c.json({ status: 'ok', uptime: process.uptime() });
});

// Static file serving (production/local mode)
app.use('/*', serveStatic({ root: './dist/client/browser' }));
app.get('*', serveStatic({ root: './dist/client/browser', path: '/index.html' }));
