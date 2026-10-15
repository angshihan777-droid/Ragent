"""访问令牌管理 CLI：签发 / 列出 / 撤销。

为什么是命令行而不是 HTTP 端点：签发令牌需要一个「已经能读写这张表」的入口，
而它本身不能用令牌保护（鸡生蛋）。放在命令行里由运维在服务器上执行，
既不必在 API 上开一个无鉴权的后门端点，也不必给前端再补一套登录注册。

用法（在 backend 目录下执行，读 .env 里的 DATABASE_URL）：

    python -m app.tokens create --owner svc-opsmind --name opsmind-mcp
    python -m app.tokens list
    python -m app.tokens list --owner svc-opsmind
    python -m app.tokens revoke --id <uuid>
"""
import argparse
import asyncio
import sys
from uuid import UUID

import asyncpg

from app.config import get_settings
from app.middleware.owner import normalize_owner_id
from app.repositories import api_tokens as repo
from app.security import generate_token, hash_token


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m app.tokens", description="Ragent 访问令牌管理"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="签发一枚新令牌（明文只打印这一次）")
    create.add_argument("--owner", required=True, help="令牌代表的身份 id，如 svc-opsmind")
    create.add_argument("--name", default="", help="用途备注，如 opsmind-mcp")

    listing = sub.add_parser("list", help="列出令牌（只显示元信息，不含明文）")
    listing.add_argument("--owner", default=None, help="只看某个身份的令牌")

    revoke = sub.add_parser("revoke", help="撤销一枚令牌")
    revoke.add_argument("--id", required=True, help="令牌 id（用 list 查看）")

    return parser


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    conn = await asyncpg.connect(dsn=settings.database_url)
    try:
        if args.command == "create":
            # 复用与 Cookie 同一套白名单：身份 id 必须能当 Cookie 值用，
            # 否则这个身份在前端永远显示不出来，出问题时也没法用它去复现用户视角。
            if normalize_owner_id(args.owner) != args.owner:
                print("身份 id 只允许字母、数字、下划线和连字符，长度 1~64", file=sys.stderr)
                return 2
            raw_token = generate_token()
            row = await repo.insert_token(conn, hash_token(raw_token), args.owner, args.name)
            print("令牌已签发。明文只显示这一次，请立刻保存到调用方的配置里：")
            print(raw_token)
            print(f"id={row['id']}  owner={row['owner_id']}  name={row['name']}")
            return 0

        if args.command == "list":
            if args.owner is not None and normalize_owner_id(args.owner) != args.owner:
                print("身份 id 非法", file=sys.stderr)
                return 2
            rows = await repo.list_tokens(conn, args.owner)
            if not rows:
                print("（没有令牌）")
                return 0
            for row in rows:
                state = "已撤销" if row["revoked_at"] else "有效  "
                last_used = row["last_used_at"] or "-"
                print(
                    f"{row['id']}  {row['owner_id']:<20} {state}  "
                    f"创建={row['created_at']:%Y-%m-%d %H:%M}  最近使用={last_used}  "
                    f"备注={row['name']}"
                )
            return 0

        if args.command == "revoke":
            try:
                token_id = UUID(args.id)
            except ValueError:
                print("--id 不是合法的 UUID", file=sys.stderr)
                return 2
            ok = await repo.revoke_token_by_id(conn, token_id)
            print("已撤销" if ok else "没找到这枚未撤销的令牌")
            return 0 if ok else 1
    finally:
        await conn.close()
    return 2


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except asyncpg.exceptions.UndefinedTableError:
        print(
            "api_tokens 表不存在：先启动一次应用（schema.sql 启动时会建表）再执行本命令",
            file=sys.stderr,
        )
        return 1
    except OSError as exc:
        print(f"连不上数据库：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
