# CourtBazaar

CourtBazaar is a legal-ops and court-services marketplace for India. It connects advocates, law firms, and institutions with verified court-area service providers for tasks such as document handling, court support, vendor fulfillment, and order tracking.

This repository contains the full-stack application for the CourtBazaar platform, including a FastAPI backend, a React frontend, and supporting product and engineering documentation.

---

## Project overview

CourtBazaar is designed to make legal and court-related operational work more efficient by combining:

- a user-facing marketplace experience,
- role-based workflows for advocates, vendors, admins, and partners,
- order lifecycle tracking,
- payments and settlement handling,
- admin operations and reporting,
- AI-assisted support for document and filing workflows.

The current focus is the Delhi MVP: a narrow, high-confidence slice of the full platform that can be launched and tested with real users.

---

## Features

- Role-based access for advocates, vendors, admins, and partners
- Court and service selection for legal workflows
- Vendor matching and order management
- Payment and settlement support
- Notifications and admin oversight
- AI assistant and filing support features
- Compliance and audit-oriented capabilities
- Vendor onboarding and KYC workflows

---

## High-level architecture

CourtBazaar follows a simple full-stack architecture:

- Frontend: React application with a component-based UI
- Backend: FastAPI service exposing API routes for business logic
- Database: MongoDB for application data
- Integrations: payments, notifications, storage, and AI services

The frontend talks to the backend through API endpoints, while the backend manages business rules, persistence, and external integrations.

---

## Tech stack

### Frontend
- React
- React Router
- Tailwind CSS
- shadcn-style UI components
- CRACO for CRA-based customization

### Backend
- Python
- FastAPI
- Uvicorn
- Motor / PyMongo for MongoDB access
- JWT-based authentication
- Pydantic models

### Tooling
- npm
- pytest
- Docker (optional for MongoDB)

---

## Folder structure

```text
backend/              # FastAPI backend application
  server.py           # Main app entrypoint
  requirements.txt    # Python dependencies
  tests/              # Backend tests
  *.py                # Domain modules such as notifications, OCR, payments, audits

frontend/             # React frontend application
  src/                # App pages, UI components, API helpers, context, etc.
  package.json        # Frontend dependencies and scripts

memory/               # Product documentation and planning artifacts
  PRD.md              # Product requirements and roadmap

test_reports/         # Historical verification and test artifacts

tests/                # Repo-level test hooks
```

---

## Environment variables

The application expects a set of environment variables for local and deployment use. At minimum, configure:

- MONGO_URL
- DB_NAME
- JWT secret values for auth
- Any payment, notification, storage, or AI credentials required by the enabled modules

For local development, keep these values in the backend environment and avoid committing secrets to the repository.

---

## Local setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- MongoDB running locally or via Docker

### Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Start the backend:

```bash
cd backend
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm start
```

The frontend should be available at:

```text
http://localhost:3000
```

### MongoDB with Docker

If you want a quick local database setup:

```bash
docker run -d --name courtbazaar-mongo -p 27017:27017 mongo:7
```

---

## Running frontend/backend

### Backend

```bash
cd backend
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd frontend
npm start
```

---

## Testing

### Backend tests

```bash
cd backend
pytest
```

### Frontend checks

```bash
cd frontend
npm test -- --watch=false
```

For feature work, also perform a manual smoke test of the main user flow before considering the work complete.

---

## Deployment overview

The current deployment approach is a simple production setup for a Hostinger VPS:

- Backend served with Uvicorn via a process manager such as systemd
- Frontend built and served through Nginx
- MongoDB accessed from the server environment
- Secrets loaded from environment variables

For a full deployment playbook, see [FOUNDING_ENGINEER_PLAYBOOK.md](FOUNDING_ENGINEER_PLAYBOOK.md).

---

## Contribution guide

1. Create a branch from main.
2. Make focused, testable changes.
3. Add or update tests when relevant.
4. Run local checks before opening a PR.
5. Open a PR with a clear summary, testing notes, and any deployment impact.

Keep changes small and aligned with the Delhi MVP scope unless the work is explicitly strategic.

---

## Documentation links

- [FOUNDING_ENGINEER_PLAYBOOK.md](FOUNDING_ENGINEER_PLAYBOOK.md) — engineering operating guide
- [memory/PRD.md](memory/PRD.md) — product requirements and roadmap
- [backend/requirements.txt](backend/requirements.txt) — backend dependencies
- [frontend/package.json](frontend/package.json) — frontend dependencies and scripts

---

## Quick start summary

If you want the shortest path to running the project locally:

```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn server:app --reload --host 0.0.0.0 --port 8000

cd ../frontend
npm install
npm start
```

