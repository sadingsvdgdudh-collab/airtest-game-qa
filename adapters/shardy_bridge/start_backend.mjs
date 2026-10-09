import { dirname, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';
import { mkdirSync } from 'node:fs';

const here = dirname(fileURLToPath(import.meta.url));
const vendor = resolve(process.argv[2] || process.env.SHARDY_VENDOR || resolve(here, '../../../../work/shardy/vendor/shardy-tictactoe'));
const require = createRequire(resolve(vendor, 'package.json'));
const logs = resolve(process.env.SHARDY_LOGS || resolve(here, '../../../../work/shardy/logs'));
mkdirSync(logs, { recursive: true });
process.chdir(vendor);
Object.assign(process.env, {
  ENV: 'development', SERVICE_NAME: 'shardy-tictactoe', SERVICE_HOST: '127.0.0.1',
  SERVICE_PORT: process.env.SHARDY_PORT || '3000', SERVICE_TRANSPORT: 'websocket',
  PULSE_INTERVAL: '1000', PULSE_LIMIT: '3', REQUEST_TIMEOUT: '5000',
  LOGS_DIR: relative(dirname(require.resolve('shardy')), logs),
});
require(resolve(vendor, 'dist/app.js'));
