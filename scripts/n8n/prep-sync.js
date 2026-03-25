// Collect all DB IDs that were synced to Sheet and build UPDATE query
let formatItems;
try { formatItems = $('Format Sheet Rows').all(); } catch (e) { formatItems = []; }
const ids = formatItems.map(item => item.json._dbId).filter(Boolean);

if (ids.length === 0) return [{ json: { _syncQuery: 'SELECT 1', _synced: 0 } }];

return [{ json: {
  _syncQuery: `UPDATE jobs SET sheet_synced = TRUE, sheet_synced_at = NOW() WHERE id IN (${ids.join(',')})`,
  _synced: ids.length
}}];
