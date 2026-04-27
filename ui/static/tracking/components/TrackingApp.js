import { computed, onMounted } from 'https://unpkg.com/vue@3/dist/vue.esm-browser.prod.js';
import { store, fetchJobs, isJobClosed } from '../state.js';

export const TrackingApp = {
  name: 'TrackingApp',
  setup() {
    onMounted(fetchJobs);

    const visibleJobs = computed(() => {
      const closed = store.tab === 'closed';
      return store.jobs.filter((j) => isJobClosed(j) === closed);
    });

    return { store, visibleJobs };
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
      <div v-else>
        <p class="text-muted">{{ visibleJobs.length }} job(s) · timeline component lands in Task 8</p>
        <ul>
          <li v-for="j in visibleJobs" :key="j.id">
            <strong>{{ j.company }}</strong> — {{ j.title }}
            ({{ j.events.length }} event(s))
          </li>
        </ul>
      </div>
    </div>
  `,
};
