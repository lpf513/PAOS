from datetime import datetime
import enum
from typing import Any, Dict, List, Optional

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, Float, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.mutable import MutableDict, MutableList
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TaskStatus(str, enum.Enum):
    """Lifecycle status for DAG task execution nodes."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    BLOCKED = "BLOCKED"
    COMPLETED = "COMPLETED"


class Project(Base):
    """Top-level workspace that owns identity, experience, and DAG task data."""

    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    identity_graph: Mapped[Optional["IdentityGraph"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        uselist=False,
    )
    experience_ledgers: Mapped[List["ExperienceLedger"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )
    dag_task_nodes: Mapped[List["DAGTaskNode"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
    )


class IdentityGraph(Base):
    """Persistent project identity: non-negotiable constraints and brand voice."""

    __tablename__ = "identity_graphs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    hard_constraints: Mapped[Dict[str, Any]] = mapped_column(
        MutableDict.as_mutable(JSONB),
        default=dict,
        nullable=False,
        comment="Structured immutable project constraints stored as JSON.",
    )
    brand_voice: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    project: Mapped[Project] = relationship(back_populates="identity_graph")


class ExperienceLedger(Base):
    """Vector-searchable memory entry for scenario outcomes and reflections."""

    __tablename__ = "experience_ledgers"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scenario_summary: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[List[float]] = mapped_column(
        Vector(1536),
        nullable=False,
        comment="1536-dimensional pgvector embedding for semantic retrieval.",
    )
    reflection_result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    success_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    project: Mapped[Project] = relationship(back_populates="experience_ledgers")


class DAGTaskNode(Base):
    """Task node in a project DAG, with dependencies stored as predecessor IDs."""

    __tablename__ = "dag_task_nodes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        Enum(TaskStatus, name="dag_task_status"),
        default=TaskStatus.PENDING,
        nullable=False,
        index=True,
    )
    dependencies: Mapped[List[int]] = mapped_column(
        MutableList.as_mutable(JSONB),
        default=list,
        nullable=False,
        comment="JSON array of prerequisite DAGTaskNode IDs.",
    )
    assigned_agent_role: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    output_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    project: Mapped[Project] = relationship(back_populates="dag_task_nodes")
