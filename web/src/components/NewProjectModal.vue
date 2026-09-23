<script setup>
import { ref } from "vue";
import { api } from "../api.js";
import Icon from "./Icon.vue";
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
      <p class="sub">项目是资料与会话的容器，助手只在当前项目范围内检索。</p>
      <label for="project-name">项目名称 <span class="req">*</span></label>
      <input id="project-name" v-model="name" required maxlength="120" :disabled="busy || !!projectId" placeholder="例如：产品需求文档" />
      <label for="project-description">项目描述</label>
      <input id="project-description" v-model="description" :disabled="busy || !!projectId" placeholder="可选" />
      <div class="section">
        <h4>项目资料</h4>
        <p class="hint">支持 PDF、Markdown、Word（.docx）和 TXT，单文件最大 20 MB。扫描 PDF 请先 OCR，旧 .doc 请先转换。</p>
      </div>
      <label class="drop" :class="{ dragging }" @dragover.prevent="dragging = true" @dragleave.prevent="dragging = false" @drop.prevent="onDrop">
        <input type="file" :accept="ACCEPT" multiple :disabled="busy" @change="onPick" />
        <Icon name="upload" :size="20" />
        <span>点击选择或拖入多个文件</span>
      </label>
      <ul v-if="files.length" class="files" aria-live="polite">
        <li v-for="(item, index) in files" :key="item.key">
          <span class="file-icon" aria-hidden="true"><Icon name="book" :size="14" /></span>
          <div class="file-info">
            <span class="truncate">{{ item.file.name }}</span>
            <small :class="{ error: item.status === '失败' }">{{ item.status }}{{ item.error ? '：' + item.error : '' }}</small>
          </div>
          <button v-if="item.status !== '已入库'" type="button" class="quiet icon-btn" :disabled="busy" :aria-label="'移除 ' + item.file.name" @click="files.splice(index, 1)"><Icon name="x" :size="15" /></button>
          <span v-else class="done" aria-hidden="true"><Icon name="check" :size="15" /></span>
        </li>
      </ul>
      <p class="hint tail">{{ !name.trim() ? '请填写项目名称后继续。' : files.length && !projectId ? '文件已选好，点击“创建并上传”后开始入库。' : !files.length ? '也可以先创建空项目，稍后在项目资料中上传。' : '' }}</p>
      <p v-if="err" class="error-box" role="alert">{{ err }}</p>
      <div class="actions">
        <button type="button" class="secondary" :disabled="busy" @click="close">{{ projectId ? '先进入项目' : '取消' }}</button>
        <button class="btn-brand" :disabled="busy || !name.trim()">{{ busy ? '处理中…' : projectId ? '重试未完成文件' : files.length ? '创建并上传' : '创建项目' }}</button>
      </div>
    </form>
  </div>
</template>
<style scoped>
.mask { position: fixed; inset: 0; background: rgba(23, 23, 26, .34); backdrop-filter: blur(2px); display: flex; align-items: center; justify-content: center; z-index: 50; padding: var(--s-5); }
.modal { box-sizing: border-box; background: var(--surface); border: 1px solid var(--border); border-radius: var(--r-xl); padding: var(--s-6); width: 520px; max-width: 100%; max-height: 88dvh; overflow: auto; box-shadow: var(--shadow-lg); }
h3 { margin: 0; font-size: var(--fs-title); }
.sub { margin: var(--s-2) 0 var(--s-5); color: var(--muted); font-size: var(--fs-sm); line-height: 1.7; }
label { display: block; margin: var(--s-4) 0 var(--s-2); font-size: var(--fs-sm); font-weight: 500; color: var(--text); }
label[for="project-name"] { margin-top: 0; }
.req { color: var(--danger); }
.section { margin: var(--s-5) 0 var(--s-3); padding-top: var(--s-5); border-top: 1px solid var(--border-soft); }
.section h4 { margin: 0 0 var(--s-1); font-size: var(--fs-body); }
.hint { color: var(--faint); font-size: var(--fs-xs); line-height: 1.7; margin: 0; }
.tail { margin-top: var(--s-3); min-height: 1em; }
.drop { position: relative; display: flex; flex-direction: column; align-items: center; gap: var(--s-2); margin: 0; border: 1px dashed var(--border); border-radius: var(--r-lg); padding: var(--s-6) var(--s-5); text-align: center; cursor: pointer; color: var(--muted); font-size: var(--fs-sm); background: var(--surface-2); transition: border-color .12s var(--ease), color .12s var(--ease), background .12s var(--ease); }
.drop > svg { color: var(--brand); }
.drop:hover { border-color: var(--brand-line); color: var(--brand-ink); background: var(--brand-soft); }
.drop input { position: absolute; inset: 0; opacity: 0; cursor: pointer; width: 100%; }
.drop:focus-within, .drop.dragging { border-color: var(--brand); background: var(--brand-soft); color: var(--brand-ink); outline: 3px solid var(--ring); outline-offset: 1px; }
.files { list-style: none; padding: 0; margin: var(--s-3) 0 0; border: 1px solid var(--border-soft); border-radius: var(--r-md); overflow: hidden; }
.files li { display: flex; gap: var(--s-3); align-items: center; padding: var(--s-3); background: var(--surface); }
.files li + li { border-top: 1px solid var(--border-soft); }
.file-icon { flex-shrink: 0; width: 26px; height: 26px; display: grid; place-content: center; border-radius: var(--r-sm); background: var(--surface-3); color: var(--muted); }
.file-info { flex: 1; min-width: 0; font-size: var(--fs-sm); }
.file-info small { display: block; color: var(--faint); margin-top: 2px; font-size: var(--fs-xs); overflow-wrap: anywhere; }
.file-info small.error { color: var(--danger-ink); }
.icon-btn { padding: var(--s-2); border-radius: var(--r-sm); flex-shrink: 0; }
.icon-btn:hover:not(:disabled) { background: var(--danger-soft); color: var(--danger-ink); }
.done { flex-shrink: 0; color: var(--brand); display: grid; place-content: center; }
.error-box { margin-top: var(--s-3); }
.actions { display: flex; justify-content: flex-end; gap: var(--s-2); margin-top: var(--s-5); }
</style>
