# Django Order Processing

Systém pro správu zakázek od příjmu přes zpracování až po expedici, včetně práce s bednami, kamiony, importu z XLSX a tisku PDF dokumentů. Postaveno na Django, pandas a WeasyPrint.

## ✨ Funkce

- Dashboardy:
  - stav beden podle zákazníka,
  - měsíční přehled příjmu/výdeje kamionů,
  - přehled „Bedny k navezení“ s tiskem a PDF exportem.
- Import zakázek z XLSX:
  - náhled před importem (bez zápisu do DB),
  - robustní normalizace pole artiklu (vždy text, bez koncovky `.0`),
  - validace a atomický import (all-or-nothing),
  - zachování nahraného souboru mezi náhledem a potvrzením.
- Tisk a PDF (WeasyPrint):
  - karty beden a KKK,
  - dodací listy a proforma faktury,
  - PDF export přehledu „Bedny k navezení“.
- Admin akce a workflow:
  - expedice zakázek (včetně rozdělení nepřipravených beden do nové zakázky),
  - označení beden k navezení s kontrolou kapacit,
  - bohaté filtry podle stavu, délky, tryskání, rovnání, priority, zákazníka atd.
- Historie změn přes `django-simple-history`.

## 🚀 Rychlý start

- Požadavky: Python 3.11+, pip. Databáze: SQLite (výchozí). Podporováno na Linux a Windows.
- Instalace a spuštění:
  1. Vytvořte a aktivujte virtuální prostředí.
  2. Nainstalujte závislosti: `pip install -r requirements.txt`.
  3. Proveďte migrace: `python manage.py migrate`.
  4. Vytvořte administrátora: `python manage.py createsuperuser`.
  5. Spusťte server: `python manage.py runserver` a otevřete `http://127.0.0.1:8000/admin/`.

Poznámka k PDF: WeasyPrint je součástí závislostí. Na Windows většinou funguje bez dalších kroků. Pokud chybí systémové knihovny (Cairo/Pango), postupujte podle oficiální dokumentace WeasyPrint.

## 📥 Import XLSX

- Přístup: v Django adminu přes stránku importu zakázek (náhled + potvrzení importu).
- Podporovaný formát: `.xlsx` (openpyxl).
- Náhled: zobrazí zpracovaná data bez zápisu do databáze.
- Import: atomický (buď vše, nebo nic) s hlášením chyb/varování.
- Pole „artikl“: vždy se ukládá jako text. Čistě číselné buňky se nepřevádí na float (`902925.0` -> `902925`).

Tipy:

- Pokud Excel míchá čísla a texty v artiklu, import zůstává stabilní a výsledek je vždy text.
- Pokud import selže, zkontrolujte hlavičky a že jde opravdu o `.xlsx`.

## 🖨️ Tisk a PDF

- Karty beden a KKK: dostupné jako admin akce nad vybranými záznamy.
- Dodací list a proforma: dostupné jako akce nad vybraným kamionem.
- „Bedny k navezení“: vlastní tisková stránka a PDF export.

## 🧭 Struktura projektu (výběr)

- `order_processing/` - nastavení projektu a URL.
- `orders/` - hlavní aplikace (modely, admin, akce, filtry, formuláře, views, utils).
- `templates/` a `orders/templates/` - šablony včetně tiskových výstupů.
- `static/` a `staticfiles/` - statické soubory.
- `requirements.txt` - závislosti (Django, pandas, openpyxl, WeasyPrint, django-simple-history, ...).

## 📚 Uživatelské manuály

- [Manuál pro bedny](docs/manual_bedna.md) - manuál práce s bednami (`Bedna`, `BednaAdmin`).
- [Manuál pro zakázky](docs/manual_zakazka.md) - manuál práce se zakázkami (`Zakazka`, `ZakazkaAdmin`).
- [Manuál pro kamióny](docs/manual_kamion.md) - manuál práce s kamiony (`Kamion`, `KamionAdmin`).
- [Manuál pro deník pece](docs/manual_denik_pece.md) - manuál práce s deníkem pece (`SarzeBedna`, `SarzeBednaAdmin`).

## 🧪 Testy

- Spuštění testů: `python manage.py test`
- Doporučení: při rozšíření funkcí doplnit testy hlavně pro import a klíčové admin akce.

## 🚢 Nasazení

- Vypněte `DEBUG` a nastavte `ALLOWED_HOSTS`.
- Pro statické soubory spusťte `collectstatic`.
- Pro produkci zvažte PostgreSQL a WSGI/ASGI server (např. gunicorn/uvicorn + reverse proxy).

## 🛠️ Řešení problémů

- Problémy s PDF: ověřte verzi WeasyPrint a dostupnost systémových knihoven.
- Problémy s importem: ověřte `.xlsx`, očekávané hlavičky a chybová hlášení z náhledu.

## 📜 Licence

Projekt je licencován pod GNU General Public License v3.0 (GPL-3.0). Kompletní text je v souboru `LICENSE` nebo na https://www.gnu.org/licenses/gpl-3.0.en.html.
