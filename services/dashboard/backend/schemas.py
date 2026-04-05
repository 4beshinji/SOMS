from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime

# Task Schemas
class TaskBase(BaseModel):
    title: str
    description: Optional[str] = None
    location: Optional[str] = None
    bounty_gold: int = 10
    bounty_xp: int = 50
    expires_at: Optional[datetime] = None
    task_type: Optional[List[str]] = None

    # Intelligent scheduling fields
    urgency: int = 2  # 0-4 (DEFERRED to CRITICAL)
    zone: Optional[str] = None
    min_people_required: int = 1
    estimated_duration: int = 10  # minutes

    # Voice data (optional, provided by Brain if voice enabled)
    announcement_audio_url: Optional[str] = None
    announcement_text: Optional[str] = None
    completion_audio_url: Optional[str] = None
    completion_text: Optional[str] = None

    # Federation
    region_id: str = "local"

    # Audience targeting
    audience: str = "user"  # "user" or "admin"

class TaskCreate(TaskBase):
    pass

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None
    bounty_gold: Optional[int] = None
    is_completed: Optional[bool] = None
    expires_at: Optional[datetime] = None
    task_type: Optional[List[str]] = None
    urgency: Optional[int] = None
    zone: Optional[str] = None
    is_queued: Optional[bool] = None

class Task(TaskBase):
    id: int
    is_completed: bool
    is_queued: bool = False
    created_at: datetime
    completed_at: Optional[datetime] = None
    dispatched_at: Optional[datetime] = None
    
    # Voice announcement fields
    announcement_audio_url: Optional[str] = None
    announcement_text: Optional[str] = None
    completion_audio_url: Optional[str] = None
    completion_text: Optional[str] = None
    assigned_to: Optional[int] = None
    accepted_at: Optional[datetime] = None
    last_reminded_at: Optional[datetime] = None
    report_status: Optional[str] = None
    completion_note: Optional[str] = None

    class Config:
        from_attributes = True


class TaskCompleteResponse(Task):
    """Extended task response returned after completion, includes reward multiplier info."""
    reward_multiplier: Optional[float] = None       # Zone device XP multiplier (1.0-3.0)
    reward_adjusted_bounty: Optional[int] = None     # bounty_gold * multiplier

class TaskComplete(BaseModel):
    report_status: Optional[str] = None  # no_issue / resolved / needs_followup / cannot_resolve
    completion_note: Optional[str] = None  # Free-text (max 500 chars)

class TaskAccept(BaseModel):
    user_id: Optional[int] = None

# SystemStats Schemas
class SystemStatsResponse(BaseModel):
    total_xp: int = 0
    tasks_completed: int = 0
    tasks_created: int = 0
    tasks_active: int = 0
    tasks_queued: int = 0
    tasks_completed_last_hour: int = 0

# VoiceEvent Schemas
class VoiceEventCreate(BaseModel):
    message: str
    audio_url: str
    zone: Optional[str] = None
    tone: str = "neutral"

class VoiceEvent(VoiceEventCreate):
    id: int
    created_at: datetime

    class Config:
        from_attributes = True

# User Schemas
class UserBase(BaseModel):
    username: str
    display_name: Optional[str] = None
    region_id: str = "local"

class UserCreate(UserBase):
    pass

class UserUpdate(BaseModel):
    username: Optional[str] = None
    display_name: Optional[str] = None

class User(UserBase):
    id: int
    is_active: bool = True
    created_at: datetime
    global_user_id: Optional[str] = None

    class Config:
        from_attributes = True


# Shopping / Inventory Schemas
class ShoppingItemCreate(BaseModel):
    name: str
    category: Optional[str] = None
    quantity: int = 1
    unit: Optional[str] = None
    store: Optional[str] = None
    price: Optional[int] = None
    is_recurring: bool = False
    recurrence_days: Optional[int] = None
    notes: Optional[str] = None
    priority: int = 1
    created_by: str = "user"

class ShoppingItemUpdate(BaseModel):
    name: Optional[str] = None
    category: Optional[str] = None
    quantity: Optional[int] = None
    unit: Optional[str] = None
    store: Optional[str] = None
    price: Optional[int] = None
    is_recurring: Optional[bool] = None
    recurrence_days: Optional[int] = None
    notes: Optional[str] = None
    priority: Optional[int] = None

class ShoppingItem(BaseModel):
    id: int
    name: str
    category: Optional[str] = None
    quantity: int = 1
    unit: Optional[str] = None
    store: Optional[str] = None
    price: Optional[int] = None
    is_purchased: bool = False
    is_recurring: bool = False
    recurrence_days: Optional[int] = None
    last_purchased_at: Optional[datetime] = None
    next_purchase_at: Optional[datetime] = None
    notes: Optional[str] = None
    priority: int = 1
    created_at: Optional[datetime] = None
    purchased_at: Optional[datetime] = None
    created_by: str = "user"
    share_token: Optional[str] = None

    class Config:
        from_attributes = True

class PurchaseHistory(BaseModel):
    id: int
    item_name: str
    category: Optional[str] = None
    store: Optional[str] = None
    price: Optional[int] = None
    quantity: int = 1
    purchased_at: Optional[datetime] = None

    class Config:
        from_attributes = True

class ShoppingStats(BaseModel):
    total_items: int
    purchased_items: int
    pending_items: int
    total_spent_this_month: int
    category_breakdown: dict

class ShoppingShareResponse(BaseModel):
    share_url: str
    token: str
    items: List[ShoppingItem]


# Inventory Item Schemas (shelf sensor → item mapping)
# Chat Schemas
class ChatRequest(BaseModel):
    message: str

class ChatChunk(BaseModel):
    text: str
    audio_url: Optional[str] = None
    tone: Optional[str] = None
    motion_id: Optional[str] = None

class ChatResponse(BaseModel):
    content: str
    audio_url: Optional[str] = None
    tone: Optional[str] = None
    motion_id: Optional[str] = None
    chunks: Optional[List[ChatChunk]] = None

class ChatLogResponse(BaseModel):
    id: int
    user_message: str
    assistant_message: str
    audio_url: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


# Inventory Item Schemas (shelf sensor → item mapping)
class InventoryItemCreate(BaseModel):
    device_id: str
    channel: str = "weight"
    zone: str
    item_name: str
    category: Optional[str] = None
    unit_weight_g: float
    tare_weight_g: float = 0.0
    min_threshold: int = 2
    reorder_quantity: int = 1
    store: Optional[str] = None
    price: Optional[int] = None
    barcode: Optional[str] = None

class InventoryItemUpdate(BaseModel):
    item_name: Optional[str] = None
    category: Optional[str] = None
    unit_weight_g: Optional[float] = None
    tare_weight_g: Optional[float] = None
    min_threshold: Optional[int] = None
    reorder_quantity: Optional[int] = None
    store: Optional[str] = None
    price: Optional[int] = None
    barcode: Optional[str] = None
    is_active: Optional[bool] = None

class InventoryItemResponse(BaseModel):
    id: int
    device_id: str
    channel: str
    zone: str
    item_name: str
    category: Optional[str] = None
    unit_weight_g: float
    tare_weight_g: float
    min_threshold: int
    reorder_quantity: int
    store: Optional[str] = None
    price: Optional[int] = None
    barcode: Optional[str] = None
    is_active: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True
