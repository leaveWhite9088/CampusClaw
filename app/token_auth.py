"""JWT（HS256）签发与校验：stdlib 实现，密钥仅来自 SECRET_KEY 环境变量。

payload 声明：sub（user_id）、username、role、class_id、iat、exp。
令牌仅经 Authorization: Bearer 头提交，不出现在 URL 中。
"""

import base64
import hashlib
import hmac
import json
import time

TOKEN_TTL_SECONDS = 2 * 3600  # 2 小时


class TokenError(ValueError):
    pass


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _b64decode(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def _sign(signing_input: str, secret: str) -> str:
    sig = hmac.new(secret.encode("utf-8"), signing_input.encode("ascii"),
                   hashlib.sha256).digest()
    return _b64encode(sig)


def issue_token(user, secret: str, ttl: int = TOKEN_TTL_SECONDS) -> str:
    """user 为 users 表行（含 id/username/role/class_id）。"""
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user["id"],
        "username": user["username"],
        "role": user["role"],
        "class_id": user["class_id"],
        "iat": now,
        "exp": now + ttl,
    }
    signing_input = ".".join([
        _b64encode(json.dumps(header, separators=(",", ":")).encode("utf-8")),
        _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8")),
    ])
    return f"{signing_input}.{_sign(signing_input, secret)}"


def verify_token(token: str, secret: str) -> dict:
    """校验签名与有效期，返回 payload；任何问题抛 TokenError。"""
    parts = token.split(".")
    if len(parts) != 3 or not all(parts):
        raise TokenError("令牌格式错误")
    signing_input = f"{parts[0]}.{parts[1]}"
    expected = _sign(signing_input, secret)
    if not hmac.compare_digest(expected, parts[2]):
        raise TokenError("令牌签名不符")
    try:
        payload = json.loads(_b64decode(parts[1]))
    except (ValueError, json.JSONDecodeError) as e:
        raise TokenError("令牌 payload 非法") from e
    if not isinstance(payload, dict) or "sub" not in payload:
        raise TokenError("令牌缺少必要声明")
    if int(payload.get("exp", 0)) < int(time.time()):
        raise TokenError("令牌已过期")
    return payload
