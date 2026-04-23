from __future__ import annotations

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, create_engine

from app.config import settings


def build_engine(database_url: str | None = None):
    url = database_url or settings.database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    if url in {"sqlite://", "sqlite:///:memory:"} or url.endswith(":memory:"):
        return create_engine(url, connect_args=connect_args, poolclass=StaticPool)
    return create_engine(url, connect_args=connect_args)


def init_db(engine) -> None:
    SQLModel.metadata.create_all(engine)
    _migrate_sqlite_schema(engine)


def _migrate_sqlite_schema(engine) -> None:
    if engine.url.get_backend_name() != "sqlite":
        return

    with engine.begin() as connection:
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info('user')").fetchall()}

        if "email" not in columns:
            connection.exec_driver_sql("ALTER TABLE user ADD COLUMN email TEXT")
        if "password_hash" not in columns:
            connection.exec_driver_sql("ALTER TABLE user ADD COLUMN password_hash TEXT")
        if "password_salt" not in columns:
            connection.exec_driver_sql("ALTER TABLE user ADD COLUMN password_salt TEXT")
        if "is_active" not in columns:
            connection.exec_driver_sql("ALTER TABLE user ADD COLUMN is_active BOOLEAN DEFAULT 1")

        connection.exec_driver_sql(
            "CREATE UNIQUE INDEX IF NOT EXISTS ix_user_email_unique ON user(email)"
        )
        rows = connection.exec_driver_sql("SELECT id FROM user WHERE email IS NULL OR email = ''").fetchall()
        for row in rows:
            user_id = row[0]
            connection.exec_driver_sql(
                "UPDATE user SET email = ?, password_hash = ?, password_salt = ? WHERE id = ?",
                (f"legacy-{user_id[:8]}@local.invalid", "legacy", "legacy", user_id),
            )

        task_columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info('task')").fetchall()}
        if "assigned_by_role" not in task_columns:
            connection.exec_driver_sql("ALTER TABLE task ADD COLUMN assigned_by_role TEXT")
        if "assigned_by_user_id" not in task_columns:
            connection.exec_driver_sql("ALTER TABLE task ADD COLUMN assigned_by_user_id TEXT")
        if "assignment_id" not in task_columns:
            connection.exec_driver_sql("ALTER TABLE task ADD COLUMN assignment_id TEXT")
        if "origin" not in task_columns:
            connection.exec_driver_sql("ALTER TABLE task ADD COLUMN origin TEXT DEFAULT 'STUDENT'")
        if "educational_validated" not in task_columns:
            connection.exec_driver_sql("ALTER TABLE task ADD COLUMN educational_validated BOOLEAN DEFAULT 1")
        if "educational_reason" not in task_columns:
            connection.exec_driver_sql("ALTER TABLE task ADD COLUMN educational_reason TEXT")

        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_task_assignment_id ON task(assignment_id)"
        )
        connection.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_task_assigned_by_user_id ON task(assigned_by_user_id)"
        )

        connection.exec_driver_sql("UPDATE user SET role = UPPER(role) WHERE role IS NOT NULL")
        connection.exec_driver_sql("UPDATE schoolclass SET approval_mode = UPPER(approval_mode) WHERE approval_mode IS NOT NULL")
        connection.exec_driver_sql("UPDATE classjoinrequest SET status = UPPER(status) WHERE status IS NOT NULL")
        connection.exec_driver_sql("UPDATE helprequest SET status = UPPER(status) WHERE status IS NOT NULL")
        connection.exec_driver_sql("UPDATE parentgoal SET status = UPPER(status) WHERE status IS NOT NULL")
        connection.exec_driver_sql("UPDATE notification SET type = UPPER(type) WHERE type IS NOT NULL")

        connection.exec_driver_sql("UPDATE task SET priority = UPPER(priority) WHERE priority IS NOT NULL")
        connection.exec_driver_sql("UPDATE task SET source = UPPER(source) WHERE source IS NOT NULL")
        connection.exec_driver_sql("UPDATE task SET status = UPPER(status) WHERE status IS NOT NULL")
        connection.exec_driver_sql("UPDATE task SET origin = UPPER(origin) WHERE origin IS NOT NULL")
        connection.exec_driver_sql("UPDATE task SET assigned_by_role = UPPER(assigned_by_role) WHERE assigned_by_role IS NOT NULL")

        connection.exec_driver_sql("UPDATE task SET priority = 'MEDIUM' WHERE priority IS NULL OR priority = ''")
        connection.exec_driver_sql("UPDATE task SET source = 'MANUAL' WHERE source IS NULL OR source = ''")
        connection.exec_driver_sql("UPDATE task SET status = 'TODO' WHERE status IS NULL OR status = ''")
        connection.exec_driver_sql("UPDATE task SET origin = 'STUDENT' WHERE origin IS NULL OR origin = ''")
