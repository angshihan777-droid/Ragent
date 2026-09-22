import { ref, shallowRef, watch, onScopeDispose } from "vue";
import { api } from "../api.js";

// scope 为项目列表；跨项目与单项目页面共用同一套加载与竞态保护。
export function useDocuments(scope) {
  const documents = ref([]);
  const loading = shallowRef(false);
  const error = shallowRef("");
  let version = 0;
  async function reload() {
    const current = ++version;
    loading.value = true; error.value = "";
    try {
      const lists = await Promise.all(scope.value.map(async project =>
        (await api.listDocuments(project.id)).map(doc => ({ ...doc, project_id: project.id, project_name: project.name }))));
      if (current === version) documents.value = lists.flat();
    } catch (e) { if (current === version) error.value = e.message; }
    finally { if (current === version) loading.value = false; }
  }
  watch(scope, () => { documents.value = []; reload(); }, { immediate: true });
  onScopeDispose(() => { version++; });
  return { documents, loading, error, reload };
}
