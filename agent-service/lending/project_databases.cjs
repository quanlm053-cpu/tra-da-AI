const assert = require('node:assert/strict');

async function main() {
  const [driver, ...databases] = process.argv.slice(2);
  assert.equal(databases.length, 2);
  assert.ok(databases.every(name => /^AI_[A-Za-z0-9_]{1,100}_(Test|Preview)$/.test(name)));
  const sql = require(driver);
  const pool = await new sql.ConnectionPool({
    connectionString: 'Driver={ODBC Driver 17 for SQL Server};Server=lpc:localhost;' +
      'Database=master;Trusted_Connection=yes;Encrypt=yes;TrustServerCertificate=yes;',
  }).connect();
  try {
    for (const database of databases) {
      await pool.request().query(
        "IF DB_ID(N'" + database + "') IS NULL CREATE DATABASE [" + database + "]"
      );
    }
    console.log('Project test and preview databases ready.');
  } finally {
    await pool.close();
  }
}
main().catch(error => { console.error(error.message); process.exitCode = 1; });
