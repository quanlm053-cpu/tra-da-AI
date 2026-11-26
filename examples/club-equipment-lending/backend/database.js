import { readFile } from 'node:fs/promises';
import { hashPassword } from './password.js';

export const sessionSeconds = 8 * 60 * 60;
const decisionErrors = new Map([
  [51040, 'NOT_FOUND'],
  [51041, 'INVALID_TRANSITION'],
  [51042, 'SCHEDULE_CONFLICT'],
  [51043, 'EQUIPMENT_IN_USE'],
]);

export async function connectDatabase(env = process.env) {
  if (!env.DATABASE_URL) throw new Error('Set DATABASE_URL for SQL Server');
  const native = env.SQLSERVER_DRIVER === 'odbc';
  const sql = native
    ? (await import('mssql/msnodesqlv8.js')).default
    : (await import('mssql')).default;
  const config = native ? { connectionString: env.DATABASE_URL }
    : sql.ConnectionPool.parseConnectionString(env.DATABASE_URL);
  config.options = { ...config.options, useUTC: true };
  const pool = await new sql.ConnectionPool(config).connect();
  return { pool, sql };
}

function tables(schema = 'dbo') {
  if (!/^[a-zA-Z][a-zA-Z0-9_]{0,63}$/.test(schema)) throw new Error('Invalid SQL Server schema');
  return Object.fromEntries(['users', 'sessions', 'equipment', 'loan_requests', 'loan_events']
    .map(name => [name, `[${schema}].[${name}]`]));
}

export function sqlServerStore(pool, sql, schema) {
  const { users, sessions, equipment, loan_requests, loan_events } = tables(schema);
  const loanFields = ['id', 'equipment_id', 'start_at', 'end_at', 'created_at', 'status'];
  const loanColumns = loanFields.join(', ');
  const managedLoanFields = `${loanFields.map(field => 'r.' + field).join(', ')}, r.borrower_id,
                               e.asset_code AS equipment_asset_code, e.name AS equipment_name,
                               u.username AS borrower_username`;
  const managedLoans = `FROM ${loan_requests} AS r
                        JOIN ${equipment} AS e ON e.id = r.equipment_id
                        JOIN ${users} AS u ON u.id = r.borrower_id`;
  return {
    async createMember(username, passwordHash) {
      try {
        await pool.request().input('username', sql.NVarChar(255), username)
          .input('hash', sql.VarChar(255), passwordHash)
          .query(`INSERT INTO ${users} (username, password_hash, role)
                  VALUES (@username, @hash, 'MEMBER')`);
        return true;
      } catch (error) {
        // The insert supplies username as its only unique key. SQL Server generates id.
        const number = Number(error.number ?? error.originalError?.info?.number);
        if (number === 2601 || number === 2627) return false;
        throw error;
      }
    },
    async userByUsername(username) {
      const result = await pool.request().input('username', sql.NVarChar(255), username)
        .query(`SELECT id, username, role, password_hash FROM ${users} WHERE username = @username`);
      return result.recordset[0];
    },
    async createSession(tokenHash, userId) {
      await pool.request().input('token', sql.Binary(32), tokenHash)
        .input('user', sql.Int, userId).input('seconds', sql.Int, sessionSeconds)
        .query(`INSERT INTO ${sessions} (token_hash, user_id, expires_at)
                VALUES (@token, @user, DATEADD(second, @seconds, SYSUTCDATETIME()))`);
    },
    async userBySession(tokenHash) {
      const result = await pool.request().input('token', sql.Binary(32), tokenHash)
        .query(`SELECT u.id, u.username, u.role FROM ${sessions} s JOIN ${users} u ON u.id = s.user_id
                WHERE s.token_hash = @token AND s.expires_at > SYSUTCDATETIME()`);
      return result.recordset[0];
    },
    async deleteSession(tokenHash) {
      await pool.request().input('token', sql.Binary(32), tokenHash)
        .query(`DELETE FROM ${sessions} WHERE token_hash = @token`);
    },
    async deleteExpiredSessions() {
      await pool.request().query(`DELETE FROM ${sessions} WHERE expires_at <= SYSUTCDATETIME()`);
    },
    async listEquipment() {
      const result = await pool.request().query(`SELECT id, asset_code, name FROM ${equipment} ORDER BY asset_code`);
      return result.recordset;
    },
    async createLoanRequest(borrowerId, { equipmentId, start, end }) {
      const result = await pool.request().input('borrower_id', sql.Int, borrowerId)
        .input('equipment_id', sql.Int, equipmentId)
        .input('start_utc', sql.DateTime2(3), start).input('end_utc', sql.DateTime2(3), end)
        .query(`INSERT INTO ${loan_requests} (equipment_id, borrower_id, start_at, end_at, status)
                OUTPUT ${loanFields.map(field => 'inserted.' + field).join(', ')}
                SELECT id, @borrower_id, @start_utc, @end_utc, 'PENDING'
                FROM ${equipment} WITH (HOLDLOCK)
                WHERE id = @equipment_id`);
      return result.recordset[0];
    },
    async listLoanRequests(borrowerId) {
      const result = await pool.request().input('borrower_id', sql.Int, borrowerId)
        .query(`SELECT ${loanColumns} FROM ${loan_requests}
                WHERE borrower_id = @borrower_id ORDER BY created_at DESC, id DESC`);
      return result.recordset;
    },
    async readLoanRequest(borrowerId, requestId) {
      const result = await pool.request().input('borrower_id', sql.Int, borrowerId)
        .input('request_id', sql.Int, requestId)
        .query(`SELECT ${loanColumns} FROM ${loan_requests}
                WHERE id = @request_id AND borrower_id = @borrower_id`);
      return result.recordset[0];
    },
    async listManagedLoanRequests(status) {
      const result = await pool.request().input('status', sql.VarChar(16), status).query(`
        SELECT ${managedLoanFields} ${managedLoans}
        WHERE r.status = @status ORDER BY r.created_at, r.id`);
      return result.recordset;
    },
    async readManagedLoanRequest(requestId) {
      const result = await pool.request().input('request_id', sql.Int, requestId)
        .query(`SELECT ${managedLoanFields}, returned.actor_id AS returned_by,
                       returned.occurred_at AS returned_at, receiver.username AS returned_by_username
                ${managedLoans}
                OUTER APPLY (
                  SELECT TOP (1) actor_id, occurred_at FROM ${loan_events}
                  WHERE r.status = 'RETURNED' AND request_id = r.id
                    AND from_status = 'HANDED_OVER' AND to_status = 'RETURNED'
                  ORDER BY id DESC
                ) AS returned
                LEFT JOIN ${users} AS receiver ON receiver.id = returned.actor_id
                WHERE r.id = @request_id`);
      const loan = result.recordset[0];
      if (!loan) return;
      const { returned_by, returned_at, returned_by_username, ...fields } = loan;
      return returned_by === null ? fields : loan;
    },
    async decideLoanRequest(requestId, actorId, target) {
      try {
        const result = await pool.request().input('request_id', sql.Int, requestId)
          .input('actor_id', sql.Int, actorId).input('target', sql.VarChar(16), target)
          .query(`
            SET XACT_ABORT ON;
            SET TRANSACTION ISOLATION LEVEL READ COMMITTED;

            BEGIN TRY
              BEGIN TRANSACTION;
              DECLARE @equipment_id int, @locked_equipment_id int;
              DECLARE @status varchar(16), @start_at datetime2(3), @end_at datetime2(3);
              DECLARE @source varchar(16) = CASE @target
                WHEN 'HANDED_OVER' THEN 'APPROVED'
                WHEN 'RETURNED' THEN 'HANDED_OVER'
                ELSE 'PENDING'
              END;
              DECLARE @updated TABLE (
                id int, equipment_id int, start_at datetime2(3), end_at datetime2(3),
                created_at datetime2(3), status varchar(16), borrower_id int
              );

              -- Resolve the immutable equipment ID before taking update locks.
              SELECT @equipment_id = equipment_id FROM ${loan_requests} WHERE id = @request_id;
              IF @equipment_id IS NULL THROW 51040, 'NOT_FOUND', 1;

              SELECT @locked_equipment_id = id FROM ${equipment} WITH (UPDLOCK, HOLDLOCK)
              WHERE id = @equipment_id;
              IF @locked_equipment_id IS NULL THROW 51050, 'INTEGRITY_ERROR', 1;

              SELECT @status = status, @start_at = start_at, @end_at = end_at
              FROM ${loan_requests} WITH (UPDLOCK, HOLDLOCK)
              WHERE id = @request_id AND equipment_id = @locked_equipment_id;
              IF @status IS NULL THROW 51040, 'NOT_FOUND', 1;
              IF @status <> @source THROW 51041, 'INVALID_TRANSITION', 1;

              IF @target = 'APPROVED' AND EXISTS (
                SELECT 1 FROM ${loan_requests}
                WHERE equipment_id = @locked_equipment_id
                  AND status IN ('APPROVED', 'HANDED_OVER')
                  AND start_at < @end_at AND end_at > @start_at
              ) THROW 51042, 'SCHEDULE_CONFLICT', 1;

              IF @target = 'HANDED_OVER' AND EXISTS (
                SELECT 1 FROM ${loan_requests}
                WHERE equipment_id = @locked_equipment_id AND status = 'HANDED_OVER' AND id <> @request_id
              ) THROW 51043, 'EQUIPMENT_IN_USE', 1;

              DECLARE @now datetime2(3) = SYSUTCDATETIME();
              BEGIN TRY
                UPDATE ${loan_requests}
                SET status = @target
                OUTPUT ${[...loanFields, 'borrower_id'].map(field => 'inserted.' + field).join(', ')}
                  INTO @updated (${loanColumns}, borrower_id)
                WHERE id = @request_id AND status = @source;
                IF @@ROWCOUNT <> 1 THROW 51041, 'INVALID_TRANSITION', 1;
              END TRY
              BEGIN CATCH
                IF @target = 'HANDED_OVER' AND ERROR_NUMBER() = 2601
                  AND CHARINDEX(N'''UX_loan_requests_equipment_handed_over''', ERROR_MESSAGE()) > 0
                  THROW 51043, 'EQUIPMENT_IN_USE', 1;
                THROW;
              END CATCH;

              INSERT INTO ${loan_events} (request_id, actor_id, from_status, to_status, occurred_at)
              VALUES (@request_id, @actor_id, @status, @target, @now);

              COMMIT TRANSACTION;
              IF @target = 'RETURNED'
                SELECT ${loanColumns}, borrower_id, @actor_id AS returned_by, @now AS returned_at FROM @updated;
              ELSE
                SELECT ${loanColumns}, borrower_id FROM @updated;
            END TRY
            BEGIN CATCH
              IF XACT_STATE() <> 0 ROLLBACK TRANSACTION;
              THROW;
            END CATCH;
          `);
        return { loan: result.recordset[0] };
      } catch (error) {
        const code = decisionErrors.get(Number(error.number));
        if (code) return { code };
        throw error;
      }
    },
    async readAvailability(equipmentId, from, to) {
      const result = await pool.request().input('equipment_id', sql.Int, equipmentId)
        .input('from_utc', sql.DateTime2(3), from).input('to_utc', sql.DateTime2(3), to)
        .query(`SELECT e.id AS equipment_id, r.start_at, r.end_at
                FROM ${equipment} AS e WITH (HOLDLOCK)
                LEFT JOIN ${loan_requests} AS r WITH (HOLDLOCK)
                  ON r.equipment_id = e.id
                  AND r.status IN ('APPROVED', 'HANDED_OVER')
                  AND r.start_at < @to_utc
                  AND r.end_at > @from_utc
                WHERE e.id = @equipment_id
                ORDER BY r.start_at, r.end_at`);
      return result.recordset;
    },
  };
}

async function transaction(pool, sql, schema, work) {
  const tx = new sql.Transaction(pool);
  await tx.begin();
  try {
    await tx.request().input('resource', sql.NVarChar(255), 'lending:foundation:' + schema).query(`
      DECLARE @lock int;
      EXEC @lock = sp_getapplock @Resource = @resource, @LockMode = 'Exclusive',
        @LockOwner = 'Transaction', @LockTimeout = 5000;
      IF @lock < 0 THROW 51000, 'Could not lock lending schema', 1;
    `);
    await work(tx);
    await tx.commit();
  } catch (error) {
    await tx.rollback().catch(() => {});
    throw error;
  }
}

export async function migrate(pool, sql, schema = 'dbo') {
  tables(schema);
  const migrations = [
    '001-foundation.sql', '002-loan-requests.sql', '003-loan-request-borrower-index.sql', '004-loan-events.sql',
    '005-loan-request-active-holder.sql',
  ];
  const scripts = await Promise.all(migrations.map(file =>
    readFile(new URL('./migrations/' + file, import.meta.url), 'utf8')));
  await transaction(pool, sql, schema, async tx => {
    for (const script of scripts) await tx.request().batch(script.replaceAll('__SCHEMA__', schema));
  });
}

export async function seedDemo(pool, sql, env, schema = 'dbo') {
  if (!['demo', 'test'].includes(env.LENDING_ENV)) throw new Error('Seed requires LENDING_ENV=demo or test');
  const { users, equipment } = tables(schema);
  const accounts = [
    ['demo.member', 'MEMBER', env.DEMO_MEMBER_PASSWORD],
    ['demo.manager', 'MANAGER', env.DEMO_MANAGER_PASSWORD],
  ];
  if (accounts.some(([, , password]) => !password || Buffer.byteLength(password) > 1024)) {
    throw new Error('Set both demo passwords to nonempty values of at most 1024 bytes');
  }
  const hashes = await Promise.all(accounts.map(([, , password]) => hashPassword(password)));
  await transaction(pool, sql, schema, async tx => {
    for (const [index, [username, role]] of accounts.entries()) {
      await tx.request().input('username', sql.NVarChar(255), username)
        .input('role', sql.VarChar(16), role).input('hash', sql.VarChar(255), hashes[index])
        .query(`IF NOT EXISTS (SELECT 1 FROM ${users} WHERE username = @username)
                INSERT INTO ${users} (username, role, password_hash) VALUES (@username, @role, @hash)`);
    }
    await tx.request().input('name', sql.NVarChar(255), 'Máy chiếu').query(`
      INSERT INTO ${equipment} (asset_code, name)
      SELECT d.asset_code, @name FROM (VALUES ('DEMO-01'), ('DEMO-02')) d(asset_code)
      WHERE NOT EXISTS (SELECT 1 FROM ${equipment} e WHERE e.asset_code = d.asset_code)`);
  });
}
