// Tiny reactive store + fetch helpers.
import { reactive } from 'https://unpkg.com/vue@3/dist/vue.esm-browser.prod.js';

export const store = reactive({
  jobs: [],
  loading: false,
  error: null,
  tab: 'active', // 'active' | 'closed'
});

const CLOSED_LABEL_RE = /reject|declin|withdraw|ghost|accept|offer accepted/i;

export function isJobClosed(job) {
  if (!job.events || job.events.length === 0) return false;
  const last = job.events[job.events.length - 1];
  return last.kind === 'decision' && CLOSED_LABEL_RE.test(last.label || '');
}

export async function fetchJobs() {
  store.loading = true;
  store.error = null;
  try {
    const r = await fetch('/api/tracking/jobs');
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    store.jobs = await r.json();
  } catch (e) {
    store.error = e.message;
  } finally {
    store.loading = false;
  }
}

export async function createEvent(payload) {
  const r = await fetch('/api/tracking/events', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  await fetchJobs();
  return r.json();
}

export async function updateEvent(eventId, payload) {
  const r = await fetch(`/api/tracking/events/${eventId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  await fetchJobs();
  return r.json();
}

export async function deleteEvent(eventId) {
  const r = await fetch(`/api/tracking/events/${eventId}`, { method: 'DELETE' });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  await fetchJobs();
}

export async function stopTracking(jobId) {
  const r = await fetch(`/api/tracking/jobs/${jobId}/stop`, { method: 'POST' });
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  await fetchJobs();
}
