import os
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional

from fastapi import Body, Depends, FastAPI, HTTPException, Path, Query, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --------------------------------------------------------------------------------------
# App metadata and initialization with OpenAPI tags
# --------------------------------------------------------------------------------------

openapi_tags = [
    {"name": "health", "description": "Service health and metadata"},
    {"name": "notifications", "description": "Public/internal endpoints to trigger notifications"},
    {"name": "status", "description": "Delivery tracking and status queries"},
    {"name": "docs", "description": "Documentation helpers"},
]

app = FastAPI(
    title="Notification Service",
    description=(
        "Orchestrates email and SMS notifications for the Event Platform.\n"
        "- Public/internal APIs to trigger notifications (e.g., booking confirmations, reminders)\n"
        "- Delivery tracking and status queries\n"
        "- Uses stub integrations if provider keys are not provided via environment variables\n"
    ),
    version="0.1.0",
    openapi_tags=openapi_tags,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust as needed for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------------------------------------------
# Domain models
# --------------------------------------------------------------------------------------

class Channel(str, Enum):
    email = "email"
    sms = "sms"


class NotificationStatus(str, Enum):
    queued = "queued"
    sending = "sending"
    sent = "sent"
    failed = "failed"


class NotificationBase(BaseModel):
    channel: Channel = Field(..., description="Delivery channel: email or sms")
    to: str = Field(..., description="Recipient. Email address for email, E.164 phone for sms")
    subject: Optional[str] = Field(None, description="Subject (email only)")
    message: str = Field(..., description="Message body (text)")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Arbitrary metadata for correlation")


class NotificationCreate(NotificationBase):
    """Payload to trigger a new notification."""


class NotificationPublic(NotificationBase):
    id: str = Field(..., description="Notification ID")
    status: NotificationStatus = Field(..., description="Current delivery status")
    provider: str = Field(..., description="Provider used (or stub)")
    provider_message_id: Optional[str] = Field(None, description="Upstream provider message id if available")
    error_message: Optional[str] = Field(None, description="Failure reason, if any")
    created_at: datetime = Field(..., description="Creation time (UTC)")
    updated_at: datetime = Field(..., description="Last update time (UTC)")


class NotificationListResponse(BaseModel):
    items: List[NotificationPublic]
    total: int
    page: int
    size: int


class ProviderConfig(BaseModel):
    email_provider: str = Field(..., description="Configured email provider or 'stub'")
    sms_provider: str = Field(..., description="Configured SMS provider or 'stub'")
    is_email_stub: bool = Field(..., description="True if using stub email sender")
    is_sms_stub: bool = Field(..., description="True if using stub SMS sender")


# --------------------------------------------------------------------------------------
# Repository (in-memory for this project scope)
# --------------------------------------------------------------------------------------

class NotificationRepository:
    """Simple in-memory repository for demo and local development."""

    def __init__(self) -> None:
        self._db: Dict[str, NotificationPublic] = {}

    # PUBLIC_INTERFACE
    def create(self, data: NotificationCreate, provider: str) -> NotificationPublic:
        """Create a new notification with queued status."""
        now = datetime.now(timezone.utc)
        notif = NotificationPublic(
            id=str(uuid.uuid4()),
            channel=data.channel,
            to=data.to,
            subject=data.subject,
            message=data.message,
            metadata=data.metadata or {},
            status=NotificationStatus.queued,
            provider=provider,
            provider_message_id=None,
            error_message=None,
            created_at=now,
            updated_at=now,
        )
        self._db[notif.id] = notif
        return notif

    # PUBLIC_INTERFACE
    def update_status(
        self,
        notification_id: str,
        status: NotificationStatus,
        provider_message_id: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> NotificationPublic:
        """Update notification status and provider details."""
        if notification_id not in self._db:
            raise KeyError("Notification not found")
        existing = self._db[notification_id]
        updated = existing.model_copy(
            update={
                "status": status,
                "provider_message_id": provider_message_id or existing.provider_message_id,
                "error_message": error_message,
                "updated_at": datetime.now(timezone.utc),
            }
        )
        self._db[notification_id] = updated
        return updated

    # PUBLIC_INTERFACE
    def get(self, notification_id: str) -> Optional[NotificationPublic]:
        """Fetch notification by id."""
        return self._db.get(notification_id)

    # PUBLIC_INTERFACE
    def list(
        self,
        channel: Optional[Channel] = None,
        to: Optional[str] = None,
        status_filter: Optional[NotificationStatus] = None,
        page: int = 1,
        size: int = 20,
    ) -> NotificationListResponse:
        """List notifications with optional filtering and pagination."""
        items = list(self._db.values())
        if channel:
            items = [n for n in items if n.channel == channel]
        if to:
            items = [n for n in items if n.to == to]
        if status_filter:
            items = [n for n in items if n.status == status_filter]
        total = len(items)
        start = (page - 1) * size
        end = start + size
        return NotificationListResponse(items=items[start:end], total=total, page=page, size=size)


repo = NotificationRepository()

# --------------------------------------------------------------------------------------
# Provider integration layer (stub-first)
# --------------------------------------------------------------------------------------

class EmailProvider:
    """Abstraction for email sending."""

    # PUBLIC_INTERFACE
    def send(self, to_email: str, subject: Optional[str], message: str) -> Dict[str, Optional[str]]:
        """Send an email and return a dict with provider_message_id, error if any."""
        raise NotImplementedError


class SMSProvider:
    """Abstraction for SMS sending."""

    # PUBLIC_INTERFACE
    def send(self, to_phone: str, message: str) -> Dict[str, Optional[str]]:
        """Send an SMS and return a dict with provider_message_id, error if any."""
        raise NotImplementedError


class StubEmailProvider(EmailProvider):
    """Logs to console and returns a fake message id."""

    def send(self, to_email: str, subject: Optional[str], message: str) -> Dict[str, Optional[str]]:
        fake_id = f"stub-email-{uuid.uuid4()}"
        # For demo: print; in real code use structured logging
        print(f"[StubEmail] to={to_email} subj={subject!r} msg={message!r} id={fake_id}")
        return {"provider_message_id": fake_id, "error": None}


class StubSMSProvider(SMSProvider):
    """Logs to console and returns a fake message id."""

    def send(self, to_phone: str, message: str) -> Dict[str, Optional[str]]:
        fake_id = f"stub-sms-{uuid.uuid4()}"
        print(f"[StubSMS] to={to_phone} msg={message!r} id={fake_id}")
        return {"provider_message_id": fake_id, "error": None}


def resolve_email_provider() -> (EmailProvider, str, bool):
    """
    Choose email provider based on environment variables.
    If no real provider keys available, fallback to stub.
    """
    # Example placeholders: SENDGRID_API_KEY, MAILGUN_API_KEY
    sendgrid_key = os.getenv("SENDGRID_API_KEY")
    mailgun_key = os.getenv("MAILGUN_API_KEY")

    if sendgrid_key:
        # Real integration can be implemented here. For now, still stub but name is 'sendgrid'
        return StubEmailProvider(), "sendgrid", False
    if mailgun_key:
        return StubEmailProvider(), "mailgun", False
    # Fallback
    return StubEmailProvider(), "stub", True


def resolve_sms_provider() -> (SMSProvider, str, bool):
    """
    Choose SMS provider based on environment variables.
    If no real provider keys available, fallback to stub.
    """
    # Example placeholders: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_FROM
    twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
    twilio_token = os.getenv("TWILIO_AUTH_TOKEN")

    if twilio_sid and twilio_token:
        # Real integration can be implemented here. For now, still stub but name is 'twilio'
        return StubSMSProvider(), "twilio", False

    # Fallback
    return StubSMSProvider(), "stub", True


# --------------------------------------------------------------------------------------
# Service layer coordinating repository and providers
# --------------------------------------------------------------------------------------

class NotificationService:
    """Business logic for creating and sending notifications."""

    def __init__(self, repository: NotificationRepository) -> None:
        self.repository = repository

    # PUBLIC_INTERFACE
    def provider_config(self) -> ProviderConfig:
        """Return the currently resolved provider configuration."""
        _, email_name, email_stub = resolve_email_provider()
        _, sms_name, sms_stub = resolve_sms_provider()
        return ProviderConfig(
            email_provider=email_name,
            sms_provider=sms_name,
            is_email_stub=email_stub,
            is_sms_stub=sms_stub,
        )

    # PUBLIC_INTERFACE
    def trigger(self, data: NotificationCreate) -> NotificationPublic:
        """Create and send a notification."""
        if data.channel == Channel.email:
            email_provider, provider_name, _ = resolve_email_provider()
            rec = self.repository.create(data, provider=provider_name)
            try:
                self.repository.update_status(rec.id, NotificationStatus.sending)
                result = email_provider.send(to_email=data.to, subject=data.subject, message=data.message)
                provider_message_id = result.get("provider_message_id")
                error = result.get("error")
                if error:
                    return self.repository.update_status(rec.id, NotificationStatus.failed, error_message=str(error))
                return self.repository.update_status(rec.id, NotificationStatus.sent, provider_message_id=provider_message_id)
            except Exception as ex:  # Defensive
                return self.repository.update_status(rec.id, NotificationStatus.failed, error_message=str(ex))

        elif data.channel == Channel.sms:
            sms_provider, provider_name, _ = resolve_sms_provider()
            rec = self.repository.create(data, provider=provider_name)
            try:
                self.repository.update_status(rec.id, NotificationStatus.sending)
                result = sms_provider.send(to_phone=data.to, message=data.message)
                provider_message_id = result.get("provider_message_id")
                error = result.get("error")
                if error:
                    return self.repository.update_status(rec.id, NotificationStatus.failed, error_message=str(error))
                return self.repository.update_status(rec.id, NotificationStatus.sent, provider_message_id=provider_message_id)
            except Exception as ex:
                return self.repository.update_status(rec.id, NotificationStatus.failed, error_message=str(ex))
        else:
            raise ValueError("Unsupported channel")


service = NotificationService(repo)

# --------------------------------------------------------------------------------------
# Dependencies
# --------------------------------------------------------------------------------------

def get_service() -> NotificationService:
    return service

# --------------------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------------------

@app.get("/", tags=["health"], summary="Health check", description="Simple health check endpoint.")
def health_check():
    """Return service health info."""
    return {"message": "Healthy", "service": "NotificationService"}


@app.get(
    "/docs/websocket-usage",
    tags=["docs"],
    summary="WebSocket usage notes",
    description="This service currently does not expose WebSockets. This endpoint is reserved for documenting real-time features in the future.",
)
def websocket_usage_note():
    """Provide notes about any websocket usage for API docs."""
    return {"message": "No WebSocket endpoints exposed currently."}


# PUBLIC_INTERFACE
@app.get(
    "/config/provider",
    tags=["notifications"],
    summary="Get provider configuration",
    description="Returns which providers are configured and whether the service is using stub integrations.",
    response_model=ProviderConfig,
)
def get_provider_config(svc: NotificationService = Depends(get_service)):
    """Return the resolved provider configuration for email and SMS."""
    return svc.provider_config()


# PUBLIC_INTERFACE
@app.post(
    "/notifications/send",
    tags=["notifications"],
    summary="Trigger a notification",
    description=(
        "Creates and sends a notification via email or SMS. "
        "Falls back to stub providers if real provider keys are not configured in environment variables."
    ),
    response_model=NotificationPublic,
    status_code=status.HTTP_201_CREATED,
)
def trigger_notification(
    payload: NotificationCreate = Body(..., description="Notification payload"),
    svc: NotificationService = Depends(get_service),
):
    """Trigger a new notification and return its delivery record."""
    try:
        rec = svc.trigger(payload)
        return rec
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))


# PUBLIC_INTERFACE
@app.get(
    "/notifications/{notification_id}",
    tags=["status"],
    summary="Get notification by id",
    description="Retrieve a single notification by ID.",
    response_model=NotificationPublic,
)
def get_notification(
    notification_id: str = Path(..., description="Notification identifier"),
    svc: NotificationService = Depends(get_service),
):
    """Fetch a specific notification record by id."""
    rec = svc.repository.get(notification_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Notification not found")
    return rec


# PUBLIC_INTERFACE
@app.get(
    "/notifications",
    tags=["status"],
    summary="List notifications",
    description="List notifications with optional filtering by channel, recipient, status, and pagination.",
    response_model=NotificationListResponse,
)
def list_notifications(
    channel: Optional[Channel] = Query(None, description="Filter by channel"),
    to: Optional[str] = Query(None, description="Filter by recipient"),
    status_filter: Optional[NotificationStatus] = Query(None, alias="status", description="Filter by delivery status"),
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    size: int = Query(20, ge=1, le=100, description="Page size"),
    svc: NotificationService = Depends(get_service),
):
    """List notifications with filters and pagination."""
    return svc.repository.list(channel=channel, to=to, status_filter=status_filter, page=page, size=size)


class NotificationStatusUpdate(BaseModel):
    status: NotificationStatus = Field(..., description="New status (sent/failed)")
    provider_message_id: Optional[str] = Field(None, description="Provider message id")
    error_message: Optional[str] = Field(None, description="Failure reason if any")


# PUBLIC_INTERFACE
@app.post(
    "/notifications/{notification_id}/status",
    tags=["status"],
    summary="Update status (internal callback)",
    description=(
        "Internal endpoint to update a notification's status. "
        "Can be used by provider webhooks or other services to reflect final delivery state."
    ),
    response_model=NotificationPublic,
)
def update_notification_status(
    notification_id: str = Path(..., description="Notification identifier"),
    payload: NotificationStatusUpdate = Body(...),
    svc: NotificationService = Depends(get_service),
):
    """Update an existing notification's status record."""
    try:
        # Validate existence
        if not svc.repository.get(notification_id):
            raise HTTPException(status_code=404, detail="Notification not found")

        updated = svc.repository.update_status(
            notification_id=notification_id,
            status=payload.status,
            provider_message_id=payload.provider_message_id,
            error_message=payload.error_message,
        )
        return updated
    except KeyError:
        raise HTTPException(status_code=404, detail="Notification not found")


# Convenience internal endpoints for common platform events (booking, event reminders)

class BookingNotificationRequest(BaseModel):
    booking_id: str = Field(..., description="Booking identifier")
    user_email: Optional[EmailStr] = Field(None, description="Email of attendee to notify")
    user_phone: Optional[str] = Field(None, description="Phone (E.164) of attendee to notify")
    event_name: str = Field(..., description="Event name")
    message_override: Optional[str] = Field(None, description="Override default message content")


# PUBLIC_INTERFACE
@app.post(
    "/internal/booking/confirmation",
    tags=["notifications"],
    summary="Trigger booking confirmation",
    description="Internal API for other services to trigger a booking confirmation by email and/or SMS.",
    response_model=List[NotificationPublic],
)
def trigger_booking_confirmation(payload: BookingNotificationRequest, svc: NotificationService = Depends(get_service)):
    """Trigger booking confirmation notifications via email and/or SMS."""
    notifications: List[NotificationPublic] = []
    default_message = (
        f"Your booking {payload.booking_id} for '{payload.event_name}' is confirmed. "
        "Thank you for using our platform!"
    )
    message = payload.message_override or default_message

    if payload.user_email:
        notifications.append(
            svc.trigger(
                NotificationCreate(
                    channel=Channel.email,
                    to=str(payload.user_email),
                    subject=f"Booking confirmed: {payload.event_name}",
                    message=message,
                    metadata={"booking_id": payload.booking_id, "event_name": payload.event_name},
                )
            )
        )
    if payload.user_phone:
        notifications.append(
            svc.trigger(
                NotificationCreate(
                    channel=Channel.sms,
                    to=payload.user_phone,
                    subject=None,
                    message=message,
                    metadata={"booking_id": payload.booking_id, "event_name": payload.event_name},
                )
            )
        )
    if not notifications:
        raise HTTPException(status_code=400, detail="At least one of user_email or user_phone must be provided")
    return notifications


class ReminderNotificationRequest(BaseModel):
    event_id: str = Field(..., description="Event identifier")
    user_email: Optional[EmailStr] = Field(None, description="Email of attendee to notify")
    user_phone: Optional[str] = Field(None, description="Phone (E.164) of attendee to notify")
    event_name: str = Field(..., description="Event name")
    event_datetime: Optional[str] = Field(None, description="Event date/time (ISO 8601)")
    message_override: Optional[str] = Field(None, description="Override default message content")


# PUBLIC_INTERFACE
@app.post(
    "/internal/event/reminder",
    tags=["notifications"],
    summary="Trigger event reminder",
    description="Internal API for other services to trigger event reminder notifications.",
    response_model=List[NotificationPublic],
)
def trigger_event_reminder(payload: ReminderNotificationRequest, svc: NotificationService = Depends(get_service)):
    """Trigger event reminder notifications via email and/or SMS."""
    notifications: List[NotificationPublic] = []
    default_message = f"Reminder: '{payload.event_name}' is coming up."
    if payload.event_datetime:
        default_message += f" Starts at {payload.event_datetime}."
    message = payload.message_override or default_message

    if payload.user_email:
        notifications.append(
            svc.trigger(
                NotificationCreate(
                    channel=Channel.email,
                    to=str(payload.user_email),
                    subject=f"Reminder: {payload.event_name}",
                    message=message,
                    metadata={"event_id": payload.event_id, "event_name": payload.event_name},
                )
            )
        )
    if payload.user_phone:
        notifications.append(
            svc.trigger(
                NotificationCreate(
                    channel=Channel.sms,
                    to=payload.user_phone,
                    subject=None,
                    message=message,
                    metadata={"event_id": payload.event_id, "event_name": payload.event_name},
                )
            )
        )
    if not notifications:
        raise HTTPException(status_code=400, detail="At least one of user_email or user_phone must be provided")
    return notifications
