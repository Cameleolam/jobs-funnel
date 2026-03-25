// Collect pipeline run metrics and format for Metrics sheet tab
let formatItems = [];
try { formatItems = $('Format Sheet Rows').all().filter(i => i.json.Date); } catch (e) { /* no items */ }

const pass = formatItems.filter(i => i.json.Decision === 'PASS').length;
const maybe = formatItems.filter(i => i.json.Decision === 'MAYBE').length;
const skip = formatItems.filter(i => i.json.Decision === 'SKIP').length;
const total = pass + maybe + skip;
const now = new Date();

return [{ json: {
  'Date': now.toISOString().slice(0, 10),
  'Timestamp': now.toISOString().replace('T', ' ').slice(0, 19) + ' UTC',
  'Analyzed': total,
  'PASS': pass,
  'MAYBE': maybe,
  'SKIP': skip,
  'Pass Rate': total > 0 ? Math.round(pass / total * 100) + '%' : '0%',
  'Synced': formatItems.length,
}}];
