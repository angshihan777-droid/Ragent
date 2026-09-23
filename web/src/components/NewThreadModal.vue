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
      <p class="sub">知识库助手会根据问题决定是否检索当前项目资料。</p>
      <label for="thread-title">会话标题</label>
      <input id="thread-title" v-model="title" maxlength="120" :disabled="busy" />
      <p v-if="err" class="error-box" role="alert">{{ err }}</p>
      <div class="actions">
        <button type="button" class="secondary" :disabled="busy" @click="emit('close')">取消</button>
        <button class="btn-brand" :disabled="busy">{{ busy ? '创建中…' : '创建会话' }}</button>
      </div>
    </form>
  </div>
</template>
<style scoped>
.mask { position: fixed; inset: 0; background: rgba(23, 23, 26, .34); backdrop-filter: blur(2px); display: flex; align-items: center; justify-content: center; z-index: 50; padding: var(--s-5); }
.modal { box-sizing: border-box; background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-xl); padding: var(--s-6); width: 460px; max-width: 100%; max-height: 88dvh; overflow-y: auto; box-shadow: var(--shadow-lg); }
h3 { margin: 0; font-size: var(--fs-title); }
.sub { margin: var(--s-2) 0 var(--s-5); color: var(--muted); font-size: var(--fs-sm); line-height: 1.7; }
label { display: block; margin: 0 0 var(--s-2); font-size: var(--fs-sm); font-weight: 500; color: var(--text); }
.error-box { margin-top: var(--s-4); }
.actions { margin-top: var(--s-5); display: flex; justify-content: flex-end; gap: var(--s-2); }
</style>
