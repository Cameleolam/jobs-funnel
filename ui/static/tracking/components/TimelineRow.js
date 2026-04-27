import { positionPercent, bucketEventsByDay } from '../timeline_math.js';
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
  },
  template: `
    <div class="timeline-row" :id="'job-' + job.id">
      <div class="timeline-row-label">
        <strong>{{ job.company }}</strong>
        <span class="role">{{ job.title }}</span>
        <a v-if="job.url" :href="job.url" target="_blank" rel="noopener"
           class="job-link">↗</a>
      </div>
      <div class="timeline-row-track">
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
