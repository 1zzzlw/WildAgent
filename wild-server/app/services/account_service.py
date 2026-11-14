"""密码散列和邮箱验证码；密码与验证码不进入日志或会话历史。"""
import hashlib
import json
import secrets
import smtplib
import ssl

from fastapi import HTTPException
from redis.exceptions import LockError
from sqlalchemy.exc import IntegrityError

from app.infrastructure.cache import cache
from app.repositories.accounts import accounts
from app.services.email_messages import build_registration_email
from config import config


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        method, salt, expected = encoded.split("$")
        if method != "scrypt":
            return False
        actual = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1, dklen=32)
        return secrets.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


def email_key(email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()


def limit(key: str, maximum: int, seconds: int) -> None:
    key = cache.key(key)
    count = cache.client.eval("local n=redis.call('INCR',KEYS[1]); "
        "if n==1 then redis.call('EXPIRE',KEYS[1],ARGV[1]) end; return n", 1, key, seconds)
    if count > maximum:
        raise HTTPException(status_code=429, detail="操作过于频繁，请稍后重试")


def send_email_code(email: str, client_ip: str) -> dict:
    cfg = config.smtp
    if not cfg.host or not cfg.from_address:
        raise HTTPException(status_code=503, detail="邮箱验证服务暂未配置")
    limit("email:ip:" + email_key(client_ip), 20, 3600)
    if accounts.exists(email=email):
        raise HTTPException(status_code=409, detail="邮箱已注册，请直接登录")
    key = email_key(email)
    cooldown = cache.key("email:cooldown:" + key)
    if not cache.client.set(cooldown, "1", nx=True, ex=cfg.resend_seconds):
        raise HTTPException(status_code=429, detail="验证码已发送，请稍后再试")
    code = f"{secrets.randbelow(1000000):06d}"
    nonce = secrets.token_hex(16)
    value = json.dumps({"nonce": nonce, "digest": hashlib.sha256((nonce + code).encode()).hexdigest(), "attempts": 0})
    code_key = cache.key("email:code:" + key)
    cache.client.set(code_key, value, ex=cfg.code_seconds)
    try:
        message = build_registration_email(recipient=email, sender=cfg.from_address,
                                           code=code, validity_seconds=cfg.code_seconds)
        context = ssl.create_default_context()
        smtp = (smtplib.SMTP_SSL(cfg.host, cfg.port, timeout=15, context=context)
                if cfg.security == "ssl" else smtplib.SMTP(cfg.host, cfg.port, timeout=15))
        with smtp:
            if cfg.security == "starttls":
                smtp.starttls(context=context)
            if cfg.username:
                smtp.login(cfg.username, cfg.password.get_secret_value())
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        cache.client.delete(code_key, cooldown)
        raise HTTPException(status_code=503, detail="验证码发送失败，请稍后重试") from exc
    return {"resend_after": cfg.resend_seconds, "expires_in": cfg.code_seconds}


def register_account(username: str, email: str, password: str, code: str) -> dict:
    key = email_key(email)
    code_key = cache.key("email:code:" + key)
    lock = cache.client.lock(cache.key("email:register:" + key), timeout=30, blocking=False)
    if not lock.acquire(blocking=False):
        raise HTTPException(status_code=429, detail="正在处理注册，请稍后重试")
    try:
        raw = cache.client.get(code_key)
        value = json.loads(raw) if raw else None
        if value is None:
            raise HTTPException(status_code=400, detail="验证码已过期，请重新获取")
        actual = hashlib.sha256((value["nonce"] + code).encode()).hexdigest()
        if not secrets.compare_digest(value["digest"], actual):
            value["attempts"] += 1
            if value["attempts"] >= 5:
                cache.client.delete(code_key)
            else:
                cache.client.set(code_key, json.dumps(value), xx=True, keepttl=True)
            raise HTTPException(status_code=400, detail="验证码错误")
        try:
            account = accounts.create(username, email, hash_password(password))
        except IntegrityError as exc:
            raise HTTPException(status_code=409, detail="邮箱已注册") from exc
        cache.client.delete(code_key)
        return account
    finally:
        try:
            lock.release()
        except LockError:
            pass
