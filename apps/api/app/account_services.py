"""Durable auth controls, single-use tokens and transactional account privacy."""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import and_, case, delete, exists, or_, select, update
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.models import AuthSession, User
from app.db.account_models import AccountToken, AuthThrottle, NotificationOutbox
from app.security import new_token, token_digest


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def throttle_key(scope: str, subject: str) -> str:
    return hashlib.sha256((scope + "\0" + subject.casefold()).encode()).hexdigest()


def throttle(db: Session, *, scope: str, subject: str, limit: int, window_seconds: int = 60) -> None:
    """An atomic fixed-window counter committed even when login subsequently fails.

    PostgreSQL and SQLite use their native conflict update. No in-memory counters
    or process locks participate in admission. Keys contain no raw address/email.
    """
    key, now = throttle_key(scope, subject), utcnow()
    cutoff = now - timedelta(seconds=window_seconds)
    dialect = db.get_bind().dialect.name
    if dialect == "postgresql":
        from sqlalchemy.dialects.postgresql import insert
    elif dialect == "sqlite":
        from sqlalchemy.dialects.sqlite import insert
    else:
        raise HTTPException(503, "Authentication admission is unavailable")
    statement = insert(AuthThrottle).values(key=key, window_start=now, attempts=1)
    statement = statement.on_conflict_do_update(index_elements=[AuthThrottle.key], set_={
        "window_start": case((AuthThrottle.window_start <= cutoff, now), else_=AuthThrottle.window_start),
        "attempts": case((AuthThrottle.window_start <= cutoff, 1), else_=AuthThrottle.attempts + 1),
    }).returning(AuthThrottle.attempts)
    count = db.execute(statement).scalar_one()
    # Expired buckets have no relation to an account and need no permanent retention.
    db.execute(delete(AuthThrottle).where(AuthThrottle.window_start < now - timedelta(days=1)))
    db.commit()
    if count > limit:
        raise HTTPException(429, "Too many authentication attempts", headers={"Retry-After": str(window_seconds)})


def issue_token(db: Session, user_id: UUID, purpose: str, ttl_minutes: int) -> tuple[str, datetime]:
    now = utcnow()
    # A new request invalidates previous links and removes their private delivery material.
    db.execute(update(AccountToken).where(AccountToken.user_id == user_id, AccountToken.purpose == purpose,
                                         AccountToken.used_at.is_(None)).values(used_at=now))
    if purpose in {"email_verify", "password_reset"}:
        db.execute(update(NotificationOutbox).where(NotificationOutbox.user_id == user_id,
            NotificationOutbox.template == purpose, NotificationOutbox.status.in_(("pending", "failed")))
            .values(status="cancelled", payload={}))
    raw, expiry = new_token(), now + timedelta(minutes=ttl_minutes)
    db.add(AccountToken(user_id=user_id, purpose=purpose, token_hash=token_digest(raw), expires_at=expiry))
    return raw, expiry


def consume_token(db: Session, raw: str, purpose: str) -> User:
    """CAS consumption and the following user mutation share one transaction."""
    now = utcnow()
    user_id = db.execute(update(AccountToken).where(AccountToken.token_hash == token_digest(raw),
        AccountToken.purpose == purpose, AccountToken.used_at.is_(None), AccountToken.expires_at > now)
        .values(used_at=now).returning(AccountToken.user_id)).scalar_one_or_none()
    user = db.scalar(select(User).where(User.id == user_id).with_for_update()) if user_id else None
    if user is None or not user.is_active:
        raise HTTPException(400, "The link is invalid or has expired")
    return user


def revoke_sessions(db: Session, user_id: UUID) -> int:
    result = db.execute(update(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
                        .values(revoked_at=utcnow()))
    return result.rowcount


def owned_table_predicates(user_id: UUID) -> dict:
    """Follow FK children, including derived rows with no direct user_id.

    Shared authored exercise/skill catalogs are not descendants of a User and
    cannot enter this graph. Composite FK edges use a correlated EXISTS so
    identity components cannot be accidentally combined across tenants.
    """
    owned = {}
    for table in Base.metadata.sorted_tables:
        parts = []
        if table.name == "users":
            parts.append(table.c.id == user_id)
        elif "user_id" in table.c and any(fk.column.table.name == "users" for fk in table.c.user_id.foreign_keys):
            # A direct owner always wins over incidental references to another
            # user's row; malformed cross-owner links must not broaden export.
            owned[table] = table.c.user_id == user_id
            continue
        for constraint in table.foreign_key_constraints:
            parent = constraint.referred_table
            if parent in owned:
                joins = [element.parent == element.column for element in constraint.elements]
                parts.append(exists(select(1).select_from(parent).where(owned[parent], and_(*joins))).correlate(table))
        if parts:
            owned[table] = or_(*parts)
    return owned


def _export_value(value):
    if isinstance(value, (UUID, datetime)):
        return str(value) if isinstance(value, UUID) else aware(value).isoformat()
    if isinstance(value, bytes):
        return base64.b64encode(value).decode("ascii")
    return value


def export_account(db: Session, user_id: UUID) -> dict:
    secret_tables = {"account_tokens", "auth_throttle", "notification_outbox", "billing_events"}
    secret_columns = {"password_hash", "token_hash", "csrf_token_hash", "lease_token", "payload_digest"}
    result, count = {}, 0
    for table, predicate in owned_table_predicates(user_id).items():
        if table.name in secret_tables:
            continue
        columns = [column for column in table.columns if column.name not in secret_columns]
        rows = db.execute(select(*columns).where(predicate).limit(10001 - count)).mappings().all()
        count += len(rows)
        if count > 10000:
            raise HTTPException(413, "Account export exceeds the online limit; request an operator export")
        result[table.name] = [{key: _export_value(value) for key, value in row.items()} for row in rows]
    return {"format": "mentor-account-v1", "exported_at": utcnow().isoformat(), "data": result}


def delete_account(db: Session, user_id: UUID, *, email: str) -> None:
    db.execute(select(User.id).where(User.id == user_id).with_for_update()).scalar_one()
    predicates = owned_table_predicates(user_id)
    # Child rows go first even on SQLite with foreign_keys enabled. No reliance on
    # ORM relationships or an incomplete hand-maintained list of learning tables.
    for table, predicate in reversed(list(predicates.items())):
        db.execute(delete(table).where(predicate))
    keys = [throttle_key(scope, email) for scope in ("auth_account", "reset_account")]
    keys += [throttle_key(scope, str(user_id)) for scope in ("verify_user", "delete_user", "telegram_bind_user", "checkout_user", "telegram_tutor", "coding_submission", "password_user")]
    db.execute(delete(AuthThrottle).where(AuthThrottle.key.in_(keys)))
    db.commit()
