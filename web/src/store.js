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
    if (this.currentProjectId) await this.loadProjectDetail();
  },

  async loadProjectDetail() {
    // 切项目要同时刷新它的 Agent 与会话；会话默认选最新一条
    const [agents, threads] = await Promise.all([
      api.listAgents(this.currentProjectId),
      api.listThreads(this.currentProjectId),
    ]);
    this.agents = agents;
    this.threads = threads;
    if (!this.threads.find((t) => t.id === this.currentThreadId)) {
      this.currentThreadId = this.threads[0]?.id || null;
    }
  },

  async selectProject(id) {
    this.currentProjectId = id;
    this.currentThreadId = null;
    await this.loadProjectDetail();
  },

  async selectThread(id) {
    this.currentThreadId = id;
  },

  async deleteThread(id) {
    // 删当前会话后，若删的正是选中项，回退到剩下的第一条（可能为空）
    await api.deleteThread(id);
    if (this.currentThreadId === id) this.currentThreadId = null;
    await this.loadProjectDetail();
  },

  agentOf(thread) {
    return this.agents.find((a) => a.id === thread?.agent_id) || null;
  },
});
