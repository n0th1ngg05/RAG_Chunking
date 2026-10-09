const { pool } = require("./pool");
const logger = require("../utils/logger");

/**
 * Runs `fn` inside a Postgres transaction with `app.current_user_id` set via
 * SET LOCAL, so the RLS policies in sql/init.sql transparently scope every
 * query in `fn` to this user's own rows.
 *
 * ALWAYS use this instead of pool.query() directly for any request-scoped
 * DB access in route handlers. Never query with pool.query() from a route
 * that touches `documents` or `document_chunks` — you'd bypass the whole
 * point of RLS if you did (app_user technically still can't see other
 * users' rows without this, since RLS is enforced regardless — but without
 * current_user_id set, the policy's current_setting(...) comparison will be
 * NULL and match nothing, so queries will just silently return no rows
 * instead of the data you expect. Using this helper avoids that confusion.)
 *
 * @param {number} userId - the authenticated user's id, from the JWT
 * @param {(client: import('pg').PoolClient) => Promise<any>} fn
 */
async function withUserContext(userId, fn) {
  const client = await pool.connect();
  try {
    await client.query("BEGIN");
    // SET LOCAL takes a string literal, not a bind param — but userId is
    // always a number we parsed from a verified JWT, never raw user input,
    // so this is safe. Still validated as an integer before use.
    if (!Number.isInteger(userId)) {
      throw new Error("withUserContext: userId must be an integer");
    }
    await client.query(`SET LOCAL app.current_user_id = '${userId}'`);
    logger.debug(`Scoped DB transaction context to app.current_user_id=${userId}`);
    const result = await fn(client);
    await client.query("COMMIT");
    return result;
  } catch (err) {
    await client.query("ROLLBACK");
    logger.debug(`Rolled back DB transaction for app.current_user_id=${userId}`);
    throw err;
  } finally {
    client.release();
  }
}

module.exports = { withUserContext };

