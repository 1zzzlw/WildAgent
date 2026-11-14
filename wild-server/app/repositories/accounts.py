from time import time
from uuid import uuid4

from sqlalchemy import insert, select

from app.infrastructure.database import database
from app.infrastructure.schema import users


class AccountRepository:
    def find(self, email: str) -> dict | None:
        with database.engine.connect() as conn:
            row = conn.execute(select(users).where(users.c.email == email.lower())).mappings().first()
            return dict(row) if row else None

    def get(self, user_id: str) -> dict | None:
        with database.engine.connect() as conn:
            row = conn.execute(select(users.c.id, users.c.username, users.c.email, users.c.identity, users.c.status)
                               .where(users.c.id == user_id)).mappings().first()
            return dict(row) if row else None

    def exists(self, email: str) -> bool:
        with database.engine.connect() as conn:
            return conn.execute(select(users.c.id).where(users.c.email == email.lower())).first() is not None

    def create(self, username: str, email: str, password_hash: str) -> dict:
        value = dict(id=str(uuid4()), username=username,
                     email=email.lower(), identity=1, password_hash=password_hash,
                     status="active", created_at=int(time() * 1000))
        with database.engine.begin() as conn:
            conn.execute(insert(users).values(**value))
        return value


accounts = AccountRepository()
