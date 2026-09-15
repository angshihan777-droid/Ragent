<script setup>
// 新建项目弹窗：引导用户填项目名 + 首批资料(可选)。
// 决策：创建时就提示传资料，因为知识库项目没资料就没意义；
// 但不强制(留空也能建)，避免挡住只想先建壳的用户。
// 建项目后自动补一个默认 Agent(知识库助手,use_rag)，保证新项目立刻能开对话。
import { ref } from "vue";
import { api } from "../api.js";

const emit = defineEmits(["created", "close"]);
const name = ref("");
const description = ref("");
const docTitle = ref("");
const docContent = ref("");
const busy = ref(false);
const err = ref("");

async function submit() {
  if (!name.value.trim() || busy.value) return;
  busy.value = true;
  err.value = "";
  try {
    const project = await api.createProject(name.value.trim(), description.value.trim());
    // 默认 Agent：新项目至少要有一个能对话的 Agent
    await api.createAgent(project.id, {
      name: "知识库问答助手",
      persona: "严谨的资料检索员",
      system_prompt:
        "你是严谨的知识库助手。只根据检索到的参考资料回答，资料里没有就直说「资料里没有相关内容」，并在末尾标注依据的资料。",
      use_rag: true,
    });
    // 首批资料可选：填了才入库
    if (docTitle.value.trim() && docContent.value.trim()) {
      await api.ingestDocument(project.id, docTitle.value.trim(), docContent.value.trim());
    }
    emit("created", project.id);
  } catch (e) {
    err.value = "创建失败: " + e.message;
  } finally {
    busy.value = false;
  }
}
</script>

<template>
  <div class="mask" @click.self="emit('close')">
    <div class="modal">
      <h3>新建项目</h3>
      <label>项目名称 *</label>
      <input v-model="name" placeholder="例如：公司制度问答" />
      <label>项目描述</label>
      <input v-model="description" placeholder="一句话说明这个项目做什么（可选）" />

      <div class="divider">首批资料（可选，建完也能在「资料管理」里加）</div>
      <label>资料标题</label>
      <input v-model="docTitle" placeholder="例如：请假制度" />
      <label>资料正文</label>
      <textarea v-model="docContent" rows="5" placeholder="粘贴资料正文，会自动切块向量化用于检索" />

      <div v-if="err" class="err">{{ err }}</div>
      <div class="actions">
        <button class="ghost" @click="emit('close')">取消</button>
        <button :disabled="busy || !name.trim()" @click="submit">
          {{ busy ? "创建中" : "创建项目" }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.mask {
  position: fixed; inset: 0; background: rgba(45,45,42,0.42);
  display: flex; align-items: center; justify-content: center; z-index: 50;
}
.modal {
  background: var(--card); border-radius: 14px; padding: 24px; width: 480px; max-width: 92vw;
  max-height: 88vh; overflow-y: auto; box-shadow: 0 20px 40px rgba(0,0,0,0.25);
}
h3 { margin: 0 0 8px; }
label { display: block; margin: 12px 0 6px; font-size: 13px; font-weight: 500; }
.divider { margin: 18px 0 4px; padding-top: 14px; border-top: 1px solid var(--border); font-size: 13px; color: var(--muted); }
.err { margin-top: 12px; color: #b91c1c; font-size: 14px; }
.actions { margin-top: 20px; display: flex; justify-content: flex-end; gap: 10px; }
.ghost { background: rgba(0,0,0,0.05); color: var(--muted); }
.ghost:hover:not(:disabled) { background: rgba(0,0,0,0.09); }
</style>
