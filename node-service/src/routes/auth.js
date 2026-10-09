const express = require("express");
const bcrypt = require("bcrypt");
const jwt = require("jsonwebtoken");
const { z } = require("zod");
const { pool } = require("../db/pool");
const logger = require("../utils/logger");

const router = express.Router();

const BCRYPT_ROUNDS = 12;

const registerSchema = z.object({
  name: z.string().min(1).max(150),
  dob: z.string().date().optional(), // "YYYY-MM-DD"
  username: z.string().min(3).max(50),
  password: z.string().min(8).max(200),
  email: z.string().email().max(254),
  contact_no: z.string().max(20).optional(),
});

const loginSchema = z.object({
  username: z.string().min(1),
  password: z.string().min(1),
});

// POST /auth/register
router.post("/register", async (req, res) => {
  const parsed = registerSchema.safeParse(req.body);
  if (!parsed.success) {
    logger.warn("Registration failed validation:", parsed.error.flatten());
    return res.status(400).json({ error: "Invalid input", details: parsed.error.flatten() });
  }
  const { name, dob, username, password, email, contact_no } = parsed.data;
  logger.auth(`Registration initiated for username='${username}', email='${email}'`);

  try {
    const password_hash = await bcrypt.hash(password, BCRYPT_ROUNDS);

    // Uses pool directly (not withUserContext) because there is no
    // authenticated user yet — this is the one legitimate place in the app
    // that writes to `users` outside an RLS-scoped transaction. `users` has
    // no RLS policy enabled (only documents/document_chunks do), by design.
    const result = await pool.query(
      `INSERT INTO users (name, dob, username, password_hash, email, contact_no)
       VALUES ($1, $2, $3, $4, $5, $6)
       RETURNING id, name, username, email, user_type, created_at`,
      [name, dob || null, username, password_hash, email, contact_no || null]
    );

    const newUser = result.rows[0];
    logger.success(`User registered successfully: id=${newUser.id}, username='${newUser.username}', role='${newUser.user_type}'`);
    return res.status(201).json({ user: newUser });
  } catch (err) {
    if (err.code === "23505") {
      // unique_violation on username or email
      logger.warn(`Registration conflict: username='${username}' or email='${email}' already taken`);
      return res.status(409).json({ error: "Username or email already in use" });
    }
    logger.error("Registration query error:", err);
    return res.status(500).json({ error: "Internal server error" });
  }
});

// POST /auth/login
router.post("/login", async (req, res) => {
  const parsed = loginSchema.safeParse(req.body);
  if (!parsed.success) {
    logger.warn("Login request missing username or password");
    return res.status(400).json({ error: "Invalid input" });
  }
  const { username, password } = parsed.data;
  logger.auth(`Login attempt for username='${username}'`);

  try {
    const result = await pool.query(
      `SELECT id, username, password_hash, user_type FROM users WHERE username = $1`,
      [username]
    );
    const user = result.rows[0];

    // Always run bcrypt.compare even on a missing user, against a dummy hash,
    // to avoid a timing side-channel that reveals whether a username exists.
    const hashToCheck =
      user?.password_hash || "$2b$12$invalidinvalidinvalidinvalidinvalidinvalidinvalid";
    const valid = await bcrypt.compare(password, hashToCheck);

    if (!user || !valid) {
      logger.warn(`Login rejected: invalid credentials for username='${username}'`);
      return res.status(401).json({ error: "Invalid username or password" });
    }

    // pg returns BIGINT/BIGSERIAL columns (users.id) as strings, not numbers,
    // to avoid silent precision loss above Number.MAX_SAFE_INTEGER. Convert
    // explicitly here, once, so every downstream consumer of the JWT's `sub`
    // (requireAuth, withUserContext, the RLS SET LOCAL) gets a real number —
    // Number.isInteger("1") is false, which otherwise fails every login.
    const userId = Number(user.id);
    if (!Number.isSafeInteger(userId)) {
      logger.error(`User id ${user.id} exceeds safe integer range; refusing to issue token`);
      return res.status(500).json({ error: "Internal server error" });
    }

    const token = jwt.sign(
      { sub: userId, username: user.username, user_type: user.user_type },
      process.env.JWT_SECRET,
      { expiresIn: process.env.JWT_EXPIRES_IN || "24h" }
    );

    logger.success(`Login successful for user_id=${userId} (@${user.username}) — JWT generated`);
    return res.json({ token });
  } catch (err) {
    logger.error("Login processing error:", err);
    return res.status(500).json({ error: "Internal server error" });
  }
});

module.exports = router;