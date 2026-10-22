"""Alembic revision identity."""
revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


def upgrade() -> None:
    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("event_type", sa.String(128), nullable=False),
        sa.Column("external_id", sa.String(256), nullable=False),
        sa.Column("idempotency_key", sa.String(512), nullable=False),
        sa.Column("raw", postgresql.JSONB(), nullable=False),
        sa.Column("canonical", postgresql.JSONB(), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key", name="uq_events_idempotency_key"),
    )
    op.create_index("ix_events_received_at", "events", ["received_at"])
    op.create_table(
        "outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("routing_key", sa.String(256), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_outbox_published_at", "outbox", ["published_at"])
    op.create_table(
        "deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("consumer", sa.String(32), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_deliveries_event_id", "deliveries", ["event_id"])
    op.create_table(
        "intakes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("idempotency_key", sa.String(512), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id"), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "consumer_controls",
        sa.Column("name", sa.String(32), primary_key=True),
        sa.Column("fail_next", sa.Boolean(), nullable=False),
    )
    op.bulk_insert(
        sa.table(
            "consumer_controls",
            sa.column("name", sa.String),
            sa.column("fail_next", sa.Boolean),
        ),
        [
            {"name": "crm", "fail_next": False},
            {"name": "email", "fail_next": False},
            {"name": "audit", "fail_next": False},
        ],
    )


def downgrade() -> None:
    op.drop_table("consumer_controls")
    op.drop_table("intakes")
    op.drop_table("deliveries")
    op.drop_table("outbox")
    op.drop_table("events")
