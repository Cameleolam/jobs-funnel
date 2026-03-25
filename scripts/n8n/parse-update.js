// Unbatch: match each Claude response to its batch, then build UPDATE SQL
const batchItems = $('Batch Items').all();
const VALID_VARIANTS = ['software', 'data', 'fullstack', 'systems'];
const ERROR_KEYWORDS = ['parse error', 'incomplete', 'timed out', 'filter error', 'claude response parse'];

// Proper SQL escaping: handles quotes, backslashes, null bytes
function sqlStr(s) {
  if (s === null || s === undefined) return 'NULL';
  return "'" + String(s).replace(/\\/g, '\\\\').replace(/'/g, "''").replace(/\0/g, '') + "'";
}

const results = [];
for (let b = 0; b < $input.all().length; b++) {
  const item = $input.all()[b];
  const stdout = item.json.stdout || '[]';
  const originals = (batchItems[b] && batchItems[b].json._batchOriginals) || [];

  let assessments;
  try {
    assessments = JSON.parse(stdout);
    if (!Array.isArray(assessments)) assessments = [assessments];
  } catch (e) {
    for (const orig of originals) {
      results.push({ json: {
        _updateQuery: `UPDATE jobs SET status = 'error', error = ${sqlStr('Failed to parse Claude response: ' + e.message)}, retry_count = retry_count + 1 WHERE id = ${orig.id}`
      }});
    }
    continue;
  }

  for (let i = 0; i < originals.length; i++) {
    const orig = originals[i];
    const assessment = assessments[i];

    if (!assessment) {
      results.push({ json: {
        _updateQuery: `UPDATE jobs SET status = 'error', error = 'No result returned for this job in batch response', retry_count = retry_count + 1 WHERE id = ${orig.id}`
      }});
      continue;
    }

    const rawDecision = String(assessment.decision || 'SKIP').trim().toUpperCase();
    const decision = ['PASS', 'MAYBE', 'SKIP'].includes(rawDecision) ? rawDecision : 'SKIP';
    const score = Number(assessment.fit_score) || 0;

    // Detect batch padding (job was never evaluated by Claude)
    const isBatchPadding = (assessment.priority_notes || '').includes('BATCH_PADDING');

    // Detect fallback/error responses from filter.py
    const isErrorFallback = isBatchPadding || (score === 0 && (assessment.hard_blockers || []).some(b =>
      ERROR_KEYWORDS.some(kw => b.toLowerCase().includes(kw))
    ));

    if (isErrorFallback) {
      results.push({ json: {
        _updateQuery: `UPDATE jobs SET status = 'error', error = ${sqlStr(assessment.reasoning || 'Fallback SKIP from failed Claude call')}, retry_count = retry_count + 1 WHERE id = ${orig.id}`
      }});
      continue;
    }

    // Validate cv_variant
    const cvVariant = VALID_VARIANTS.includes(assessment.cv_variant) ? assessment.cv_variant : 'software';

    results.push({ json: {
      _updateQuery: `UPDATE jobs SET status = 'analyzed', analyzed_at = NOW(), error = NULL, retry_count = 0, fit_score = ${score}, decision = '${decision}', cv_variant = '${cvVariant}', hard_blockers = ${sqlStr(JSON.stringify(assessment.hard_blockers || []))}::jsonb, soft_gaps = ${sqlStr(JSON.stringify(assessment.soft_gaps || []))}::jsonb, strong_matches = ${sqlStr(JSON.stringify(assessment.strong_matches || []))}::jsonb, reasoning = ${sqlStr(assessment.reasoning || '')}, priority_notes = ${sqlStr(assessment.priority_notes || null)} WHERE id = ${orig.id}`
    }});
  }
}
return results;
