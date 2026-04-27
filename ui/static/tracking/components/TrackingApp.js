import { computed, onMounted } from 'https://unpkg.com/vue@3/dist/vue.esm-browser.prod.js';
import { store, fetchJobs, isJobClosed } from '../state.js';
import { computeDomain } from '../timeline_math.js';
import { TimeAxis } from './TimeAxis.js';
import { TimelineRow } from './TimelineRow.js';

export const TrackingApp = {
  name: 'TrackingApp',
  components: { TimeAxis, TimelineRow },
  setup() {
    onMounted(fetchJobs);

    const visibleJobs = computed(() => {
      const closed = store.tab === 'closed';
      return store.jobs.filter((j) => isJobClosed(j) === closed);
    });

    const domain = computed(() => {
      const allEvents = visibleJobs.value.flatMap((j) => j.events);
      return computeDomain(allEvents, new Date());
    });

    function onEventClick(_ev) {
      // Wired up in Task 9 (modal).
    }
    function onAddEvent(_job) {
      // Wired up in Task 9 (modal).
    }

    return { store, visibleJobs, domain, onEventClick, onAddEvent };
  },
  template: `
    <div class="tracking-page">
      <div class="tracking-header">
        <h2>Tracking</h2>
        <div class="tracking-tabs">
          <button :class="{active: store.tab === 'active'}"
                  @click="store.tab = 'active'">Active</button>
          <button :class="{active: store.tab === 'closed'}"
                  @click="store.tab = 'closed'">Closed</button>
        </div>
      </div>

      <p v-if="store.loading" class="text-muted">Loading…</p>
      <p v-else-if="store.error" class="error-banner">{{ store.error }}</p>
      <div v-else-if="visibleJobs.length === 0" class="tracking-empty">
        <p>No {{ store.tab }} tracked jobs yet.</p>
        <p class="text-muted">
          Start tracking from a job row on
          <a href="/">the Jobs page</a>,
          or use <a href="/jobs/new">Add job</a> with the
          "already applied externally" checkbox.
        </p>
      </div>
      <div v-else class="timeline-wrap">
        <TimeAxis :domain="domain" />
        <TimelineRow v-for="job in visibleJobs" :key="job.id"
                     :job="job" :domain="domain"
                     @event-click="onEventClick"
                     @add-event="onAddEvent" />
      </div>
    </div>
  `,
};
