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
  projectLoading: false,

  // LLM 配置：左栏展示当前模型并支持切换；models 是可切换的候选列表
  llm: { base_url: "", model: "", key_set: false },
  models: [],

  // 当前身份 id：只做展示与迁移用。
  // 为什么要存一份在前端：身份本体在 httpOnly Cookie 里，JS 读不到，
  // 想在界面上显示「你是谁」只能靠后端接口回一次再缓存，不能从 document.cookie 取。
  ownerId: "",

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

  async loadIdentity() {
    const { owner_id } = await api.getIdentity();
    this.ownerId = owner_id;
  },

  async switchIdentity(ownerId) {
    // 切换后本地缓存的项目/会话全是上一个身份的，必须整体重载，
    // 否则界面上还留着旧列表，点进去却 404，看着像后端坏了
    const { owner_id } = await api.switchIdentity(ownerId);
    this.ownerId = owner_id;
    this.currentProjectId = null;
    this.currentThreadId = null;
    this.threads = [];
    this.threadsByProject = {};
    await this.loadProjects();
    await this.loadLLM();
  },

  async switchModel(model) {
    // 左栏一键切模型：空密钥表示不改密钥，保留库里原值
    await api.saveLLMConfig(this.llm.base_url, model, "");
    this.llm = await api.getLLMConfig();
  },

});
