<script setup>
import { ref } from "vue";
import { api } from "../api.js";
const emit = defineEmits(["created", "close"]);
const ACCEPT = ".pdf,.docx,.md,.markdown,.txt";
const name = ref("");
const description = ref("");
const files = ref([]);
const projectId = ref(null);
const busy = ref(false);
const err = ref("");
const dragging = ref(false);

function addFiles(picked) {
  if (busy.value) return;
  err.value = "";
  for (const file of picked) {
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!ACCEPT.split(',').includes(ext) || file.size > 20 * 1024 * 1024) {
      err.value = `${file.name}：请使用支持的格式，且单文件不超过 20 MB。`;
      continue;
    }
    if (!name.value.trim() && !projectId.value) name.value = file.name.replace(/\.[^.]+$/, "").slice(0, 120);
    const key = `${file.name}:${file.size}:${file.lastModified}`;
    if (!files.value.some(item => item.key === key)) files.value.push({ key, file, status: "已选择，创建后自动上传", error: "" });
  }
}
function onPick(event) { addFiles(event.target.files); event.target.value = ""; }
function onDrop(event) { dragging.value = false; addFiles(event.dataTransfer.files); }
function close() {
  if (busy.value) return;
  if (projectId.value) emit("created", projectId.value);
  else emit("close");
}
async function submit() {
  if (!name.value.trim() || busy.value) return;
  busy.value = true; err.value = "";
  try {
    // 项目与首个会话由后端一次事务创建；文件失败后重试不重建项目。
    if (!projectId.value) {
      const project = await api.createProject(name.value.trim(), description.value.trim());
      projectId.value = project.id;
    }
    for (const item of files.value.filter(item => item.status !== "已入库")) {
      item.status = "上传并入库中"; item.error = "";
      try {
        await api.uploadDocument(projectId.value, item.file);
        item.status = "已入库";
      } catch (e) { item.status = "失败"; item.error = e.message; }
    }
    if (files.value.some(item => item.status === "失败")) err.value = "项目已创建，成功资料已保留。可重试失败文件，或先进入项目。";
    else emit("created", projectId.value);
  } catch (e) { err.value = e.message; }
  finally { busy.value = false; }
}
</script>
<template>
  <div class="mask" @click.self="close">
    <form class="modal" @submit.prevent="submit">
      <h3>{{ projectId ? '添加项目资料' : '新建知识库项目' }}</h3>
      <label for="project-name">项目名称 *</label>
      <input id="project-name" v-model="name" required maxlength="120" :disabled="busy || !!projectId" placeholder="项目名称" />
      <label for="project-description">项目描述</label>
      <input id="project-description" v-model="description" :disabled="busy || !!projectId" placeholder="可选" />
      <h4>项目资料</h4>
      <p class="hint">支持 PDF、Markdown、Word（.docx）和 TXT，单文件最大 20 MB。扫描 PDF 请先 OCR，旧 .doc 请先转换。</p>
      <label class="drop" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="onDrop">
        <input type="file" :accept="ACCEPT" multiple :disabled="busy" @change="onPick" />
        <span>点击选择或拖入多个文件</span>
      </label>
      <ul class="files" aria-live="polite">
        <li v-for="(item, index) in files" :key="item.key">
          <div class="file-info"><span>{{ item.file.name }}</span><small :class="{ error: item.status === '失败' }">{{ item.status }}{{ item.error ? '：' + item.error : '' }}</small></div>
          <button v-if="item.status !== '已入库'" type="button" class="ghost" :disabled="busy" :aria-label="'移除 ' + item.file.name" @click="files.splice(index, 1)">×</button>
        </li>
      </ul>
      <p v-if="files.length && !projectId" class="hint">文件已选好，点击“创建并上传”后开始入库。</p>
      <p v-if="!name.trim()" class="hint">请填写项目名称后继续。</p>
      <p v-if="!files.length" class="hint">也可以先创建空项目，稍后在项目资料中上传。</p>
      <p v-if="err" class="error" role="alert">{{ err }}</p>
      <div class="actions">
        <button type="button" class="ghost" :disabled="busy" @click="close">{{ projectId ? '先进入项目' : '取消' }}</button>
        <button :disabled="busy || !name.trim()">{{ busy ? '处理中…' : projectId ? '重试未完成文件' : files.length ? '创建并上传' : '创建项目' }}</button>
      </div>
    </form>
  </div>
</template>
<style scoped>
.mask { position: fixed; inset: 0; background: rgba(45,45,42,.42); display: flex; align-items: center; justify-content: center; z-index: 50; }
.modal { background: var(--panel); border-radius: 14px; padding: 24px; width: 520px; max-width: 92vw; max-height: 88dvh; overflow: auto; box-shadow: 0 20px 40px rgba(0,0,0,.2); }
h3 { margin: 0 0 12px; } h4 { margin-bottom: 6px; }
label { display: block; margin: 12px 0 6px; font-size: 13px; }
.hint { color: var(--muted); font-size: 12px; line-height: 1.7; }
.drop { position: relative; border: 1px dashed var(--border); border-radius: 10px; padding: 24px; text-align: center; cursor: pointer; color: var(--accent-d); }
.drop input { position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; }
.drop:focus-within, .dragging { outline: 2px solid var(--accent); outline-offset: 2px; }
.files { list-style: none; padding: 0; }
.files li { display: flex; gap: 12px; justify-content: space-between; align-items: center; padding: 10px; border-bottom: 1px solid var(--line); }
.file-info { min-width: 0; overflow-wrap: anywhere; font-size: 13px; }.file-info small { display: block; color: var(--muted); margin-top: 4px; }
.error, .file-info .error { color: #ad3737; font-size: 13px; }
.actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 20px; }
.ghost { background: var(--panel); color: var(--ink); border: 1px solid var(--line); }
</style>
