const { createClient } = require("redis");
const logger = require("../utils/logger");

/**
 * WIRING NOTE: the python-worker uses Python's `arq` library for its job
 * *execution* semantics (concurrency cap, per-job timeout, retries — see
 * python-service/app/worker.py). ARQ's own enqueue format is a Python-
 * specific Redis wire protocol, not something to hand-roll correctly from
 * Node. Rather than pull in a second, incompatible queue library (e.g.
 * BullMQ, which ARQ cannot read), the hand-off here is kept deliberately
 * simple: Node pushes a plain JSON payload onto a Redis list; the Python
 * side runs a small consumer loop (BRPOP) that reads this list and calls
 * the same `process_document()` pipeline that ARQ's cron sweeper also
 * supervises for stuck-job recovery. See python-service/app/queue_consumer.py.
 */
const redisClient = createClient({
  socket: {
    host: process.env.REDIS_HOST,
    port: Number(process.env.REDIS_PORT),
  },
});

redisClient.on("error", (err) => {
  logger.error("Redis client error:", err);
});

redisClient.on("connect", () => {
  logger.queue(`Connected to Redis instance at ${process.env.REDIS_HOST}:${process.env.REDIS_PORT}`);
});

let connected = false;
async function ensureConnected() {
  if (!connected) {
    logger.queue(`Connecting to Redis at ${process.env.REDIS_HOST}:${process.env.REDIS_PORT}...`);
    await redisClient.connect();
    connected = true;
  }
}

const QUEUE_KEY = "ingestion:jobs";

const ingestionQueue = {
  async add(_jobName, payload) {
    await ensureConnected();
    await redisClient.lPush(QUEUE_KEY, JSON.stringify(payload));
    logger.queue(`Pushed job to Redis list '${QUEUE_KEY}' for document_id=${payload.document_id}`);
  },
};

module.exports = { ingestionQueue };

