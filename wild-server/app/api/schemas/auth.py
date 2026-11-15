"""账号接口请求结构。"""
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator


class LoginInput(BaseModel):
    email: EmailStr = Field(max_length=254)
    password: str = Field(max_length=128)


class EmailCodeInput(BaseModel):
    email: EmailStr = Field(max_length=254)


class RegisterInput(EmailCodeInput):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(min_length=2, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    confirm_password: str = Field(min_length=8, max_length=128)
    code: str = Field(pattern=r"^[0-9]{6}$")

    @field_validator("username")
    @classmethod
    def valid_username(cls, value: str) -> str:
        value = value.strip()
        if len(value) < 2 or any(ord(char) < 32 for char in value):
            raise ValueError("用户名至少 2 个字符，且不能包含控制字符")
        return value

    @model_validator(mode="after")
    def matching_passwords(self):
        if self.password != self.confirm_password:
            raise ValueError("两次输入的密码不一致")
        return self
