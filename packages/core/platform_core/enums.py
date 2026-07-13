from __future__ import annotations

from enum import Enum


class SubscriptionStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    GRACE = "grace"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class PaymentStatus(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentPurpose(str, Enum):
    NEW_SUBSCRIPTION = "new_subscription"
    RENEWAL = "renewal"


class DeploymentStatus(str, Enum):
    PENDING = "pending"
    PROVISIONING = "provisioning"
    RUNNING = "running"
    STOPPED = "stopped"
    SUSPENDED = "suspended"
    FAILED = "failed"
    DELETED = "deleted"


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    CLOSED = "closed"


class NotificationType(str, Enum):
    REMINDER_7D = "reminder_7d"
    REMINDER_3D = "reminder_3d"
    REMINDER_24H = "reminder_24h"
    EXPIRED = "expired"
    DAILY_EXPIRED = "daily_expired"
    DEPLOYED = "deployed"
    SUSPENDED = "suspended"
    REACTIVATED = "reactivated"
    FAILED = "failed"


class UserRole(str, Enum):
    USER = "user"
    ADMIN = "admin"
    SUPERADMIN = "superadmin"
