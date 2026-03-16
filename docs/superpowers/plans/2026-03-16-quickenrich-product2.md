# QuickEnrich Product 2: Company Name + Location to Website Finder

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an email-gated tool where users upload CSVs of company names + locations and receive enriched websites and contacts via a 5-phase pipeline.

**Architecture:** Monorepo with Next.js frontend and Python/FastAPI backend. Single-page flow (upload → config → email → processing → results). Backend processes through Search (Serper) → Verify (LLM) → Normalize → Enrich (QuickEnrich) → Deliver pipeline using ARQ workers. Redis for job queue + caching. Supabase Postgres for persistence.

**Tech Stack:** Next.js 14 (App Router, Tailwind CSS), Python 3.11+ (FastAPI, ARQ, SQLAlchemy async, httpx, tldextract), Supabase Postgres, Redis, Serper API, Gemini/OpenAI, Resend

---

## File Structure

```
QuickEnrich/
├── frontend/
│   ├── package.json
│   ├── next.config.mjs
│   ├── tailwind.config.ts
│   ├── tsconfig.json
│   ├── postcss.config.mjs
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx
│   │   │   ├── globals.css
│   │   │   └── tools/
│   │   │       └── website-finder/
│   │   │           └── page.tsx
│   │   ├── components/
│   │   │   ├── UploadZone.tsx
│   │   │   ├── ColumnMapper.tsx
│   │   │   ├── ConfigPanel.tsx
│   │   │   ├── EmailGate.tsx
│   │   │   ├── ProgressTracker.tsx
│   │   │   ├── LivePreview.tsx
│   │   │   ├── ResultsPanel.tsx
│   │   │   └── ClayPushModal.tsx
│   │   ├── hooks/
│   │   │   └── useSSE.ts
│   │   └── lib/
│   │       ├── api.ts
│   │       └── tool-registry.ts
├── backend/
│   ├── requirements.txt
│   ├── .env.example
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── auth.py
│   │   ├── models.py
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── email_capture.py
│   │   │   ├── upload.py
│   │   │   ├── jobs.py
│   │   │   ├── download.py
│   │   │   ├── clay.py
│   │   │   └── tools.py
│   │   ├── services/
│   │   │   ├── __init__.py
│   │   │   ├── serper.py
│   │   │   ├── normalizer.py
│   │   │   ├── enrichment.py
│   │   │   ├── delivery.py
│   │   │   ├── email_service.py
│   │   │   ├── cache.py
│   │   │   ├── rate_limiter.py
│   │   │   └── llm/
│   │   │       ├── __init__.py
│   │   │       ├── base.py
│   │   │       ├── gemini.py
│   │   │       └── openai_provider.py
│   │   └── workers/
│   │       ├── __init__.py
│   │       └── pipeline.py
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_normalizer.py
│       ├── test_csv_handler.py
│       └── test_pipeline.py
├── database/
│   └── schema.sql
└── .gitignore
```

---

## Parallelization Map

```
Phase 1: Foundation
  Task 1 (git init) ──→ Tasks 2, 3, 4 (parallel)

Phase 2: Backend Core (all parallel, after Phase 1)
  Tasks 5, 6, 7, 8

Phase 3: Pipeline Services (all parallel, after Phase 2)
  Tasks 9, 10, 11, 12

Phase 4: Pipeline Orchestrator (after Phase 3)
  Task 13

Phase 5: Frontend (all parallel, after Phase 1 — can run alongside Phase 2-4)
  Tasks 14, 15, 16, 17

Phase 6: Integration (after Phase 4 + Phase 5)
  Task 18
```

---

## Chunk 1: Foundation (Phase 1)

### Task 1: Initialize monorepo

**Files:**
- Create: `.gitignore`, `backend/requirements.txt`, `backend/.env.example`, `backend/app/__init__.py`

- [ ] **Step 1: Git init and create .gitignore**

```bash
cd C:/Users/Matt/Desktop/QuickEnrich
git init
```

`.gitignore`:
```
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
.venv/
venv/
.env

# Node
node_modules/
.next/
out/

# IDE
.vscode/
.idea/

# OS
.DS_Store
Thumbs.db

# Redis
dump.rdb
```

- [ ] **Step 2: Create backend requirements.txt**

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy[asyncio]==2.0.35
asyncpg==0.29.0
pydantic-settings==2.5.0
python-jose[cryptography]==3.3.0
python-multipart==0.0.12
httpx==0.27.0
tldextract==5.1.2
arq==0.26.1
redis[hiredis]==5.1.0
resend==2.4.0
google-generativeai==0.8.0
openai==1.50.0
boto3==1.35.0
pytest==8.3.0
pytest-asyncio==0.24.0
```

- [ ] **Step 3: Create backend .env.example**

```
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/quickenrich
REDIS_URL=redis://localhost:6379
JWT_SECRET=change-me-in-production
SERPER_API_KEY=
GEMINI_API_KEY=
OPENAI_API_KEY=
RESEND_API_KEY=
QUICKENRICH_API_KEY=
LLM_PROVIDER=gemini
STORAGE_BUCKET=quickenrich-results
FRONTEND_URL=http://localhost:3000
```

- [ ] **Step 4: Create backend/app/__init__.py**

Empty file.

- [ ] **Step 5: Commit**

```bash
git add .gitignore backend/requirements.txt backend/.env.example backend/app/__init__.py
git commit -m "chore: initialize monorepo structure"
```

---

### Task 2: Database schema SQL (parallel with Tasks 3, 4)

**Files:**
- Create: `database/schema.sql`

- [ ] **Step 1: Write schema**

```sql
-- QuickEnrich Database Schema
-- Paste this into the Supabase SQL Editor

-- Email captures (lead magnet)
CREATE TABLE IF NOT EXISTS email_captures (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) NOT NULL,
    ip_address INET,
    tool_slug VARCHAR(50) NOT NULL,
    source VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(email, tool_slug)
);

CREATE INDEX idx_email_captures_email ON email_captures(email);

-- Tools registry
CREATE TABLE IF NOT EXISTS tools (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL DEFAULT true,
    config_schema JSONB
);

-- Seed website-finder tool
INSERT INTO tools (slug, name, description, is_active) VALUES
    ('website-finder', 'Company Website Finder', 'Find company websites from names and locations', true)
ON CONFLICT (slug) DO NOTHING;

-- Jobs
CREATE TABLE IF NOT EXISTS jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email_capture_id UUID NOT NULL REFERENCES email_captures(id),
    tool_slug VARCHAR(50) NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    total_rows INT NOT NULL DEFAULT 0,
    processed_rows INT NOT NULL DEFAULT 0,
    current_phase VARCHAR(30),
    phase_progress JSONB DEFAULT '{}',
    config JSONB DEFAULT '{}',
    input_file_path VARCHAR(500),
    output_file_path VARCHAR(500),
    error_message TEXT,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_jobs_email_capture ON jobs(email_capture_id);
CREATE INDEX idx_jobs_status ON jobs(status);

-- Job results (one per CSV row)
CREATE TABLE IF NOT EXISTS job_results (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    row_index INT NOT NULL,
    input_data JSONB NOT NULL,
    search_results JSONB,
    raw_domain VARCHAR(500),
    verified_domain VARCHAR(500),
    verification_confidence FLOAT,
    normalized_domain VARCHAR(500),
    contacts JSONB,
    status VARCHAR(20) NOT NULL DEFAULT 'pending',
    error_message TEXT
);

CREATE INDEX idx_job_results_job ON job_results(job_id);
CREATE INDEX idx_job_results_status ON job_results(job_id, status);

-- Rate limits
CREATE TABLE IF NOT EXISTS rate_limits (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    identifier VARCHAR(255) NOT NULL,
    identifier_type VARCHAR(10) NOT NULL,
    action VARCHAR(50) NOT NULL,
    window_start TIMESTAMPTZ NOT NULL,
    request_count INT NOT NULL DEFAULT 1
);

CREATE INDEX idx_rate_limits_lookup ON rate_limits(identifier, identifier_type, action, window_start);
```

- [ ] **Step 2: Commit**

```bash
git add database/schema.sql
git commit -m "feat: add database schema for Supabase"
```

---

### Task 3: Backend scaffolding (parallel with Tasks 2, 4)

**Files:**
- Create: `backend/app/config.py`, `backend/app/database.py`, `backend/app/auth.py`, `backend/app/models.py`, `backend/app/main.py`, `backend/app/routers/__init__.py`, `backend/app/services/__init__.py`, `backend/app/services/llm/__init__.py`, `backend/app/workers/__init__.py`, `backend/tests/__init__.py`, `backend/tests/conftest.py`

- [ ] **Step 1: Create config.py**

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://localhost:5432/quickenrich"
    redis_url: str = "redis://localhost:6379"
    jwt_secret: str = "change-me"
    jwt_expiry_hours: int = 24
    serper_api_key: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    resend_api_key: str = ""
    quickenrich_api_key: str = ""
    llm_provider: str = "gemini"
    storage_bucket: str = "quickenrich-results"
    frontend_url: str = "http://localhost:3000"
    max_file_size_mb: int = 50
    max_rows: int = 100_000
    uploads_per_email_per_day: int = 3
    uploads_per_ip_per_day: int = 5
    downloads_per_job: int = 10
    serper_concurrency: int = 20
    llm_concurrency: int = 10
    normalize_concurrency: int = 50
    enrich_concurrency: int = 10
    search_batch_size: int = 100
    llm_batch_size: int = 20
    normalize_batch_size: int = 200
    enrich_batch_size: int = 50
    cache_ttl_days: int = 7

    model_config = {"env_file": ".env", "extra": "ignore"}


settings = Settings()
```

- [ ] **Step 2: Create database.py**

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.database_url, pool_size=20, max_overflow=10)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session
```

- [ ] **Step 3: Create auth.py**

```python
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings

security = HTTPBearer()


def create_token(email: str, job_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expiry_hours)
    payload = {"sub": email, "job_id": job_id, "exp": expire}
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def verify_token(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret, algorithms=["HS256"])
        return payload
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
```

- [ ] **Step 4: Create models.py**

```python
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text, ForeignKey
from sqlalchemy.dialects.postgresql import INET, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class EmailCapture(Base):
    __tablename__ = "email_captures"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), nullable=False)
    ip_address = Column(INET)
    tool_slug = Column(String(50), nullable=False)
    source = Column(String(50))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    jobs = relationship("Job", back_populates="email_capture")


class Tool(Base):
    __tablename__ = "tools"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    config_schema = Column(JSONB)


class Job(Base):
    __tablename__ = "jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email_capture_id = Column(UUID(as_uuid=True), ForeignKey("email_captures.id"), nullable=False)
    tool_slug = Column(String(50), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    total_rows = Column(Integer, default=0)
    processed_rows = Column(Integer, default=0)
    current_phase = Column(String(30))
    phase_progress = Column(JSONB, default=dict)
    config = Column(JSONB, default=dict)
    input_file_path = Column(String(500))
    output_file_path = Column(String(500))
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    email_capture = relationship("EmailCapture", back_populates="jobs")
    results = relationship("JobResult", back_populates="job", cascade="all, delete-orphan")


class JobResult(Base):
    __tablename__ = "job_results"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    job_id = Column(UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False)
    row_index = Column(Integer, nullable=False)
    input_data = Column(JSONB, nullable=False)
    search_results = Column(JSONB)
    raw_domain = Column(String(500))
    verified_domain = Column(String(500))
    verification_confidence = Column(Float)
    normalized_domain = Column(String(500))
    contacts = Column(JSONB)
    status = Column(String(20), nullable=False, default="pending")
    error_message = Column(Text)

    job = relationship("Job", back_populates="results")


class RateLimit(Base):
    __tablename__ = "rate_limits"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    identifier = Column(String(255), nullable=False)
    identifier_type = Column(String(10), nullable=False)
    action = Column(String(50), nullable=False)
    window_start = Column(DateTime(timezone=True), nullable=False)
    request_count = Column(Integer, default=1)
```

- [ ] **Step 5: Create main.py**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import email_capture, upload, jobs, download, clay, tools


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(title="QuickEnrich API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(email_capture.router, prefix="/api/v1")
app.include_router(upload.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(download.router, prefix="/api/v1")
app.include_router(clay.router, prefix="/api/v1")
app.include_router(tools.router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [ ] **Step 6: Create empty __init__.py files**

Create empty `__init__.py` in:
- `backend/app/routers/__init__.py`
- `backend/app/services/__init__.py`
- `backend/app/services/llm/__init__.py`
- `backend/app/workers/__init__.py`
- `backend/tests/__init__.py`

- [ ] **Step 7: Create tests/conftest.py**

```python
import pytest


@pytest.fixture
def sample_csv_rows():
    return [
        {"company_name": "Acme Corp", "location": "Chicago, IL"},
        {"company_name": "Globex Inc", "location": "New York, NY"},
        {"company_name": "Initech", "location": "Austin, TX"},
        {"company_name": "Umbrella Corp", "location": ""},
        {"company_name": "Stark Industries", "location": "Los Angeles, CA"},
    ]


@pytest.fixture
def blocked_domains():
    return [
        "facebook.com", "linkedin.com", "twitter.com", "x.com",
        "instagram.com", "youtube.com", "tiktok.com", "pinterest.com",
        "glassdoor.com", "yelp.com", "bbb.org", "crunchbase.com",
        "zoominfo.com", "yellowpages.com",
    ]
```

- [ ] **Step 8: Commit**

```bash
git add backend/
git commit -m "feat: backend scaffolding - FastAPI, config, models, auth"
```

---

### Task 4: Frontend scaffolding (parallel with Tasks 2, 3)

**Files:**
- Create: `frontend/package.json`, `frontend/next.config.mjs`, `frontend/tailwind.config.ts`, `frontend/tsconfig.json`, `frontend/postcss.config.mjs`, `frontend/src/app/layout.tsx`, `frontend/src/app/page.tsx`, `frontend/src/app/globals.css`, `frontend/src/lib/tool-registry.ts`

- [ ] **Step 1: Create package.json**

```json
{
  "name": "quickenrich-frontend",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint"
  },
  "dependencies": {
    "next": "^14.2.0",
    "react": "^18.3.0",
    "react-dom": "^18.3.0",
    "papaparse": "^5.4.0"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "@types/react": "^18.3.0",
    "@types/react-dom": "^18.3.0",
    "@types/papaparse": "^5.3.0",
    "typescript": "^5.5.0",
    "tailwindcss": "^3.4.0",
    "postcss": "^8.4.0",
    "autoprefixer": "^10.4.0"
  }
}
```

- [ ] **Step 2: Create next.config.mjs**

```javascript
/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
};

export default nextConfig;
```

- [ ] **Step 3: Create tailwind.config.ts**

```typescript
import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: "#2b7ec8",
          hover: "#1e6bb8",
          light: "rgba(43, 126, 200, 0.1)",
        },
        border: "#e5e7eb",
        "text-primary": "#1f2937",
        "text-secondary": "#6b7280",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
```

- [ ] **Step 4: Create tsconfig.json**

```json
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": ["dom", "dom.iterable", "esnext"],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "preserve",
    "incremental": true,
    "plugins": [{ "name": "next" }],
    "paths": { "@/*": ["./src/*"] }
  },
  "include": ["next-env.d.ts", "**/*.ts", "**/*.tsx", ".next/types/**/*.ts"],
  "exclude": ["node_modules"]
}
```

- [ ] **Step 5: Create postcss.config.mjs**

```javascript
const config = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};

export default config;
```

- [ ] **Step 6: Create globals.css**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

:root {
  --primary-color: #2b7ec8;
  --primary-rgb: 43, 126, 200;
  --border-color: #e5e7eb;
  --text-primary: #1f2937;
  --text-secondary: #6b7280;
}

body {
  font-family: 'Inter', system-ui, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  color: var(--text-primary);
}
```

- [ ] **Step 7: Create layout.tsx**

```tsx
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "QuickEnrich Tools",
  description: "Lead enrichment tools by QuickEnrich",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="bg-white min-h-screen">
        <header className="border-b border-border">
          <div className="max-w-6xl mx-auto px-4 py-4 flex items-center justify-between">
            <a href="/" className="text-xl font-semibold text-primary">
              QuickEnrich Tools
            </a>
            <a
              href="https://quickenrich.io"
              className="text-sm text-text-secondary hover:text-primary transition-colors"
            >
              quickenrich.io
            </a>
          </div>
        </header>
        <main>{children}</main>
      </body>
    </html>
  );
}
```

- [ ] **Step 8: Create page.tsx (landing)**

```tsx
import Link from "next/link";
import { tools } from "@/lib/tool-registry";

export default function Home() {
  return (
    <div className="max-w-4xl mx-auto px-4 py-16">
      <h1 className="text-3xl font-bold text-center mb-4">QuickEnrich Tools</h1>
      <p className="text-text-secondary text-center mb-12">
        Free lead enrichment tools. Upload a CSV, get enriched data back.
      </p>
      <div className="grid gap-6 md:grid-cols-2">
        {tools.filter((t) => t.isActive).map((tool) => (
          <Link
            key={tool.slug}
            href={`/tools/${tool.slug}`}
            className="block p-6 border border-border rounded-lg hover:border-primary hover:shadow-md transition-all duration-200 hover:-translate-y-0.5"
          >
            <h2 className="text-lg font-semibold mb-2">{tool.name}</h2>
            <p className="text-text-secondary text-sm">{tool.description}</p>
          </Link>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 9: Create tool-registry.ts**

```typescript
interface ToolConfig {
  slug: string;
  name: string;
  description: string;
  isActive: boolean;
  backendUrl: string;
  requiredColumns: string[];
  optionalColumns: string[];
  columnPatterns: Record<string, RegExp>;
}

export const tools: ToolConfig[] = [
  {
    slug: "website-finder",
    name: "Company Website Finder",
    description:
      "Upload company names and locations to find their websites, verify domains, and enrich with contact data.",
    isActive: true,
    backendUrl: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
    requiredColumns: ["company_name"],
    optionalColumns: ["location"],
    columnPatterns: {
      company_name: /company|name|org|business|brand/i,
      location: /location|city|state|address|geo|region/i,
    },
  },
];

export function getToolBySlug(slug: string): ToolConfig | undefined {
  return tools.find((t) => t.slug === slug);
}
```

- [ ] **Step 10: Run npm install**

```bash
cd frontend && npm install
```

- [ ] **Step 11: Commit**

```bash
git add frontend/
git commit -m "feat: frontend scaffolding - Next.js, Tailwind, design system"
```

---

## Chunk 2: Backend Core Services (Phase 2)

### Task 5: Email capture + JWT auth route (parallel with Tasks 6, 7, 8)

**Files:**
- Create: `backend/app/routers/email_capture.py`

- [ ] **Step 1: Create email_capture.py router**

```python
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.auth import create_token
from app.database import get_db
from app.models import EmailCapture
from app.services.rate_limiter import check_rate_limit

router = APIRouter()


class EmailCaptureRequest(BaseModel):
    email: EmailStr
    tool_slug: str
    source: str | None = None


class EmailCaptureResponse(BaseModel):
    email_capture_id: str
    message: str


@router.post("/email-capture", response_model=EmailCaptureResponse)
async def capture_email(
    body: EmailCaptureRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    client_ip = request.client.host if request.client else "unknown"

    await check_rate_limit(db, client_ip, "ip", "upload")
    await check_rate_limit(db, body.email, "email", "upload")

    stmt = (
        pg_insert(EmailCapture)
        .values(
            email=body.email,
            ip_address=client_ip,
            tool_slug=body.tool_slug,
            source=body.source,
        )
        .on_conflict_do_update(
            index_elements=["email", "tool_slug"],
            set_={"source": body.source, "ip_address": client_ip},
        )
        .returning(EmailCapture.id)
    )

    result = await db.execute(stmt)
    await db.commit()
    capture_id = result.scalar_one()

    return EmailCaptureResponse(
        email_capture_id=str(capture_id),
        message="Email captured successfully",
    )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/routers/email_capture.py
git commit -m "feat: email capture endpoint with rate limiting"
```

---

### Task 6: CSV upload + parsing (parallel with Tasks 5, 7, 8)

**Files:**
- Create: `backend/app/routers/upload.py`, `backend/tests/test_csv_handler.py`

- [ ] **Step 1: Create upload.py router**

```python
import csv
import hashlib
import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import create_token, verify_token
from app.config import settings
from app.database import get_db
from app.models import Job, JobResult

router = APIRouter()


def parse_csv_streaming(file_content: bytes, company_col: str, location_col: str | None):
    """Parse CSV and yield rows with company_name and location."""
    text = file_content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))

    for idx, row in enumerate(reader):
        if idx >= settings.max_rows:
            break

        company_name = row.get(company_col, "").strip()
        if not company_name:
            continue

        location = ""
        if location_col and location_col in row:
            location = row.get(location_col, "").strip()

        yield {
            "row_index": idx,
            "company_name": company_name,
            "location": location,
        }


@router.post("/upload")
async def upload_csv(
    file: UploadFile = File(...),
    company_column: str = Form(...),
    location_column: str = Form(default=""),
    email_capture_id: str = Form(...),
    enrich_contacts: bool = Form(default=False),
    job_titles: str = Form(default=""),
    max_contacts: int = Form(default=1),
    token_data: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename or not file.filename.endswith(".csv"):
        raise HTTPException(400, "File must be a CSV")

    content = await file.read()
    if len(content) > settings.max_file_size_mb * 1024 * 1024:
        raise HTTPException(400, f"File exceeds {settings.max_file_size_mb}MB limit")

    config = {
        "company_column": company_column,
        "location_column": location_column,
        "enrich_contacts": enrich_contacts,
        "job_titles": [t.strip() for t in job_titles.split(",") if t.strip()] if job_titles else [],
        "max_contacts": min(max_contacts, 5),
    }

    job = Job(
        email_capture_id=uuid.UUID(email_capture_id),
        tool_slug="website-finder",
        status="pending",
        config=config,
        created_at=datetime.now(timezone.utc),
    )
    db.add(job)
    await db.flush()

    loc_col = location_column if location_column else None
    rows = list(parse_csv_streaming(content, company_column, loc_col))

    if not rows:
        raise HTTPException(400, "No valid rows found in CSV")

    job.total_rows = len(rows)

    batch = []
    for row_data in rows:
        result = JobResult(
            job_id=job.id,
            row_index=row_data["row_index"],
            input_data={"company_name": row_data["company_name"], "location": row_data["location"]},
            status="pending",
        )
        batch.append(result)

    db.add_all(batch)
    await db.commit()

    token = create_token(token_data["sub"], str(job.id))

    return {
        "job_id": str(job.id),
        "total_rows": len(rows),
        "token": token,
    }
```

- [ ] **Step 2: Write CSV parsing test**

```python
# backend/tests/test_csv_handler.py
from app.routers.upload import parse_csv_streaming


def test_parse_csv_basic():
    content = b"company_name,location\nAcme Corp,Chicago\nGlobex,New York\n"
    rows = list(parse_csv_streaming(content, "company_name", "location"))
    assert len(rows) == 2
    assert rows[0]["company_name"] == "Acme Corp"
    assert rows[0]["location"] == "Chicago"


def test_parse_csv_missing_location():
    content = b"company_name,location\nAcme Corp,\nGlobex,New York\n"
    rows = list(parse_csv_streaming(content, "company_name", "location"))
    assert len(rows) == 2
    assert rows[0]["location"] == ""


def test_parse_csv_no_location_column():
    content = b"company_name\nAcme Corp\nGlobex\n"
    rows = list(parse_csv_streaming(content, "company_name", None))
    assert len(rows) == 2
    assert rows[0]["location"] == ""


def test_parse_csv_skips_empty_company():
    content = b"company_name,location\n,Chicago\nGlobex,New York\n"
    rows = list(parse_csv_streaming(content, "company_name", "location"))
    assert len(rows) == 1
    assert rows[0]["company_name"] == "Globex"


def test_parse_csv_bom():
    content = b"\xef\xbb\xbfcompany_name,location\nAcme,Chicago\n"
    rows = list(parse_csv_streaming(content, "company_name", "location"))
    assert len(rows) == 1
    assert rows[0]["company_name"] == "Acme"
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/upload.py backend/tests/test_csv_handler.py
git commit -m "feat: CSV upload endpoint with streaming parser"
```

---

### Task 7: Job management + SSE + download routes (parallel with Tasks 5, 6, 8)

**Files:**
- Create: `backend/app/routers/jobs.py`, `backend/app/routers/download.py`

- [ ] **Step 1: Create jobs.py router**

```python
import asyncio
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_token
from app.database import get_db
from app.models import Job, JobResult

router = APIRouter()


class JobStatusResponse(BaseModel):
    id: str
    status: str
    total_rows: int
    processed_rows: int
    current_phase: str | None
    phase_progress: dict
    config: dict
    error_message: str | None
    started_at: str | None
    completed_at: str | None
    created_at: str


@router.get("/jobs/{job_id}")
async def get_job(
    job_id: str,
    token_data: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(404, "Job not found")

    return {
        "id": str(job.id),
        "status": job.status,
        "total_rows": job.total_rows,
        "processed_rows": job.processed_rows,
        "current_phase": job.current_phase,
        "phase_progress": job.phase_progress or {},
        "config": job.config or {},
        "error_message": job.error_message,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "created_at": job.created_at.isoformat(),
    }


@router.get("/jobs/{job_id}/sse")
async def job_sse(
    job_id: str,
    token_data: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    async def event_stream():
        while True:
            async with get_db().__aclass__() as session:
                result = await session.execute(select(Job).where(Job.id == job_id))
                job = result.scalar_one_or_none()

                if not job:
                    yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                    return

                data = {
                    "status": job.status,
                    "processed_rows": job.processed_rows,
                    "total_rows": job.total_rows,
                    "current_phase": job.current_phase,
                    "phase_progress": job.phase_progress or {},
                }

                yield f"data: {json.dumps(data)}\n\n"

                if job.status in ("completed", "failed"):
                    return

            await asyncio.sleep(2)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/jobs/{job_id}/preview")
async def job_preview(
    job_id: str,
    limit: int = Query(default=50, le=100),
    offset: int = Query(default=0),
    token_data: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(JobResult)
        .where(JobResult.job_id == job_id)
        .where(JobResult.status != "pending")
        .order_by(JobResult.row_index.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = result.scalars().all()

    return {
        "rows": [
            {
                "row_index": r.row_index,
                "company_name": r.input_data.get("company_name", ""),
                "location": r.input_data.get("location", ""),
                "domain": r.normalized_domain or r.verified_domain or r.raw_domain,
                "confidence": r.verification_confidence,
                "status": r.status,
                "contacts": r.contacts,
            }
            for r in rows
        ],
    }
```

- [ ] **Step 2: Create download.py router**

```python
import csv
import io
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_token
from app.database import get_db
from app.models import Job, JobResult

router = APIRouter()


@router.get("/download/{job_id}")
async def download_results(
    job_id: str,
    token_data: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(404, "Job not found")
    if job.status != "completed":
        raise HTTPException(400, "Job is not completed yet")

    config = job.config or {}
    job_titles = config.get("job_titles", [])

    async def generate_csv():
        output = io.StringIO()
        output.write("\ufeff")  # UTF-8 BOM for Excel

        headers = ["company_name", "location", "website", "verification_confidence", "status"]
        for title in job_titles:
            headers.extend([
                f"{title} - First Name",
                f"{title} - Last Name",
                f"{title} - Email",
                f"{title} - Phone",
                f"{title} - LinkedIn",
            ])

        writer = csv.DictWriter(output, fieldnames=headers)
        writer.writeheader()
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        batch_size = 500
        offset = 0

        while True:
            rows_result = await db.execute(
                select(JobResult)
                .where(JobResult.job_id == job_id)
                .order_by(JobResult.row_index)
                .offset(offset)
                .limit(batch_size)
            )
            rows = rows_result.scalars().all()
            if not rows:
                break

            for row in rows:
                row_data = {
                    "company_name": row.input_data.get("company_name", ""),
                    "location": row.input_data.get("location", ""),
                    "website": row.normalized_domain or "",
                    "verification_confidence": row.verification_confidence or "",
                    "status": row.status,
                }

                contacts = row.contacts or []
                for title in job_titles:
                    contact = next(
                        (c for c in contacts if c.get("title", "").lower() == title.lower()),
                        {},
                    )
                    row_data[f"{title} - First Name"] = contact.get("first_name", "")
                    row_data[f"{title} - Last Name"] = contact.get("last_name", "")
                    row_data[f"{title} - Email"] = contact.get("email", "")
                    row_data[f"{title} - Phone"] = contact.get("phone", "")
                    row_data[f"{title} - LinkedIn"] = contact.get("linkedin_url", "")

                writer.writerow(row_data)
                yield output.getvalue()
                output.seek(0)
                output.truncate(0)

            offset += batch_size

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"website_finder_results_{timestamp}.csv"

    return StreamingResponse(
        generate_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/jobs.py backend/app/routers/download.py
git commit -m "feat: job status, SSE progress, preview, and download routes"
```

---

### Task 8: Rate limiter + cache + tools route (parallel with Tasks 5, 6, 7)

**Files:**
- Create: `backend/app/services/rate_limiter.py`, `backend/app/services/cache.py`, `backend/app/routers/tools.py`, `backend/app/routers/clay.py`

- [ ] **Step 1: Create rate_limiter.py**

```python
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select, and_, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import RateLimit


LIMITS = {
    ("email", "upload"): settings.uploads_per_email_per_day,
    ("ip", "upload"): settings.uploads_per_ip_per_day,
}


async def check_rate_limit(
    db: AsyncSession,
    identifier: str,
    identifier_type: str,
    action: str,
):
    limit = LIMITS.get((identifier_type, action))
    if not limit:
        return

    window_start = datetime.now(timezone.utc) - timedelta(hours=24)

    result = await db.execute(
        select(RateLimit).where(
            and_(
                RateLimit.identifier == identifier,
                RateLimit.identifier_type == identifier_type,
                RateLimit.action == action,
                RateLimit.window_start >= window_start,
            )
        )
    )
    record = result.scalar_one_or_none()

    if record and record.request_count >= limit:
        raise HTTPException(
            429,
            f"Rate limit exceeded: max {limit} {action}s per 24h for this {identifier_type}",
        )

    if record:
        record.request_count += 1
        await db.flush()
    else:
        new_record = RateLimit(
            identifier=identifier,
            identifier_type=identifier_type,
            action=action,
            window_start=datetime.now(timezone.utc),
            request_count=1,
        )
        db.add(new_record)
        await db.flush()
```

- [ ] **Step 2: Create cache.py**

```python
import hashlib
import json

import redis.asyncio as redis

from app.config import settings

_redis: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(settings.redis_url, decode_responses=True)
    return _redis


def make_cache_key(prefix: str, *args: str) -> str:
    raw = "|".join(args)
    hashed = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"{prefix}:{hashed}"


async def cache_get(key: str) -> dict | None:
    r = await get_redis()
    data = await r.get(key)
    if data:
        return json.loads(data)
    return None


async def cache_set(key: str, value: dict, ttl_days: int | None = None):
    r = await get_redis()
    ttl = (ttl_days or settings.cache_ttl_days) * 86400
    await r.set(key, json.dumps(value), ex=ttl)
```

- [ ] **Step 3: Create tools.py router**

```python
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Tool

router = APIRouter()


@router.get("/tools")
async def list_tools(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Tool).where(Tool.is_active == True))
    tools = result.scalars().all()

    return {
        "tools": [
            {
                "slug": t.slug,
                "name": t.name,
                "description": t.description,
            }
            for t in tools
        ]
    }
```

- [ ] **Step 4: Create clay.py router**

```python
import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import verify_token
from app.database import get_db
from app.models import Job, JobResult

router = APIRouter()


class ClayPushRequest(BaseModel):
    clay_api_key: str
    table_id: str


@router.post("/clay-push/{job_id}")
async def push_to_clay(
    job_id: str,
    body: ClayPushRequest,
    token_data: dict = Depends(verify_token),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Job).where(Job.id == job_id))
    job = result.scalar_one_or_none()

    if not job:
        raise HTTPException(404, "Job not found")
    if job.status != "completed":
        raise HTTPException(400, "Job not completed")

    rows_result = await db.execute(
        select(JobResult)
        .where(JobResult.job_id == job_id)
        .where(JobResult.normalized_domain.isnot(None))
        .order_by(JobResult.row_index)
    )
    rows = rows_result.scalars().all()

    pushed = 0
    failed = 0
    batch_size = 100

    async with httpx.AsyncClient() as client:
        for i in range(0, len(rows), batch_size):
            batch = rows[i : i + batch_size]
            records = []
            for row in batch:
                record = {
                    "company_name": row.input_data.get("company_name", ""),
                    "location": row.input_data.get("location", ""),
                    "website": row.normalized_domain,
                    "confidence": row.verification_confidence,
                }
                contacts = row.contacts or []
                for contact in contacts:
                    title = contact.get("title", "Unknown")
                    record[f"{title} Email"] = contact.get("email", "")
                    record[f"{title} Name"] = f"{contact.get('first_name', '')} {contact.get('last_name', '')}".strip()
                records.append(record)

            try:
                resp = await client.post(
                    f"https://api.clay.com/v1/tables/{body.table_id}/rows",
                    headers={"Authorization": f"Bearer {body.clay_api_key}"},
                    json={"rows": records},
                    timeout=30,
                )
                resp.raise_for_status()
                pushed += len(batch)
            except httpx.HTTPError:
                failed += len(batch)

    return {"pushed": pushed, "failed": failed, "total": len(rows)}
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/rate_limiter.py backend/app/services/cache.py backend/app/routers/tools.py backend/app/routers/clay.py
git commit -m "feat: rate limiter, Redis cache, tools listing, Clay push"
```

---

## Chunk 3: Pipeline Services (Phase 3)

### Task 9: Serper search service (parallel with Tasks 10, 11, 12)

**Files:**
- Create: `backend/app/services/serper.py`

- [ ] **Step 1: Create serper.py**

```python
import asyncio

import httpx

from app.config import settings
from app.services.cache import cache_get, cache_set, make_cache_key

SERPER_URL = "https://google.serper.dev/search"


async def search_company(
    client: httpx.AsyncClient,
    company_name: str,
    location: str = "",
) -> dict:
    """Search for a company's website using Serper API. Returns top 3 results."""
    cache_key = make_cache_key("serper", company_name.lower(), location.lower())
    cached = await cache_get(cache_key)
    if cached:
        return cached

    query = f'"{company_name}"'
    if location:
        query += f" {location}"
    query += " official website"

    resp = await client.post(
        SERPER_URL,
        headers={"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"},
        json={"q": query, "num": 3},
        timeout=15,
    )
    resp.raise_for_status()
    data = resp.json()

    organic = data.get("organic", [])[:3]
    result = {
        "query": query,
        "results": [
            {
                "title": r.get("title", ""),
                "link": r.get("link", ""),
                "snippet": r.get("snippet", ""),
                "domain": r.get("link", "").split("/")[2] if "/" in r.get("link", "") else "",
            }
            for r in organic
        ],
        "candidate_domain": organic[0].get("link", "").split("/")[2] if organic else None,
    }

    await cache_set(cache_key, result)
    return result


async def batch_search(
    rows: list[dict],
    concurrency: int | None = None,
) -> list[dict]:
    """Search for multiple companies with concurrency control."""
    sem = asyncio.Semaphore(concurrency or settings.serper_concurrency)
    results = []

    # Deduplicate by company_name + location
    seen: dict[str, dict] = {}
    dedup_map: dict[str, list[int]] = {}

    for row in rows:
        key = f"{row['company_name'].lower()}|{row.get('location', '').lower()}"
        if key not in seen:
            seen[key] = row
            dedup_map[key] = []
        dedup_map[key].append(row["row_index"])

    async with httpx.AsyncClient() as client:
        async def search_one(key: str, row: dict) -> tuple[str, dict]:
            async with sem:
                result = await search_company(
                    client,
                    row["company_name"],
                    row.get("location", ""),
                )
                return key, result

        tasks = [search_one(k, v) for k, v in seen.items()]
        completed = await asyncio.gather(*tasks, return_exceptions=True)

    # Map results back to all rows
    result_map: dict[str, dict] = {}
    for item in completed:
        if isinstance(item, Exception):
            continue
        key, result = item
        result_map[key] = result

    for row in rows:
        key = f"{row['company_name'].lower()}|{row.get('location', '').lower()}"
        search_result = result_map.get(key, {"results": [], "candidate_domain": None})
        results.append({
            "row_index": row["row_index"],
            "search_results": search_result["results"],
            "candidate_domain": search_result.get("candidate_domain"),
        })

    return results
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/serper.py
git commit -m "feat: Serper search service with dedup and caching"
```

---

### Task 10: LLM provider abstraction + verification (parallel with Tasks 9, 11, 12)

**Files:**
- Create: `backend/app/services/llm/base.py`, `backend/app/services/llm/gemini.py`, `backend/app/services/llm/openai_provider.py`, `backend/app/services/llm/__init__.py`

- [ ] **Step 1: Create base.py**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class VerificationResult:
    row_index: int
    match: bool
    confidence: float
    reason: str
    suggested_domain: str | None


class BaseLLMProvider(ABC):
    @abstractmethod
    async def verify_domains(self, batch: list[dict]) -> list[VerificationResult]:
        """
        Verify a batch of company-domain pairs.
        Each item in batch: {row_index, company_name, location, candidate_domain, search_snippet}
        Returns list of VerificationResult.
        """
        ...

    @property
    @abstractmethod
    def max_batch_size(self) -> int:
        ...
```

- [ ] **Step 2: Create gemini.py**

```python
import json

import google.generativeai as genai

from app.config import settings
from app.services.llm.base import BaseLLMProvider, VerificationResult

VERIFY_PROMPT = """You are a domain verification assistant. For each company below, determine if the candidate domain is the company's official website.

Consider:
- Does the domain name match the company name?
- Does the search snippet mention the company?
- Is the domain a social media site or directory (these should NOT match)?
- Does the location context help confirm this is the right company (not a same-named company elsewhere)?

Return a JSON array with one object per company:
{
  "row_index": <int>,
  "match": <bool>,
  "confidence": <float 0-1>,
  "reason": "<brief explanation>",
  "suggested_domain": "<string or null>"
}

Companies to verify:
"""


class GeminiProvider(BaseLLMProvider):
    def __init__(self):
        genai.configure(api_key=settings.gemini_api_key)
        self.model = genai.GenerativeModel("gemini-1.5-flash")

    @property
    def max_batch_size(self) -> int:
        return 20

    async def verify_domains(self, batch: list[dict]) -> list[VerificationResult]:
        items_text = json.dumps(
            [
                {
                    "row_index": item["row_index"],
                    "company_name": item["company_name"],
                    "location": item.get("location", ""),
                    "candidate_domain": item.get("candidate_domain", ""),
                    "search_snippet": item.get("search_snippet", ""),
                }
                for item in batch
            ],
            indent=2,
        )

        prompt = VERIFY_PROMPT + items_text

        response = await self.model.generate_content_async(
            prompt,
            generation_config=genai.GenerationConfig(
                response_mime_type="application/json",
                temperature=0.1,
            ),
        )

        try:
            results_data = json.loads(response.text)
        except json.JSONDecodeError:
            # Fallback: mark all as low confidence
            return [
                VerificationResult(
                    row_index=item["row_index"],
                    match=False,
                    confidence=0.0,
                    reason="LLM response parsing failed",
                    suggested_domain=None,
                )
                for item in batch
            ]

        results = []
        for item in results_data:
            results.append(
                VerificationResult(
                    row_index=item["row_index"],
                    match=item.get("match", False),
                    confidence=item.get("confidence", 0.0),
                    reason=item.get("reason", ""),
                    suggested_domain=item.get("suggested_domain"),
                )
            )
        return results
```

- [ ] **Step 3: Create openai_provider.py**

```python
import json

from openai import AsyncOpenAI

from app.config import settings
from app.services.llm.base import BaseLLMProvider, VerificationResult

VERIFY_PROMPT = """You are a domain verification assistant. For each company below, determine if the candidate domain is the company's official website.

Consider:
- Does the domain name match the company name?
- Does the search snippet mention the company?
- Is the domain a social media site or directory (these should NOT match)?
- Does the location context help confirm this is the right company (not a same-named company elsewhere)?

Return a JSON array with one object per company:
{
  "row_index": <int>,
  "match": <bool>,
  "confidence": <float 0-1>,
  "reason": "<brief explanation>",
  "suggested_domain": "<string or null>"
}
"""


class OpenAIProvider(BaseLLMProvider):
    def __init__(self):
        self.client = AsyncOpenAI(api_key=settings.openai_api_key)

    @property
    def max_batch_size(self) -> int:
        return 20

    async def verify_domains(self, batch: list[dict]) -> list[VerificationResult]:
        items_text = json.dumps(
            [
                {
                    "row_index": item["row_index"],
                    "company_name": item["company_name"],
                    "location": item.get("location", ""),
                    "candidate_domain": item.get("candidate_domain", ""),
                    "search_snippet": item.get("search_snippet", ""),
                }
                for item in batch
            ],
            indent=2,
        )

        response = await self.client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": VERIFY_PROMPT},
                {"role": "user", "content": f"Companies to verify:\n{items_text}"},
            ],
            response_format={"type": "json_object"},
            temperature=0.1,
        )

        try:
            content = response.choices[0].message.content or "[]"
            parsed = json.loads(content)
            results_data = parsed if isinstance(parsed, list) else parsed.get("results", [])
        except (json.JSONDecodeError, IndexError):
            return [
                VerificationResult(
                    row_index=item["row_index"],
                    match=False,
                    confidence=0.0,
                    reason="LLM response parsing failed",
                    suggested_domain=None,
                )
                for item in batch
            ]

        results = []
        for item in results_data:
            results.append(
                VerificationResult(
                    row_index=item["row_index"],
                    match=item.get("match", False),
                    confidence=item.get("confidence", 0.0),
                    reason=item.get("reason", ""),
                    suggested_domain=item.get("suggested_domain"),
                )
            )
        return results
```

- [ ] **Step 4: Create llm/__init__.py**

```python
from app.config import settings
from app.services.llm.base import BaseLLMProvider


def get_llm_provider() -> BaseLLMProvider:
    if settings.llm_provider == "openai":
        from app.services.llm.openai_provider import OpenAIProvider
        return OpenAIProvider()
    else:
        from app.services.llm.gemini import GeminiProvider
        return GeminiProvider()
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/llm/
git commit -m "feat: LLM provider abstraction with Gemini and OpenAI"
```

---

### Task 11: Domain normalizer (parallel with Tasks 9, 10, 12)

**Files:**
- Create: `backend/app/services/normalizer.py`, `backend/tests/test_normalizer.py`

- [ ] **Step 1: Write normalizer tests**

```python
# backend/tests/test_normalizer.py
import pytest
from app.services.normalizer import normalize_domain, is_blocked_domain, clean_url


def test_clean_url_strips_protocol():
    assert clean_url("https://www.example.com/about") == "example.com"
    assert clean_url("http://example.com/") == "example.com"


def test_clean_url_strips_www():
    assert clean_url("www.example.com") == "example.com"


def test_clean_url_strips_path():
    assert clean_url("example.com/about/us") == "example.com"


def test_clean_url_handles_subdomains():
    assert clean_url("blog.example.com") == "example.com"


def test_clean_url_preserves_co_uk():
    assert clean_url("https://www.example.co.uk/page") == "example.co.uk"


def test_is_blocked_domain():
    assert is_blocked_domain("facebook.com") is True
    assert is_blocked_domain("linkedin.com") is True
    assert is_blocked_domain("yelp.com") is True
    assert is_blocked_domain("acme.com") is False


def test_normalize_domain_basic():
    result = normalize_domain("https://www.acme.com/about")
    assert result["domain"] == "acme.com"
    assert result["blocked"] is False


def test_normalize_domain_blocked():
    result = normalize_domain("https://www.linkedin.com/company/acme")
    assert result["blocked"] is True
    assert result["domain"] is None


def test_normalize_domain_empty():
    result = normalize_domain("")
    assert result["domain"] is None


def test_normalize_domain_invalid_tld():
    result = normalize_domain("example.invalidtld12345")
    assert result["domain"] is None
```

- [ ] **Step 2: Create normalizer.py**

```python
import asyncio
from urllib.parse import urlparse

import httpx
import tldextract

BLOCKED_DOMAINS = frozenset({
    "facebook.com", "linkedin.com", "twitter.com", "x.com",
    "instagram.com", "youtube.com", "tiktok.com", "pinterest.com",
    "glassdoor.com", "yelp.com", "bbb.org", "crunchbase.com",
    "zoominfo.com", "yellowpages.com", "indeed.com", "reddit.com",
    "wikipedia.org", "bloomberg.com", "dnb.com",
})


def clean_url(url: str) -> str | None:
    """Extract root domain from a URL string."""
    url = url.strip().lower()
    if not url:
        return None

    # Remove protocol
    for prefix in ("https://", "http://"):
        if url.startswith(prefix):
            url = url[len(prefix):]

    # Remove www.
    if url.startswith("www."):
        url = url[4:]

    # Remove path and query
    url = url.split("/")[0].split("?")[0].split("#")[0]

    # Extract root domain with tldextract
    extracted = tldextract.extract(url)
    if not extracted.domain or not extracted.suffix:
        return None

    return f"{extracted.domain}.{extracted.suffix}"


def is_blocked_domain(domain: str) -> bool:
    return domain.lower() in BLOCKED_DOMAINS


def normalize_domain(raw_url: str) -> dict:
    """Normalize a URL to its root domain. Returns dict with domain, blocked, error."""
    if not raw_url:
        return {"domain": None, "blocked": False, "error": "empty input"}

    domain = clean_url(raw_url)

    if not domain:
        return {"domain": None, "blocked": False, "error": "invalid URL"}

    # Validate TLD
    extracted = tldextract.extract(domain)
    if not extracted.suffix:
        return {"domain": None, "blocked": False, "error": "invalid TLD"}

    if is_blocked_domain(domain):
        return {"domain": None, "blocked": True, "error": f"blocked domain: {domain}"}

    return {"domain": domain, "blocked": False, "error": None}


async def resolve_redirect(client: httpx.AsyncClient, domain: str) -> str:
    """Follow redirects to find final domain. Returns resolved domain or original."""
    try:
        resp = await client.head(
            f"https://{domain}",
            follow_redirects=True,
            timeout=5,
        )
        final_url = str(resp.url)
        resolved = clean_url(final_url)
        return resolved or domain
    except (httpx.HTTPError, httpx.TimeoutException):
        return domain


async def batch_normalize(
    rows: list[dict],
    resolve_redirects: bool = True,
    concurrency: int = 50,
) -> list[dict]:
    """Normalize and deduplicate domains for a batch of rows."""
    sem = asyncio.Semaphore(concurrency)
    results = []
    seen_domains: dict[str, str] = {}

    async with httpx.AsyncClient() as client:
        async def process_one(row: dict) -> dict:
            domain_input = row.get("verified_domain") or row.get("raw_domain") or ""
            normalized = normalize_domain(domain_input)

            if normalized["domain"] and resolve_redirects:
                domain = normalized["domain"]
                if domain in seen_domains:
                    normalized["domain"] = seen_domains[domain]
                else:
                    async with sem:
                        resolved = await resolve_redirect(client, domain)
                    if is_blocked_domain(resolved):
                        normalized = {"domain": None, "blocked": True, "error": f"redirected to blocked: {resolved}"}
                    else:
                        normalized["domain"] = resolved
                        seen_domains[domain] = resolved

            return {
                "row_index": row["row_index"],
                **normalized,
            }

        tasks = [process_one(row) for row in rows]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    return [r if not isinstance(r, Exception) else {"row_index": -1, "domain": None, "error": str(r)} for r in results]
```

- [ ] **Step 3: Run tests**

```bash
cd backend && python -m pytest tests/test_normalizer.py -v
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/normalizer.py backend/tests/test_normalizer.py
git commit -m "feat: domain normalizer with blocked list and redirect resolution"
```

---

### Task 12: Enrichment + delivery services (parallel with Tasks 9, 10, 11)

**Files:**
- Create: `backend/app/services/enrichment.py`, `backend/app/services/email_service.py`, `backend/app/services/delivery.py`

- [ ] **Step 1: Create enrichment.py**

```python
import asyncio

import httpx

from app.config import settings


async def enrich_company(
    client: httpx.AsyncClient,
    domain: str,
    job_titles: list[str],
    max_contacts: int = 1,
) -> list[dict]:
    """Call QuickEnrich API to find contacts for a company domain."""
    contacts = []

    for title in job_titles:
        try:
            resp = await client.get(
                "https://app.quickenrich.io/api/employees/dataset-search",
                params={"company_url": domain, "title": title},
                headers={"Authorization": f"Bearer {settings.quickenrich_api_key}"},
                timeout=15,
            )
            resp.raise_for_status()
            data = resp.json()

            results = data if isinstance(data, list) else data.get("results", [])
            for person in results[:max_contacts]:
                contacts.append({
                    "title": title,
                    "first_name": person.get("first_name", ""),
                    "last_name": person.get("last_name", ""),
                    "email": person.get("email", ""),
                    "phone": person.get("phone", ""),
                    "linkedin_url": person.get("linkedin_url", ""),
                })
        except (httpx.HTTPError, httpx.TimeoutException):
            continue

    return contacts


async def batch_enrich(
    domains_with_rows: dict[str, list[int]],
    job_titles: list[str],
    max_contacts: int = 1,
    concurrency: int | None = None,
) -> dict[str, list[dict]]:
    """Enrich multiple domains with contact data. Returns {domain: [contacts]}."""
    sem = asyncio.Semaphore(concurrency or settings.enrich_concurrency)
    results: dict[str, list[dict]] = {}

    async with httpx.AsyncClient() as client:
        async def enrich_one(domain: str):
            async with sem:
                contacts = await enrich_company(client, domain, job_titles, max_contacts)
                results[domain] = contacts

        tasks = [enrich_one(d) for d in domains_with_rows.keys()]
        await asyncio.gather(*tasks, return_exceptions=True)

    return results
```

- [ ] **Step 2: Create email_service.py**

```python
import resend

from app.config import settings


def send_results_email(to_email: str, download_url: str, job_stats: dict):
    """Send results email via Resend."""
    resend.api_key = settings.resend_api_key

    total = job_stats.get("total_rows", 0)
    found = job_stats.get("found", 0)
    match_rate = round((found / total * 100) if total > 0 else 0, 1)

    html = f"""
    <div style="font-family: Inter, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #2b7ec8;">Your QuickEnrich Results Are Ready!</h2>
        <p>Your company website finder job has completed processing.</p>

        <div style="background: #f9fafb; border-radius: 8px; padding: 16px; margin: 20px 0;">
            <p><strong>Total Rows:</strong> {total}</p>
            <p><strong>Websites Found:</strong> {found}</p>
            <p><strong>Match Rate:</strong> {match_rate}%</p>
        </div>

        <a href="{download_url}"
           style="display: inline-block; background: #2b7ec8; color: white; padding: 12px 24px; border-radius: 6px; text-decoration: none; font-weight: 600;">
            Download Results CSV
        </a>

        <p style="margin-top: 30px; color: #6b7280; font-size: 14px;">
            This link expires in 7 days. Need more enrichment?
            <a href="https://quickenrich.io" style="color: #2b7ec8;">Visit QuickEnrich</a>
        </p>
    </div>
    """

    resend.Emails.send({
        "from": "QuickEnrich Tools <tools@quickenrich.io>",
        "to": to_email,
        "subject": f"Your QuickEnrich Results — {found}/{total} websites found",
        "html": html,
    })
```

- [ ] **Step 3: Create delivery.py**

```python
import csv
import io
from datetime import datetime, timezone


def generate_output_csv(rows: list[dict], job_titles: list[str]) -> bytes:
    """Generate output CSV bytes with BOM for Excel compatibility."""
    output = io.StringIO()
    output.write("\ufeff")  # UTF-8 BOM

    headers = ["company_name", "location", "website", "verification_confidence", "status"]
    for title in job_titles:
        headers.extend([
            f"{title} - First Name",
            f"{title} - Last Name",
            f"{title} - Email",
            f"{title} - Phone",
            f"{title} - LinkedIn",
        ])

    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()

    for row in rows:
        row_data = {
            "company_name": row.get("company_name", ""),
            "location": row.get("location", ""),
            "website": row.get("normalized_domain", ""),
            "verification_confidence": row.get("verification_confidence", ""),
            "status": row.get("status", ""),
        }

        contacts = row.get("contacts", [])
        for title in job_titles:
            contact = next(
                (c for c in contacts if c.get("title", "").lower() == title.lower()),
                {},
            )
            row_data[f"{title} - First Name"] = contact.get("first_name", "")
            row_data[f"{title} - Last Name"] = contact.get("last_name", "")
            row_data[f"{title} - Email"] = contact.get("email", "")
            row_data[f"{title} - Phone"] = contact.get("phone", "")
            row_data[f"{title} - LinkedIn"] = contact.get("linkedin_url", "")

        writer.writerow(row_data)

    return output.getvalue().encode("utf-8")
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/enrichment.py backend/app/services/email_service.py backend/app/services/delivery.py
git commit -m "feat: enrichment, email (Resend), and CSV delivery services"
```

---

## Chunk 4: Pipeline Orchestrator (Phase 4)

### Task 13: ARQ worker + pipeline orchestrator

**Files:**
- Create: `backend/app/workers/pipeline.py`

- [ ] **Step 1: Create pipeline.py**

```python
import asyncio
import logging
from datetime import datetime, timezone

from arq import create_pool
from arq.connections import RedisSettings
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import async_session
from app.models import Job, JobResult, EmailCapture
from app.services.serper import batch_search
from app.services.llm import get_llm_provider
from app.services.llm.base import VerificationResult
from app.services.normalizer import batch_normalize, normalize_domain
from app.services.enrichment import batch_enrich
from app.services.email_service import send_results_email

logger = logging.getLogger(__name__)


async def update_job_progress(
    db: AsyncSession,
    job_id: str,
    phase: str,
    done: int,
    total: int,
    processed_rows: int | None = None,
):
    values = {
        "current_phase": phase,
        "phase_progress": {phase: {"done": done, "total": total}},
    }
    if processed_rows is not None:
        values["processed_rows"] = processed_rows
    await db.execute(update(Job).where(Job.id == job_id).values(**values))
    await db.commit()


async def phase_search(db: AsyncSession, job_id: str, results: list[JobResult]):
    """Phase 1: Search for company websites via Serper."""
    batch_size = settings.search_batch_size
    total = len(results)

    for i in range(0, total, batch_size):
        batch = results[i : i + batch_size]
        rows = [
            {
                "row_index": r.row_index,
                "company_name": r.input_data["company_name"],
                "location": r.input_data.get("location", ""),
            }
            for r in batch
        ]

        search_results = await batch_search(rows)

        for sr in search_results:
            for r in batch:
                if r.row_index == sr["row_index"]:
                    r.search_results = sr["search_results"]
                    r.raw_domain = sr["candidate_domain"]
                    r.status = "searched"
                    break

        await db.commit()
        await update_job_progress(db, job_id, "search", min(i + batch_size, total), total)


async def phase_verify(db: AsyncSession, job_id: str, results: list[JobResult]):
    """Phase 2: Verify domains with LLM."""
    provider = get_llm_provider()
    batch_size = provider.max_batch_size
    sem = asyncio.Semaphore(settings.llm_concurrency)

    # Only verify rows that have a candidate domain
    to_verify = [r for r in results if r.raw_domain]
    total = len(to_verify)

    done = 0
    for i in range(0, total, batch_size):
        batch = to_verify[i : i + batch_size]
        items = [
            {
                "row_index": r.row_index,
                "company_name": r.input_data["company_name"],
                "location": r.input_data.get("location", ""),
                "candidate_domain": r.raw_domain,
                "search_snippet": (r.search_results[0].get("snippet", "") if r.search_results else ""),
            }
            for r in batch
        ]

        async with sem:
            verifications = await provider.verify_domains(items)

        for v in verifications:
            for r in batch:
                if r.row_index == v.row_index:
                    if v.match and v.confidence >= 0.7:
                        r.verified_domain = r.raw_domain
                    elif v.suggested_domain:
                        r.verified_domain = v.suggested_domain
                    else:
                        r.status = "not_found"
                    r.verification_confidence = v.confidence
                    if r.status != "not_found":
                        r.status = "verified"
                    break

        done += len(batch)
        await db.commit()
        await update_job_progress(db, job_id, "verify", done, total)

    # Mark rows without candidates as not_found
    for r in results:
        if not r.raw_domain and r.status == "searched":
            r.status = "not_found"
    await db.commit()


async def phase_normalize(db: AsyncSession, job_id: str, results: list[JobResult]):
    """Phase 3: Normalize and deduplicate domains."""
    to_normalize = [r for r in results if r.verified_domain]
    total = len(to_normalize)
    batch_size = settings.normalize_batch_size

    done = 0
    for i in range(0, total, batch_size):
        batch = to_normalize[i : i + batch_size]
        rows = [
            {"row_index": r.row_index, "verified_domain": r.verified_domain}
            for r in batch
        ]

        normalized = await batch_normalize(rows, resolve_redirects=True, concurrency=settings.normalize_concurrency)

        for n in normalized:
            for r in batch:
                if r.row_index == n["row_index"]:
                    if n.get("domain"):
                        r.normalized_domain = n["domain"]
                        r.status = "normalized"
                    elif n.get("blocked"):
                        r.status = "blocked"
                    else:
                        r.status = "failed"
                        r.error_message = n.get("error", "normalization failed")
                    break

        done += len(batch)
        await db.commit()
        await update_job_progress(db, job_id, "normalize", done, total)


async def phase_enrich(db: AsyncSession, job_id: str, results: list[JobResult], config: dict):
    """Phase 4: Enrich with contact data (optional)."""
    if not config.get("enrich_contacts"):
        return

    job_titles = config.get("job_titles", [])
    max_contacts = config.get("max_contacts", 1)

    if not job_titles:
        return

    # Group rows by domain for dedup
    domain_rows: dict[str, list[int]] = {}
    for r in results:
        if r.normalized_domain:
            domain_rows.setdefault(r.normalized_domain, []).append(r.row_index)

    total = len(domain_rows)
    batch_size = settings.enrich_batch_size

    domain_list = list(domain_rows.keys())
    done = 0

    for i in range(0, len(domain_list), batch_size):
        batch_domains = domain_list[i : i + batch_size]
        batch_map = {d: domain_rows[d] for d in batch_domains}

        enriched = await batch_enrich(batch_map, job_titles, max_contacts)

        for domain, contacts in enriched.items():
            for row_idx in domain_rows[domain]:
                for r in results:
                    if r.row_index == row_idx:
                        r.contacts = contacts
                        r.status = "enriched"
                        break

        done += len(batch_domains)
        await db.commit()
        await update_job_progress(db, job_id, "enrich", done, total)


async def phase_deliver(db: AsyncSession, job_id: str, job: Job):
    """Phase 5: Send results email."""
    await update_job_progress(db, job_id, "deliver", 0, 1)

    # Count stats
    result = await db.execute(select(JobResult).where(JobResult.job_id == job_id))
    all_results = result.scalars().all()

    found = sum(1 for r in all_results if r.normalized_domain)
    total = len(all_results)

    # Get email
    email_result = await db.execute(
        select(EmailCapture).where(EmailCapture.id == job.email_capture_id)
    )
    email_capture = email_result.scalar_one()

    download_url = f"{settings.frontend_url}/api/download/{job_id}"

    try:
        send_results_email(
            to_email=email_capture.email,
            download_url=download_url,
            job_stats={"total_rows": total, "found": found},
        )
    except Exception as e:
        logger.error(f"Failed to send results email: {e}")

    await update_job_progress(db, job_id, "deliver", 1, 1)


async def run_pipeline(ctx: dict, job_id: str):
    """Main pipeline orchestrator. Called by ARQ worker."""
    async with async_session() as db:
        result = await db.execute(select(Job).where(Job.id == job_id))
        job = result.scalar_one_or_none()

        if not job:
            logger.error(f"Job {job_id} not found")
            return

        try:
            job.status = "searching"
            job.started_at = datetime.now(timezone.utc)
            await db.commit()

            # Load all results
            results_q = await db.execute(
                select(JobResult).where(JobResult.job_id == job_id).order_by(JobResult.row_index)
            )
            results = list(results_q.scalars().all())

            # Phase 1: Search
            await phase_search(db, job_id, results)

            # Phase 2: Verify
            job.status = "verifying"
            await db.commit()
            await phase_verify(db, job_id, results)

            # Phase 3: Normalize
            job.status = "normalizing"
            await db.commit()
            await phase_normalize(db, job_id, results)

            # Phase 4: Enrich
            if job.config.get("enrich_contacts"):
                job.status = "enriching"
                await db.commit()
                await phase_enrich(db, job_id, results, job.config)

            # Phase 5: Deliver
            job.status = "delivering"
            await db.commit()
            await phase_deliver(db, job_id, job)

            # Done
            found = sum(1 for r in results if r.normalized_domain)
            job.status = "completed"
            job.processed_rows = len(results)
            job.completed_at = datetime.now(timezone.utc)
            await db.commit()

            logger.info(f"Job {job_id} completed: {found}/{len(results)} domains found")

        except Exception as e:
            logger.exception(f"Job {job_id} failed: {e}")
            job.status = "failed"
            job.error_message = str(e)
            await db.commit()


class WorkerSettings:
    """ARQ worker settings."""
    functions = [run_pipeline]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 5
    job_timeout = 7200  # 2 hours
```

- [ ] **Step 2: Wire ARQ job dispatch in upload router**

Add to the end of the `upload_csv` function in `backend/app/routers/upload.py`, before the return statement:

```python
    # Dispatch to ARQ worker
    from arq import create_pool
    from arq.connections import RedisSettings
    from app.config import settings as app_settings

    redis_pool = await create_pool(RedisSettings.from_dsn(app_settings.redis_url))
    await redis_pool.enqueue_job("run_pipeline", str(job.id))
    await redis_pool.close()
```

- [ ] **Step 3: Fix SSE endpoint to use Redis pub/sub instead of polling**

Replace the `job_sse` function in `backend/app/routers/jobs.py` with a proper implementation:

```python
@router.get("/jobs/{job_id}/sse")
async def job_sse(
    job_id: str,
    token_data: dict = Depends(verify_token),
):
    async def event_stream():
        while True:
            async with async_session() as session:
                result = await session.execute(select(Job).where(Job.id == job_id))
                job = result.scalar_one_or_none()

                if not job:
                    yield f"data: {json.dumps({'error': 'Job not found'})}\n\n"
                    return

                found_count = 0
                if job.status not in ("pending",):
                    count_result = await session.execute(
                        select(func.count(JobResult.id))
                        .where(JobResult.job_id == job_id)
                        .where(JobResult.normalized_domain.isnot(None))
                    )
                    found_count = count_result.scalar() or 0

                data = {
                    "status": job.status,
                    "processed_rows": job.processed_rows,
                    "total_rows": job.total_rows,
                    "current_phase": job.current_phase,
                    "phase_progress": job.phase_progress or {},
                    "found_count": found_count,
                }

                yield f"data: {json.dumps(data)}\n\n"

                if job.status in ("completed", "failed"):
                    return

            await asyncio.sleep(2)

    return StreamingResponse(event_stream(), media_type="text/event-stream")
```

Also add this import at the top of jobs.py:
```python
from app.database import async_session
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/workers/pipeline.py backend/app/routers/upload.py backend/app/routers/jobs.py
git commit -m "feat: ARQ pipeline orchestrator with 5-phase processing"
```

---

## Chunk 5: Frontend Components (Phase 5)

### Task 14: Upload zone + column mapper (parallel with Tasks 15, 16, 17)

**Files:**
- Create: `frontend/src/components/UploadZone.tsx`, `frontend/src/components/ColumnMapper.tsx`

- [ ] **Step 1: Create UploadZone.tsx**

```tsx
"use client";

import { useCallback, useState } from "react";

interface UploadZoneProps {
  onFileSelected: (file: File, headers: string[], preview: Record<string, string>[]) => void;
}

export default function UploadZone({ onFileSelected }: UploadZoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const processFile = useCallback(
    (file: File) => {
      setError(null);

      if (!file.name.endsWith(".csv")) {
        setError("Please upload a CSV file");
        return;
      }

      if (file.size > 50 * 1024 * 1024) {
        setError("File exceeds 50MB limit");
        return;
      }

      const reader = new FileReader();
      reader.onload = (e) => {
        const text = e.target?.result as string;
        const lines = text.split("\n").filter((l) => l.trim());

        if (lines.length < 2) {
          setError("CSV must have a header row and at least one data row");
          return;
        }

        const headers = lines[0].split(",").map((h) => h.trim().replace(/"/g, ""));
        const preview: Record<string, string>[] = [];

        for (let i = 1; i <= Math.min(5, lines.length - 1); i++) {
          const values = lines[i].split(",").map((v) => v.trim().replace(/"/g, ""));
          const row: Record<string, string> = {};
          headers.forEach((h, idx) => {
            row[h] = values[idx] || "";
          });
          preview.push(row);
        }

        onFileSelected(file, headers, preview);
      };
      reader.readAsText(file);
    },
    [onFileSelected]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragging(false);
      const file = e.dataTransfer.files[0];
      if (file) processFile(file);
    },
    [processFile]
  );

  const handleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      if (file) processFile(file);
    },
    [processFile]
  );

  return (
    <div>
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setIsDragging(true);
        }}
        onDragLeave={() => setIsDragging(false)}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-all duration-200 ${
          isDragging
            ? "border-primary bg-primary-light"
            : "border-border hover:border-primary/50"
        }`}
      >
        <input
          type="file"
          accept=".csv"
          onChange={handleChange}
          className="hidden"
          id="csv-upload"
        />
        <label htmlFor="csv-upload" className="cursor-pointer">
          <div className="text-4xl mb-4">+</div>
          <p className="text-text-primary font-medium mb-1">
            Drop your CSV here or click to browse
          </p>
          <p className="text-text-secondary text-sm">
            Max 50MB, up to 100,000 rows
          </p>
        </label>
      </div>
      {error && (
        <p className="mt-2 text-red-500 text-sm">{error}</p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create ColumnMapper.tsx**

```tsx
"use client";

import { useMemo } from "react";

interface ColumnMapperProps {
  headers: string[];
  preview: Record<string, string>[];
  companyColumn: string;
  locationColumn: string;
  onCompanyColumnChange: (col: string) => void;
  onLocationColumnChange: (col: string) => void;
}

const COMPANY_PATTERN = /company|name|org|business|brand/i;
const LOCATION_PATTERN = /location|city|state|address|geo|region/i;

export function autoDetectColumns(headers: string[]): {
  company: string;
  location: string;
} {
  const company = headers.find((h) => COMPANY_PATTERN.test(h)) || headers[0] || "";
  const location = headers.find((h) => LOCATION_PATTERN.test(h)) || "";
  return { company, location };
}

export default function ColumnMapper({
  headers,
  preview,
  companyColumn,
  locationColumn,
  onCompanyColumnChange,
  onLocationColumnChange,
}: ColumnMapperProps) {
  return (
    <div className="space-y-4">
      <h3 className="font-semibold text-text-primary">Map Your Columns</h3>

      <div className="grid grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-text-secondary mb-1">
            Company Name <span className="text-red-500">*</span>
          </label>
          <select
            value={companyColumn}
            onChange={(e) => onCompanyColumnChange(e.target.value)}
            className="w-full border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-light focus:border-primary"
          >
            <option value="">Select column...</option>
            {headers.map((h) => (
              <option key={h} value={h}>{h}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-text-secondary mb-1">
            Location (optional)
          </label>
          <select
            value={locationColumn}
            onChange={(e) => onLocationColumnChange(e.target.value)}
            className="w-full border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-light focus:border-primary"
          >
            <option value="">None</option>
            {headers.map((h) => (
              <option key={h} value={h}>{h}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Preview table */}
      <div className="border border-border rounded-lg overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50">
                {headers.map((h) => (
                  <th
                    key={h}
                    className={`px-3 py-2 text-left font-medium ${
                      h === companyColumn
                        ? "bg-primary/10 text-primary"
                        : h === locationColumn
                        ? "bg-blue-50 text-blue-600"
                        : "text-text-secondary"
                    }`}
                  >
                    {h}
                    {h === companyColumn && " (Company)"}
                    {h === locationColumn && " (Location)"}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {preview.map((row, i) => (
                <tr key={i} className={i % 2 === 0 ? "bg-white" : "bg-gray-50/50"}>
                  {headers.map((h) => (
                    <td key={h} className="px-3 py-2 truncate max-w-[200px]">
                      {row[h]}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="px-3 py-2 bg-gray-50 text-xs text-text-secondary">
          Showing first {preview.length} rows
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/UploadZone.tsx frontend/src/components/ColumnMapper.tsx
git commit -m "feat: upload zone and column mapper components"
```

---

### Task 15: Config panel + email gate (parallel with Tasks 14, 16, 17)

**Files:**
- Create: `frontend/src/components/ConfigPanel.tsx`, `frontend/src/components/EmailGate.tsx`

- [ ] **Step 1: Create ConfigPanel.tsx**

```tsx
"use client";

import { useState } from "react";

interface ConfigPanelProps {
  enrichContacts: boolean;
  jobTitles: string[];
  maxContacts: number;
  onEnrichContactsChange: (v: boolean) => void;
  onJobTitlesChange: (titles: string[]) => void;
  onMaxContactsChange: (n: number) => void;
}

const SUGGESTED_TITLES = [
  "CEO", "CTO", "CFO", "COO", "CMO",
  "VP Sales", "VP Marketing", "VP Engineering",
  "Head of Growth", "Head of Sales", "Head of Marketing",
  "Founder", "Co-Founder", "Director of Sales",
];

export default function ConfigPanel({
  enrichContacts,
  jobTitles,
  maxContacts,
  onEnrichContactsChange,
  onJobTitlesChange,
  onMaxContactsChange,
}: ConfigPanelProps) {
  const [titleInput, setTitleInput] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);

  const addTitle = (title: string) => {
    const trimmed = title.trim();
    if (trimmed && !jobTitles.includes(trimmed)) {
      onJobTitlesChange([...jobTitles, trimmed]);
    }
    setTitleInput("");
    setShowSuggestions(false);
  };

  const removeTitle = (title: string) => {
    onJobTitlesChange(jobTitles.filter((t) => t !== title));
  };

  const filteredSuggestions = SUGGESTED_TITLES.filter(
    (t) =>
      t.toLowerCase().includes(titleInput.toLowerCase()) &&
      !jobTitles.includes(t)
  );

  return (
    <div className="space-y-4 p-4 border border-border rounded-lg">
      <h3 className="font-semibold text-text-primary">Configuration</h3>

      <label className="flex items-center gap-3 cursor-pointer">
        <input
          type="checkbox"
          checked={enrichContacts}
          onChange={(e) => onEnrichContactsChange(e.target.checked)}
          className="w-4 h-4 rounded border-border text-primary focus:ring-primary"
        />
        <span className="text-sm text-text-primary">
          Enrich with contact data (names, emails, phones)
        </span>
      </label>

      {enrichContacts && (
        <div className="space-y-3 pl-7">
          <div className="relative">
            <label className="block text-sm font-medium text-text-secondary mb-1">
              Job Titles to Find
            </label>
            <input
              type="text"
              value={titleInput}
              onChange={(e) => {
                setTitleInput(e.target.value);
                setShowSuggestions(true);
              }}
              onFocus={() => setShowSuggestions(true)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  addTitle(titleInput);
                }
              }}
              placeholder="Type a job title..."
              className="w-full border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-light focus:border-primary"
            />
            {showSuggestions && filteredSuggestions.length > 0 && (
              <div className="absolute z-10 w-full mt-1 bg-white border border-border rounded-md shadow-lg max-h-48 overflow-y-auto">
                {filteredSuggestions.map((t) => (
                  <button
                    key={t}
                    onClick={() => addTitle(t)}
                    className="w-full text-left px-3 py-2 text-sm hover:bg-gray-50 transition-colors"
                  >
                    {t}
                  </button>
                ))}
              </div>
            )}
          </div>

          {jobTitles.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {jobTitles.map((t) => (
                <span
                  key={t}
                  className="inline-flex items-center gap-1 px-2.5 py-1 bg-primary/10 text-primary text-sm rounded-full"
                >
                  {t}
                  <button
                    onClick={() => removeTitle(t)}
                    className="hover:text-primary-hover"
                  >
                    x
                  </button>
                </span>
              ))}
            </div>
          )}

          <div>
            <label className="block text-sm font-medium text-text-secondary mb-1">
              Max contacts per company
            </label>
            <select
              value={maxContacts}
              onChange={(e) => onMaxContactsChange(Number(e.target.value))}
              className="border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-light focus:border-primary"
            >
              {[1, 2, 3, 4, 5].map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Create EmailGate.tsx**

```tsx
"use client";

import { useState } from "react";

interface EmailGateProps {
  onSubmit: (email: string) => Promise<void>;
  isLoading: boolean;
}

export default function EmailGate({ onSubmit, isLoading }: EmailGateProps) {
  const [email, setEmail] = useState("");
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    if (!email || !email.includes("@")) {
      setError("Please enter a valid email address");
      return;
    }

    try {
      await onSubmit(email);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong");
    }
  };

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <div>
        <label className="block text-sm font-medium text-text-primary mb-1">
          Enter your email to start processing
        </label>
        <p className="text-xs text-text-secondary mb-2">
          Results will be emailed to you when complete.
        </p>
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="you@company.com"
          required
          className="w-full border border-border rounded-md px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-primary-light focus:border-primary"
        />
      </div>
      {error && <p className="text-red-500 text-sm">{error}</p>}
      <button
        type="submit"
        disabled={isLoading || !email}
        className="w-full bg-primary text-white py-2.5 px-4 rounded-md font-medium hover:bg-primary-hover transition-all duration-200 hover:-translate-y-0.5 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:translate-y-0"
      >
        {isLoading ? "Processing..." : "Start Processing"}
      </button>
    </form>
  );
}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/ConfigPanel.tsx frontend/src/components/EmailGate.tsx
git commit -m "feat: config panel and email gate components"
```

---

### Task 16: Progress tracker + live preview (parallel with Tasks 14, 15, 17)

**Files:**
- Create: `frontend/src/components/ProgressTracker.tsx`, `frontend/src/components/LivePreview.tsx`, `frontend/src/hooks/useSSE.ts`

- [ ] **Step 1: Create useSSE.ts**

```typescript
"use client";

import { useEffect, useRef, useState, useCallback } from "react";

interface JobProgress {
  status: string;
  processed_rows: number;
  total_rows: number;
  current_phase: string | null;
  phase_progress: Record<string, { done: number; total: number }>;
  found_count: number;
  error?: string;
}

export function useSSE(jobId: string | null, token: string | null) {
  const [progress, setProgress] = useState<JobProgress | null>(null);
  const [connected, setConnected] = useState(false);
  const eventSourceRef = useRef<EventSource | null>(null);
  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const cleanup = useCallback(() => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close();
      eventSourceRef.current = null;
    }
    if (pollingRef.current) {
      clearInterval(pollingRef.current);
      pollingRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!jobId || !token) return;

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

    // Try SSE first
    try {
      const es = new EventSource(
        `${apiUrl}/api/v1/jobs/${jobId}/sse?token=${token}`
      );

      es.onopen = () => setConnected(true);

      es.onmessage = (e) => {
        const data: JobProgress = JSON.parse(e.data);
        setProgress(data);
        if (data.status === "completed" || data.status === "failed") {
          cleanup();
        }
      };

      es.onerror = () => {
        es.close();
        // Fallback to polling
        startPolling(apiUrl, jobId, token);
      };

      eventSourceRef.current = es;
    } catch {
      startPolling(apiUrl, jobId, token);
    }

    function startPolling(apiUrl: string, jobId: string, token: string) {
      setConnected(true);
      pollingRef.current = setInterval(async () => {
        try {
          const resp = await fetch(`${apiUrl}/api/v1/jobs/${jobId}`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          const data = await resp.json();
          setProgress(data);
          if (data.status === "completed" || data.status === "failed") {
            cleanup();
          }
        } catch {
          // silently retry
        }
      }, 3000);
    }

    return cleanup;
  }, [jobId, token, cleanup]);

  return { progress, connected };
}
```

- [ ] **Step 2: Create ProgressTracker.tsx**

```tsx
"use client";

interface ProgressTrackerProps {
  status: string;
  currentPhase: string | null;
  phaseProgress: Record<string, { done: number; total: number }>;
  processedRows: number;
  totalRows: number;
  foundCount: number;
}

const PHASES = [
  { key: "search", label: "Search" },
  { key: "verify", label: "Verify" },
  { key: "normalize", label: "Normalize" },
  { key: "enrich", label: "Enrich" },
  { key: "deliver", label: "Deliver" },
];

export default function ProgressTracker({
  status,
  currentPhase,
  phaseProgress,
  processedRows,
  totalRows,
  foundCount,
}: ProgressTrackerProps) {
  const currentIdx = PHASES.findIndex((p) => p.key === currentPhase);
  const overallPercent = totalRows > 0 ? Math.round((processedRows / totalRows) * 100) : 0;

  const currentPhaseData = currentPhase ? phaseProgress[currentPhase] : null;
  const phasePercent = currentPhaseData && currentPhaseData.total > 0
    ? Math.round((currentPhaseData.done / currentPhaseData.total) * 100)
    : 0;

  return (
    <div className="space-y-6">
      {/* Phase indicator */}
      <div className="flex items-center justify-between">
        {PHASES.map((phase, idx) => (
          <div key={phase.key} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium transition-colors ${
                  idx < currentIdx
                    ? "bg-green-500 text-white"
                    : idx === currentIdx
                    ? "bg-primary text-white"
                    : "bg-gray-200 text-text-secondary"
                }`}
              >
                {idx < currentIdx ? "\u2713" : idx + 1}
              </div>
              <span className="text-xs mt-1 text-text-secondary">{phase.label}</span>
            </div>
            {idx < PHASES.length - 1 && (
              <div
                className={`w-12 h-0.5 mx-2 ${
                  idx < currentIdx ? "bg-green-500" : "bg-gray-200"
                }`}
              />
            )}
          </div>
        ))}
      </div>

      {/* Progress bar */}
      <div>
        <div className="flex justify-between text-sm mb-1">
          <span className="text-text-secondary">
            {currentPhase ? `${currentPhase.charAt(0).toUpperCase() + currentPhase.slice(1)}ing...` : "Starting..."}
          </span>
          <span className="font-medium">{phasePercent}%</span>
        </div>
        <div className="w-full bg-gray-200 rounded-full h-2.5">
          <div
            className="bg-primary h-2.5 rounded-full transition-all duration-500"
            style={{ width: `${phasePercent}%` }}
          />
        </div>
      </div>

      {/* Stats cards */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-gray-50 rounded-lg p-3 text-center">
          <p className="text-2xl font-semibold text-text-primary">
            {processedRows.toLocaleString()}
          </p>
          <p className="text-xs text-text-secondary">Processed</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-3 text-center">
          <p className="text-2xl font-semibold text-green-600">
            {foundCount.toLocaleString()}
          </p>
          <p className="text-xs text-text-secondary">Found</p>
        </div>
        <div className="bg-gray-50 rounded-lg p-3 text-center">
          <p className="text-2xl font-semibold text-text-primary">
            {totalRows.toLocaleString()}
          </p>
          <p className="text-xs text-text-secondary">Total Rows</p>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create LivePreview.tsx**

```tsx
"use client";

import { useEffect, useState, useCallback } from "react";

interface PreviewRow {
  row_index: number;
  company_name: string;
  location: string;
  domain: string | null;
  confidence: number | null;
  status: string;
}

interface LivePreviewProps {
  jobId: string;
  token: string;
}

export default function LivePreview({ jobId, token }: LivePreviewProps) {
  const [rows, setRows] = useState<PreviewRow[]>([]);

  const fetchPreview = useCallback(async () => {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
    try {
      const resp = await fetch(`${apiUrl}/api/v1/jobs/${jobId}/preview?limit=50`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      const data = await resp.json();
      setRows(data.rows || []);
    } catch {
      // silently retry
    }
  }, [jobId, token]);

  useEffect(() => {
    fetchPreview();
    const interval = setInterval(fetchPreview, 5000);
    return () => clearInterval(interval);
  }, [fetchPreview]);

  const statusColor = (status: string) => {
    switch (status) {
      case "normalized":
      case "enriched":
        return "text-green-600";
      case "not_found":
      case "blocked":
      case "failed":
        return "text-red-500";
      default:
        return "text-text-secondary";
    }
  };

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <div className="px-3 py-2 bg-gray-50 border-b border-border">
        <h4 className="text-sm font-medium text-text-primary">Live Results</h4>
      </div>
      <div className="overflow-x-auto max-h-80">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-white">
            <tr>
              <th className="px-3 py-2 text-left text-text-secondary font-medium">#</th>
              <th className="px-3 py-2 text-left text-text-secondary font-medium">Company</th>
              <th className="px-3 py-2 text-left text-text-secondary font-medium">Location</th>
              <th className="px-3 py-2 text-left text-text-secondary font-medium">Website</th>
              <th className="px-3 py-2 text-left text-text-secondary font-medium">Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.row_index} className="border-t border-border/50">
                <td className="px-3 py-1.5 text-text-secondary">{row.row_index + 1}</td>
                <td className="px-3 py-1.5 truncate max-w-[200px]">{row.company_name}</td>
                <td className="px-3 py-1.5 truncate max-w-[150px] text-text-secondary">{row.location}</td>
                <td className="px-3 py-1.5 text-primary truncate max-w-[200px]">
                  {row.domain || "-"}
                </td>
                <td className={`px-3 py-1.5 font-medium ${statusColor(row.status)}`}>
                  {row.status}
                </td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-text-secondary">
                  Waiting for results...
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/useSSE.ts frontend/src/components/ProgressTracker.tsx frontend/src/components/LivePreview.tsx
git commit -m "feat: SSE hook, progress tracker, and live preview components"
```

---

### Task 17: Results panel + main tool page (parallel with Tasks 14, 15, 16)

**Files:**
- Create: `frontend/src/components/ResultsPanel.tsx`, `frontend/src/components/ClayPushModal.tsx`, `frontend/src/lib/api.ts`, `frontend/src/app/tools/website-finder/page.tsx`

- [ ] **Step 1: Create api.ts**

```typescript
const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI(path: string, options: RequestInit = {}) {
  const resp = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      ...options.headers,
    },
  });

  if (!resp.ok) {
    const error = await resp.json().catch(() => ({ detail: "Request failed" }));
    throw new Error(error.detail || `HTTP ${resp.status}`);
  }

  return resp.json();
}

export async function captureEmail(email: string, toolSlug: string, source?: string) {
  return fetchAPI("/api/v1/email-capture", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, tool_slug: toolSlug, source }),
  });
}

export async function uploadCSV(
  file: File,
  config: {
    companyColumn: string;
    locationColumn: string;
    emailCaptureId: string;
    enrichContacts: boolean;
    jobTitles: string[];
    maxContacts: number;
  },
  token: string
) {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("company_column", config.companyColumn);
  formData.append("location_column", config.locationColumn);
  formData.append("email_capture_id", config.emailCaptureId);
  formData.append("enrich_contacts", String(config.enrichContacts));
  formData.append("job_titles", config.jobTitles.join(","));
  formData.append("max_contacts", String(config.maxContacts));

  return fetchAPI("/api/v1/upload", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: formData,
  });
}

export async function getJobStatus(jobId: string, token: string) {
  return fetchAPI(`/api/v1/jobs/${jobId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
}

export function getDownloadUrl(jobId: string, token: string) {
  return `${API_URL}/api/v1/download/${jobId}?token=${token}`;
}

export async function pushToClay(
  jobId: string,
  clayApiKey: string,
  tableId: string,
  token: string
) {
  return fetchAPI(`/api/v1/clay-push/${jobId}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ clay_api_key: clayApiKey, table_id: tableId }),
  });
}
```

- [ ] **Step 2: Create ResultsPanel.tsx**

```tsx
"use client";

import { useState } from "react";
import ClayPushModal from "./ClayPushModal";

interface ResultsPanelProps {
  jobId: string;
  token: string;
  totalRows: number;
  foundCount: number;
}

export default function ResultsPanel({
  jobId,
  token,
  totalRows,
  foundCount,
}: ResultsPanelProps) {
  const [showClay, setShowClay] = useState(false);
  const matchRate = totalRows > 0 ? Math.round((foundCount / totalRows) * 100) : 0;
  const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  return (
    <div className="space-y-6">
      <div className="text-center">
        <div className="inline-flex items-center justify-center w-16 h-16 bg-green-100 rounded-full mb-4">
          <span className="text-3xl text-green-600">{"\u2713"}</span>
        </div>
        <h3 className="text-xl font-semibold">Processing Complete!</h3>
        <p className="text-text-secondary mt-1">
          Found {foundCount.toLocaleString()} websites out of {totalRows.toLocaleString()} companies ({matchRate}% match rate)
        </p>
      </div>

      <div className="flex gap-3">
        <a
          href={`${apiUrl}/api/v1/download/${jobId}`}
          className="flex-1 bg-primary text-white py-3 px-4 rounded-md font-medium text-center hover:bg-primary-hover transition-all duration-200 hover:-translate-y-0.5"
        >
          Download CSV
        </a>
        <button
          onClick={() => setShowClay(true)}
          className="flex-1 border border-border py-3 px-4 rounded-md font-medium text-text-primary hover:bg-gray-50 transition-all duration-200"
        >
          Push to Clay
        </button>
      </div>

      <p className="text-xs text-text-secondary text-center">
        A download link has also been emailed to you. Link expires in 7 days.
      </p>

      {showClay && (
        <ClayPushModal
          jobId={jobId}
          token={token}
          onClose={() => setShowClay(false)}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 3: Create ClayPushModal.tsx**

```tsx
"use client";

import { useState } from "react";
import { pushToClay } from "@/lib/api";

interface ClayPushModalProps {
  jobId: string;
  token: string;
  onClose: () => void;
}

export default function ClayPushModal({ jobId, token, onClose }: ClayPushModalProps) {
  const [clayApiKey, setClayApiKey] = useState("");
  const [tableId, setTableId] = useState("");
  const [status, setStatus] = useState<"idle" | "pushing" | "done" | "error">("idle");
  const [result, setResult] = useState<{ pushed: number; failed: number } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handlePush = async () => {
    if (!clayApiKey || !tableId) return;
    setStatus("pushing");
    setError(null);

    try {
      const data = await pushToClay(jobId, clayApiKey, tableId, token);
      setResult(data);
      setStatus("done");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Push failed");
      setStatus("error");
    }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50">
      <div className="bg-white rounded-lg p-6 w-full max-w-md">
        <h3 className="text-lg font-semibold mb-4">Push to Clay</h3>

        {status === "done" && result ? (
          <div className="space-y-4">
            <p className="text-green-600 font-medium">
              Pushed {result.pushed} rows to Clay
              {result.failed > 0 && ` (${result.failed} failed)`}
            </p>
            <button
              onClick={onClose}
              className="w-full border border-border py-2 rounded-md hover:bg-gray-50"
            >
              Close
            </button>
          </div>
        ) : (
          <div className="space-y-3">
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1">
                Clay API Key
              </label>
              <input
                type="password"
                value={clayApiKey}
                onChange={(e) => setClayApiKey(e.target.value)}
                placeholder="clay_..."
                className="w-full border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-light"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-text-secondary mb-1">
                Table ID
              </label>
              <input
                type="text"
                value={tableId}
                onChange={(e) => setTableId(e.target.value)}
                placeholder="tbl_..."
                className="w-full border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary-light"
              />
            </div>
            {error && <p className="text-red-500 text-sm">{error}</p>}
            <div className="flex gap-2">
              <button
                onClick={handlePush}
                disabled={status === "pushing" || !clayApiKey || !tableId}
                className="flex-1 bg-primary text-white py-2 rounded-md font-medium hover:bg-primary-hover disabled:opacity-50"
              >
                {status === "pushing" ? "Pushing..." : "Push"}
              </button>
              <button
                onClick={onClose}
                className="flex-1 border border-border py-2 rounded-md hover:bg-gray-50"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create the main website-finder page**

```tsx
// frontend/src/app/tools/website-finder/page.tsx
"use client";

import { useState, useCallback } from "react";
import UploadZone from "@/components/UploadZone";
import ColumnMapper, { autoDetectColumns } from "@/components/ColumnMapper";
import ConfigPanel from "@/components/ConfigPanel";
import EmailGate from "@/components/EmailGate";
import ProgressTracker from "@/components/ProgressTracker";
import LivePreview from "@/components/LivePreview";
import ResultsPanel from "@/components/ResultsPanel";
import { useSSE } from "@/hooks/useSSE";
import { captureEmail, uploadCSV } from "@/lib/api";

type Phase = "upload" | "config" | "email" | "processing" | "results";

export default function WebsiteFinderPage() {
  // Flow state
  const [phase, setPhase] = useState<Phase>("upload");

  // Upload state
  const [file, setFile] = useState<File | null>(null);
  const [headers, setHeaders] = useState<string[]>([]);
  const [preview, setPreview] = useState<Record<string, string>[]>([]);
  const [companyColumn, setCompanyColumn] = useState("");
  const [locationColumn, setLocationColumn] = useState("");

  // Config state
  const [enrichContacts, setEnrichContacts] = useState(false);
  const [jobTitles, setJobTitles] = useState<string[]>([]);
  const [maxContacts, setMaxContacts] = useState(1);

  // Job state
  const [jobId, setJobId] = useState<string | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // SSE
  const { progress } = useSSE(
    phase === "processing" ? jobId : null,
    token
  );

  // Check if processing is complete
  if (progress?.status === "completed" && phase === "processing") {
    setPhase("results");
  }

  const handleFileSelected = useCallback(
    (f: File, h: string[], p: Record<string, string>[]) => {
      setFile(f);
      setHeaders(h);
      setPreview(p);

      const detected = autoDetectColumns(h);
      setCompanyColumn(detected.company);
      setLocationColumn(detected.location);
      setPhase("config");
    },
    []
  );

  const handleEmailSubmit = async (email: string) => {
    if (!file) return;
    setIsSubmitting(true);

    try {
      // 1. Capture email
      const captureResp = await captureEmail(email, "website-finder");
      const emailCaptureId = captureResp.email_capture_id;

      // Create a temp token for upload (email capture returns it)
      const tempToken = captureResp.token || "";

      // 2. Upload CSV
      const uploadResp = await uploadCSV(
        file,
        {
          companyColumn,
          locationColumn,
          emailCaptureId,
          enrichContacts,
          jobTitles,
          maxContacts,
        },
        tempToken
      );

      setJobId(uploadResp.job_id);
      setToken(uploadResp.token);
      setPhase("processing");
    } catch (err) {
      throw err;
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <div className="text-center mb-8">
        <h1 className="text-2xl font-bold text-text-primary">Company Website Finder</h1>
        <p className="text-text-secondary mt-2">
          Upload company names and locations to find their websites, verify domains,
          and optionally enrich with contact data.
        </p>
      </div>

      <div className="bg-white border border-border rounded-xl p-6 shadow-sm space-y-6">
        {/* Phase 1: Upload */}
        {phase === "upload" && (
          <UploadZone onFileSelected={handleFileSelected} />
        )}

        {/* Phase 2: Config */}
        {phase === "config" && (
          <>
            <ColumnMapper
              headers={headers}
              preview={preview}
              companyColumn={companyColumn}
              locationColumn={locationColumn}
              onCompanyColumnChange={setCompanyColumn}
              onLocationColumnChange={setLocationColumn}
            />

            <ConfigPanel
              enrichContacts={enrichContacts}
              jobTitles={jobTitles}
              maxContacts={maxContacts}
              onEnrichContactsChange={setEnrichContacts}
              onJobTitlesChange={setJobTitles}
              onMaxContactsChange={setMaxContacts}
            />

            <div className="flex gap-3">
              <button
                onClick={() => setPhase("upload")}
                className="border border-border py-2 px-4 rounded-md text-sm hover:bg-gray-50"
              >
                Back
              </button>
              <button
                onClick={() => setPhase("email")}
                disabled={!companyColumn}
                className="flex-1 bg-primary text-white py-2 px-4 rounded-md font-medium hover:bg-primary-hover disabled:opacity-50 transition-all duration-200"
              >
                Continue
              </button>
            </div>
          </>
        )}

        {/* Phase 3: Email */}
        {phase === "email" && (
          <>
            <button
              onClick={() => setPhase("config")}
              className="text-sm text-text-secondary hover:text-text-primary"
            >
              &larr; Back to configuration
            </button>
            <EmailGate onSubmit={handleEmailSubmit} isLoading={isSubmitting} />
          </>
        )}

        {/* Phase 4: Processing */}
        {phase === "processing" && progress && (
          <>
            <ProgressTracker
              status={progress.status}
              currentPhase={progress.current_phase}
              phaseProgress={progress.phase_progress}
              processedRows={progress.processed_rows}
              totalRows={progress.total_rows}
              foundCount={progress.found_count}
            />
            {jobId && token && (
              <LivePreview jobId={jobId} token={token} />
            )}
          </>
        )}

        {phase === "processing" && !progress && (
          <div className="text-center py-8">
            <p className="text-text-secondary">Connecting to job...</p>
          </div>
        )}

        {/* Phase 5: Results */}
        {phase === "results" && jobId && token && progress && (
          <ResultsPanel
            jobId={jobId}
            token={token}
            totalRows={progress.total_rows}
            foundCount={progress.found_count}
          />
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/ResultsPanel.tsx frontend/src/components/ClayPushModal.tsx frontend/src/lib/api.ts frontend/src/app/tools/website-finder/page.tsx
git commit -m "feat: results panel, Clay push, API client, and main tool page"
```

---

## Chunk 6: Integration (Phase 6)

### Task 18: Final wiring + auth fix + SSE token support

**Files:**
- Modify: `backend/app/routers/email_capture.py` (return token), `backend/app/routers/jobs.py` (SSE token query param), `backend/app/main.py` (verify lifespan)

- [ ] **Step 1: Update email_capture.py to return a JWT token**

Add token generation to the email capture response. After the `capture_id` is obtained, create a token:

```python
# Add to end of capture_email function, before return
from app.auth import create_token

token = create_token(body.email, str(capture_id))

return {
    "email_capture_id": str(capture_id),
    "token": token,
    "message": "Email captured successfully",
}
```

Update the response model:
```python
class EmailCaptureResponse(BaseModel):
    email_capture_id: str
    token: str
    message: str
```

- [ ] **Step 2: Update SSE endpoint to accept token as query param**

SSE (EventSource) can't send custom headers. Update `jobs.py`:

```python
from fastapi import Query

@router.get("/jobs/{job_id}/sse")
async def job_sse(
    job_id: str,
    token: str = Query(...),
):
    # Manually verify token from query param
    from jose import JWTError, jwt
    from app.config import settings

    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(401, "Invalid token")

    # ... rest of SSE implementation unchanged
```

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/email_capture.py backend/app/routers/jobs.py
git commit -m "feat: auth token in email capture response, SSE query param auth"
```

---

## Summary

**18 tasks across 6 phases:**

| Phase | Tasks | Can Parallelize | Dependencies |
|-------|-------|----------------|--------------|
| 1: Foundation | 1-4 | Tasks 2,3,4 parallel after 1 | None |
| 2: Backend Core | 5-8 | All 4 parallel | Phase 1 |
| 3: Pipeline | 9-12 | All 4 parallel | Phase 2 |
| 4: Orchestrator | 13 | Sequential | Phase 3 |
| 5: Frontend | 14-17 | All 4 parallel | Phase 1 only |
| 6: Integration | 18 | Sequential | Phase 4 + 5 |

**Phase 5 (Frontend) can run in parallel with Phases 2-4 (Backend) since they're independent.**

**To run locally:**
```bash
# Backend
cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload

# Worker
cd backend && arq app.workers.pipeline.WorkerSettings

# Frontend
cd frontend && npm install && npm run dev

# Redis (must be running)
redis-server
```
