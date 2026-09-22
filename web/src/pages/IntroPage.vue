<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

const tutorialSteps = [
  { no: "01", icon: "⌘", title: "创建项目", body: "先建立一个独立的知识空间。项目资料、会话和检索范围彼此隔离。", detail: "项目 → 新建项目 → 填写名称" },
  { no: "02", icon: "▧", title: "放入资料", body: "上传 PDF、Markdown 或 Word，系统会解析结构、切分内容并建立向量索引。", detail: "资料 → 上传资料 → 等待入库" },
  { no: "03", icon: "⌕", title: "提出问题", body: "在项目会话中提问。知识库 Agent 会先判断是否需要检索，而不是每次都盲目查库。", detail: "新对话 → 输入问题 → 发送" },
  { no: "04", icon: "↗", title: "核对依据", body: "答案会带上来源，右侧面板展示执行过程、命中资料和匹配度。", detail: "回答 → 查看引用 → 回到原文" },
];

const activeTutorial = ref(0);
const tutorialPlaying = ref(true);
let tutorialTimer;
function startTutorialTimer() {
  clearInterval(tutorialTimer);
  if (!tutorialPlaying.value) return;
  tutorialTimer = setInterval(() => {
    activeTutorial.value = (activeTutorial.value + 1) % tutorialSteps.length;
  }, 3600);
}
function selectTutorial(index) {
  activeTutorial.value = index;
  startTutorialTimer();
}
function toggleTutorial() {
  tutorialPlaying.value = !tutorialPlaying.value;
  startTutorialTimer();
}

const pipelineStages = [
  { key: "send", no: "01", label: "发送请求", front: "输入框提交问题", back: "API 创建 request + run，写入 PostgreSQL" },
  { key: "context", no: "02", label: "准备上下文", front: "对话区出现“正在处理”", back: "读取项目、会话与此前已完成的问答" },
  { key: "decide", no: "03", label: "判断是否检索", front: "右侧执行过程高亮决策", back: "知识库 Agent 输出 direct / clarify / retrieve" },
  { key: "retrieve", no: "04", label: "检索与重排", front: "命中资料卡片逐条出现", back: "向量召回 → cross-encoder 重排 → 返回来源" },
  { key: "answer", no: "05", label: "生成并校验", front: "答案带引用显示", back: "回答 → 引用结构检查 → 原子写入最终结果" },
  { key: "done", no: "06", label: "结束本轮", front: "执行卡片显示已完成", back: "SSE 推送终态；断线时从 PostgreSQL 补发" },
];
const activePipeline = ref(-1);
const pipelineRunning = ref(false);
let pipelineTimer;
const pipelineStage = computed(() => pipelineStages[activePipeline.value] || null);
function resetPipeline() {
  clearInterval(pipelineTimer);
  activePipeline.value = -1;
  pipelineRunning.value = false;
}
function playPipeline() {
  clearInterval(pipelineTimer);
  activePipeline.value = 0;
  pipelineRunning.value = true;
  pipelineTimer = setInterval(() => {
    if (activePipeline.value >= pipelineStages.length - 1) {
      clearInterval(pipelineTimer);
      pipelineRunning.value = false;
      return;
    }
    activePipeline.value += 1;
  }, 1150);
}
function stageState(index) {
  if (activePipeline.value < 0) return "idle";
  if (index < activePipeline.value) return "done";
  if (index === activePipeline.value) return pipelineRunning.value ? "running" : "done";
  return "waiting";
}
onMounted(() => startTutorialTimer());
onBeforeUnmount(() => { clearInterval(tutorialTimer); clearInterval(pipelineTimer); });
</script>

<template>
  <main class="intro-page">
    <section class="intro-hero">
      <div class="eyebrow"><span class="eyebrow-dot"></span> RAGENT / KNOWLEDGE WORKSPACE</div>
      <h1>让每个答案，<em>都有来处。</em></h1>
      <p class="hero-copy">这是一个面向项目资料的知识工作台：资料进入索引，问题进入 LangGraph，答案带着可核对的依据回来。</p>
      <div class="hero-actions">
        <RouterLink class="hero-primary" to="/chat">进入知识工作台 <span>↗</span></RouterLink>
        <a class="hero-secondary" href="#how-it-works">先看它怎么运行 <span>↓</span></a>
      </div>
      <div class="hero-note"><span>●</span> 单一知识库 Agent · 按需检索 · 项目级隔离 · 可追溯回答</div>
    </section>

    <section class="tutorial-section" id="how-it-works">
      <div class="section-heading">
        <div><span class="section-kicker">01 / 使用教程</span><h2>从资料，到答案</h2></div>
        <button class="play-button" type="button" @click="toggleTutorial">{{ tutorialPlaying ? "暂停动画" : "播放动画" }} <span>{{ tutorialPlaying ? "Ⅱ" : "▶" }}</span></button>
      </div>
      <div class="tutorial-layout">
        <div class="tutorial-visual">
          <div class="visual-grid"></div>
          <div class="tutorial-orbit orbit-one"></div><div class="tutorial-orbit orbit-two"></div>
          <div class="tutorial-core"><span>{{ tutorialSteps[activeTutorial].icon }}</span><small>{{ tutorialSteps[activeTutorial].no }}</small></div>
          <div class="tutorial-float float-top">{{ tutorialSteps[activeTutorial].detail }}</div>
          <div class="tutorial-float float-bottom"><span class="pulse-dot"></span> {{ activeTutorial === 3 ? "依据已就绪" : "工作台正在运行" }}</div>
        </div>
        <div class="tutorial-copy">
          <div class="tutorial-progress"><span v-for="(_, index) in tutorialSteps" :key="index" :class="{ active: index === activeTutorial, done: index < activeTutorial }"></span></div>
          <button v-for="(step, index) in tutorialSteps" :key="step.no" type="button" class="tutorial-step" :class="{ active: index === activeTutorial }" @click="selectTutorial(index)">
            <span class="step-no">{{ step.no }}</span><span class="step-icon">{{ step.icon }}</span><span class="step-content"><strong>{{ step.title }}</strong><small>{{ step.body }}</small></span><span class="step-arrow">↗</span>
          </button>
        </div>
      </div>
    </section>

    <section class="pipeline-section">
      <div class="section-heading pipeline-heading">
        <div><span class="section-kicker">02 / 点击之后</span><h2>一次提问，前后端如何一起动起来？</h2><p>点击左侧的发送按钮，观察浏览器界面与服务端状态沿着同一条链路同步变化。</p></div>
        <button class="pipeline-button" type="button" @click="playPipeline"><span>{{ pipelineRunning ? "执行中…" : activePipeline >= pipelineStages.length - 1 ? "再演示一次" : "点击发送问题" }}</span><b>↑</b></button>
      </div>
      <div class="pipeline-board" :class="{ running: pipelineRunning }">
        <div class="browser-side">
          <div class="board-label"><span class="label-dot front-dot"></span> 浏览器 / 前端状态</div>
          <div class="mock-chat">
            <div class="mock-head"><span>测试 / 知识库对话</span><span class="mock-status">{{ activePipeline < 0 ? "等待输入" : pipelineStage.front }}</span></div>
            <div class="mock-message user-message">正式员工每年有几天带薪年假？</div>
            <div class="mock-message assistant-message" :class="{ visible: activePipeline >= 4 }"><span class="mock-spark">✦</span><span>{{ activePipeline >= 4 ? "正式员工每年享有 15 天带薪年假。" : "等待知识库助手回答…" }}</span><i v-if="activePipeline >= 4">[S1]</i></div>
            <div class="mock-composer"><span>{{ activePipeline < 0 ? "输入问题…" : activePipeline >= 5 ? "本轮已完成" : "正在处理本轮问题…" }}</span><button type="button" :disabled="pipelineRunning" @click="playPipeline">↑</button></div>
          </div>
          <div class="front-events"><div v-for="(stage, index) in pipelineStages" :key="stage.key" class="event-line" :class="stageState(index)"><span>{{ stageState(index) === 'done' ? '✓' : stageState(index) === 'running' ? '•' : '○' }}</span>{{ stage.front }}</div></div>
        </div>
        <div class="sync-rail"><div class="sync-line"></div><span class="sync-badge">同步</span><div class="sync-caption">同一个 request_id<br>贯穿整次执行</div></div>
        <div class="backend-side">
          <div class="board-label"><span class="label-dot back-dot"></span> 服务端 / LangGraph + RAG</div>
          <div class="backend-terminal">
            <div class="terminal-head"><span>ragent-worker</span><span>{{ activePipeline < 0 ? "idle" : pipelineRunning ? "running" : "done" }}</span></div>
            <div class="terminal-body"><div v-for="(stage, index) in pipelineStages" :key="stage.key" class="backend-stage" :class="stageState(index)"><span class="stage-marker">{{ stage.no }}</span><div><strong>{{ stage.label }}</strong><small>{{ stage.back }}</small></div><em>{{ stageState(index) === 'done' ? 'done' : stageState(index) === 'running' ? 'running' : 'queued' }}</em></div></div>
          </div>
          <div class="backend-note"><span>↳</span><span>{{ pipelineStage ? pipelineStage.back : "等待点击发送；不会修改真实项目资料或会话" }}</span></div>
        </div>
      </div>
      <div class="pipeline-legend"><span><i class="legend-front"></i>前端反馈</span><span><i class="legend-back"></i>后端状态</span><span><i class="legend-sync"></i>同一阶段同步高亮</span></div>
    </section>

    <section class="principles-section">
      <span class="section-kicker">03 / 设计原则</span>
      <div class="principles-grid"><article><span>01</span><h3>先判断，再检索</h3><p>问候与一般问题不被强制塞进 RAG；只有需要项目资料时才进入召回与重排。</p></article><article><span>02</span><h3>先事实，再回答</h3><p>执行过程和命中来源独立展示，答案在校验并持久化后再返回界面。</p></article><article><span>03</span><h3>失败也可恢复</h3><p>Redis 负责投递，PostgreSQL 保存事实；通知丢失时，SSE 仍能从数据库补回终态。</p></article></div>
    </section>
    <footer class="intro-footer"><span>Ragent · 项目知识工作台</span><RouterLink to="/chat">开始使用 →</RouterLink></footer>
  </main>
</template>

<style scoped>
.intro-page { min-height: 100%; background: #f7f8f5; color: #1e2923; overflow: hidden; }
.intro-hero, .tutorial-section, .pipeline-section, .principles-section, .intro-footer { width: min(1120px, calc(100% - 56px)); margin: 0 auto; }
.intro-hero { padding: 86px 0 76px; position: relative; }
.intro-hero::after { content: ""; position: absolute; right: 4%; top: 40px; width: 300px; height: 300px; border-radius: 50%; background: radial-gradient(circle at 45% 42%, rgba(73, 166, 103, .22), rgba(73, 166, 103, 0) 68%); filter: blur(2px); pointer-events: none; }
.eyebrow, .section-kicker { color: #4c8460; font-size: 11px; letter-spacing: .16em; font-weight: 700; text-transform: uppercase; }
.eyebrow { display: flex; gap: 8px; align-items: center; margin-bottom: 24px; }.eyebrow-dot { width: 7px; height: 7px; border-radius: 50%; background: #2f9a5b; box-shadow: 0 0 0 5px rgba(47,154,91,.12); }
.intro-hero h1 { position: relative; z-index: 1; max-width: 720px; margin: 0; font-size: clamp(42px, 7vw, 84px); line-height: .98; letter-spacing: -.065em; font-weight: 760; }.intro-hero h1 em { color: #2c9858; font-style: normal; }.hero-copy { position: relative; z-index: 1; max-width: 610px; margin: 26px 0 0; color: #68736c; font-size: 17px; line-height: 1.85; }.hero-actions { position: relative; z-index: 1; display: flex; gap: 10px; margin-top: 34px; }.hero-primary, .hero-secondary { border-radius: 999px; padding: 12px 18px; text-decoration: none; font-size: 13px; transition: transform .2s, box-shadow .2s, background .2s; }.hero-primary { background: #1e8c50; color: #fff; box-shadow: 0 8px 24px rgba(30,140,80,.18); }.hero-primary:hover { transform: translateY(-2px); box-shadow: 0 12px 28px rgba(30,140,80,.26); }.hero-secondary { color: #315d40; background: #fff; border: 1px solid #e1e9e2; }.hero-secondary:hover { background: #edf7ef; }.hero-actions span { margin-left: 10px; }.hero-note { position: relative; z-index: 1; margin-top: 34px; color: #99a39c; font-size: 12px; }.hero-note span { color: #36a063; margin-right: 7px; }
.tutorial-section, .pipeline-section, .principles-section { padding: 74px 0; border-top: 1px solid #e1e8e1; }.section-heading { display: flex; align-items: flex-end; justify-content: space-between; gap: 28px; margin-bottom: 28px; }.section-heading h2 { margin: 10px 0 0; font-size: clamp(28px, 4vw, 46px); letter-spacing: -.05em; color: #243229; }.play-button, .pipeline-button { border: 1px solid #dbe6dc; background: #fff; color: #356247; box-shadow: none; font-size: 12px; padding: 10px 13px; }.play-button:hover, .pipeline-button:hover { background: #eef7ef; }.play-button span { color: #2f9858; margin-left: 7px; }.tutorial-layout { display: grid; grid-template-columns: minmax(0, 1.12fr) minmax(320px, .88fr); gap: 74px; align-items: center; }.tutorial-visual { min-height: 420px; border-radius: 24px; background: #1f2a24; position: relative; overflow: hidden; display: grid; place-items: center; box-shadow: 0 22px 55px rgba(29, 51, 36, .16); }.visual-grid { position: absolute; inset: 0; opacity: .3; background-image: linear-gradient(rgba(159, 229, 177, .08) 1px, transparent 1px), linear-gradient(90deg, rgba(159, 229, 177, .08) 1px, transparent 1px); background-size: 32px 32px; }.tutorial-orbit { position: absolute; border: 1px solid rgba(147, 219, 162, .34); border-radius: 50%; animation: orbit 10s linear infinite; }.orbit-one { width: 270px; height: 270px; }.orbit-two { width: 390px; height: 170px; transform: rotate(-26deg); animation-duration: 13s; animation-direction: reverse; }.tutorial-core { position: relative; width: 140px; height: 140px; display: grid; place-items: center; align-content: center; border-radius: 34px; background: linear-gradient(145deg, #58bd78, #197a43); color: #fff; box-shadow: 0 0 0 12px rgba(83, 190, 119, .12), 0 20px 40px rgba(0,0,0,.24); animation: core-breathe 2.6s ease-in-out infinite; }.tutorial-core span { font-size: 48px; }.tutorial-core small { font-size: 11px; letter-spacing: .18em; opacity: .8; }.tutorial-float { position: absolute; color: #d6ead9; font: 12px/1.4 ui-monospace, SFMono-Regular, Consolas, monospace; background: rgba(255,255,255,.08); border: 1px solid rgba(218, 244, 220, .13); border-radius: 9px; padding: 9px 12px; backdrop-filter: blur(8px); animation: float 3.5s ease-in-out infinite; }.float-top { top: 46px; left: 38px; }.float-bottom { right: 32px; bottom: 40px; animation-delay: -1.1s; }.pulse-dot { display: inline-block; width: 7px; height: 7px; border-radius: 50%; background: #8de2a4; margin-right: 6px; box-shadow: 0 0 0 5px rgba(141,226,164,.14); }
.tutorial-progress { display: flex; gap: 6px; margin-bottom: 20px; }.tutorial-progress span { width: 28px; height: 3px; border-radius: 3px; background: #dce5dd; transition: width .35s, background .35s; }.tutorial-progress span.active { width: 52px; background: #2d9859; }.tutorial-progress span.done { background: #a5d6b2; }.tutorial-step { width: 100%; display: grid; grid-template-columns: 30px 30px 1fr 18px; gap: 10px; align-items: start; padding: 16px 14px; background: transparent; color: #667169; border-radius: 12px; text-align: left; box-shadow: none; border: 1px solid transparent; }.tutorial-step:hover { background: #fff; color: #28372d; }.tutorial-step.active { background: #fff; border-color: #dfeae0; box-shadow: 0 8px 22px rgba(49, 94, 61, .07); color: #26392b; }.step-no { font: 11px ui-monospace, monospace; color: #a4b0a7; padding-top: 3px; }.step-icon { color: #319b5d; font-size: 18px; }.step-content { display: grid; gap: 5px; }.step-content strong { font-size: 14px; }.step-content small { font-size: 12px; line-height: 1.65; color: #8a948d; }.step-arrow { color: #58a36f; opacity: 0; transition: opacity .2s; }.tutorial-step.active .step-arrow { opacity: 1; }
.pipeline-heading { align-items: flex-end; }.pipeline-heading p { max-width: 650px; margin: 12px 0 0; color: #7c877f; line-height: 1.7; font-size: 14px; }.pipeline-button { display: inline-flex; align-items: center; gap: 18px; padding: 11px 12px 11px 16px; background: #218f51; color: #fff; border-color: #218f51; border-radius: 999px; box-shadow: 0 8px 22px rgba(33,143,81,.18); }.pipeline-button:hover { background: #197a43; color: #fff; }.pipeline-button b { display: grid; place-items: center; width: 25px; height: 25px; background: rgba(255,255,255,.18); border-radius: 50%; font-size: 17px; }
.pipeline-board { display: grid; grid-template-columns: minmax(0, 1fr) 110px minmax(0, 1fr); gap: 20px; align-items: stretch; padding: 25px; border-radius: 22px; background: #edf2ec; border: 1px solid #dce6dc; }.board-label { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; font-size: 11px; letter-spacing: .04em; color: #66756b; text-transform: uppercase; }.label-dot { width: 7px; height: 7px; border-radius: 50%; }.front-dot { background: #e3945c; }.back-dot { background: #4c9a70; }.mock-chat, .backend-terminal { min-height: 350px; overflow: hidden; border-radius: 13px; background: #fff; border: 1px solid #dbe5dc; box-shadow: 0 10px 24px rgba(55,80,60,.07); }.mock-head, .terminal-head { display: flex; justify-content: space-between; gap: 12px; padding: 13px 14px; border-bottom: 1px solid #edf0ed; font-size: 11px; color: #445248; }.mock-status { color: #4c9b68; max-width: 45%; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }.mock-message { margin: 20px 16px; padding: 11px 13px; border-radius: 11px; font-size: 12px; line-height: 1.6; }.user-message { margin-left: 24%; background: #f1f5f1; color: #556159; }.assistant-message { display: flex; gap: 7px; margin-right: 12%; background: #f2faf3; color: #6a776e; border: 1px dashed #cfe8d3; opacity: .72; transition: opacity .4s, transform .4s; }.assistant-message.visible { opacity: 1; transform: translateX(0); }.assistant-message i { color: #39935b; font-style: normal; white-space: nowrap; }.mock-spark { color: #2e9c5c; }.mock-composer { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin: 65px 13px 13px; padding: 8px 8px 8px 12px; border: 1px solid #e4eae5; border-radius: 9px; color: #a0aaa2; font-size: 11px; }.mock-composer button { width: 28px; height: 28px; padding: 0; border-radius: 8px; background: #91d0a4; font-size: 17px; }.front-events { display: grid; gap: 5px; margin-top: 15px; }.event-line { display: flex; gap: 8px; align-items: center; color: #acb5ad; font-size: 11px; transition: color .25s, transform .25s; }.event-line.done, .event-line.running { color: #39774e; }.event-line.running { transform: translateX(4px); font-weight: 650; }.event-line span { width: 15px; text-align: center; }
.sync-rail { display: flex; align-items: center; flex-direction: column; position: relative; padding-top: 36px; }.sync-line { width: 1px; flex: 1; background: linear-gradient(#d9e4da, #70b987, #d9e4da); }.sync-badge { margin: 15px 0; padding: 6px 8px; border-radius: 999px; background: #fff; border: 1px solid #d7e4d8; color: #428c5a; font-size: 11px; writing-mode: vertical-rl; }.sync-caption { position: absolute; bottom: 15px; width: 100px; color: #97a49a; font-size: 10px; line-height: 1.5; text-align: center; }.backend-terminal { background: #202b24; border-color: #2c3e31; box-shadow: 0 16px 30px rgba(29,45,34,.18); }.terminal-head { color: #b6cdb8; border-color: #324336; }.backend-stage { display: grid; grid-template-columns: 26px 1fr auto; gap: 9px; align-items: center; margin: 7px 10px; padding: 8px 7px; border-radius: 8px; color: #7e9581; transition: background .35s, color .35s, transform .35s; }.backend-stage.running { background: rgba(115, 202, 137, .16); color: #bdeac5; transform: translateX(4px); }.backend-stage.done { color: #9cc8a6; }.stage-marker { font: 10px ui-monospace, monospace; color: #70ae7d; }.backend-stage strong, .backend-stage small { display: block; }.backend-stage strong { font-size: 11px; }.backend-stage small { margin-top: 3px; font-size: 10px; line-height: 1.45; color: #77907d; }.backend-stage em { font: 9px ui-monospace, monospace; color: #73947a; font-style: normal; }.backend-stage.running em { color: #a9e9b6; }.backend-note { display: flex; gap: 8px; min-height: 48px; margin-top: 14px; padding: 10px 12px; border-radius: 9px; background: #fff; color: #6c796e; font-size: 11px; line-height: 1.5; }.backend-note > span:first-child { color: #3c9a5b; font-size: 15px; }.pipeline-legend { display: flex; gap: 18px; margin-top: 14px; color: #89948b; font-size: 11px; }.pipeline-legend span { display: inline-flex; align-items: center; gap: 6px; }.pipeline-legend i { width: 7px; height: 7px; border-radius: 50%; }.legend-front { background: #e3945c; }.legend-back { background: #4c9a70; }.legend-sync { background: #a5ccab; }
.principles-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; margin-top: 28px; }.principles-grid article { padding: 20px; background: #fff; border: 1px solid #e3ebe4; border-radius: 15px; }.principles-grid article > span { color: #75a682; font: 11px ui-monospace, monospace; }.principles-grid h3 { margin: 17px 0 8px; font-size: 17px; }.principles-grid p { margin: 0; color: #7d887f; font-size: 13px; line-height: 1.7; }.intro-footer { display: flex; justify-content: space-between; gap: 20px; padding: 24px 0 35px; color: #89958b; font-size: 12px; border-top: 1px solid #e1e8e1; }.intro-footer a { color: #2f8d53; text-decoration: none; }
@keyframes orbit { to { transform: rotate(360deg); } } @keyframes core-breathe { 0%,100% { transform: scale(1); } 50% { transform: scale(1.04); } } @keyframes float { 0%,100% { transform: translateY(0); } 50% { transform: translateY(-7px); } }
@media (max-width: 860px) { .intro-hero, .tutorial-section, .pipeline-section, .principles-section, .intro-footer { width: min(100% - 32px, 680px); }.tutorial-layout { grid-template-columns: 1fr; gap: 30px; }.tutorial-visual { min-height: 340px; }.pipeline-board { grid-template-columns: 1fr; }.sync-rail { display: none; }.principles-grid { grid-template-columns: 1fr; }.section-heading { align-items: flex-start; flex-direction: column; }.pipeline-button { align-self: flex-start; } }
@media (max-width: 520px) { .intro-hero { padding-top: 52px; }.intro-hero h1 { font-size: 48px; }.hero-actions { flex-direction: column; align-items: flex-start; }.tutorial-visual { min-height: 290px; }.tutorial-core { width: 110px; height: 110px; }.float-top { left: 16px; top: 24px; }.float-bottom { right: 16px; bottom: 24px; }.pipeline-board { padding: 15px; } }
</style>
