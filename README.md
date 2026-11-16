# Smart Delivery Operations

A full-stack delivery planning and operations app with a FastAPI backend and a
React frontend. It includes account login, role-based access, synthetic data
generation, route planning and delivery simulation.

## Run it

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Set BOOTSTRAP_ADMIN_USERNAME and BOOTSTRAP_ADMIN_PASSWORD in .env to create
# the initial operations manager account.
uvicorn app.main:app --reload
```

New users can create accounts from the frontend login screen. Public signups
receive the carrier / warehouse operator role. The optional bootstrap settings
create the initial operations manager account on backend startup; keep their
values private and do not commit `.env`. The interactive API documentation is
at `http://127.0.0.1:8000/api/v1/docs`.

Run the frontend in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

The frontend is available at `http://127.0.0.1:5173`.

## Roles

| Role | Access |
| --- | --- |
| Supplier | Read sites, deliveries, and routes |
| Planner | Read operational data and run route optimization |
| Carrier / warehouse operator | Read fleet and route data and run delivery simulation |
| Logistics analyst | Read delivery and route data and view analytics |
| Operations manager | Full access, including synthetic data generation |

User passwords are hashed and sessions expire after seven days. Add additional
account provisioning and production-grade identity protections before exposing
this service to the public internet.

## API overview

- `GET /api/v1/health`
- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- `POST /api/v1/auth/logout`
- `POST /api/v1/data/generate` (manager)
- `GET /api/v1/sites`, `GET /api/v1/deliveries`
- `GET /api/v1/vehicles`, `GET /api/v1/drivers`
- `POST /api/v1/optimization/run` (planner)
- `GET /api/v1/routes`, `GET /api/v1/routes/{route_id}`
- `POST /api/v1/simulation/{route_id}/run` (carrier / warehouse operator)
- `GET /api/v1/analytics/summary` (analyst)

Generate a small local dataset by posting JSON to `/api/v1/data/generate`:

```json
{"sites":30,"deliveries":100,"vehicles":10,"seed":20261022,"reference_date":"2026-10-22"}
```

SQLite is used by default. Set `DATABASE_URL` to point at PostgreSQL when a
PostgreSQL driver and deployment configuration are added.

Run backend tests with:

```powershell
cd backend
pip install -r requirements-dev.txt
python -m pytest
```

## Current scope

The route solver uses OR-Tools with weight capacity, volume capacity, customer
time windows, service time, driver shift limits, and delivery vehicle-type
restrictions. It uses exact site-to-site traffic samples for the generation
date, depot samples for a 30-day horizon, and derives documented estimates
when an exact edge/date sample is unavailable. The simulator records actual
arrival/departure timestamps and appends every run to `outcome_events`.

The seeded generator adds effective-dated vehicle capacities and time windows,
variable service windows, VAN/TRUCK restrictions, one labeled over-capacity
delivery, one labeled out-of-region site, and five isolated negative scenario
fixtures. The fixtures cover an over-capacity route, duplicate and omitted
stops, an arrival before the previous departure, and a driver shift overrun.
Fixtures and ground-truth labels are not optimizer inputs. The data tools are
available to an operations manager:

- `GET /api/v1/data/validate` returns a validation summary.
- `GET /api/v1/data/export.json` exports all operational tables, a separate
  `ground_truth` section, and the dataset manifest.
- `GET /api/v1/data/export.zip` exports per-entity CSV files, separate ground
  truth CSV files, and `manifest.json`.
- `GET /api/v1/data/export.sql` exports SQLite schema and seed statements,
  excluding authentication users and sessions.
- `GET /api/v1/data/export.csv` exports deliveries.

The default random seed is `20261022`. To reproduce a dataset, keep both its
seed and `reference_date` unchanged; the generated checksum is included in the
manifest. All records are synthetic; no external dataset is used. Data
generation replaces the current synthetic operational dataset, while
simulation history is retained as snapshots. See
[docs/data-dictionary.md](docs/data-dictionary.md) for field definitions,
relationships, units, validation rules, and lifecycle details. No TypeScript
files or TypeScript dependencies are used.
