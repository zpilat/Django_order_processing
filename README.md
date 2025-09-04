# Django Order Processing

Order management system for receiving, processing, and shipping orders, including crates management, trucks, and PDF printing. Built with Django, XLSX import via pandas, and PDF via WeasyPrint.

## ✨ Features

- Dashboards:
  - Crates status per customer.
  - Monthly truck inbound/outbound with aggregates.
  - “Crates to be moved” view with clean print and PDF export.
- XLSX order import:
  - Preview before import (no DB writes).
  - Robust normalization of “article number” (always a string, no trailing “.0”).
  - Strict `.xlsx` (openpyxl), validation, and atomic import (all-or-nothing).
  - Persist selected file between preview and import.
- Printing and PDF (WeasyPrint):
  - Crate production cards and Quality Control cards (KKK).
  - Delivery notes and proforma invoices for trucks.
  - PDF for the “crates to be moved” dashboard.
- Admin actions and workflow:
  - Expedite orders (with split of non-ready crates into a new order).
  - Mark crates “to be moved” with position selection and capacity checks.
  - Rich admin filters (state, length, blasting, straightening, priority, customer, …).
- See / change history with django-simple-history.

## 🚀 Quick start

- Requirements: Python 3.11+, pip. DB: SQLite (default). Windows supported.
- Install and run:
  1) Create and activate a virtual environment.
  2) Install dependencies: `pip install -r requirements.txt`.
  3) Migrate: `python manage.py migrate`.
  4) Create superuser: `python manage.py createsuperuser`.
  5) Start: `python manage.py runserver` and open `http://127.0.0.1:8000/admin/`.

PDF note: WeasyPrint ships as a dependency. On Windows it usually works out of the box. If system libs (Cairo/Pango) are missing, follow WeasyPrint docs.

## 📥 XLSX import

- Access: in Django Admin, open the orders import page (preview + import flow).
- Supported files: `.xlsx` (openpyxl only).
- Preview: shows normalized data without writing to DB.
- Import: atomic (all-or-nothing) with errors/warnings reporting.
- Field “article number” (artikl): always stored as text. Numeric-only cells are not converted to floats (e.g., `902925.0` → `902925`).

Tips:
- If Excel mixes numbers and texts in “Artikel-nummer”, import is robust and the final value is always a string.
- If import fails, double-check headers and `.xlsx` format.

## 🖨️ Printing & PDF

- Crate production cards and KKK: available as admin actions for selected objects.
- Truck delivery note and proforma: actions on the chosen truck.
- “Crates to be moved”: dedicated print page and PDF export (clean print styles).

## 🧭 Project structure (selected)

- `order_processing/` – project settings and URLs.
- `orders/` – main app (models, admin, actions, filters, forms, views, utils).
- `templates/` and `orders/templates/` – templates including printing.
- `static/` and `staticfiles/` – static assets.
- `requirements.txt` – dependencies (Django, pandas, openpyxl, WeasyPrint, django-simple-history, …).

## 🧪 Tests

- Run tests: `python manage.py test`
- Recommendation: add tests for import and key admin actions when extending features.

## 🚢 Deployment

- Disable DEBUG and set `ALLOWED_HOSTS`.
- For static assets run `collectstatic`.
- Consider production DB (PostgreSQL) and a WSGI/ASGI server (gunicorn/uvicorn + reverse proxy).

## 🛠️ Troubleshooting

- PDF issues: check WeasyPrint version and system libraries as per docs.
- Import issues: ensure the file is `.xlsx` and contains expected headers; check preview error messages.

## 📜 License

This project is licensed under the GNU General Public License v3.0 (GPL-3.0). See the `LICENSE` file for the full text or visit https://www.gnu.org/licenses/gpl-3.0.en.html.
