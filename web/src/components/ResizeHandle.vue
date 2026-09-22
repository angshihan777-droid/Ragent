<script setup>
import { onBeforeUnmount } from "vue";
const props = defineProps({ modelValue: Number, min: Number, max: Number, reverse: Boolean, label: String });
const emit = defineEmits(["update:modelValue"]);
let cleanup;
function update(value) { emit("update:modelValue", Math.round(Math.min(props.max, Math.max(props.min, value)))); }
function start(event) {
  if (event.button !== 0) return;
  cleanup?.();
  const startX = event.clientX, initial = props.modelValue;
  const move = (e) => update(initial + (e.clientX - startX) * (props.reverse ? -1 : 1));
  const stop = () => {
    window.removeEventListener("pointermove", move);
    window.removeEventListener("pointerup", stop);
    window.removeEventListener("pointercancel", stop);
    window.removeEventListener("blur", stop);
    document.body.classList.remove("resizing");
  };
  cleanup = stop;
  window.addEventListener("pointermove", move);
  window.addEventListener("pointerup", stop);
  window.addEventListener("pointercancel", stop);
  window.addEventListener("blur", stop);
  document.body.classList.add("resizing");
  event.preventDefault();
}
function keydown(event) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  event.preventDefault();
  if (event.key === "Home") update(props.min);
  else if (event.key === "End") update(props.max);
  else update(props.modelValue + (event.key === "ArrowRight" ? 16 : -16) * (props.reverse ? -1 : 1));
}
onBeforeUnmount(() => cleanup?.());
</script>

<template>
  <div class="resize-handle" role="separator" tabindex="0" aria-orientation="vertical"
    :aria-label="label" :aria-valuenow="modelValue" :aria-valuemin="min" :aria-valuemax="max"
    @pointerdown="start" @keydown="keydown"><span></span></div>
</template>

<style scoped>
.resize-handle { width: 8px; flex: 0 0 8px; cursor: col-resize; touch-action: none; display: grid; place-items: center; background: var(--panel2); }
.resize-handle span { width: 2px; height: 32px; border-radius: 2px; background: var(--border); }
.resize-handle:hover span, .resize-handle:focus-visible span { background: var(--accent); }
@media (max-width: 760px) { .resize-handle { display: none; } }
</style>
