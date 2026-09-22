<script setup>
import { ref } from "vue";
import { store } from "../store.js";
import { api } from "../api.js";
const emit = defineEmits(["created", "close"]);
const title = ref("新会话");
const busy = ref(false);
const err = ref("");
async function submit() {
  if (busy.value) return;
  busy.value = true; err.value = "";
  try {
    const thread = await api.createThread(store.currentProjectId, title.value.trim() || "新会话");
    emit("created", thread.id);
  } catch (e) { err.value = e.message; }
  finally { busy.value = false; }
}
</script>
<template>
  <div class="mask" @click.self="!busy && emit('close')">
    <form class="modal" @submit.prevent="submit">
      <h3>新建会话</h3>
      <p>知识库助手会根据问题决定是否检索当前项目资料。</p>
      <label for="thread-title">会话标题</label>
      <input id="thread-title" v-model="title" maxlength="120" :disabled="busy" />
      <p v-if="err" class="err" role="alert">{{ err }}</p>
      <div class="actions">
        <button type="button" class="ghost" :disabled="busy" @click="emit('close')">取消</button>
        <button :disabled="busy">{{ busy ? '创建中…' : '创建会话' }}</button>
      </div>
    </form>
  </div>
</template>
<style scoped>
.mask { position: fixed; inset: 0; background: rgba(15,15,25,0.32); display: flex; align-items: center; justify-content: center; z-index: 50; }
.modal { background: #fff; border: 1px solid var(--border); border-radius: 14px; padding: 26px; width: 460px; max-width: 92vw; max-height: 88vh; overflow-y: auto; box-shadow: var(--shadow); }
h3 { margin: 0 0 8px; }
label { display: block; margin: 12px 0 6px; font-size: 13px; font-weight: 500; }
.err { margin-top: 12px; color: #c0392b; font-size: 14px; }
.actions { margin-top: 20px; display: flex; justify-content: flex-end; gap: 10px; }
.ghost { background: rgba(0,0,0,0.05); color: var(--muted); }
.ghost:hover:not(:disabled) { background: rgba(0,0,0,0.09); }
</style>
