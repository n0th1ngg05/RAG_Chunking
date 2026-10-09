const path = require("path");
const fs = require("fs");
const dotenv = require("dotenv");

const candidateEnvPaths = [
  path.resolve(__dirname, "../../.env"),
  path.resolve(__dirname, "../.env"),
  path.resolve(process.cwd(), "../.env"),
  path.resolve(process.cwd(), ".env"),
];

for (const envPath of candidateEnvPaths) {
  if (fs.existsSync(envPath)) {
    dotenv.config({ path: envPath });
  }
}
const express = require("express");
const helmet = require("helmet");
const rateLimit = require("express-rate-limit");
const swaggerUi = require("swagger-ui-express");
const openApiSpec = require("./openapi.json");
const logger = require("./utils/logger");

const authRoutes = require("./routes/auth");
const documentRoutes = require("./routes/documents");
const dashboardRoutes = require("./routes/dashboard");

// Fail fast if required secrets/config are missing — never start with a
// silently-undefined JWT secret or DB credentials.
const REQUIRED_ENV = [
  "JWT_SECRET",
  "POSTGRES_HOST",
  "POSTGRES_PORT",
  "POSTGRES_DB",
  "APP_DB_USER",
  "APP_DB_PASSWORD",
  "REDIS_HOST",
  "REDIS_PORT",
];
const missing = REQUIRED_ENV.filter((key) => !process.env[key]);
if (missing.length > 0) {
  logger.error(`Missing required environment variables: ${missing.join(", ")}`);
  process.exit(1);
}

const app = express();

app.use(
  helmet({
    contentSecurityPolicy: false,
  })
);
app.use(express.json({ limit: "1mb" }));

// Request logging middleware
app.use(logger.requestLogger());

// Global rate limit — generous default, tune per route if needed (e.g.
// stricter limits on /auth/login to slow brute-force attempts).
app.use(
  rateLimit({
    windowMs: 15 * 60 * 1000,
    max: 300,
    standardHeaders: true,
    legacyHeaders: false,
  })
);

app.use(
  "/auth/login",
  rateLimit({ windowMs: 15 * 60 * 1000, max: 10, standardHeaders: true, legacyHeaders: false })
);

app.get("/health", (req, res) => res.json({ status: "ok" }));
app.get("/openapi.json", (req, res) => res.json(openApiSpec));
app.use("/docs", swaggerUi.serve, swaggerUi.setup(openApiSpec));

app.use("/auth", authRoutes);
app.use("/documents", documentRoutes);
app.use("/dashboard", dashboardRoutes);

// Centralized error handler — never leak stack traces to clients.
// eslint-disable-next-line no-unused-vars
app.use((err, req, res, next) => {
  if (err.type === "entity.too.large" || err.code === "LIMIT_FILE_SIZE") {
    logger.warn(`Request payload rejected: payload too large for ${req.method} ${req.originalUrl}`);
    return res.status(413).json({ error: "File too large" });
  }
  logger.error(`Unhandled error on ${req.method} ${req.originalUrl}:`, err);
  return res.status(500).json({ error: "Internal server error" });
});

const PORT = process.env.NODE_PORT || 3000;
app.listen(PORT, () => {
  logger.banner("Document Chunking Node API Service", {
    "Status": "ONLINE & READY",
    "HTTP Port": PORT,
    "Postgres DB": `${process.env.POSTGRES_HOST}:${process.env.POSTGRES_PORT}/${process.env.POSTGRES_DB} (user: ${process.env.APP_DB_USER})`,
    "Redis Queue": `${process.env.REDIS_HOST}:${process.env.REDIS_PORT}`,
    "API Docs": `http://localhost:${PORT}/docs`,
    "Metrics Dashboard": `http://localhost:${PORT}/dashboard`,
    "Health Endpoint": `http://localhost:${PORT}/health`,
  });
});

