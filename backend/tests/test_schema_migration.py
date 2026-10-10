"""schema.sql 的幂等性与摘要阈值语义：纯静态检查，不连数据库。

项目没有迁移框架，schema.sql 每次启动都整份重跑，所以「幂等」是它唯一的正确性保证。
这里把幂等约定固化成测试，防止后来加的 DDL 漏掉 IF NOT EXISTS —— 那种错误只会在
第二次启动时才炸，本地一次性建库根本测不出来。
"""
import re
from pathlib import Path

from app import config

SCHEMA = (Path(__file__).resolve().parents[1] / "app" / "schema.sql").read_text(encoding="utf-8")

# DO $$ ... END $$; 块内部允许写裸 DDL（由块自己的 IF NOT EXISTS 守卫兜住），
# 所以做语句级检查前先把它们摘出来单独验。
_DO_BLOCK = re.compile(r"DO \$\$.*?END \$\$;", re.S)


def _do_blocks() -> list[str]:
    return _DO_BLOCK.findall(SCHEMA)


def _top_level_statements() -> list[str]:
    """去掉 DO 块与注释后，按分号切出的顶层语句。"""
    body = _DO_BLOCK.sub("", SCHEMA)
    body = re.sub(r"--[^\n]*", "", body)
    return [s.strip() for s in body.split(";") if s.strip()]


# ---- 幂等：重复启动不报错 ----

def test_top_level_create_statements_are_idempotent():
    for stmt in _top_level_statements():
        if re.match(r"(?is)^CREATE\s+(TABLE|EXTENSION|(UNIQUE\s+)?INDEX|SEQUENCE)\b", stmt):
            assert "IF NOT EXISTS" in stmt.upper(), f"缺少 IF NOT EXISTS: {stmt[:80]}"


def test_add_column_statements_are_idempotent():
    for stmt in _top_level_statements():
        if re.search(r"(?is)\bADD\s+COLUMN\b", stmt):
            assert re.search(r"(?is)ADD\s+COLUMN\s+IF\s+NOT\s+EXISTS", stmt), stmt[:80]


def test_drop_statements_are_idempotent():
    for stmt in _top_level_statements():
        if re.search(r"(?is)\bDROP\s+(TABLE|COLUMN|CONSTRAINT)\b", stmt):
            assert "IF EXISTS" in stmt.upper(), stmt[:80]


def test_do_blocks_are_existence_guarded():
    """DO 块里的裸 DDL 只有在存在性守卫下才幂等，缺守卫等于第二次启动必炸。"""
    blocks = _do_blocks()
    assert blocks, "schema.sql 里应当有 DO 块"
    for block in blocks:
        assert re.search(r"(?is)IF\s+(NOT\s+)?EXISTS\s*\(", block), block[:120]


# ---- messages.seq：水位列的回填必须与 created_at 同序 ----

def test_seq_backfill_is_ordered_by_created_at():
    """回填顺序必须显式按 (created_at, id)。

    直接 ADD COLUMN seq BIGSERIAL 拿到的是物理堆顺序，被 UPDATE 过的旧行会挪到堆尾，
    和 created_at 不一致；而水位建立后不能再重排编号，否则存量 covered_until_seq 整体错位。
    """
    block = next(b for b in _do_blocks() if "messages_seq_seq" in b)
    assert "row_number() OVER (ORDER BY created_at, id)" in block
    # 只看可执行 SQL：注释里提到 BIGSERIAL 是在解释为什么不用它。
    executable = re.sub(r"--[^\n]*", "", SCHEMA).upper()
    assert "BIGSERIAL" not in executable


def test_seq_block_runs_only_when_column_missing():
    """整段以「列不存在」为前置条件，保证只跑一次、不会二次重排编号。"""
    block = next(b for b in _do_blocks() if "messages_seq_seq" in b)
    assert "column_name = 'seq'" in block
    assert re.search(r"(?is)IF\s+NOT\s+EXISTS\s*\(", block)


def test_thread_summaries_has_watermark_and_degrade_columns():
    """摘要表必须同时具备水位、成本与降级状态列，缺一项后面的设计就落不了地。"""
    for column in ("covered_until_seq", "covered_turns", "summary_tokens",
                   "stale", "consecutive_failures"):
        assert re.search(rf"(?m)^\s+{column}\b", SCHEMA), column


# ---- 归属与配置 ----

def test_legacy_owner_constant_matches_schema_backfill():
    """常量与 SQL 回填值必须同一个字面量，否则认领存量数据时会对不上。"""
    assert f"owner_id = '{config.LEGACY_OWNER_ID}'" in SCHEMA


def test_owner_id_not_null_landed_in_p1_after_backfill():
    """P1 落地 NOT NULL，且必须排在回填语句之后。

    这条原本是 P0 的阶段闸门（断言 NOT NULL 还没加），P1 把写入代码改成显式带 owner_id
    之后反转成正向断言。顺序是重点：约束若排在 UPDATE 回填之前，存量的 NULL 行会让
    整个 schema.sql 执行中断，表现是「迁移脚本跑一半失败」而不是某条语句报错。
    """
    executable = re.sub(r"--[^\n]*", "", SCHEMA)
    for table in ("projects", "llm_config"):
        constraint = re.search(
            rf"(?is)ALTER\s+TABLE\s+{table}\s+ALTER\s+COLUMN\s+owner_id\s+SET\s+NOT\s+NULL",
            executable,
        )
        assert constraint, f"{table}.owner_id 的 NOT NULL 应当在 P1 落地"
        backfill = re.search(rf"(?is)UPDATE\s+{table}\s+SET\s+owner_id", executable)
        assert backfill, f"{table} 的回填语句不能被删掉"
        assert backfill.start() < constraint.start(), f"{table}：回填必须排在 NOT NULL 之前"


def test_llm_config_single_row_constraint_dropped_and_owner_unique():
    """按 owner 一行：单行约束要去掉，同时补上 owner 唯一键，避免一个身份多份配置。"""
    assert "DROP CONSTRAINT IF EXISTS llm_config_single_row" in SCHEMA
    assert "CREATE UNIQUE INDEX IF NOT EXISTS idx_llm_config_owner" in SCHEMA


def test_llm_config_sequence_catches_up_on_every_startup():
    """序列追赶必须在建序列的 IF 之外，且用 GREATEST 保证只单调前进。

    钉住一个已在真实库复现的故障：序列在空表时建好（停在 1），随后旧代码用
    DEFAULT 1 硬塞了一行 id=1。若追赶逻辑写在「序列不存在才执行」的分支里，
    它永远不会再跑，下一个 owner 播种时 nextval 取到 1 撞主键，
    表现是「新访客的模型配置永远存不进去」（UniqueViolationError）。
    """
    executable = re.sub(r"--[^\n]*", "", SCHEMA)
    setval = re.search(r"(?is)setval\(\s*'llm_config_id_seq'.*?\)\s*;", executable)
    assert setval, "必须有 llm_config_id_seq 的 setval 追赶语句"
    # 追赶语句不能落在 CREATE SEQUENCE 所在的那个 IF 分支里：
    # 用「它排在 CREATE SEQUENCE 之后、且与之不在同一个 DO 块」来判定。
    create = re.search(r"(?is)CREATE\s+SEQUENCE\s+llm_config_id_seq", executable)
    assert create, "建序列语句不能被删掉"
    assert setval.start() > create.start(), "追赶应排在建序列之后"
    # 追赶必须在所有 DO 块之外：写进建序列那个 IF 分支就等于「只在建库那次跑」
    assert not any("llm_config_id_seq" in b and "setval" in b for b in _do_blocks()), \
        "追赶语句不能写在 DO 块内，否则会被建序列的存在性守卫连带跳过"
    # 单调前进：没有 GREATEST 就可能把序列回拨，导致已删除的 id 被重用
    assert "GREATEST" in setval.group(0).upper(), "setval 必须用 GREATEST 只向前推进"


# ---- 双阈值语义：两个阈值管两件不同的事 ----

def test_trigger_and_keep_thresholds_are_independent():
    """保留阈值是近窗大小，不是摘要触发下限；它必须严格小于触发轮次，

    否则近窗会吃掉全部待摘要区间，触发了也没有东西可摘。
    """
    assert config.KEEP_RECENT_TURNS > 0
    assert config.SUMMARY_TRIGGER_TURNS > config.KEEP_RECENT_TURNS
    assert config.SUMMARY_TRIGGER_CHARS > 0


def test_circuit_breaker_threshold_is_positive():
    assert config.SUMMARY_MAX_CONSECUTIVE_FAILURES >= 1

