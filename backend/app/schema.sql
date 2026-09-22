-- M1 数据表：把「用户请求」与「系统运行」拆成两个状态模型，是整条链路的账本。
-- 全部用 IF NOT EXISTS，重复启动不报错；单人精简版不引入迁移框架。
-- id 统一 UUID，由数据库默认生成，便于「落库即返回 ID」而不依赖自增回填。

-- 消息：一次会话里最终要展示给用户看的问答文本
CREATE TABLE IF NOT EXISTS messages (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    thread_id   TEXT NOT NULL,                 -- 单用户单 agent 阶段，thread 就是个会话标识
    role        TEXT NOT NULL,                 -- 'user' 或 'assistant'，约定取值不建 enum
    content     TEXT NOT NULL,
    -- assistant 回复绑定发起它的请求；SSE late-join 据此精确取本请求结果，不猜最后一条
    request_id  UUID,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 请求（用户视角）：用户一提问就落一条并立刻返回，记录「想要什么」和「排队排到哪」
CREATE TABLE IF NOT EXISTS agent_run_requests (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     TEXT NOT NULL,
    agent_id    TEXT NOT NULL,
    thread_id   TEXT NOT NULL,
    -- 绑定发起本请求的那条 user 消息；worker 据此取「本次该回答的问题」，不靠猜最后一条
    message_id  UUID REFERENCES messages(id),
    -- queued 排队中 / dispatched 已派发 / done 完成 / failed 失败
    status      TEXT NOT NULL DEFAULT 'queued',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 运行（系统视角）：请求排到 FIFO 队头、真正开跑时才创建，记录一次执行的生命周期
CREATE TABLE IF NOT EXISTS agent_runs (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    request_id    UUID NOT NULL REFERENCES agent_run_requests(id),  -- 结果必须绑回发起它的请求
    -- pending 待认领(刚建、还没 worker 抢到) / running 执行中 / done 完成 / failed 失败
    -- 初态是 pending 而非 running：建 run 到 worker 认领之间若投递失败(先 commit 后 enqueue)，
    -- 这条 run 会停在 pending，reaper 据此把它当孤儿捞回重投，不会永久卡死本组队列。
    status        TEXT NOT NULL DEFAULT 'pending',
    lease_owner   TEXT,           -- 哪个 worker 抢到了这次执行
    heartbeat_at  TIMESTAMPTZ,    -- 最近一次心跳续约时间；停跳即视为 worker 已死可被接管
    error         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 已建库补列：让旧表也具备 message_id，幂等无害
ALTER TABLE agent_run_requests ADD COLUMN IF NOT EXISTS message_id UUID REFERENCES messages(id);
ALTER TABLE messages ADD COLUMN IF NOT EXISTS request_id UUID;
-- 已建库改默认：run 初态从 running 改为 pending(孤儿窗口修复)，幂等无害
ALTER TABLE agent_runs ALTER COLUMN status SET DEFAULT 'pending';

-- 按 (user, agent, thread) 查同组请求做 FIFO 排队，加索引避免全表扫
CREATE INDEX IF NOT EXISTS idx_requests_fifo
    ON agent_run_requests (user_id, agent_id, thread_id, created_at);

-- 项目隔离资料，项目内会话使用统一知识库 Agent。
CREATE TABLE IF NOT EXISTS projects (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 会话属于项目，统一由知识库 Agent 处理。
CREATE TABLE IF NOT EXISTS threads (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title       TEXT NOT NULL DEFAULT '新会话',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- M7 RAG 知识库：文档切成 chunk，每块存一条向量，检索时按向量相似度取 top-k。
-- 用本地 fastembed(BAAI/bge-small-zh-v1.5) 生成向量，维度固定 512，故写死 vector(512)。
CREATE EXTENSION IF NOT EXISTS vector;  -- pgvector 镜像已装扩展，仍需在库里 enable

-- 文档：资料归属到项目(而非单个 Agent)，同项目多会话共享同一份资料
CREATE TABLE IF NOT EXISTS documents (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id  UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    title       TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 文本块：一篇文档切成多块，每块一条向量，检索的最小单位
CREATE TABLE IF NOT EXISTS chunks (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    content     TEXT NOT NULL,
    embedding   vector(512) NOT NULL,   -- bge-small-zh-v1.5 输出 512 维
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- M10 LLM 配置：单行表，保存当前生效的 OpenAI 兼容接入配置。
-- 为什么落库而不只用环境变量：api 与 worker 是两个进程、内存态不共享，
-- 配置页改了要让真正调模型的 worker 也生效，唯一可靠的共享真相就是数据库。
-- 单行设计：单用户精简版只有一套配置，用固定主键 id=1 保证永远只有一行。
CREATE TABLE IF NOT EXISTS llm_config (
    id          INT PRIMARY KEY DEFAULT 1,
    base_url    TEXT NOT NULL,
    api_key     TEXT NOT NULL,
    model       TEXT NOT NULL,
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT llm_config_single_row CHECK (id = 1)  -- 只允许 id=1 这一行
);

-- 单知识库 Agent 迁移：保留所有会话/消息/请求，仅移除废弃配置。
ALTER TABLE threads DROP COLUMN IF EXISTS agent_id;
DROP TABLE IF EXISTS agents;
UPDATE agent_run_requests SET agent_id = 'knowledge-base' WHERE agent_id <> 'knowledge-base';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS blocks JSONB;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS index_version INTEGER NOT NULL DEFAULT 1;
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS metadata JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE documents ADD COLUMN IF NOT EXISTS source_hash TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS idx_document_upload ON documents(project_id, source_hash) WHERE source_hash IS NOT NULL;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS sources JSONB NOT NULL DEFAULT '[]'::jsonb;
ALTER TABLE messages ADD COLUMN IF NOT EXISTS steps JSONB NOT NULL DEFAULT '[]'::jsonb;

-- 某些旧库保存了请求步骤：保留记录，仅修正删除请求时的依赖行为。
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'run_steps_request_id_fkey'
               AND conrelid = to_regclass('run_steps') AND confdeltype <> 'c') THEN
        ALTER TABLE run_steps DROP CONSTRAINT run_steps_request_id_fkey;
        ALTER TABLE run_steps ADD CONSTRAINT run_steps_request_id_fkey
            FOREIGN KEY (request_id) REFERENCES agent_run_requests(id) ON DELETE CASCADE;
    END IF;
END $$;

-- 编辑采用版本校验，避免多个页面静默覆盖同一份资料。
ALTER TABLE documents ADD COLUMN IF NOT EXISTS revision UUID NOT NULL DEFAULT gen_random_uuid();
