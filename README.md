# RAISA Synapse — Layer 1 Foundation

Enterprise regulatory-affairs platform foundation: multi-tenancy, auth,
RBAC with scope + segregation of duties, audit, document-storage
foundation, a regulatory standards registry, the dual RAISA
Office / RAISA GenX theme system, and — as of Layer 2 — a real
Product → Application → Dossier → CTD Module/Section data model with a
controlled dossier lifecycle, and — as of Layer 3 — a Regulatory
Intelligence domain: CoLAB-owned global intelligence distributed to
authorized customer tenants, alongside each tenant's own private and
tenant-wide intelligence.

**Layers 1-3 only.** No eCTD generation, AI writing or assistant,
crawler/ingestion engine, Response Center, Knowledge Graph, or native
mobile app yet — see [`docs/LAYER_1_FOUNDATION.md`](docs/LAYER_1_FOUNDATION.md),
[`docs/LAYER_2_DOSSIER_CTD.md`](docs/LAYER_2_DOSSIER_CTD.md) and
[`docs/LAYER_3_REGULATORY_INTELLIGENCE.md`](docs/LAYER_3_REGULATORY_INTELLIGENCE.md)
for exactly what is and isn't built.

This is a standalone codebase, isolated on purpose from the existing
RAISA (co-lab-cld) app — no shared code, database, or infrastructure.

## Run it

```bash
cp .env.example .env
docker compose up --build
```

- Web: http://localhost:3000
- API: http://localhost:8000 (docs at `/docs`)
- MinIO console: http://localhost:9001

Then seed some dev data:

```bash
docker compose exec api python seed.py
```

Log in at http://localhost:3000/login with organization `demo-pharma`
and any of the seeded emails (see seed.py output for the shared dev
password) — try `tenant.admin@example.com`. Other seeded organizations:
`tenant-b-pharma`, and `colab-systems` (the CoLAB platform org that owns
global intelligence; log in as `colab.admin@example.com`).

Note: the seeded RA specialist's role is scoped to "Product ABC / India"
(the Layer 1 spec's demo scenario), and Layer 2/3 checks aren't
scope-aware yet, so use `tenant.admin@example.com` or
`ra.manager@example.com` to try Layer 2/3 features — see
`docs/LAYER_3_REGULATORY_INTELLIGENCE.md`, "Known limitations".

## Run it without Docker

```bash
# Postgres + Redis need to be running locally first.
cd apps/api
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
./.venv/bin/python -m alembic upgrade head
./.venv/bin/python seed.py
./.venv/bin/uvicorn app.main:app --reload

# separate terminal
cd apps/web
npm install
npm run dev
```

## Run the tests

```bash
cd apps/api
export DATABASE_URL=postgresql+psycopg2://raisa_synapse:devpassword_local_only@localhost:5432/raisa_synapse_test
./.venv/bin/python -m pytest -v
```

67 tests, all passing as of this build (17 Layer 1 + 17 Layer 2 + 33
Layer 3) — see the three docs above for what they prove.

## Repository structure

```
apps/api/       FastAPI backend — models, services, API routes, migrations, tests
apps/web/       Next.js frontend — app shell, login, dashboard, theme system
docs/           Architecture docs and diagrams
scripts/        Dev convenience scripts
packages/       Reserved for shared code once >1 service needs it (empty in Layer 1 — see docs)
modules/        Reserved for a true domain-package split in a later layer (empty in Layer 1 — see docs)
```

`packages/` and `modules/` are placeholders, not dead scaffolding: spec
§6 describes a domain-oriented monorepo split, but with exactly one
frontend and one backend service in Layer 1, splitting domains into
separately-versioned packages has no payoff yet and would only add
import indirection. The same domain separation (identity, tenancy,
authorization, audit, documents, standards) exists today as
sub-packages under `apps/api/app/` — see `docs/LAYER_1_FOUNDATION.md`
§"Deviations from the spec's suggested layout" for the reasoning, and
revisit this once a second service actually needs to import one.
