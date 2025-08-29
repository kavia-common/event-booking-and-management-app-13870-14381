# Notification Service

FastAPI microservice for orchestrating email and SMS notifications for the Event Booking and Management platform.

Features:
- Trigger notifications via public/internal APIs
- Email and SMS channels
- Stub integrations if provider keys are absent
- Delivery tracking and status queries
- OpenAPI docs and schema generation

## Getting started

1. Create a `.env` file from the example:
```
cp .env.example .env
```
Fill in provider keys if available. If left blank, the service uses stub providers and logs messages to console.

2. Install dependencies:
```
pip install -r requirements.txt
```

3. Run the service:
```
uvicorn src.api.main:app --host ${HOST:-0.0.0.0} --port ${PORT:-8080} --log-level ${LOG_LEVEL:-info}
```

4. API docs:
- Swagger UI: http://localhost:8080/docs
- OpenAPI JSON: http://localhost:8080/openapi.json

## Environment variables

See `.env.example`:
- SENDGRID_API_KEY or MAILGUN_API_KEY (+ MAILGUN_DOMAIN) for email
- TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN (+ TWILIO_FROM) for SMS
- If not set, the service uses stub providers

## Endpoints

- GET `/` — Health check
- GET `/docs/websocket-usage` — Notes about WebSocket usage (none for now)

Notifications:
- GET `/config/provider` — Show provider configuration and whether stubs are used
- POST `/notifications/send` — Trigger a notification (email or sms)
- GET `/notifications/{notification_id}` — Get notification by ID
- GET `/notifications` — List notifications with filters (channel, to, status) and pagination

Internal convenience triggers:
- POST `/internal/booking/confirmation` — Trigger booking confirmation (email and/or SMS)
- POST `/internal/event/reminder` — Trigger event reminder (email and/or SMS)

Status updates:
- POST `/notifications/{notification_id}/status` — Update status (e.g., provider webhook)

## OpenAPI schema

Generate `interfaces/openapi.json`:
```
python -m src.api.generate_openapi
```

The schema is written to `interfaces/openapi.json` for other containers to consume.

## Notes on providers

This implementation includes a provider abstraction and falls back to stub providers that log messages if no real provider keys are present. To integrate with real providers (SendGrid/Mailgun/Twilio), implement the `send` methods for each provider class and change `resolve_*_provider` to instantiate the real providers when env vars are set.

## Security

- This service exposes internal endpoints; in production, place it behind the API Gateway and secure with auth and network policies.
- Do not commit real provider secrets; use environment variables.

