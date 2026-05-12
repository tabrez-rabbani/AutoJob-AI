<div align="center">

# AutoJob AI

**AI-Powered Job Application Automation Platform**

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-16-black?logo=next.js)](https://nextjs.org)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-7-DC382D?logo=redis&logoColor=white)](https://redis.io)
[![Playwright](https://img.shields.io/badge/Playwright-1.49+-2EAD33?logo=playwright&logoColor=white)](https://playwright.dev)

AutoJob AI automates the entire job-hunting pipeline — from scraping job listings on LinkedIn to screening them with AI and auto-applying with a tailored resume.

</div>

---

## Features

| Feature | Description |
|---|---|
| **Smart Job Scraping** | Scrapes LinkedIn job listings using Playwright with anti-detection stealth |
| **AI Screening Agent** | Uses LLMs (Groq / Gemini / OpenAI) to score each job against your profile |
| **Resume Tailoring** | Auto-tailors your resume and cover letter for each application |
| **Auto-Apply** | Fills forms and submits applications automatically |
| **Anti-Detection** | Stealth browser fingerprinting, human-like delays, proxy rotation |
| **Encrypted Credentials** | AES-256 encrypted LinkedIn credentials stored in the database |
| **Analytics Dashboard** | Track applications, success rates, and daily activity |
| **Rate Limiting** | Built-in daily limits to avoid platform bans |

---

## Tech Stack

### Backend
- **Framework:** FastAPI (async Python)
- **Database:** PostgreSQL 16 + SQLAlchemy 2.0 (async)
- **Cache / Queue:** Redis 7 + Celery
- **AI:** LangGraph + LangChain (supports Groq, Gemini, OpenAI)
- **Browser Automation:** Playwright (Chromium) with stealth injection
- **Auth:** JWT + bcrypt + Fernet encryption
- **Migrations:** Alembic

### Frontend
- **Framework:** Next.js 16 (App Router)
- **UI:** React 19 + TypeScript
- **Styling:** Tailwind CSS 4
- **Charts:** Recharts
- **Icons:** Lucide React

### Infrastructure
- **Containers:** Docker Compose (PostgreSQL + Redis)
- **Proxy:** Optional rotating proxy support
- **CAPTCHA:** Manual solve / 2Captcha / CapSolver integration

---

## Prerequisites

Make sure you have the following installed before setup:

| Tool | Version | Download |
|---|---|---|
| Python | 3.12 or higher | [python.org](https://python.org/downloads) |
| Node.js | 20 LTS or higher | [nodejs.org](https://nodejs.org) |
| Docker Desktop | Latest | [docker.com](https://docker.com/products/docker-desktop) |
| Git | Latest | [git-scm.com](https://git-scm.com) |

You will also need an LLM API key from one of:
- [Groq](https://console.groq.com) — free tier available, recommended for development
- [Google Gemini](https://aistudio.google.com/apikey)
- [OpenAI](https://platform.openai.com/api-keys)

---

## Setup Guide

### 1. Clone the Repository

```bash
git clone https://github.com/YOUR_USERNAME/autojob-ai.git
cd autojob-ai
```

### 2. Start Database and Redis

```bash
docker compose up -d
```

This starts:
- **PostgreSQL** on `localhost:5432` (user: `autojob`, password: `autojob_dev`, db: `autojob`)
- **Redis** on `localhost:6379`

Verify they are running:
```bash
docker compose ps
```

### 3. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv venv

# Activate it
# Windows:
.\venv\Scripts\activate
# macOS / Linux:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browser (first time only)
playwright install chromium
```

### 4. Configure Environment Variables

```bash
# Copy the example env file
cp .env.example .env       # macOS / Linux
copy .env.example .env     # Windows
```

Open `backend/.env` in a text editor and fill in the required values:

```env
# REQUIRED — Generate a random JWT secret
# Run: python -c "import secrets; print(secrets.token_urlsafe(48))"
JWT_SECRET_KEY=paste_generated_key_here

# REQUIRED — Generate a Fernet encryption key
# Run: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
ENCRYPTION_KEY=paste_generated_key_here

# REQUIRED — Your LLM API key
LLM_PROVIDER=groq
LLM_API_KEY=your_api_key_here
LLM_MODEL=llama-3.3-70b-versatile

# These defaults work for local development — no changes needed
DATABASE_URL=postgresql+asyncpg://autojob:autojob_dev@localhost:5432/autojob
REDIS_URL=redis://localhost:6379/0
APP_ENV=development
DEBUG=true
```

### 5. Run Database Migrations

```bash
cd backend
alembic upgrade head
```

This creates all required tables in the database.

### 6. Start the Backend Server

```bash
cd backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

- API: `http://localhost:8000`
- Swagger Docs: `http://localhost:8000/docs`

### 7. Frontend Setup

Open a new terminal:

```bash
cd frontend

# Copy environment file
cp .env.example .env.local       # macOS / Linux
copy .env.example .env.local     # Windows

# Install dependencies
npm install

# Start development server
npm run dev
```

- Frontend: `http://localhost:3000`

### 8. Verify Everything Works

1. Open `http://localhost:3000` in your browser
2. Create an account (Sign Up)
3. Go to Settings and add your LinkedIn credentials
4. Upload your resume (PDF)
5. Start an automation run

---

## Project Structure

```
autojob-ai/
├── docker-compose.yml          # PostgreSQL + Redis containers
├── README.md
├── LICENSE
│
├── backend/
│   ├── main.py                 # FastAPI app entrypoint
│   ├── requirements.txt        # Python dependencies
│   ├── alembic.ini             # Migration config
│   ├── alembic/                # Database migrations
│   ├── .env.example            # Environment template (copy to .env)
│   │
│   └── app/
│       ├── config.py           # Settings loaded from .env
│       ├── database.py         # Async SQLAlchemy engine
│       ├── models/             # SQLAlchemy ORM models
│       ├── schemas/            # Pydantic request/response schemas
│       ├── api/                # FastAPI route handlers
│       │   ├── auth.py         # Signup, login, profile
│       │   ├── automation.py   # Start/stop automation pipelines
│       │   └── dashboard.py    # Stats, jobs, analytics
│       ├── services/           # Business logic layer
│       ├── agents/             # AI agents (screening, resume tailoring)
│       ├── automation/         # Browser automation engine
│       │   ├── adapters/       # Platform adapters (LinkedIn, etc.)
│       │   ├── browser_manager.py
│       │   ├── stealth.py      # Anti-detection fingerprinting
│       │   ├── captcha_solver.py
│       │   └── proxy_manager.py
│       ├── workers/            # Celery background tasks
│       └── utils/              # Auth, encryption, rate limiting
│
└── frontend/
    ├── package.json
    ├── next.config.ts
    ├── .env.example            # Frontend env template (copy to .env.local)
    └── src/
        ├── app/                # Next.js App Router pages
        │   ├── page.tsx        # Landing page
        │   ├── login/          # Auth pages
        │   └── dashboard/      # Dashboard pages
        ├── components/ui/      # Reusable UI components
        └── lib/                # API client, utilities, transforms
```

---

## Environment Variables Reference

### Required

| Variable | Description |
|---|---|
| `DATABASE_URL` | PostgreSQL connection string |
| `REDIS_URL` | Redis connection string |
| `JWT_SECRET_KEY` | Secret key for JWT token signing (generate a random value) |
| `ENCRYPTION_KEY` | Fernet key for encrypting stored credentials |
| `LLM_PROVIDER` | AI provider: `groq`, `gemini`, or `openai` |
| `LLM_API_KEY` | API key for the chosen LLM provider |

### Optional

| Variable | Default | Description |
|---|---|---|
| `LLM_MODEL` | Provider default | Specific model name to use |
| `APP_ENV` | `development` | `development` or `production` |
| `DEBUG` | `false` | Enable debug logging |
| `PROXY_LIST` | — | Comma-separated proxy URLs for rotation |
| `CAPTCHA_PROVIDER` | — | `2captcha`, `capsolver`, or empty for manual solving |
| `CAPTCHA_API_KEY` | — | API key for the CAPTCHA solving service |
| `GOOGLE_CLIENT_ID` | — | Google OAuth client ID |
| `GOOGLE_CLIENT_SECRET` | — | Google OAuth client secret |
| `FRONTEND_URL` | `http://localhost:3000` | Allowed CORS origin |

> **Important:** Never commit your `.env` file to version control. It is already listed in `.gitignore`. Use `.env.example` as a template.

---

## Development Workflow

### Running All Services

**Terminal 1** — Database:
```bash
docker compose up -d
```

**Terminal 2** — Backend:
```bash
cd backend
.\venv\Scripts\activate          # Windows
source venv/bin/activate         # macOS / Linux
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

**Terminal 3** — Frontend:
```bash
cd frontend
npm run dev
```

### Database Migrations

After modifying any SQLAlchemy model:
```bash
cd backend
alembic revision --autogenerate -m "describe your change"
alembic upgrade head
```

### Adding Dependencies

Backend:
```bash
pip install package-name
pip freeze > requirements.txt
```

Frontend:
```bash
npm install package-name
```

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature-name`
3. Make your changes and commit: `git commit -m "Add: feature description"`
4. Push to your fork: `git push origin feature/your-feature-name`
5. Open a Pull Request against `main`

### Branch Naming

| Type | Format | Example |
|---|---|---|
| Feature | `feature/description` | `feature/glassdoor-adapter` |
| Bug Fix | `bugfix/description` | `bugfix/login-selector-fix` |
| Hotfix | `hotfix/description` | `hotfix/captcha-false-positive` |

### Commit Messages

```
Add: new feature description
Fix: bug description
Update: what was changed
Remove: what was removed
Refactor: what was restructured
```

---

## Troubleshooting

### Docker containers not starting
```bash
docker compose down
docker compose up -d
```

### Database migration errors
```bash
cd backend
alembic downgrade base
alembic upgrade head
```

### Playwright browser not found
```bash
cd backend
.\venv\Scripts\activate
playwright install chromium
```

### Frontend build errors
```bash
cd frontend
rm -rf node_modules .next
npm install
npm run dev
```

### Port already in use
Kill the process using the port:
```bash
# Windows
netstat -ano | findstr :8000
taskkill /PID <PID> /F

# macOS / Linux
lsof -i :8000
kill -9 <PID>
```

---

## License

This project is proprietary software. See [LICENSE](LICENSE) for details.
Unauthorized copying, distribution, or modification is strictly prohibited.

---

<div align="center">

Built by **Tabrez**

</div>
