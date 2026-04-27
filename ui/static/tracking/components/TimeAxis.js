import { positionPercent, pickTickStep } from '../timeline_math.js';

function* tickIterator(start, end, step) {
  const cur = new Date(start);
  cur.setUTCHours(0, 0, 0, 0);
  while (cur <= end) {
    yield new Date(cur);
    if (step === 'day') cur.setUTCDate(cur.getUTCDate() + 1);
    else if (step === 'week') cur.setUTCDate(cur.getUTCDate() + 7);
    else cur.setUTCMonth(cur.getUTCMonth() + 1);
  }
}

function formatTick(d, step) {
  const m = String(d.getUTCMonth() + 1).padStart(2, '0');
  const day = String(d.getUTCDate()).padStart(2, '0');
  if (step === 'month') return `${d.getUTCFullYear()}-${m}`;
  return `${m}-${day}`;
}

export const TimeAxis = {
  name: 'TimeAxis',
  props: {
    domain: { type: Object, required: true },
  },
  computed: {
    ticks() {
      const span = this.domain.end - this.domain.start;
      const step = pickTickStep(span);
      const out = [];
      for (const d of tickIterator(this.domain.start, this.domain.end, step)) {
        out.push({
          date: d,
          label: formatTick(d, step),
          pct: positionPercent(d, this.domain),
        });
      }
      // Cap to ~12 ticks: drop every other one if too dense
      if (out.length > 12) {
        const step2 = Math.ceil(out.length / 12);
        return out.filter((_, i) => i % step2 === 0);
      }
      return out;
    },
  },
  template: `
    <div class="time-axis">
      <div class="time-axis-track">
        <span v-for="t in ticks" :key="t.label"
              class="time-axis-tick"
              :style="{ left: t.pct + '%' }">
          <span class="tick-line"></span>
          <span class="tick-label">{{ t.label }}</span>
        </span>
      </div>
    </div>
  `,
};
