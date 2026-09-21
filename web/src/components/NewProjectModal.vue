<script setup>
// 新建项目弹窗：填项目名/描述，并在创建时上传首批资料(PDF/Word/Markdown/txt)。
// 决策：创建即上传，知识库项目没资料没意义；但不强制(可稍后在知识库补)。
// 建项目后自动补一个默认 Agent(知识库助手,use_rag)，保证新项目立刻能开对话。
import { ref } from "vue";
import { api } from "../api.js";

const emit = defineEmits(["created", "close"]);
const name = ref("");
const description = ref("");
const files = ref([]);       // 待上传的 File 列表
const busy = ref(false);
const progress = ref("");    // 上传进度提示
const err = ref("");

const ACCEPT = ".pdf,.docx,.md,.markdown,.txt";

function onPick(e) {
  // 追加选择的文件，去重同名，允许多次点选累加
  const picked = Array.from(e.target.files || []);
  const names = new Set(files.value.map((f) => f.name));
  for (const f of picked) if (!names.has(f.name)) files.value.push(f);
  e.target.value = "";  // 清空 input，方便再次选同名文件
}
function removeFile(i) { files.value.splice(i, 1); }

async function submit() {
  if (!name.value.trim() || busy.value) return;
  busy.value = true; err.value = ""; progress.value = "";
  try {
    const project = await api.createProject(name.value.trim(), description.value.trim());
    await api.createAgent(project.id, {
      name: "知识库问答助手",
      persona: "严谨的资料检索员",
      system_prompt:
        "你是严谨的知识库助手。只根据检索到的参考资料回答，资料里没有就直说「资料里没有相关内容」，并在末尾标注依据的资料。",
      use_rag: true,
    });
    // 逐个上传首批资料：后端解析成文本→切块向量化入库
    for (let i = 0; i < files.value.length; i++) {
      progress.value = `上传资料 ${i + 1}/${files.value.length}：${files.value[i].name}`;
      await api.uploadDocument(project.id, files.value[i]);
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

      <div class="divider">首批资料（可选，支持 PDF / Word / Markdown / txt）</div>
      <label class="drop">
        <input type="file" :accept="ACCEPT" multiple @change="onPick" hidden />
        <span>点击选择文件</span>
      </label>
      <ul v-if="files.length" class="files">
        <li v-for="(f, i) in files" :key="f.name">
          <span class="fn">{{ f.name }}</span>
          <button class="x" @click="removeFile(i)">×</button>
        </li>
      </ul>

      <div v-if="progress" class="progress">{{ progress }}</div>
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
.divider { margin: 18px 0 4px; padding-top: 14px; border-top: 1px solid var(--line); font-size: 13px; color: var(--muted); }
.drop { display: flex; align-items: center; justify-content: center; padding: 18px; margin-top: 8px; border: 1px dashed var(--border); border-radius: 10px; color: var(--muted); font-size: 14px; cursor: pointer; }
.drop:hover { border-color: var(--accent); color: var(--accent); }
.files { list-style: none; margin: 10px 0 0; padding: 0; }
.files li { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px; border: 1px solid var(--border); border-radius: 8px; margin-bottom: 6px; background: var(--panel2); font-size: 13px; }
.files .fn { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.files .x { background: transparent; color: var(--muted); padding: 0 4px; font-size: 16px; box-shadow: none; }
.files .x:hover { color: var(--ink); background: transparent; }
.progress { margin-top: 12px; font-size: 13px; color: var(--accent-d); }
.err { margin-top: 12px; color: #c0392b; font-size: 14px; }
.actions { margin-top: 20px; display: flex; justify-content: flex-end; gap: 10px; }
.ghost { background: rgba(0,0,0,0.05); color: var(--muted); }
.ghost:hover:not(:disabled) { background: rgba(0,0,0,0.09); }
</style>
