// Unbatch: match each Claude response to its batch, then build UPDATE SQL
const table = $env.JOBS_FUNNEL_TABLE;
const batchItems = $('Batch Items').all();
const VALID_VARIANTS = ['software', 'data', 'fullstack', 'systems'];
const ERROR_KEYWORDS = ['parse error', 'incomplete', 'timed out', 'filter error', 'claude response parse'];

// Proper SQL escaping: handles quotes, backslashes, null bytes
function sqlStr(s) {
  if (s === null || s === undefined) return 'NULL';
  return "'" + String(s).replace(/\\/g, '\\\\').replace(/'/g, "''").replace(/\0/g, '') + "'";
}

// Dollar-quoted JSONB literal: avoids double-encoding from sqlStr + ::jsonb cast
function jsonbLiteral(value) {
  const arr = Array.isArray(value) ? value : [];
  const json = JSON.stringify(arr);
  let tag = '$jb$';
  if (json.includes(tag)) tag = '$jb2$';
  return tag + json + tag + '::jsonb';
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
        _updateQuery: `UPDATE ${table} SET status = 'error', error = ${sqlStr('Failed to parse Claude response: ' + e.message)}, retry_count = retry_count + 1 WHERE id = ${orig.id}`
      }});
    }
    continue;
  }

  for (let i = 0; i < originals.length; i++) {
    const orig = originals[i];
    const assessment = assessments[i];

    if (!assessment) {
      results.push({ json: {
        _updateQuery: `UPDATE ${table} SET status = 'error', error = 'No result returned for this job in batch response', retry_count = retry_count + 1 WHERE id = ${orig.id}`
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
        _updateQuery: `UPDATE ${table} SET status = 'error', error = ${sqlStr(assessment.reasoning || 'Fallback SKIP from failed Claude call')}, retry_count = retry_count + 1 WHERE id = ${orig.id}`
      }});
      continue;
    }

    // Validate cv_variant
    const cvVariant = VALID_VARIANTS.includes(assessment.cv_variant) ? assessment.cv_variant : 'software';

    // Extracted fields (best-effort, may be null)
    const empType = assessment.employment_type || null;
    const senLevel = assessment.seniority_level || null;
    const startDate = assessment.start_date || null;
    const exSalMin = assessment.extracted_salary_min || null;
    const exSalMax = assessment.extracted_salary_max || null;
    const exSalCur = assessment.extracted_salary_currency || null;

    // Conditional salary: only update if DB has no salary (don't overwrite API-provided values)
    const salaryClause = exSalMin
      ? `, salary_min = CASE WHEN salary_min IS NULL THEN ${Number(exSalMin)} ELSE salary_min END, salary_max = CASE WHEN salary_max IS NULL THEN ${exSalMax ? Number(exSalMax) : 'NULL'} ELSE salary_max END, salary_currency = CASE WHEN salary_currency IS NULL OR salary_currency = 'EUR' THEN ${sqlStr(exSalCur || 'EUR')} ELSE salary_currency END`
      : '';

    results.push({ json: {
      _updateQuery: `UPDATE ${table} SET status = 'analyzed', analyzed_at = NOW(), error = NULL, retry_count = 0, fit_score = ${score}, decision = '${decision}', cv_variant = '${cvVariant}', hard_blockers = ${jsonbLiteral(assessment.hard_blockers)}, soft_gaps = ${jsonbLiteral(assessment.soft_gaps)}, strong_matches = ${jsonbLiteral(assessment.strong_matches)}, reasoning = ${sqlStr(assessment.reasoning || '')}, priority_notes = ${sqlStr(assessment.priority_notes || null)}, employment_type = ${sqlStr(empType)}, seniority_level = ${sqlStr(senLevel)}, start_date = COALESCE(start_date, ${sqlStr(startDate)})${salaryClause} WHERE id = ${orig.id}`
    }});
  }
}
return results;
