<script setup>
// 新建会话弹窗：选一个 Agent + 起标题。也能顺手在本项目新建一个自定义 Agent。
// 决策：会话必须绑定 Agent（调度键要 agent 段），故这里强制选一个；
// 允许当场建 Agent，省得为了换个人设先跳到别处。
import { ref } from "vue";
import { store } from "../store.js";
import { api } from "../api.js";

const emit = defineEmits(["created", "close"]);
const title = ref("新会话");
const agentId = ref(store.agents[0]?.id || "");
const busy = ref(false);
const err = ref("");

// 内联新建 Agent 的表单
const creatingAgent = ref(false);
const na = ref({ name: "", persona: "", system_prompt: "", use_rag: true });

async function addAgent() {
  if (!na.value.name.trim()) return;
  busy.value = true;
  err.value = "";
  try {
    const agent = await api.createAgent(store.currentProjectId, {
      name: na.value.name.trim(),
      persona: na.value.persona.trim(),
      system_prompt: na.value.system_prompt.trim(),
      use_rag: na.value.use_rag,
    });
    await store.loadProjectDetail();
    agentId.value = agent.id;
    creatingAgent.value = false;
    na.value = { name: "", persona: "", system_prompt: "", use_rag: true };
  } catch (e) {
    err.value = "新建 Agent 失败: " + e.message;
  } finally {
    busy.value = false;
  }
}

async function submit() {
  if (!agentId.value || busy.value) return;
  busy.value = true;
  err.value = "";
  try {
    const thread = await api.createThread(store.currentProjectId, agentId.value, title.value.trim() || "新会话");
    emit("created", thread.id);
  } catch (e) {
    err.value = "创建会话失败: " + e.message;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="mask" @click.self="emit('close')">
    <div class="modal">
      <h3>新建会话</h3>
      <label>会话标题</label>
      <input v-model="title" placeholder="新会话" />

      <label>选择 Agent</label>
      <select v-model="agentId">
        <option v-for="a in store.agents" :key="a.id" :value="a.id">
          {{ a.name }}{{ a.use_rag ? "（检索资料）" : "（不检索）" }}
        </option>
      </select>

      <button v-if="!creatingAgent" class="link" @click="creatingAgent = true">+ 新建一个 Agent</button>
      <div v-else class="new-agent">
        <label>名称 *</label>
        <input v-model="na.name" placeholder="例如：面试八股讲解官" />
        <label>一句话人设</label>
        <input v-model="na.persona" placeholder="例如：结构化讲解的面试导师" />
        <label>系统提示词</label>
        <textarea v-model="na.system_prompt" rows="3" placeholder="喂给模型的系统设定" />
        <label class="check"><input type="checkbox" v-model="na.use_rag" /> 回答时检索本项目资料 (RAG)</label>
        <div class="mini-actions">
          <button class="ghost" @click="creatingAgent = false">收起</button>
          <button :disabled="busy || !na.name.trim()" @click="addAgent">保存 Agent</button>
        </div>
      </div>

      <div v-if="err" class="err">{{ err }}</div>
      <div class="actions">
        <button class="ghost" @click="emit('close')">取消</button>
        <button :disabled="busy || !agentId" @click="submit">创建会话</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mask { position: fixed; inset: 0; background: rgba(45,45,42,0.42); display: flex; align-items: center; justify-content: center; z-index: 50; }
.modal { background: var(--card); border-radius: 14px; padding: 24px; width: 460px; max-width: 92vw; max-height: 88vh; overflow-y: auto; box-shadow: 0 20px 40px rgba(0,0,0,0.25); }
h3 { margin: 0 0 8px; }
label { display: block; margin: 12px 0 6px; font-size: 13px; font-weight: 500; }
.check { display: flex; align-items: center; gap: 8px; font-weight: 400; }
.check input { width: auto; }
.link { background: none; border: none; color: var(--primary); padding: 10px 0 0; cursor: pointer; font-size: 14px; }
.new-agent { margin-top: 8px; padding: 12px; border: 1px dashed var(--border); border-radius: 10px; }
.mini-actions { margin-top: 12px; display: flex; justify-content: flex-end; gap: 8px; }
.err { margin-top: 12px; color: #b91c1c; font-size: 14px; }
.actions { margin-top: 20px; display: flex; justify-content: flex-end; gap: 10px; }
.ghost { background: rgba(0,0,0,0.05); color: var(--muted); }
.ghost:hover:not(:disabled) { background: rgba(0,0,0,0.09); }
</style>
