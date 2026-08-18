# End-to-end tests

Three paths, chosen deliberately: **the demo that gets run in front of design
partners**, not a coverage target.

| Spec | Path | Why it is here |
|---|---|---|
| `onboarding.spec.ts` | sign up → profile → calendar | The core promise. If it breaks there is no product to show. |
| `evidence.spec.ts` | upload → classify → link → audit | The loop a preparer runs every filing cycle, and proof the audit trail records it. |
| `team.spec.ts` | invite → accept → roster | The step that makes it a team product; the PRD's activation metric. |

They assert on **outcomes, not URLs** — a populated table, the validation chips,
a second member on the roster. A dashboard that loads empty satisfies a URL
check and is still a dead demo.

## Running

The stack must already be up. Starting it from the config would hide a broken
build behind a test-runner convenience.

```bash
# 1. backend, against a throwaway DB
cd regis/backend
rm -f /tmp/e2e.db
REGIS_DATABASE_URL="sqlite+pysqlite:////tmp/e2e.db" REGIS_JWT_SECRET=e2e-secret python -c \
  "from app.core.db import engine, SessionLocal; from app.models import Base; \
   from app.seed.library_loader import seed_database; \
   Base.metadata.create_all(engine); s=SessionLocal(); seed_database(s); s.commit()"
REGIS_DATABASE_URL="sqlite+pysqlite:////tmp/e2e.db" REGIS_JWT_SECRET=e2e-secret \
  uvicorn app.main:app --port 8000 &

# 2. frontend
cd regis/frontend
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npm run build
NEXT_PUBLIC_API_URL=http://127.0.0.1:8000 npx next start -p 3000 &

# 3. tests
npm run e2e
```

`PLAYWRIGHT_CHROMIUM_PATH` points the runner at an already-installed Chromium
instead of downloading one — useful where the image ships a browser whose build
number does not match the `@playwright/test` version.

## Notes

- **`retries: 0` on purpose.** A flaky compliance demo is worse than a failing
  one: a retry lets a real race pass on the second attempt and reach a customer.
  The first run of `onboarding.spec.ts` caught exactly that class of bug — see
  the redirect race in `app/page.tsx`.
- **Serial (`workers: 1`).** Each path signs up a real organisation against one
  backend.
- Every account uses a unique email, so runs do not collide.
