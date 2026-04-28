import { positionPercent, bucketEventsByDay } from '../timeline_math.js';
import { closeTracking, reopenTracking } from '../state.js';
import { EventDot } from './EventDot.js';

export const TimelineRow = {
  name: 'TimelineRow',
  components: { EventDot },
  props: {
    job: { type: Object, required: true },
    domain: { type: Object, required: true },
  },
  emits: ['event-click', 'add-event'],
  computed: {
    buckets() {
      return bucketEventsByDay(this.job.events).map((b) => ({
        ...b,
        pct: positionPercent(b.date, this.domain),
      }));
    },
    segments() {
      const out = [];
      for (let i = 0; i < this.buckets.length - 1; i++) {
        out.push({
          from: this.buckets[i].pct,
          to: this.buckets[i + 1].pct,
          key: `${this.buckets[i].dayKey}-${this.buckets[i + 1].dayKey}`,
        });
      }
      return out;
    },
    isClosed() {
      return !!this.job.closed_at;
    },
  },
  methods: {
    async toggleClose() {
      if (this.isClosed) {
        await reopenTracking(this.job.id);
      } else {
        await closeTracking(this.job.id);
      }
    },
  },
  template: `
    <div class="timeline-row" :id="'job-' + job.id">
      <div class="timeline-row-label">
        <div class="timeline-row-label-line">
          <strong>{{ job.company }}</strong>
          <a v-if="job.url" :href="job.url" target="_blank" rel="noopener"
             class="job-link">↗</a>
          <button type="button" class="row-close-btn"
                  :title="isClosed ? 'Reopen tracking' : 'Close tracking'"
                  @click="toggleClose">{{ isClosed ? '↻' : '×' }}</button>
        </div>
        <span class="role">{{ job.title }}</span>
      </div>
      <div class="timeline-row-track">
        <span v-for="seg in segments" :key="seg.key"
              class="event-line"
              :style="{ left: seg.from + '%', width: (seg.to - seg.from) + '%' }"></span>
        <div v-for="bucket in buckets" :key="bucket.dayKey"
             class="event-bucket"
             :style="{ left: bucket.pct + '%' }">
          <EventDot v-for="ev in bucket.events" :key="ev.id"
                    :event="ev"
                    @click="$emit('event-click', ev)" />
        </div>
        <button class="add-event-btn" type="button"
                @click="$emit('add-event', job)">+</button>
      </div>
    </div>
  `,
};
