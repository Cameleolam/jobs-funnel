import { ref, watch, computed } from 'https://unpkg.com/vue@3/dist/vue.esm-browser.prod.js';
import { createEvent, updateEvent, deleteEvent } from '../state.js';

const KINDS = ['application', 'contact', 'interview', 'task', 'decision', 'note'];

function todayInputValue() {
  const d = new Date();
  return d.toISOString().slice(0, 10);
}

export const EventModal = {
  name: 'EventModal',
  props: {
    open: Boolean,
    jobId: { type: Number, default: null },
    event: { type: Object, default: null }, // null = create mode
  },
  emits: ['close', 'saved'],
  setup(props, { emit }) {
    const kind = ref('application');
    const label = ref('');
    const date = ref(todayInputValue());
    const notes = ref('');
    const showNotes = ref(false);
    const saving = ref(false);
    const error = ref(null);

    const isEdit = computed(() => !!props.event);

    watch(() => props.open, (isOpen) => {
      if (!isOpen) return;
      error.value = null;
      saving.value = false;
      if (props.event) {
        kind.value = props.event.kind;
        label.value = props.event.label;
        date.value = props.event.occurred_at.slice(0, 10);
        notes.value = props.event.notes || '';
        showNotes.value = !!props.event.notes;
      } else {
        kind.value = 'application';
        label.value = '';
        date.value = todayInputValue();
        notes.value = '';
        showNotes.value = false;
      }
    });

    async function onSave() {
      if (!label.value.trim()) {
        error.value = 'Label is required';
        return;
      }
      saving.value = true;
      try {
        const occurredAt = new Date(date.value + 'T12:00:00Z').toISOString();
        if (isEdit.value) {
          await updateEvent(props.event.id, {
            kind: kind.value,
            label: label.value.trim(),
            occurred_at: occurredAt,
            notes: notes.value.trim() || null,
          });
        } else {
          await createEvent({
            job_id: props.jobId,
            kind: kind.value,
            label: label.value.trim(),
            occurred_at: occurredAt,
            notes: notes.value.trim() || null,
          });
        }
        emit('saved');
        emit('close');
      } catch (e) {
        error.value = e.message;
      } finally {
        saving.value = false;
      }
    }

    async function onDelete() {
      if (!props.event) return;
      if (!confirm('Delete this event?')) return;
      saving.value = true;
      try {
        await deleteEvent(props.event.id);
        emit('saved');
        emit('close');
      } catch (e) {
        error.value = e.message;
      } finally {
        saving.value = false;
      }
    }

    return { kind, label, date, notes, showNotes, saving, error,
             isEdit, KINDS, onSave, onDelete };
  },
  template: `
    <div v-if="open" class="modal-backdrop" @click.self="$emit('close')">
      <div class="modal">
        <h3>{{ isEdit ? 'Edit event' : 'Add event' }}</h3>

        <label>Kind
          <select v-model="kind">
            <option v-for="k in KINDS" :key="k" :value="k">{{ k }}</option>
          </select>
        </label>

        <label>Label
          <input type="text" v-model="label" placeholder="e.g., Tech interview" autofocus>
        </label>

        <label>Date
          <input type="date" v-model="date">
        </label>

        <button type="button" class="link-btn" @click="showNotes = !showNotes">
          {{ showNotes ? 'Hide notes' : 'More…' }}
        </button>
        <label v-if="showNotes">Notes
          <textarea v-model="notes" rows="4" placeholder="Optional details"></textarea>
        </label>

        <p v-if="error" class="error-banner">{{ error }}</p>

        <div class="modal-actions">
          <button type="button" class="btn btn-skip" @click="$emit('close')"
                  :disabled="saving">Cancel</button>
          <button v-if="isEdit" type="button" class="btn btn-warn" @click="onDelete"
                  :disabled="saving">Delete</button>
          <button type="button" class="btn btn-primary" @click="onSave"
                  :disabled="saving">{{ saving ? 'Saving…' : 'Save' }}</button>
        </div>
      </div>
    </div>
  `,
};
