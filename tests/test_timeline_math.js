// Run with: node tests/test_timeline_math.js
// Exits 0 on all pass, 1 on any failure.
import {
  computeDomain,
  positionPercent,
  bucketEventsByDay,
  pickTickStep,
} from '../ui/static/tracking/timeline_math.js';

let failed = 0;
function assert(cond, msg) {
  if (!cond) { console.error('FAIL:', msg); failed++; }
}

// computeDomain
{
  const events = [
    { occurred_at: '2026-03-01T00:00:00Z' },
    { occurred_at: '2026-03-15T00:00:00Z' },
  ];
  const now = new Date('2026-04-01T00:00:00Z');
  const d = computeDomain(events, now);
  assert(d.start.toISOString() === '2026-03-01T00:00:00.000Z', 'domain.start');
  assert(d.end.toISOString() === '2026-04-01T00:00:00.000Z', 'domain.end');
}

// computeDomain handles empty
{
  const now = new Date('2026-04-01T00:00:00Z');
  const d = computeDomain([], now);
  assert(d.start <= d.end, 'empty domain valid');
}

// positionPercent
{
  const start = new Date('2026-03-01T00:00:00Z');
  const end = new Date('2026-03-31T00:00:00Z');
  const mid = new Date('2026-03-16T00:00:00Z');
  const pct = positionPercent(mid, { start, end });
  assert(pct >= 49 && pct <= 51, `mid pct ~50, got ${pct}`);
  assert(positionPercent(start, { start, end }) === 0, 'start pct 0');
  assert(positionPercent(end, { start, end }) === 100, 'end pct 100');
}

// bucketEventsByDay
{
  const events = [
    { id: 1, occurred_at: '2026-03-01T09:00:00Z', kind: 'application' },
    { id: 2, occurred_at: '2026-03-01T15:00:00Z', kind: 'contact' },
    { id: 3, occurred_at: '2026-03-05T10:00:00Z', kind: 'interview' },
  ];
  const buckets = bucketEventsByDay(events);
  assert(buckets.length === 2, `expected 2 buckets, got ${buckets.length}`);
  assert(buckets[0].events.length === 2, 'bucket 0 has 2 events');
  assert(buckets[1].events.length === 1, 'bucket 1 has 1 event');
  assert(buckets[0].dayKey === '2026-03-01', 'bucket 0 day key');
}

// pickTickStep
{
  const day = 86400000;
  assert(pickTickStep(10 * day) === 'day', '10d -> day');
  assert(pickTickStep(60 * day) === 'week', '60d -> week');
  assert(pickTickStep(400 * day) === 'month', '400d -> month');
}

if (failed > 0) {
  console.error(`${failed} test(s) failed`);
  process.exit(1);
} else {
  console.log('All timeline_math tests passed');
}
