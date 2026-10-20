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

-- 执行次数上限：每次 worker 认领 +1，reaper 回收时超过上限就判失败，防止毒消息无限重投卡死同组队列。
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS attempts INTEGER NOT NULL DEFAULT 0;
-- 成本统计：一次执行里所有模型调用的 token 用量与调用次数（框架 usage_metadata 汇总）。
ALTER TABLE agent_runs ADD COLUMN IF NOT EXISTS usage JSONB;

-- 常用查询补索引，避免随数据增长走全表扫描。
-- 会话回放 / 历史上下文：按会话取消息并按时间排序
CREATE INDEX IF NOT EXISTS idx_messages_thread_created ON messages (thread_id, created_at);
-- SSE 补读、历史上下文：按请求找 assistant 回复
CREATE INDEX IF NOT EXISTS idx_messages_request ON messages (request_id);
-- 按请求找 run（失败回放、删除清理）
CREATE INDEX IF NOT EXISTS idx_runs_request ON agent_runs (request_id);
-- reaper 每 5 秒扫一次：只扫未结束的 run
CREATE INDEX IF NOT EXISTS idx_runs_active ON agent_runs (status, heartbeat_at) WHERE status IN ('pending', 'running');
-- 检索时按文档取块、删文档级联
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks (document_id);
-- 向量近似检索：HNSW 按余弦距离建索引，查询不再逐块算距离。
-- 取舍：HNSW 先取近似近邻再按项目过滤，项目很多时返回数可能少于 LIMIT（面试可讲的"过滤式向量检索"问题）。
CREATE INDEX IF NOT EXISTS idx_chunks_embedding_hnsw ON chunks USING hnsw (embedding vector_cosine_ops);

-- ============================================================
-- P0 增量摘要与多用户隔离：本轮改造的幂等迁移段。
-- 沿用本文件既有风格：只用 IF NOT EXISTS / IF EXISTS，重复启动不报错。
-- ============================================================

-- 会话摘要：一个会话一行，随轮次增量推进。
-- 为什么单独建表而不塞进 threads：摘要是可失败、可重算的派生数据，生命周期和会话本体不同；
-- 单独一行才装得下自己的水位、失败计数与熔断状态，且整表不可用时上层能直接回退到原文截断
-- —— 摘要是纯增强，不是链路依赖。
CREATE TABLE IF NOT EXISTS thread_summaries (
    thread_id            UUID PRIMARY KEY REFERENCES threads(id) ON DELETE CASCADE,
    summary_text         TEXT NOT NULL DEFAULT '',
    -- 水位：摘要已覆盖到哪条消息的 seq。下次只取它之后的增量，不重读全量历史。
    covered_until_seq    BIGINT NOT NULL DEFAULT 0,
    covered_turns        INTEGER NOT NULL DEFAULT 0,
    -- 摘要自身花的 token 单列累计：摘要是为省 token 引入的，它自己的成本必须能单独看到，
    -- 否则无法判断这个机制到底是赚还是亏。
    summary_tokens       INTEGER NOT NULL DEFAULT 0,
    -- 上次该摘要但失败了：旧摘要仍照常使用（stale 也比丢历史好），水位不前进，下次自然重试。
    stale                BOOLEAN NOT NULL DEFAULT false,
    -- 连续失败计数：连续多次失败即熔断，只走原文截断，不每轮再去撞一个必然失败的调用。
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- messages 需要一个单调序号做摘要水位：同一事务里多条消息的 created_at 可能完全相同，
-- 按时间戳比较会漏轮或重复覆盖；只有单调序号能表达「覆盖到这条为止」这个确定边界。
--
-- 为什么用 DO 块显式回填，而不是直接 ADD COLUMN seq BIGSERIAL：
-- BIGSERIAL 给存量行回填的是物理堆顺序，不保证与 created_at 一致（被 UPDATE 过的行会挪到堆尾）。
-- 而水位语义一旦建立就不能再重排编号 —— 已经存下的 covered_until_seq 会整体错位，
-- 所以必须在建列的同一时刻按 created_at 排好，且整段只在列不存在时执行（天然只跑一次，不会二次重排）。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'messages' AND column_name = 'seq'
    ) THEN
        ALTER TABLE messages ADD COLUMN seq BIGINT;
        -- 按 (created_at, id) 显式排序回填：id 兜住同一时间戳内的稳定次序，结果可复现。
        WITH ordered AS (
            SELECT id, row_number() OVER (ORDER BY created_at, id) AS rn FROM messages
        )
        UPDATE messages m SET seq = ordered.rn FROM ordered WHERE m.id = ordered.id;
        -- 序列 OWNED BY 该列：随表删除一起回收，不留孤儿序列。
        CREATE SEQUENCE IF NOT EXISTS messages_seq_seq AS BIGINT OWNED BY messages.seq;
        -- 起点接在已回填的最大值之后；空表时 COALESCE 兜到 1，避免 setval(0) 越界报错。
        PERFORM setval('messages_seq_seq', COALESCE((SELECT max(seq) FROM messages), 0) + 1, false);
        ALTER TABLE messages ALTER COLUMN seq SET DEFAULT nextval('messages_seq_seq');
        ALTER TABLE messages ALTER COLUMN seq SET NOT NULL;
    END IF;
END $$;

-- 摘要增量取数是「按会话取水位之后的消息」，加复合索引避免随会话变长走全表扫。
CREATE INDEX IF NOT EXISTS idx_messages_thread_seq ON messages (thread_id, seq);

-- 归属锚点：只有 projects 挂 owner_id，threads/messages/documents/chunks 沿既有外键链传导。
-- 为什么不每张表都加一列：多处冗余归属必然出现不一致（改一处忘一处），
-- 单一锚点让越权校验只有一个判断点，漏不掉也对不上假。
ALTER TABLE projects ADD COLUMN IF NOT EXISTS owner_id TEXT;
-- 存量项目统一归到遗留身份，再由「切换身份」入口认领回来；
-- 迁移后浏览器里看到空列表是预期结果，不是数据丢了。
-- 回填必须在加约束之前：这一行同时覆盖 P0 存量项目和「P0 已上线、P1 未上线」那段
-- 中间态里新建的项目（它们的 owner_id 也是 NULL）。
UPDATE projects SET owner_id = 'legacy-u1' WHERE owner_id IS NULL;
-- P1 补约束。三步顺序不可颠倒：① 改写入代码（insert_project 现已必传 owner_id）
-- → ② 回填残留 NULL（上一行）→ ③ 加约束（下一行）。颠倒必失败，已实测。
-- 为什么不给列加 DEFAULT 'legacy-u1' 兜底：那会把「漏传 owner」从启动即失败
-- 降级成静默把别人的数据写进遗留身份名下，归属写错比起步报错难查得多。
ALTER TABLE projects ALTER COLUMN owner_id SET NOT NULL;

-- 项目列表固定按 owner 过滤 + 按时间倒序，复合索引直接覆盖这个访问模式。
CREATE INDEX IF NOT EXISTS idx_projects_owner ON projects (owner_id, created_at DESC);

-- 会话级模型/推理强度覆盖：NULL 表示跟随 owner 默认配置，不是「关掉」。
-- 为什么落库而不留在前端内存：真正调模型的是 worker 进程，和 api 不共享内存，
-- 唯一可靠的共享真相是数据库（与上面 llm_config 的理由一致）。
ALTER TABLE threads ADD COLUMN IF NOT EXISTS model TEXT;
-- reasoning_effort：NULL / 'off' 表示不传该字段，走服务端默认，保证不选就维持改造前行为。
ALTER TABLE threads ADD COLUMN IF NOT EXISTS reasoning_effort TEXT;

-- llm_config 从「全局单行」改成「按 owner 一行」：每个人的 API Key 必须相互隔离，
-- 共用一把 key 等于让任何新访客免费花掉库主的额度。
ALTER TABLE llm_config DROP CONSTRAINT IF EXISTS llm_config_single_row;
ALTER TABLE llm_config ADD COLUMN IF NOT EXISTS owner_id TEXT;
-- 同上，回填先于约束：P0 中间态里 get_effective_config 播种的那行 owner_id 是 NULL，
-- 不回填直接加约束必然失败（workbuddy 在真实库上已复现这一行）。
UPDATE llm_config SET owner_id = 'legacy-u1' WHERE owner_id IS NULL;

-- owner 唯一：一个身份最多一行配置，service 层的 upsert 直接挂在这个唯一键上。
-- 顺序要求：必须先回填再建唯一索引。NULL 之间不互相冲突，但回填会把多行 NULL
-- collapse 成同一个 legacy-u1 值；先建索引再回填只会把失败推迟到回填那步。
CREATE UNIQUE INDEX IF NOT EXISTS idx_llm_config_owner ON llm_config (owner_id);
-- P1 补约束：owner_id 是这张表现在真正的业务主键（id 只剩代理键作用），
-- 允许 NULL 等于允许一行「谁都读不到、又占着唯一键」的僵尸配置。
ALTER TABLE llm_config ALTER COLUMN owner_id SET NOT NULL;

-- 单行表遗留：id 原本 DEFAULT 1（配合 CHECK (id = 1)）。去掉单行约束后，
-- 第二个 owner 播种时还会拿到 id=1 撞主键，所以必须给它接上真正的序列。
-- 建序列只做一次：CREATE 与挂 DEFAULT 都是结构变更，重复执行没有意义。
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relkind = 'S' AND c.relname = 'llm_config_id_seq'
          AND n.nspname = current_schema()
    ) THEN
        CREATE SEQUENCE llm_config_id_seq AS INT OWNED BY llm_config.id;
        ALTER TABLE llm_config ALTER COLUMN id SET DEFAULT nextval('llm_config_id_seq');
    END IF;
END $$;

-- 但「追上现有最大 id」必须每次启动都做，不能塞进上面的 IF 里。
-- 已在真实库复现过的故障：序列在空表时建好（停在 1），随后旧代码用 DEFAULT 1 硬塞了
-- 一行 id=1；下一个 owner 播种时 nextval 取到 1，撞 llm_config_pkey 报
-- UniqueViolationError，表现是「新访客的模型配置永远存不进去」。
-- 只用 GREATEST 单调前进，永不回拨：回拨会让已删除的 id 被重用。
-- last_value 直接读会在序列从未取号时报错，故走 pg_sequence_last_value（未取号返回 NULL）。
-- 不套 DO 块：setval 本身就是幂等的，没有需要存在性守卫的裸 DDL。
SELECT setval(
    'llm_config_id_seq',
    GREATEST(
        COALESCE((SELECT max(id) FROM llm_config), 1),
        COALESCE(pg_sequence_last_value('llm_config_id_seq'::regclass), 1)
    )
);

-- ============================================================
-- P2 服务间鉴权：访问令牌表。
-- 背景：原设计只有「Cookie 身份」，那是给浏览器用的隔离，不是鉴权 ——
-- 服务调用方（外部 Agent 平台、脚本、CI）不该借浏览器身份，需要一枚可签发、可撤销的凭证。
-- 沿用本文件既有风格：只用 IF NOT EXISTS / IF EXISTS，重复启动不报错。
-- ============================================================

-- 只存令牌的 sha256，不存明文：库里放明文等于把全部身份写成一张可读的表，
-- 一次备份泄露就等于数据全丢。为什么不上 bcrypt：令牌是 32 字节随机串，
-- 不存在「弱口令」这个攻击面，慢哈希只会给每个请求加无谓的 CPU 开销；
-- 要防的只是「库被读走」，sha256 已经足够。
CREATE TABLE IF NOT EXISTS api_tokens (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    token_hash   TEXT NOT NULL UNIQUE,       -- sha256(明文)，查表键
    owner_id     TEXT NOT NULL,              -- 这枚令牌代表哪个身份
    name         TEXT NOT NULL DEFAULT '',   -- 用途备注，如 "opsmind-mcp"
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    -- 撤销用时间戳而不是物理删除：审计要能回答「什么时候建的、什么时候被停的」。
    revoked_at   TIMESTAMPTZ
);

-- 「某个身份有哪些令牌」是运维最常见的查询，按 owner + 时间倒序直接覆盖它。
CREATE INDEX IF NOT EXISTS idx_api_tokens_owner ON api_tokens (owner_id, created_at DESC);

-- 推理强度：DeepSeek V4 这类推理模型服务端默认档是 high，一次简单问答也要几十秒。
-- 存成「每个身份可覆盖」的一列，NULL 表示跟随环境变量 LLM_REASONING_EFFORT 的默认值。
-- 不复用 threads.reasoning_effort：那个列是会话级的、至今没有任何读写方，
-- 而「用哪个档位的模型」和 base_url/model/api_key 一样属于模型接入配置，放在同一行才自洽。
ALTER TABLE llm_config ADD COLUMN IF NOT EXISTS reasoning_effort TEXT;

-- 成本估算单价（元 / 1K tokens）：和模型接入配置放在同一行、按身份隔离。
-- 默认 0 表示不估算；用户在「模型配置」页填写后，统计页直接使用这里的值，
-- 不再要求改 .env 或重启进程。
ALTER TABLE llm_config ADD COLUMN IF NOT EXISTS cost_input_per_1k NUMERIC(12,6) NOT NULL DEFAULT 0;
ALTER TABLE llm_config ADD COLUMN IF NOT EXISTS cost_output_per_1k NUMERIC(12,6) NOT NULL DEFAULT 0;

-- 安全审计：记录被拦截的注入、限流等事件；只写结构化摘要，不落攻击原文。
CREATE TABLE IF NOT EXISTS audit_logs (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id   TEXT NOT NULL,
    action     TEXT NOT NULL,
    detail     JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_owner_time ON audit_logs (owner_id, created_at DESC);

