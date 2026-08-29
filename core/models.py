from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime,
    ForeignKey, Enum as SAEnum, UniqueConstraint
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql import func
import enum

Base = declarative_base()


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    SUPERADMIN = "superadmin"


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
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    role = Column(SAEnum(UserRole), default=UserRole.ADMIN)

    user = relationship("User")
    department = relationship("Department", back_populates="admins")


class Ticket(Base):
    __tablename__ = "tickets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=True)
    topic = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    status = Column(SAEnum(TicketStatus), default=TicketStatus.NEW)
    response_text = Column(Text, nullable=True)
    is_anonymous = Column(Boolean, default=False)
    auto_closed = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    user = relationship("User", back_populates="tickets")
    department = relationship("Department", back_populates="tickets")


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

    id = Column(Integer, primary_key=True, autoincrement=True)
    department_id = Column(Integer, ForeignKey("departments.id"), nullable=False)
    parent_id = Column(Integer, ForeignKey("faq_nodes.id"), nullable=True)
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

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    event_id = Column(Integer, ForeignKey("events.id"), nullable=False)
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