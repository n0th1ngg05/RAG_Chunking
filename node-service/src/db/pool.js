const { Pool } = require("pg");
const logger = require("../utils/logger");

// The node-service connects ONLY as `app_user`, the RLS-restricted role.
// It can never see rows across users even on a bug, because the DB enforces
// it, not the app code. The python-worker connects separately as
// `worker_user` (BYPASSRLS) — see python-service/app/core/database.py.
const pool = new Pool({
  host: process.env.POSTGRES_HOST,
  port: Number(process.env.POSTGRES_PORT),
  database: process.env.POSTGRES_DB,
  user: process.env.APP_DB_USER,
  password: process.env.APP_DB_PASSWORD,
  max: 20,
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 5000,
});

pool.on("error", (err) => {
  logger.error("Unexpected error on idle Postgres client:", err);
});

pool.on("connect", () => {
  logger.debug("New Postgres client acquired from pool");
});

module.exports = { pool };

