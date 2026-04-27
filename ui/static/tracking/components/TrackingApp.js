import { computed, onMounted, ref } from 'https://unpkg.com/vue@3/dist/vue.esm-browser.prod.js';
import { store, fetchJobs, isJobClosed } from '../state.js';
import { computeDomain } from '../timeline_math.js';
import { TimeAxis } from './TimeAxis.js';
import { TimelineRow } from './TimelineRow.js';
import { EventModal } from './EventModal.js';

export const TrackingApp = {
  name: 'TrackingApp',
  components: { TimeAxis, TimelineRow, EventModal },
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

    const modalOpen = ref(false);
    const modalJobId = ref(null);
    const modalEvent = ref(null);

    function onEventClick(ev) {
      modalEvent.value = ev;
      modalJobId.value = null;
      modalOpen.value = true;
    }
    function onAddEvent(job) {
      modalEvent.value = null;
      modalJobId.value = job.id;
      modalOpen.value = true;
    }
    function closeModal() {
      modalOpen.value = false;
      modalEvent.value = null;
      modalJobId.value = null;
    }

    return {
      store, visibleJobs, domain,
      modalOpen, modalJobId, modalEvent,
      onEventClick, onAddEvent, closeModal,
    };
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

      <EventModal
        :open="modalOpen"
        :job-id="modalJobId"
        :event="modalEvent"
        @close="closeModal"
        @saved="closeModal" />
    </div>
  `,
};
