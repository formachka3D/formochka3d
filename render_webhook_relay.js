const http = require('http');
const https = require('https');

const PORT = process.env.PORT || 10000;
const VERIFY_TOKEN = process.env.WEBHOOK_VERIFY_TOKEN || '';
const TARGET_URL = process.env.TARGET_URL || '';

function forward(body) {
  if (!TARGET_URL) return;
  const u = new URL(TARGET_URL);
  const req = https.request({
    hostname: u.hostname,
    port: 443,
    path: u.pathname + u.search,
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Content-Length': Buffer.byteLength(body),
      'User-Agent': 'Formochka3D-Webhook-Relay/1.0'
    },
    timeout: 12000
  }, res => {
    res.resume();
    console.log('forward status', res.statusCode);
  });
  req.on('timeout', () => req.destroy(new Error('forward timeout')));
  req.on('error', err => console.error('forward error', err.message));
  req.write(body);
  req.end();
}

const server = http.createServer((req, res) => {
  const u = new URL(req.url, 'http://localhost');

  if (req.method === 'GET' && u.pathname === '/health') {
    res.writeHead(200, {'Content-Type': 'application/json'});
    return res.end(JSON.stringify({status:'ok', service:'formochka3d-instagram-webhook'}));
  }

  if (req.method === 'GET' && u.pathname === '/instagram/webhook') {
    const mode = u.searchParams.get('hub.mode') || '';
    const token = u.searchParams.get('hub.verify_token') || '';
    const challenge = u.searchParams.get('hub.challenge') || '';
    if (mode === 'subscribe' && token === VERIFY_TOKEN) {
      res.writeHead(200, {'Content-Type': 'text/plain'});
      return res.end(challenge);
    }
    res.writeHead(403, {'Content-Type': 'text/plain'});
    return res.end('Forbidden');
  }

  if (req.method === 'POST' && u.pathname === '/instagram/webhook') {
    let body = '';
    req.on('data', chunk => {
      body += chunk;
      if (body.length > 2_000_000) req.destroy();
    });
    req.on('end', () => {
      forward(body || '{}');
      res.writeHead(200, {'Content-Type': 'text/plain'});
      res.end('EVENT_RECEIVED');
    });
    return;
  }

  res.writeHead(404, {'Content-Type': 'text/plain'});
  res.end('Not found');
});

server.listen(PORT, '0.0.0.0', () => console.log('listening on', PORT));
