from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date,
    ForeignKey, Enum as SAEnum, UniqueConstraint, Index, CheckConstraint
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
import enum

Base = declarative_base()


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


class WebRole(str, enum.Enum):
    """Роли пользователей веб-админки."""
    SUPERADMIN = "SUPERADMIN"
    DEPARTMENT_ADMIN = "DEPARTMENT_ADMIN"
    VIEWER = "VIEWER"


class MessageAuthorType(str, enum.Enum):
    """Автор сообщения в истории заявки."""
    USER = "user"        # студент (VK)
    ADMIN = "admin"      # администратор (веб-панель)
    SYSTEM = "system"    # системные события (смена статуса и т.п.)


class TicketStatus(str, enum.Enum):
    NEW = "Новое"
    IN_PROGRESS = "В обработке"
    TRANSFERRED_ADMIN = "Передано в администрацию СГ"
    TRANSFERRED_HOUSEKEEPING = "Передано в Хозчасть"
    COMPLETED = "Выполнено"
    COMPLETED_AUTO = "Выполнено (авто)"
    ANONYMOUS = "Анонимное"


class Department(Base):
    __tablename__ = "departments"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)

    admins = relationship("Admin", back_populates="department")
    tickets = relationship("Ticket", back_populates="department")
    knowledge_base = relationship("KnowledgeBase", back_populates="department")
    faq_nodes = relationship("FAQNode", back_populates="department")
    events = relationship("Event", back_populates="department")


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    vk_id = Column(Integer, unique=True, nullable=False)
    full_name = Column(String, nullable=True)
    dormitory = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    tickets = relationship("Ticket", back_populates="user")
    subscriptions = relationship("Subscription", back_populates="user")
    registrations = relationship("Registration", back_populates="user")
    logs = relationship("Log", back_populates="user")


class Admin(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    role = Column(SAEnum(UserRole), default=UserRole.ADMIN)

    user = relationship("User")
    department = relationship("Department", back_populates="admins")


class Ticket(Base):
    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_user_id", "user_id"),
        Index("ix_tickets_department_id", "department_id"),
        Index("ix_tickets_status", "status"),
        Index("ix_tickets_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    topic = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    status = Column(SAEnum(TicketStatus), default=TicketStatus.NEW, nullable=False)
    response_text = Column(Text, nullable=True)
    is_anonymous = Column(Boolean, default=False, nullable=False)
    auto_closed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="tickets")
    department = relationship("Department", back_populates="tickets")
    messages = relationship(
        "TicketMessage",
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketMessage.created_at",
    )


class TicketMessage(Base):
    """Сообщение в истории заявки (вопрос студента, ответ администратора, системные события)."""
    __tablename__ = "ticket_messages"
    __table_args__ = (
        Index("ix_ticket_messages_ticket_id", "ticket_id"),
        CheckConstraint(
            "author_type IN ('USER', 'ADMIN', 'SYSTEM')",
            name="ck_ticket_messages_author_type",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticket_id = Column(
        Integer,
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_type = Column(SAEnum(MessageAuthorType), nullable=False)
    author_vk_id = Column(Integer, nullable=True)  # VK ID автора, если это студент
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    ticket = relationship("Ticket", back_populates="messages")


class WebUser(Base):
    """Пользователь веб-админки (пароль хранится только в виде хеша)."""
    __tablename__ = "web_users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)  # формат: pbkdf2_sha256$iterations$salt$hash
    role = Column(SAEnum(WebRole), default=WebRole.VIEWER, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    last_login_at = Column(DateTime(timezone=True), nullable=True)

    department = relationship("Department")


class ReportRun(Base):
    """Факт отправки ежедневного отчёта — защита от повторных отправок."""
    __tablename__ = "report_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_date = Column(Date, unique=True, nullable=False)  # дата отчёта (за которую он сформирован)
    status = Column(String, default="sent", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class KnowledgeBase(Base):
    __tablename__ = "knowledge_base"

    id = Column(Integer, primary_key=True, autoincrement=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    keywords = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    department = relationship("Department", back_populates="knowledge_base")


class FAQNode(Base):
    __tablename__ = "faq_nodes"
    __table_args__ = (
        # Для финальных узлов обязателен final_answer
        CheckConstraint(
            "NOT is_final OR final_answer IS NOT NULL",
            name="ck_faq_final_answer_required",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="CASCADE"), nullable=False)
    parent_id = Column(Integer, ForeignKey("faq_nodes.id", ondelete="SET NULL"), nullable=True)
    question = Column(Text, nullable=False)
    is_final = Column(Boolean, default=False, nullable=False)
    final_answer = Column(Text, nullable=True)
    button_text = Column(String, nullable=True)
    order_index = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    department = relationship("Department", back_populates="faq_nodes")
    parent = relationship("FAQNode", remote_side="FAQNode.id", backref="children")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("user_id", "department_id", name="uq_subscription_user_department"),)

    user = relationship("User", back_populates="subscriptions")


class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    event_date = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    department = relationship("Department", back_populates="events")
    registrations = relationship("Registration", back_populates="event")


class Registration(Base):
    __tablename__ = "registrations"
    __table_args__ = (
        UniqueConstraint("user_id", "event_id", name="uq_registration_user_event"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    event_id = Column(Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False)
    registered_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="registrations")
    event = relationship("Event", back_populates="registrations")


class Log(Base):
    __tablename__ = "logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    action = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    user = relationship("User", back_populates="logs")