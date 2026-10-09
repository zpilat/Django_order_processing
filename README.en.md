# Django Order Processing

Internal application for receiving, heat treating, inspecting and shipping orders. It tracks customers, inbound/outbound trucks, orders, crates, batches and workstation steps. Users work in Django Admin or operational pages with code scanning.

## Features

- XLSX delivery note import with preview, validation and atomic saving; article numbers remain strings.
- Crate states, warehouse positions, priorities, paused items and change history.
- Quick batch creation for workstations 1–6, crates arranged into rack floors and traveler printing.
- Batch step logs, workstation transfers and start/end dates and times.
- Camera and reader scanning, operational state changes and crate movement history.
- Crate inspection: individual measurements, cleanliness, placement, bent screw counts, release decisions and nonconformity reasons.
- Chemical measurement import from Vanta JSON exports, with preview and processed file archiving.
- Loading, workstation, inspection and nonconformity overviews; production, straightening, crate and truck dashboards with history.
- Shipment of orders or selected crates, splitting unfinished crates into another order and adding shipments to an existing outbound truck.
- PDF crate cards, quality control cards (KKK), batch travelers, delivery notes, certificates and proforma invoices. Filled KKK are supported for EUR.
- Task permissions and auditing through `django-simple-history`.

## Local setup on Windows

**PostgreSQL is used both locally and in production.** Prepare a local database and database role. Dependencies are pinned in [requirements.txt](requirements.txt), including Django 5.2, pandas, openpyxl, psycopg and WeasyPrint.

Use the existing `venv`. For a fresh checkout, create it with an available Python interpreter:

```powershell
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Create a local `.env` (ignored by Git), replacing the placeholders:

```dotenv
DJANGO_SECRET_KEY=replace-with-your-own-random-secret
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DJANGO_DB_ENGINE=postgres
POSTGRES_DB=orders_local
POSTGRES_USER=orders_local_user
POSTGRES_PASSWORD=your_local_password
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
```

Run commands from the repository root using its virtual environment:

```powershell
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py createsuperuser
.\venv\Scripts\python.exe manage.py runserver
```

Open `http://127.0.0.1:8000/` or `/admin/`. Staff accounts are redirected from the home page to Admin; other authenticated users see the operational menu. Assign task permissions and populate customer, specification, position and workstation records. Quick batch creation requires an unambiguous workstation of type **Nakládání** (loading).

WeasyPrint also needs system text rendering libraries. If PDF generation fails, check those libraries and static asset loading through `WEASYPRINT_BASEURL` in [settings.py](order_processing/settings.py).

### Database selection

Set `DJANGO_DB_ENGINE=postgres` explicitly for local development. In the current settings, omitting it selects SQLite when `DJANGO_DEBUG=True`, and PostgreSQL otherwise. An explicit engine overrides that fallback.

SQLite (`DJANGO_DB_ENGINE=sqlite`, `db.sqlite3`) is optional; always report its use when validating changes. Migrations that transform existing data must be tested through the complete migration path on PostgreSQL, preferably staging or a restored anonymized production copy. Separate data-changing `RunPython` from later schema alterations on the same table. Schema-only migrations may be handed off after normal local checks on SQLite.

## Documentation

User manuals are in Czech:

| Topic | Manual |
| --- | --- |
| Printable guide from receipt to shipment | [Operational quick reference](docs/provozni_tahak.md) |
| Batch workstation steps, inspection and completion | [Batch production workflow](docs/manual_pruchod_sarze.md) |
| Crates, states, actions and scanning | [Crates](docs/manual_bedna.md) |
| Loading a batch, rack floors and traveler printing | [Quick batch creation with crates](docs/manual_rychle_zalozeni_sarze.md) |
| Measurements, release and nonconformities | [Crate inspection](docs/manual_kontrola_beden.md) |
| Order receipt, completeness and shipment | [Orders](docs/manual_zakazka.md) |
| Truck imports, receipt, shipment and documents | [Trucks](docs/manual_kamion.md) |
| Batch steps, logs and transfers | [Batch step log](docs/manual_denik_pece.md) |
| Application overview | [Presentation](docs/prezentace.md) |
| Permissions, auditing and deployment settings | [Security](docs/security.md) |

## Imports and printing

Start XLSX import for exactly one inbound truck without orders. Review the preview before confirming. Customer strategies (such as EUR and SPX) define the file layout. `EXCEL_UPLOAD_MAX_SIZE_MB` controls file size (10 MB by default); the uploaded file is retained between preview and confirmation.

Chemical import is a separate action for an inbound truck with crates. It reads JSON files from `CHEMISTRY_INCOMING_DIR`, checks Vanta export availability and archives processed files to `CHEMISTRY_ARCHIVE_DIR`. See the [truck manual](docs/manual_kamion.md).

Printing actions depend on selected objects, filters and permissions. Blank KKK and filled KKK (EUR) are separate actions. The quick batch overview provides a traveler print preview; the crates to be moved overview has dedicated print and PDF outputs.

## Project structure

- `order_processing/`: settings, root URLs and middleware.
- `orders/`: models, admin, actions, filters, forms, views and import strategies.
- `orders/services/`: shipping, PDF, measurements, chemical import and history.
- `orders/tests/`: model, form, action, admin and workflow tests.
- `orders/management/commands/`: operational commands, including `rozpracovanost`.
- `templates/`, `orders/templates/`: admin, operational and print templates.
- `orders/static/`: source assets; `staticfiles/`: `collectstatic` output.
- `deploy/`: supporting scripts, including Vanta export synchronization.
- `docs/`: user and operational documentation.

## Checks and tests

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py test
```

Use PostgreSQL for normal tests. Django creates a separate test database; the database role needs `CREATEDB`. Validate permissions, state transitions, input validation and concurrent edits when changing a workflow.

## Deployment

For hourly PostgreSQL production backups with three-day retention, use
[deploy/backup-orders.sh](deploy/backup-orders.sh). See the Czech
[backup setup guide](docs/zalohy.md) for credentials, cron and restore checks.

Set `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS` and PostgreSQL credentials. Configure `DJANGO_CSRF_TRUSTED_ORIGINS` for the deployment and ensure the reverse proxy controls `X-Forwarded-Proto`. Production settings enable secure cookies and HTTPS redirection by default. HSTS is configured separately and defaults to a duration of 0.

Back up the database, apply migrations, run `collectstatic` and `check --deploy`, and serve the application through a WSGI/ASGI server and reverse proxy. See [security settings](docs/security.md).

## License

GNU General Public License v3.0 (GPL-3.0), see [LICENSE](LICENSE).
