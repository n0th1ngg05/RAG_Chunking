const util = require("util");

// ANSI color escape sequences
const c = {
  reset: "\x1b[0m",
  bold: "\x1b[1m",
  dim: "\x1b[2m",
  italic: "\x1b[3m",
  underline: "\x1b[4m",

  // Foreground colors
  black: "\x1b[30m",
  red: "\x1b[31m",
  green: "\x1b[32m",
  yellow: "\x1b[33m",
  blue: "\x1b[34m",
  magenta: "\x1b[35m",
  cyan: "\x1b[36m",
  white: "\x1b[37m",
  gray: "\x1b[90m",

  // Bright colors
  brightRed: "\x1b[91m",
  brightGreen: "\x1b[92m",
  brightYellow: "\x1b[93m",
  brightBlue: "\x1b[94m",
  brightMagenta: "\x1b[95m",
  brightCyan: "\x1b[96m",
  brightWhite: "\x1b[97m",

  // Background colors
  bgRed: "\x1b[41m",
  bgGreen: "\x1b[42m",
  bgYellow: "\x1b[43m",
  bgBlue: "\x1b[44m",
  bgMagenta: "\x1b[45m",
  bgCyan: "\x1b[46m",
  bgWhite: "\x1b[47m",
};

function timestamp() {
  const d = new Date();
  const pad = (n, len = 2) => String(n).padStart(len, "0");
  const y = d.getFullYear();
  const m = pad(d.getMonth() + 1);
  const day = pad(d.getDate());
  const h = pad(d.getHours());
  const min = pad(d.getMinutes());
  const s = pad(d.getSeconds());
  const ms = pad(d.getMilliseconds(), 3);
  return `${c.dim}${y}-${m}-${day} ${h}:${min}:${s}.${ms}${c.reset}`;
}

function formatArgs(args) {
  return args
    .map((arg) => {
      if (arg instanceof Error) {
        return `\n${c.brightRed}${arg.stack || arg.message}${c.reset}`;
      }
      if (typeof arg === "object" && arg !== null) {
        return util.inspect(arg, { colors: true, depth: 4, compact: false });
      }
      return arg;
    })
    .join(" ");
}

const prefix = `${c.bold}${c.brightBlue}[NODE-API]${c.reset}`;

const logger = {
  colors: c,

  info(msg, ...args) {
    const badge = `${c.bold}${c.brightCyan}INFO   ${c.reset}`;
    console.log(`${timestamp()} ${prefix} ${badge} ${msg} ${formatArgs(args)}`.trimEnd());
  },

  success(msg, ...args) {
    const badge = `${c.bold}${c.brightGreen}SUCCESS${c.reset}`;
    console.log(`${timestamp()} ${prefix} ${badge} ${msg} ${formatArgs(args)}`.trimEnd());
  },

  warn(msg, ...args) {
    const badge = `${c.bold}${c.brightYellow}WARN   ${c.reset}`;
    console.warn(`${timestamp()} ${prefix} ${badge} ${c.yellow}${msg}${c.reset} ${formatArgs(args)}`.trimEnd());
  },

  error(msg, ...args) {
    const badge = `${c.bold}${c.brightRed}ERROR  ${c.reset}`;
    console.error(`${timestamp()} ${prefix} ${badge} ${c.brightRed}${msg}${c.reset} ${formatArgs(args)}`.trimEnd());
  },

  debug(msg, ...args) {
    if (process.env.NODE_ENV === "production" && !process.env.DEBUG) return;
    const badge = `${c.dim}DEBUG  ${c.reset}`;
    console.log(`${timestamp()} ${prefix} ${badge} ${c.gray}${msg}${c.reset} ${formatArgs(args)}`.trimEnd());
  },

  http(method, url, status, durationMs, details = "") {
    let methodColor = c.white;
    switch (method.toUpperCase()) {
      case "GET":
        methodColor = `${c.bold}${c.brightCyan}`;
        break;
      case "POST":
        methodColor = `${c.bold}${c.brightGreen}`;
        break;
      case "PUT":
      case "PATCH":
        methodColor = `${c.bold}${c.brightYellow}`;
        break;
      case "DELETE":
        methodColor = `${c.bold}${c.brightRed}`;
        break;
    }

    let statusColor = c.green;
    if (status >= 500) statusColor = `${c.bold}${c.brightRed}`;
    else if (status >= 400) statusColor = `${c.bold}${c.brightYellow}`;
    else if (status >= 300) statusColor = `${c.bold}${c.cyan}`;
    else if (status >= 200) statusColor = `${c.bold}${c.brightGreen}`;

    let durationColor = c.brightGreen;
    if (durationMs > 1000) durationColor = c.brightRed;
    else if (durationMs > 200) durationColor = c.brightYellow;

    const extra = details ? ` ${c.dim}(${details})${c.reset}` : "";
    console.log(
      `${timestamp()} ${prefix} ${c.bold}${c.blue}[HTTP]${c.reset} ${methodColor}${method.padEnd(6)}${c.reset} ${c.white}${url}${c.reset} -> ${statusColor}${status}${c.reset} in ${durationColor}${durationMs.toFixed(1)}ms${c.reset}${extra}`
    );
  },

  auth(msg, ...args) {
    const tag = `${c.bold}${c.brightMagenta}[AUTH]${c.reset}`;
    console.log(`${timestamp()} ${prefix} ${tag} ${msg} ${formatArgs(args)}`.trimEnd());
  },

  upload(msg, ...args) {
    const tag = `${c.bold}${c.brightCyan}[UPLOAD]${c.reset}`;
    console.log(`${timestamp()} ${prefix} ${tag} ${msg} ${formatArgs(args)}`.trimEnd());
  },

  db(msg, ...args) {
    const tag = `${c.bold}${c.magenta}[DB]${c.reset}`;
    console.log(`${timestamp()} ${prefix} ${tag} ${msg} ${formatArgs(args)}`.trimEnd());
  },

  queue(msg, ...args) {
    const tag = `${c.bold}${c.brightYellow}[QUEUE]${c.reset}`;
    console.log(`${timestamp()} ${prefix} ${tag} ${msg} ${formatArgs(args)}`.trimEnd());
  },

  banner(title, details = {}) {
    const width = 64;
    const border = `${c.cyan}=`.repeat(width) + `${c.reset}`;
    const divider = `${c.gray}-`.repeat(width) + `${c.reset}`;

    console.log(`\n${border}`);
    console.log(`  ${c.bold}${c.brightCyan}>>  ${title.toUpperCase()}${c.reset}`);
    console.log(divider);

    for (const [key, value] of Object.entries(details)) {
      const paddedKey = `${c.dim}${key.padEnd(20)}${c.reset}`;
      console.log(`  ${c.brightYellow}>${c.reset} ${paddedKey}: ${c.brightWhite}${value}${c.reset}`);
    }
    console.log(`${border}\n`);
  },

  // Express HTTP Request Logger Middleware
  requestLogger() {
    return (req, res, next) => {
      const start = process.hrtime.bigint();
      const clientIp = req.headers["x-forwarded-for"] || req.socket.remoteAddress || "unknown";

      // Hook response finish
      res.on("finish", () => {
        const end = process.hrtime.bigint();
        const durationMs = Number(end - start) / 1e6;
        const userPart = req.user ? `user_id=${req.user.id} (@${req.user.username})` : `ip=${clientIp}`;
        logger.http(req.method, req.originalUrl || req.url, res.statusCode, durationMs, userPart);
      });

      next();
    };
  },
};

module.exports = logger;
