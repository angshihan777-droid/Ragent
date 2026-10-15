"""访问令牌的纯逻辑：生成、哈希、解析。不碰数据库，便于单测。

为什么令牌不落库明文、也不上 bcrypt：见 schema.sql 里 api_tokens 表的注释。
这个文件刻意只放纯函数 —— 鉴权一旦出错，表现往往是「看着能用但谁都能进」，
必须能被测试钉死，所以把可测的部分从数据库逻辑里摘出来。
"""
import hashlib
import secrets

# 前缀让人在日志、配置文件里一眼认出这是本系统的令牌，也方便日后扫泄露。
TOKEN_PREFIX = "rag_"
# 32 字节随机 → urlsafe base64 约 43 字符，256 位熵，没有暴力破解的可能。
TOKEN_RANDOM_BYTES = 32
# Authorization 头的长度上限。哈希本身很便宜，但没有上限就等于允许别人塞一个
# 几 MB 的头进来占内存和带宽；合法的 Bearer 令牌远小于这个值。
MAX_TOKEN_LENGTH = 256


def generate_token() -> str:
    """生成一枚新令牌的明文。只在签发那一刻返回一次，此后系统里只剩哈希。"""
    return TOKEN_PREFIX + secrets.token_urlsafe(TOKEN_RANDOM_BYTES)


def hash_token(raw_token: str) -> str:
    """令牌哈希（sha256 十六进制），用作 api_tokens.token_hash 的查表键。"""
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def parse_bearer(header_value: str | None) -> str | None:
    """从 Authorization 头的值里取出 Bearer 令牌；取不到返回 None。

    取不到一律返回 None 而不是抛异常：「没带令牌」和「头写错了」在入口处是同一种情况 ——
    都还没轮到判定身份，调用方据此回退到 Cookie 身份即可。

    scheme 大小写不敏感（RFC 7235 规定 scheme 不区分大小写），但令牌本体原样返回：
    不做大小写折叠或空白清洗，否则两个不同的非法输入会被折成同一个令牌，
    等于凭空接受了一个伪造凭证。写成 "Bearer a b" 这种带内层空格的一律判非法。
    """
    if not header_value:
        return None
    scheme, separator, value = header_value.partition(" ")
    if not separator or scheme.lower() != "bearer":
        return None
    value = value.strip()
    if not value or " " in value or len(value) > MAX_TOKEN_LENGTH:
        return None
    return value
