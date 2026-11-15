"""SMTP 传输实现，模板渲染与注册用例分别维护。"""
import smtplib
import ssl

from config import config


class MailDeliveryError(Exception):
    pass


def send_message(message) -> None:
    cfg = config.smtp
    try:
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
        raise MailDeliveryError("验证码邮件发送失败") from exc
