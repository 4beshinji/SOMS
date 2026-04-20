from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime
from sqlalchemy.sql import func
from database import Base

class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, index=True)
    description = Column(String)
    location = Column(String)
    is_completed = Column(Boolean, default=False)
    
    # Voice announcement fields
    announcement_audio_url = Column(String, nullable=True)
    announcement_text = Column(String, nullable=True)
    completion_audio_url = Column(String, nullable=True)
    completion_text = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    task_type = Column(String, nullable=True) # JSON list of strings
    
    # Intelligent scheduling fields
    urgency = Column(Integer, default=2)  # 0-4 (DEFERRED to CRITICAL)
    zone = Column(String, nullable=True)
    min_people_required = Column(Integer, default=1)
    estimated_duration = Column(Integer, default=10)  # minutes
    is_queued = Column(Boolean, default=False)
    dispatched_at = Column(DateTime(timezone=True), nullable=True)
    
    # Completion report
    report_status = Column(String, nullable=True)  # no_issue / resolved / needs_followup / cannot_resolve
    completion_note = Column(String, nullable=True)  # Free-text (max 500 chars)

    # Reminder tracking
    last_reminded_at = Column(DateTime(timezone=True), nullable=True)

    # Assignment tracking
    assigned_to = Column(Integer, nullable=True)
    accepted_at = Column(DateTime(timezone=True), nullable=True)

    # Federation
    region_id = Column(String(32), default="local")

    # Audience targeting
    audience = Column(String(16), default="user")  # "user" or "admin"

class TaskAuditLog(Base):
    """Append-only audit trail of task lifecycle events (no amounts, no currency)."""
    __tablename__ = "task_audit_log"
    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, index=True, nullable=False)
    action = Column(String(32), nullable=False, index=True)  # created / assigned / accepted / completed / dispatched
    actor_user_id = Column(Integer, nullable=True)
    notes = Column(String, nullable=True)
    region_id = Column(String(32), default="local")
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)


class VoiceEvent(Base):
    __tablename__ = "voice_events"
    id = Column(Integer, primary_key=True, index=True)
    message = Column(String)
    audio_url = Column(String)
    zone = Column(String, nullable=True)
    tone = Column(String, default="neutral")
    target_zone = Column(String, nullable=True)
    target_display_ids = Column(String, nullable=True)  # JSON array
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SystemStats(Base):
    __tablename__ = "system_stats"
    id = Column(Integer, primary_key=True, default=1)
    tasks_completed = Column(Integer, default=0)
    tasks_created = Column(Integer, default=0)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class DevicePosition(Base):
    __tablename__ = "device_positions"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, unique=True, index=True)
    zone = Column(String)
    x = Column(Float)
    y = Column(Float)
    device_type = Column(String, default="sensor")
    channels = Column(String, default="[]")  # JSON array of channel names
    orientation_deg = Column(Float, nullable=True)
    fov_deg = Column(Float, nullable=True)
    detection_range_m = Column(Float, nullable=True)
    label = Column(String, nullable=True)
    context = Column(String, nullable=True)  # Natural language sensor description for LLM reports
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class CameraPosition(Base):
    __tablename__ = "camera_positions"
    id = Column(Integer, primary_key=True, index=True)
    camera_id = Column(String, unique=True, index=True)
    zone = Column(String)
    x = Column(Float)
    y = Column(Float)
    z = Column(Float, nullable=True)
    fov_deg = Column(Float, nullable=True)
    orientation_deg = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ShoppingItem(Base):
    __tablename__ = "shopping_items"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    category = Column(String, nullable=True, index=True)
    quantity = Column(Integer, default=1)
    unit = Column(String, nullable=True)
    store = Column(String, nullable=True)
    price = Column(Integer, nullable=True)
    is_purchased = Column(Boolean, default=False)
    is_recurring = Column(Boolean, default=False)
    recurrence_days = Column(Integer, nullable=True)
    last_purchased_at = Column(DateTime(timezone=True), nullable=True)
    next_purchase_at = Column(DateTime(timezone=True), nullable=True)
    notes = Column(String, nullable=True)
    priority = Column(Integer, default=1)  # 0=low, 1=normal, 2=high
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    purchased_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String, default="user")
    share_token = Column(String, nullable=True, unique=True)


class PurchaseHistory(Base):
    __tablename__ = "purchase_history"
    id = Column(Integer, primary_key=True, index=True)
    item_name = Column(String, index=True)
    category = Column(String, nullable=True)
    store = Column(String, nullable=True)
    price = Column(Integer, nullable=True)
    quantity = Column(Integer, default=1)
    purchased_at = Column(DateTime(timezone=True), server_default=func.now())


class InventoryItem(Base):
    __tablename__ = "inventory_items"
    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True)
    channel = Column(String, default="weight")
    zone = Column(String, index=True)
    item_name = Column(String)
    category = Column(String, nullable=True)
    unit_weight_g = Column(Float)
    tare_weight_g = Column(Float, default=0.0)
    min_threshold = Column(Integer, default=2)
    reorder_quantity = Column(Integer, default=1)
    store = Column(String, nullable=True)
    price = Column(Integer, nullable=True)
    barcode = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class ChatLog(Base):
    __tablename__ = "chat_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_message = Column(String)
    assistant_message = Column(String)
    audio_url = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DisplayPosition(Base):
    __tablename__ = "display_positions"
    id = Column(Integer, primary_key=True, index=True)
    display_id = Column(String, unique=True, index=True)
    display_name = Column(String, nullable=True)
    zone = Column(String)
    x = Column(Float)
    y = Column(Float)
    screen_width_px = Column(Integer, nullable=True)
    screen_height_px = Column(Integer, nullable=True)
    sort_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    last_seen_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    display_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Federation
    region_id = Column(String(32), default="local")
    global_user_id = Column(String(200), nullable=True)
