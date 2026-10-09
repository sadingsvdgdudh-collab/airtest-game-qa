import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';

const html = new URL('./index.html', import.meta.url);
createServer(async (request, response) => {
  if (request.url === '/favicon.ico') { response.writeHead(204).end(); return; }
  if (!['/', '/index.html'].includes(request.url)) { response.writeHead(404).end('Not found'); return; }
  try {
    response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
    response.end(await readFile(html));
  } catch (error) { response.writeHead(500).end('Client unavailable'); console.error(error.message); }
}).listen(3001, '127.0.0.1', () => console.log('Shardy test client: http://127.0.0.1:3001/'));
