import { ref, watch } from "vue";

// Layout preferences are optional: private mode / unavailable storage must not break navigation.
export function usePreference(key, fallback) {
  let initial = fallback;
  try {
    const saved = JSON.parse(localStorage.getItem(key));
    if (typeof saved === typeof fallback && (typeof saved !== "number" || Number.isFinite(saved))) initial = saved;
  } catch { /* use default */ }
  const value = ref(initial);
  watch(value, (next) => { try { localStorage.setItem(key, JSON.stringify(next)); } catch { /* optional */ } });
  return value;
}
