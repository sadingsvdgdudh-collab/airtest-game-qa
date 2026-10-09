import { createRequire } from 'node:module';
import { createInterface } from 'node:readline';
import { dirname, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { mkdirSync } from 'node:fs';

const here = dirname(fileURLToPath(import.meta.url));
const vendor = resolve(process.argv[2] || process.env.SHARDY_VENDOR || resolve(here, '../../../../work/shardy/vendor/shardy-tictactoe'));
const require = createRequire(resolve(vendor, 'package.json'));
const logDir = resolve(process.env.SHARDY_LOGS || resolve(here, '../../../../work/shardy/logs'));
mkdirSync(logDir, { recursive: true });
process.env.ENV = 'development';
process.env.LOGS_DIR = relative(dirname(require.resolve('shardy')), logDir);
process.env.PULSE_INTERVAL = '1000';
process.env.PULSE_LIMIT = '3';
process.env.REQUEST_TIMEOUT = '5000';
// Keep the third-party logger out of the JSONL response channel.
const output = process.stdout.write.bind(process.stdout);
process.stdout.write = process.stderr.write.bind(process.stderr);
const { Bot, TransportType } = require('shardy');
const { T3Serializer } = require(resolve(vendor, 'dist/T3Serializer.js'));
const { T3Validator } = require(resolve(vendor, 'dist/T3Validator.js'));

let bot;
let sequence = 0;
let messages = [];
let state = { connected: false, matched: false, game: null, player: null, turn: null, score: [0, 0], board: Array(9).fill(null) };
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
function decode(payload) {
  const raw = Buffer.isBuffer(payload.data) ? payload.data.toString() : payload.data;
  let data = raw;
  if (typeof raw === 'string' && raw) {
    try { data = JSON.parse(raw); } catch { /* Preserve non-JSON server data. */ }
  }
  return { type: payload.type, name: payload.name, id: payload.id, error: payload.error, data };
}
function record(payload) {
  const message = decode(payload);
  messages.push({ sequence: ++sequence, time: new Date().toISOString(), ...message });
  // ponytail: retain 1000 messages; the Python evidence collector persists each observation.
  if (messages.length > 1000) messages.shift();
  if (message.name === 'play') state.matched = true;
  if (message.name === 'round') {
    const data = message.data;
    state = { ...state, matched: true, game: data.g, player: data.p, turn: data.t, score: [...data.s], board: Array(9).fill(null) };
  }
  if (message.name === 'turn') {
    const data = message.data;
    state.board[data.y * 3 + data.x] = data.t;
    state.turn = 1 - data.t;
  }
  if (message.name === 'exit') state = { ...state, matched: false, game: null };
}
async function connect(args) {
  if (bot) throw new Error('Disconnect the current client before connecting again');
  const host = args.host || '127.0.0.1';
  const port = args.port ?? 3000;
  if (!['127.0.0.1', 'localhost'].includes(host) || !Number.isInteger(port) || port < 1 || port > 65535) {
    throw new TypeError('Expected a loopback host and integer port in 1..65535');
  }
  messages = [];
  sequence = 0;
  state = { connected: false, matched: false, game: null, player: null, turn: null, score: [0, 0], board: Array(9).fill(null) };
  bot = new Bot(host, port, TransportType.WebSocket, { serializer: new T3Serializer(), validator: new T3Validator(), commands: new Map() }, Buffer.from('gameqa_client'));
  bot.onConnect = () => {
    for (const name of ['play', 'round', 'turn', 'exit']) bot.on(name, record);
  };
  bot.onDisconnect = reason => {
    state.connected = false;
    messages.push({ sequence: ++sequence, time: new Date().toISOString(), name: 'disconnect', data: String(reason) });
  };
  bot.onReady = () => { state.connected = true; };
  await bot.start();
  const deadline = Date.now() + 5000;
  while (!state.connected && Date.now() < deadline) await delay(10);
  if (!state.connected) {
    await disconnect();
    throw new Error('Shardy handshake did not complete in 5 seconds');
  }
  return { host, port, state };
}
async function send(name, data) {
  if (!bot || !state.connected) throw new Error('Client is not connected');
  const response = decode(await bot.fetch(name, data === undefined ? undefined : Buffer.from(JSON.stringify(data))));
  if (response.error) throw new Error(response.error);
  return { response, state };
}
async function disconnect() {
  if (bot) {
    // The official Bot exposes no cancellation for an unfinished connection.
    if (bot.client) await bot.destroy();
    else if (bot.connection) bot.connection.socket.terminate();
    bot = undefined;
  }
  state.connected = false;
  return { state };
}
async function dispatch(op, args) {
  if (op === 'connect') return connect(args);
  if (op === 'disconnect') return disconnect();
  if (op === 'start') return send('start');
  if (op === 'stop') return send('stop');
  if (op === 'exit') {
    const result = await send('exit', { g: args.game ?? state.game, p: args.player ?? state.player });
    state = { ...state, matched: false, game: null };
    return { ...result, state };
  }
  if (op === 'turn') {
    if (!Number.isInteger(args.x) || !Number.isInteger(args.y)) throw new TypeError('x and y must be integers');
    return send('turn', { g: args.game ?? state.game, p: args.player ?? state.player, x: args.x, y: args.y });
  }
  if (op === 'get_messages') {
    const after = args.after ?? 0;
    const waitMs = args.wait_ms ?? 0;
    if (!Number.isInteger(after) || after < 0 || !Number.isInteger(waitMs) || waitMs < 0 || waitMs > 10000) throw new TypeError('Invalid message cursor or wait_ms');
    const end = Date.now() + waitMs;
    while (Date.now() < end && !messages.some(message => message.sequence > after && (!args.name || message.name === args.name))) await delay(20);
    return { cursor: sequence, messages: messages.filter(message => message.sequence > after), state };
  }
  throw new TypeError(`Unknown operation: ${op}`);
}

const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
for await (const line of lines) {
  let request;
  try {
    request = JSON.parse(line);
    if (!request || typeof request !== 'object' || Array.isArray(request) || !('id' in request) || typeof request.op !== 'string' || (request.args && (typeof request.args !== 'object' || Array.isArray(request.args)))) throw new TypeError('Expected {id,op,args} JSON object');
    const result = await dispatch(request.op, request.args || {});
    output(JSON.stringify({ id: request.id, ok: true, result }) + '\n');
  } catch (error) {
    output(JSON.stringify({ id: request?.id ?? null, ok: false, error: { type: error.name, message: error.message } }) + '\n');
  }
}
await disconnect();
