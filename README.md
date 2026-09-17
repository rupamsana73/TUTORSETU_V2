# TutorSetu

**Find the Right Tutor. Learn the Right Way.**

TutorSetu is a secure tutor marketplace connecting **students**, **parents** and **tutors** across Howrah, Kolkata and West Bengal. It supports both local/home tutoring and online tutoring, and is built as a production-grade SaaS-style platform — not a basic CRUD app.

---

## Features

### Students & Parents
- Search & filter tutors (subject, class, board, location, mode, fee, rating, verification, availability)
- Smart tutor matching with a score and human-readable reasons
- Save tutors, send enquiries, request demo classes
- Post public tutor requests that tutors can respond to
- Secure internal messaging, notifications, reviews (only after an accepted enquiry)
- Parents manage multiple children and their requirements

### Tutors
- Multi-step onboarding (basic info → education → teaching → location → fees → availability → documents)
- Document-based verification (identity / qualification / profile badges awarded by admins)
- Enquiry inbox with accept/reject/respond, tutor-request browsing & applications
- Availability planner, publish/unpublish toggle, students list

### Admin (`/admin/dashboard/`)
- Statistics dashboard with Chart.js (users, growth, enquiries, verification queue)
- User management (search, filter, activate/deactivate/suspend/ban, password reset by email — never plaintext)
- Verification queue (approve / reject with mandatory reason / request changes), private document viewing
- Marketplace oversight, content CRUD (subjects, classes, boards, locations)
- Review moderation, report handling, broadcast notifications, audit logs, settings

### Platform-wide
- REST API with OpenAPI/Swagger docs at `/api/docs/`
- Rate limiting everywhere it matters (login, registration, password reset, messaging, enquiries, reviews, uploads, API throttles)
- Security headers, CSRF, secure/HttpOnly/SameSite cookies, HSTS + HTTPS redirect in production
- Audit logging of every sensitive action with actor, target, IP and metadata

---

## Tech Stack

| Layer      | Technology |
|------------|------------|
| Backend    | Python 3, Django 5, Django REST Framework |
| Frontend   | HTML5, CSS3, JavaScript, Bootstrap 5, Chart.js |
| Database   | SQLite (dev) · PostgreSQL (prod, via `DATABASE_URL`) |
| Docs       | drf-spectacular (OpenAPI 3 / Swagger UI) |
| Filtering  | django-filter |
| Rate limit | django-ratelimit (views) + DRF throttling (API) |
| Serving    | Gunicorn + WhiteNoise |
| Config     | python-dotenv, dj-database-url |

---

## Architecture

```
tutorsetu/
├── config/          # settings, root urls, wsgi/asgi
├── core/            # homepage, taxonomy (subjects/classes/boards), audit log,
│                    # settings, security middleware, management dashboard (/admin/dashboard/)
├── accounts/        # custom User (roles + status), auth, RBAC decorators, middleware
├── locations/       # Location, TutorTeachingArea
├── tutors/          # TutorProfile, subjects/classes, availability, search & matching service
├── students/        # StudentProfile, dashboard
├── parents/         # ParentProfile, StudentChild
├── marketplace/     # Enquiry, TutorRequest, TutorApplication, SavedTutor
├── messaging/       # Conversation, ConversationParticipant, Message
├── notifications/   # Notification + notify() service
├── reviews/         # Review, ReviewReport, eligibility + rating services
├── verification/    # TutorVerification, VerificationDocument (private), badges
├── reports/         # User reporting (generic target)
├── api/             # DRF serializers, views, filters, throttles, exception envelope
├── templates/  static/  media/
└── requirements.txt  .env.example  render.yaml  README.md
```

Key design decisions:

- **Custom user model** (`accounts.User`) with `role` (`STUDENT|PARENT|TUTOR|ADMIN`) and `status` (`ACTIVE|INACTIVE|SUSPENDED|BANNED`). ADMIN can never be self-registered.
- **RBAC is enforced server-side** with `@role_required` decorators; object ownership is checked in every query (e.g. `get_object_or_404(Enquiry, pk=id, tutor=request.user.tutor_profile)`) — no IDOR.
- **Business logic lives in services** (`reviews/services.py`, `marketplace` + `tutors/services.py`, `notifications/services.py`), keeping views thin and the matching engine replaceable by an AI model later.
- **Rate limits are centralised** in `core/ratelimits.py` (env-overridable) and DRF `DEFAULT_THROTTLE_RATES` in settings — never hardcoded per view.

---

## Installation

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env         # then edit values
python manage.py migrate
```

## Environment Variables

See `.env.example`. Important ones:

| Variable | Purpose |
|---|---|
| `DJANGO_SECRET_KEY` | Long random secret (required in production) |
| `DJANGO_DEBUG` | `True` dev / `False` production |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated hosts |
| `DATABASE_URL` | PostgreSQL URL; empty → SQLite |
| `EMAIL_HOST` / `EMAIL_PORT` / `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` / `EMAIL_USE_TLS` | SMTP |
| `SEED_ADMIN_EMAIL` / `SEED_ADMIN_PASSWORD` | Seed admin credentials (never hardcoded) |
| `RATE_LIMIT_*`, `API_THROTTLE_*` | Optional rate-limit overrides |

## Database Setup

- **Development:** nothing to do — SQLite is used automatically.
- **Production:** set `DATABASE_URL=postgres://user:pass@host:5432/tutorsetu` and run `python manage.py migrate`.

## Running Locally

```bash
python manage.py runserver
# http://127.0.0.1:8000
```

## Creating an Admin

```bash
python manage.py createsuperuser
```

(Or use the seed command below — password comes from `SEED_ADMIN_PASSWORD`.)

## Seed Data (development only)

```bash
SEED_ADMIN_PASSWORD='choose-a-strong-dev-password' python manage.py seed_data
```

Creates: 1 admin (`admin@tutorsetu.local`), 2 students (`student1@example.com` / `Student@123`),
2 parents (`parent1@example.com` / `Parent@123`) and 20+ fictional tutors (`tutorN@example.com` / `Tutor@123`)
across Kolkata & Howrah. All data is fictional.

## Testing

```bash
python manage.py check
python manage.py test        # 64 automated tests
```

Coverage includes: authentication, RBAC, IDOR/object-permission bypass, tutor onboarding,
search & matching, enquiries/requests/applications (duplicate prevention), messaging access
control, review eligibility & dedupe, upload validation, XSS escaping, security headers,
web rate limiting actually triggering, API auth/permissions/throttling and the API error envelope.

## API Documentation

- Swagger UI: `/api/docs/`
- OpenAPI schema: `/api/schema/`

All protected endpoints require session authentication; errors use a consistent envelope:

```json
{ "success": false, "message": "Unable to process your request.", "errors": {} }
```

## Security & Rate Limiting

- Login: 5 attempts / 15 min per IP (web) and scoped `auth` throttle (API)
- Registration: 5 / hour / IP · Password reset: 5 / hour / IP (and the response never reveals whether an email exists)
- Messaging, enquiries, reviews, tutor applications, reports, uploads: scoped, env-configurable limits
- Generic auth error messages; no account-enumeration
- Upload validation: extension + MIME + size + Pillow content verification for images; executable/script/blocklisted uploads rejected
- Verification documents are stored under `private/` and only downloadable by admins via an audit-logged view — never publicly served
- Privacy: emails, phones, pincodes and coordinates are withheld from public pages and APIs
- `python manage.py check --deploy` passes with 0 security warnings in production configuration

## Deployment (Render)

`render.yaml` is included (web service + PostgreSQL). Manual equivalent:

```bash
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate
gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 3
```

Required env vars in production: `DJANGO_DEBUG=False`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`,
`DJANGO_CSRF_TRUSTED_ORIGINS`, `DATABASE_URL`, SMTP settings.

HSTS, HTTPS redirect, secure cookies and the CSP header activate automatically when `DEBUG=False`.

## Future Roadmap

Payments (Razorpay/UPI), subscriptions & commissions, AI tutor matching, video classes,
calendar & Google Calendar sync, WhatsApp & push notifications, homework/assignments,
attendance & learning progress, referral system, React Native mobile app.
The models and service layer are designed for these to be added without rewrites;
payment models are intentionally not active in the MVP.
