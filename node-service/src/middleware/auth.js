const jwt = require("jsonwebtoken");
const logger = require("../utils/logger");

/**
 * Validates the JWT bearer token and attaches { id, username, user_type }
 * to req.user. Mirrors the validate-then-lookup pattern from the reference
 * repo's app/core/security.py, minus the dual-table confusion that repo had.
 */
function requireAuth(req, res, next) {
  const header = req.headers.authorization || "";
  const [scheme, token] = header.split(" ");

  if (scheme !== "Bearer" || !token) {
    logger.warn(`Auth rejected: Missing or malformed Authorization header on ${req.method} ${req.originalUrl}`);
    return res.status(401).json({ error: "Missing or malformed Authorization header" });
  }

  try {
    const payload = jwt.verify(token, process.env.JWT_SECRET);
    if (!payload.sub || !Number.isInteger(payload.sub)) {
      logger.warn(`Auth rejected: Invalid token payload format on ${req.method} ${req.originalUrl}`);
      return res.status(401).json({ error: "Invalid token payload" });
    }
    req.user = {
      id: payload.sub,
      username: payload.username,
      user_type: payload.user_type,
    };
    logger.auth(`Authenticated user_id=${req.user.id} (@${req.user.username}, role=${req.user.user_type || "user"})`);
    return next();
  } catch (err) {
    logger.warn(`Auth rejected: Token verification failed (${err.message}) on ${req.method} ${req.originalUrl}`);
    return res.status(401).json({ error: "Invalid or expired token" });
  }
}

module.exports = { requireAuth };

