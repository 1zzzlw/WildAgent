"""邮件内容与内嵌品牌资源，不负责验证码状态或 SMTP 连接。"""
from email.message import EmailMessage
from html import escape
from pathlib import Path
from string import Template


_TEMPLATES = Path(__file__).resolve().parents[1] / "templates" / "emails"


def build_registration_email(*, recipient: str, sender: str, code: str, validity_seconds: int) -> EmailMessage:
    validity = (f"{validity_seconds // 60} 分钟" if validity_seconds % 60 == 0
                else f"{validity_seconds} 秒")
    html = Template((_TEMPLATES / "registration.html").read_text(encoding="utf-8")).substitute(
        code=escape(code), validity=escape(validity),
    )
    message = EmailMessage()
    message["Subject"] = "WILD · 邮箱注册验证码"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(
        f"欢迎加入 WILD 建筑蓝图工作台。\n\n你的注册验证码：{code}\n"
        f"请在 {validity}内返回注册页面完成验证。\n\n"
        "请勿向任何人透露验证码。如果这不是你的操作，请忽略此邮件。\n"
    )
    message.add_alternative(html, subtype="html")
    # 使用前端 favicon.svg 的 PNG 版本，CID 内嵌避免外链失效与 SVG 邮件兼容问题。
    message.get_payload()[-1].add_related(
        (_TEMPLATES / "wild-logo.png").read_bytes(), maintype="image", subtype="png",
        cid="<wild-logo>", disposition="inline", filename="wild-logo.png",
    )
    return message
