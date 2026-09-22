// 全局轻量状态：当前选中的项目 + 其下 Agent/会话列表。
// 决策：只有「当前项目/会话」是跨页面共享的选择态，用一个 reactive 对象够了，
// 不引 Pinia——单人精简版没有复杂状态流转，避免过度设计。
import { reactive } from "vue";
import { api } from "./api.js";

export const store = reactive({
  projects: [],
  currentProjectId: null,
  agents: [],       // 当前项目下的 Agent
  threads: [],      // 当前项目下的会话
  currentThreadId: null,
  threadsByProject: {},
  selectedThreads: {},
  projectLoading: false,

  // LLM 配置：左栏展示当前模型并支持切换；models 是可切换的候选列表
  llm: { base_url: "", model: "", key_set: false },
  models: [],

  // 知识库「图书馆」：跨项目看所有资料，也能按项目筛选
  library: [],        // [{project_id, project_name, id, title, chunk_count, created_at}]

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
    else { this.agents = []; this.threads = []; this.currentThreadId = null; }
  },

  async loadProjectThreads(id) {
    const threads = await api.listThreads(id);
    this.threadsByProject[id] = threads;
    return threads;
  },

  async loadProjectDetail() {
    const id = this.currentProjectId;
    if (!id) return;
    this.projectLoading = true;
    try {
      const [agents, threads] = await Promise.all([api.listAgents(id), this.loadProjectThreads(id)]);
      // Ignore late responses from a project that is no longer selected.
      if (this.currentProjectId !== id) return;
      this.agents = agents;
      this.threads = threads;
      const preferred = this.currentThreadId || this.selectedThreads[id];
      this.currentThreadId = threads.find(t => t.id === preferred)?.id || threads[0]?.id || null;
    } finally {
      if (this.currentProjectId === id) this.projectLoading = false;
    }
  },

  async selectProject(id) {
    if (this.currentProjectId === id) return;
    if (this.currentProjectId) this.selectedThreads[this.currentProjectId] = this.currentThreadId;
    this.currentProjectId = id;
    this.currentThreadId = null;
    this.agents = []; this.threads = [];
    await this.loadProjectDetail();
  },

  async selectThread(id) {
    if (!this.threads.some(t => t.id === id)) return;
    this.currentThreadId = id;
    this.selectedThreads[this.currentProjectId] = id;
  },

  async deleteThread(id) {
    // 删当前会话后，若删的正是选中项，回退到剩下的第一条（可能为空）
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

  async loadLibrary() {
    // 图书馆视图：汇总所有项目的资料，标注归属项目，前端可按项目筛选
    const all = [];
    for (const p of this.projects) {
      const docs = await api.listDocuments(p.id);
      for (const d of docs) all.push({ ...d, project_id: p.id, project_name: p.name });
    }
    this.library = all;
  },

  agentOf(thread) {
    return this.agents.find((a) => a.id === thread?.agent_id) || null;
  },
});
