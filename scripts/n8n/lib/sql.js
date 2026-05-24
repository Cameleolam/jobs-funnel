function sqlIdentifier(name) {
  const value = String(name || '');
  if (!/^[A-Za-z_][A-Za-z0-9_]*$/.test(value)) {
    throw new Error(`Invalid JOBS_FUNNEL_TABLE: ${value}`);
  }
  return value;
}

function sqlStr(s) {
  if (s === null || s === undefined) return 'NULL';
  return "'" + String(s).replace(/\\/g, '\\\\').replace(/'/g, "''").replace(/\0/g, '') + "'";
}

function sqlBool(value) {
  return value === true ? 'TRUE' : 'FALSE';
}

function sqlInt(value) {
  const n = Number(value);
  return Number.isFinite(n) ? String(Math.trunc(n)) : 'NULL';
}

function dollarQuote(value, prefix) {
  let i = 0;
  while (true) {
    const tag = i === 0 ? `$${prefix}$` : `$${prefix}${i}$`;
    if (!String(value).includes(tag)) return tag + value + tag;
    i++;
  }
}

function jsonbLiteral(value) {
  const arr = Array.isArray(value) ? value : [];
  return dollarQuote(JSON.stringify(arr), 'jb') + '::jsonb';
}
