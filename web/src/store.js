// 全局轻量状态：当前选中的项目 + 其下会话列表。
// 决策：只有「当前项目/会话」是跨页面共享的选择态，用一个 reactive 对象够了，
// 不引 Pinia——单人精简版没有复杂状态流转，避免过度设计。
import { reactive } from "vue";
import { api } from "./api.js";

export const store = reactive({
  projects: [],
  currentProjectId: null,
  threads: [],      // 当前项目下的会话
  currentThreadId: null,
  threadsByProject: {},
  docsByProject: {},   // 每个项目的资料列表，供左栏内联增删改
  projectLoading: false,

  // LLM 配置：左栏展示当前模型并支持切换；models 是可切换的候选列表
  llm: { base_url: "", model: "", key_set: false },
  models: [],

  get currentProject() {
    return this.projects.find((p) => p.id === this.currentProjectId) || null;
  },
  get currentThread() {
    return this.threads.find((t) => t.id === this.currentThreadId) || null;
  },

  async loadProjects() {
    this.projects = await api.listProjects();
    // 没选中或选中的已被删，则默认选第一个项目
    if (!this.projects.find((p) => p.id === this.currentProjectId)) {
      this.currentProjectId = this.projects[0]?.id || null;
    }
    this.threadsByProject = Object.fromEntries(Object.entries(this.threadsByProject).filter(([id]) => this.projects.some(p => p.id === id)));
    if (this.currentProjectId) await this.loadProjectDetail();
    else { this.threads = []; this.currentThreadId = null; }
  },

  async loadProjectThreads(id) {
    const threads = await api.listThreads(id);
    this.threadsByProject[id] = threads;
    return threads;
  },

  async loadProjectDocuments(id) {
    const docs = await api.listDocuments(id);
    this.docsByProject[id] = docs;
    return docs;
  },

  async loadProjectDetail() {
    const id = this.currentProjectId;
    if (!id) return;
    this.projectLoading = true;
    try {
      const threads = await this.loadProjectThreads(id);
      // Ignore late responses from a project that is no longer selected.
      if (this.currentProjectId !== id) return;
      this.threads = threads;
      // 仅保留用户明确打开的会话，不默认打开历史记录。
      this.currentThreadId = threads.find(t => t.id === this.currentThreadId)?.id || null;
    } finally {
      if (this.currentProjectId === id) this.projectLoading = false;
    }
  },

  async selectProject(id) {
    if (this.currentProjectId === id) return;
    this.currentProjectId = id;
    this.currentThreadId = null;
    this.threads = [];
    await this.loadProjectDetail();
  },

  async selectThread(id) {
    if (!this.threads.some(t => t.id === id)) return;
    this.currentThreadId = id;
  },

  async deleteThread(id) {
    // 删当前会话后回到空白页，不自动展示另一段历史。
    await api.deleteThread(id);
    if (this.currentThreadId === id) this.currentThreadId = null;
    await this.loadProjectDetail();
  },

  async loadLLM() {
    // 读当前生效配置；已保存的模型先进候选列表，未拉取远端列表时也能展示/切换
    this.llm = await api.getLLMConfig();
    if (this.llm.model && !this.models.includes(this.llm.model)) {
      this.models = [this.llm.model, ...this.models];
    }
  },

  async switchModel(model) {
    // 左栏一键切模型：空密钥表示不改密钥，保留库里原值
    await api.saveLLMConfig(this.llm.base_url, model, "");
    this.llm = await api.getLLMConfig();
  },

});
