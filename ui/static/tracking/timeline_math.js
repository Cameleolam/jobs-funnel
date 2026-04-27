// Pure functions for timeline layout. No DOM, no Vue — testable in plain Node.

const DAY_MS = 86400000;

export function computeDomain(events, now = new Date()) {
  if (!events || events.length === 0) {
    const start = new Date(now.getTime() - 30 * DAY_MS);
    return { start, end: now };
  }
  const times = events.map((e) => new Date(e.occurred_at).getTime());
  const minTs = Math.min(...times);
  return {
    start: new Date(minTs),
    end: now,
  };
}

export function positionPercent(date, domain) {
  const t = date instanceof Date ? date.getTime() : new Date(date).getTime();
  const span = domain.end.getTime() - domain.start.getTime();
  if (span <= 0) return 0;
  const pct = ((t - domain.start.getTime()) / span) * 100;
  if (pct < 0) return 0;
  if (pct > 100) return 100;
  return pct;
}

function dayKeyUTC(d) {
  const dt = d instanceof Date ? d : new Date(d);
  const y = dt.getUTCFullYear();
  const m = String(dt.getUTCMonth() + 1).padStart(2, '0');
  const day = String(dt.getUTCDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

export function bucketEventsByDay(events) {
  // Returns [{dayKey, date, events: [...sorted by occurred_at asc]}, ...]
  const map = new Map();
  for (const ev of events) {
    const key = dayKeyUTC(ev.occurred_at);
    if (!map.has(key)) {
      map.set(key, { dayKey: key, date: new Date(`${key}T00:00:00Z`), events: [] });
    }
    map.get(key).events.push(ev);
  }
  for (const bucket of map.values()) {
    bucket.events.sort((a, b) =>
      new Date(a.occurred_at).getTime() - new Date(b.occurred_at).getTime()
    );
  }
  return Array.from(map.values()).sort((a, b) => a.date - b.date);
}

export function pickTickStep(spanMs) {
  const days = spanMs / DAY_MS;
  if (days <= 30) return 'day';
  if (days <= 120) return 'week';
  return 'month';
}
