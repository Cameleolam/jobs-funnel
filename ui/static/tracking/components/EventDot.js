const KIND_COLORS = {
  application: '#2563eb',
  contact:     '#0d9488',
  interview:   '#7c3aed',
  task:        '#d97706',
  decision:    '#16a34a',
  note:        '#6b7280',
};

export const EventDot = {
  name: 'EventDot',
  props: {
    event: { type: Object, required: true },
  },
  emits: ['click'],
  computed: {
    color() { return KIND_COLORS[this.event.kind] || '#999'; },
    dateLabel() {
      return new Date(this.event.occurred_at).toISOString().slice(5, 10);
    },
    fullDate() {
      return new Date(this.event.occurred_at).toISOString().slice(0, 10);
    },
    title() {
      return `${this.event.label} · ${this.fullDate}`;
    },
  },
  template: `
    <span class="event-dot-wrap">
      <button type="button"
              class="event-dot"
              :style="{ background: color }"
              :title="title"
              @click.stop="$emit('click', event)"></button>
      <span class="dot-date">{{ dateLabel }}</span>
    </span>
  `,
};
