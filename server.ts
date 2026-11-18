import { spawn, type ChildProcess } from 'node:child_process';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import express from 'express';

const FLASK_HOST = '127.0.0.1';
const FLASK_PORT = Number(process.env.FLASK_PORT || 5001);
const PUBLIC_PORT = Number(process.env.PORT || 3000);

function resolvePythonExecutable(): string {
  const venvPython = path.resolve(process.cwd(), '.venv', 'bin', 'python');
  if (fs.existsSync(venvPython)) {
    return venvPython;
  }
  const winVenvPython = path.resolve(process.cwd(), '.venv', 'Scripts', 'python.exe');
  if (fs.existsSync(winVenvPython)) {
    return winVenvPython;
  }
  return 'python3';
}

function startFlaskBackend(): ChildProcess {
  const pythonBin = resolvePythonExecutable();
  const child = spawn(pythonBin, ['app.py'], {
    cwd: process.cwd(),
    env: {
      ...process.env,
      HOST: FLASK_HOST,
      PORT: String(FLASK_PORT),
      PYTHONUNBUFFERED: '1',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });

  child.stdout?.on('data', (chunk: Buffer) => {
    process.stdout.write(`[flask] ${chunk.toString()}`);
  });
  child.stderr?.on('data', (chunk: Buffer) => {
    process.stderr.write(`[flask] ${chunk.toString()}`);
  });
  child.on('exit', (code, signal) => {
    console.error(`[flask] exited with code=${code} signal=${signal}`);
  });

  return child;
}

async function waitForFlaskReady(timeoutMs = 20000): Promise<void> {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const ok = await new Promise<boolean>((resolve) => {
      const req = http.get(
        {
          hostname: FLASK_HOST,
          port: FLASK_PORT,
          path: '/api/health',
          timeout: 1500,
        },
        (res) => {
          res.resume();
          resolve(res.statusCode === 200);
        }
      );
      req.on('error', () => resolve(false));
      req.on('timeout', () => {
        req.destroy();
        resolve(false);
      });
    });

    if (ok) return;
    await new Promise((r) => setTimeout(r, 250));
  }
  throw new Error(`Flask backend did not become ready on ${FLASK_HOST}:${FLASK_PORT} within ${timeoutMs}ms`);
}

async function main(): Promise<void> {
  const flaskChild = startFlaskBackend();

  const shutdown = () => {
    if (!flaskChild.killed) {
      flaskChild.kill('SIGTERM');
    }
    process.exit(0);
  };

  process.on('SIGINT', shutdown);
  process.on('SIGTERM', shutdown);

  await waitForFlaskReady();

  const app = express();

  app.use((req, res) => {
    const proxyReq = http.request(
      {
        hostname: FLASK_HOST,
        port: FLASK_PORT,
        path: req.originalUrl,
        method: req.method,
        headers: {
          ...req.headers,
          host: `${FLASK_HOST}:${FLASK_PORT}`,
        },
      },
      (proxyRes) => {
        res.status(proxyRes.statusCode || 502);
        for (const [key, value] of Object.entries(proxyRes.headers)) {
          if (value !== undefined) {
            res.setHeader(key, value);
          }
        }
        proxyRes.pipe(res);
      }
    );

    proxyReq.on('error', (err) => {
      console.error('[proxy] error:', err.message);
      if (!res.headersSent) {
        res.status(502).json({ error: 'SignBridge Flask backend is unavailable.' });
      }
    });

    req.pipe(proxyReq);
  });

  app.listen(PUBLIC_PORT, '0.0.0.0', () => {
    console.log(`SignBridge proxy listening on http://0.0.0.0:${PUBLIC_PORT} -> Flask http://${FLASK_HOST}:${FLASK_PORT}`);
  });
}

main().catch((err) => {
  console.error('Failed to start SignBridge server:', err);
  process.exit(1);
});
