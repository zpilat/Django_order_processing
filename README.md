# Django Order Processing

Interní aplikace pro správu zakázek od příjmu přes tepelné zpracování a kontrolu kvality až po expedici. Eviduje zákazníky, kamiony, zakázky, bedny, šarže a jejich průchody pracovišti. Obsluha pracuje v Django administraci nebo v provozních obrazovkách se skenováním kódů.

## Funkce

- Import dodacích listů z XLSX s náhledem, validací a atomickým uložením; artikly zůstávají textem.
- Evidence beden, technologických stavů, pozic, priorit, pozastavení a historie změn.
- Rychlé založení šarže pro pracoviště 1–6, zadání beden do pater roštu a tisk průvodky.
- Deník kroků šarže, přesuny mezi pracovišti a začátek i konec včetně data.
- Skenování beden kamerou nebo čtečkou, provozní změny stavů a zobrazení pohybu.
- Kontrola beden: jednotlivá měření, čistota, uložení, počty křivých vrutů, uvolnění a důvody neshody.
- Import chemických měření z JSON exportů analyzátoru Vanta s náhledem a archivací souborů.
- Přehledy nakládání, pracovišť, kontroly a neshod; dashboardy beden, kamionů, výroby a rovnání včetně historie.
- Expedice zakázek a vybraných beden, rozdělení nehotové části zakázky a přiřazení do existujícího kamionu výdej.
- PDF karty beden, KKK, průvodky šarží, dodací listy, certifikáty a proforma faktury. Vyplněné KKK jsou podporované pro EUR.
- Oprávnění podle úkolu a audit přes `django-simple-history`.

## Lokální spuštění na Windows

Projekt používá **PostgreSQL v produkci i při běžném lokálním vývoji**. Připravte lokální databázi a roli s přístupem k ní. Závislosti jsou v [requirements.txt](requirements.txt), včetně Django 5.2, pandas, openpyxl, psycopg a WeasyPrint.

Použijte existující virtuální prostředí `venv`. Při prvním založení vytvořte prostředí dostupným interpretem Pythonu:

```powershell
python -m venv venv
```

Další příkazy spouštějte z kořene repozitáře přes toto prostředí:

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements.txt
```

Vytvořte lokální `.env` (je ignorovaný Gitem). Zástupné hodnoty nahraďte vlastními:

```dotenv
DJANGO_SECRET_KEY=nahraďte-vlastním-náhodným-tajným-klíčem
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DJANGO_DB_ENGINE=postgres
POSTGRES_DB=orders_local
POSTGRES_USER=orders_local_user
POSTGRES_PASSWORD=vaše_lokální_heslo
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
```

```powershell
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py createsuperuser
.\venv\Scripts\python.exe manage.py runserver
```

Otevřete `http://127.0.0.1:8000/` nebo `/admin/`. Účet s příznakem staff se z úvodní stránky přesměruje do administrace; ostatní přihlášení uživatelé dostanou provozní rozcestník. Operace vyžadují přidělená oprávnění. Naplňte číselníky zákazníků, předpisů, pozic a pracovišť. Rychlé založení šarže potřebuje jednoznačně určené pracoviště typu **Nakládání**.

WeasyPrint potřebuje také systémové knihovny pro vykreslování textu. Při selhání PDF ověřte jejich instalaci a načítání statických souborů podle `WEASYPRINT_BASEURL` v [settings.py](order_processing/settings.py).

### Volba databáze

`DJANGO_DB_ENGINE=postgres` nastavte výslovně i lokálně. Bez této proměnné současný kód vybírá při `DJANGO_DEBUG=True` SQLite a při vypnutém debug režimu PostgreSQL. Explicitní volba má přednost.

SQLite (`DJANGO_DB_ENGINE=sqlite`, soubor `db.sqlite3`) je jen volitelná náhrada; její použití při ověřování vždy uveďte. Migrace transformující existující data před předáním ověřte v celém migračním sledu na PostgreSQL, ideálně na stagingu nebo obnovené anonymizované kopii produkce. Data měnící `RunPython` a následnou změnu schématu stejné tabulky rozdělte do samostatných migrací. U migrací měnících pouze schéma postačuje běžné lokální ověření i na SQLite.

## Uživatelská dokumentace

Manuály jsou v češtině a obsahují postupy, omezení a řešení běžných chyb.

| Agenda | Návod |
| --- | --- |
| Stručný postup od příjmu po expedici pro obsluhu | [Provozní tahák](docs/provozni_tahak.md) |
| Celý průchod šarže pracovišti, kontrola a ukončení | [Průchod šarže výrobou](docs/manual_pruchod_sarze.md) |
| Bedny, stavy, filtry, akce a skenování | [Bedny](docs/manual_bedna.md) |
| Nakládání, patra, rozdělení roštu a průvodka | [Rychlé založení šarže s bednami](docs/manual_rychle_zalozeni_sarze.md) |
| Měření, výstupní kontrola, uvolnění a neshody | [Kontrola beden](docs/manual_kontrola_beden.md) |
| Příjem, kompletnost a expedice zakázek | [Zakázky](docs/manual_zakazka.md) |
| Importy, příjem a výdej kamionů, doklady | [Kamiony](docs/manual_kamion.md) |
| Šarže, kroky, deník a přesuny | [Deník beden v krocích šarže](docs/manual_denik_pece.md) |
| Představení aplikace týmu | [Prezentace](docs/prezentace.md) |
| Oprávnění, audit a provozní nastavení | [Bezpečnost](docs/security.md) |

## Importy a tisk

Import XLSX spouštějte nad právě jedním kamionem příjem bez zakázek. Nejprve zkontrolujte náhled a potom potvrďte import. Formát se řídí strategií zákazníka (například EUR nebo SPX); limit velikosti souboru nastavuje `EXCEL_UPLOAD_MAX_SIZE_MB` (výchozí 10 MB). Nahraný soubor se zachová mezi náhledem a potvrzením.

Chemická měření se importují samostatnou akcí nad jedním kamionem příjem s bednami. Import čte JSONy z `CHEMISTRY_INCOMING_DIR`, kontroluje dostupnost exportů Vanta a archivuje zpracované soubory do `CHEMISTRY_ARCHIVE_DIR`. Postup je v [manuálu kamionů](docs/manual_kamion.md).

Tiskové akce jsou dostupné v seznamech beden, zakázek a kamionů podle kontextu a oprávnění. Prázdné KKK a vyplněné KKK (EUR) mají samostatné akce. Přehled rychlého založení poskytuje náhled průvodky; „Bedny k navezení“ mají vlastní tisk a PDF.

## Struktura projektu

- `order_processing/`: nastavení, hlavní URL a middleware.
- `orders/`: modely, admin, akce, filtry, formuláře, views a importní strategie.
- `orders/services/`: expedice, PDF, měření, chemické importy a historie.
- `orders/tests/`: testy modelů, formulářů, akcí, adminu a provozních postupů.
- `orders/management/commands/`: provozní příkazy, například `rozpracovanost`.
- `templates/`, `orders/templates/`: administrační, provozní a tiskové šablony.
- `orders/static/`: zdrojové styly a skripty; `staticfiles/`: výstup `collectstatic`.
- `deploy/`: podpůrné skripty včetně synchronizace exportů Vanta.
- `docs/`: uživatelská a provozní dokumentace.

## Ověření a testy

```powershell
.\venv\Scripts\python.exe manage.py check
.\venv\Scripts\python.exe manage.py test
```

Testy standardně spouštějte na PostgreSQL. Django vytváří samostatnou testovací databázi; databázová role potřebuje oprávnění `CREATEDB`. Při změně funkce ověřte zejména validaci, oprávnění, stavové přechody a souběžné úpravy.

## Nasazení

Hodinové zálohování produkční PostgreSQL s uchováním tří dnů je připravené ve
skriptu [deploy/backup-orders.sh](deploy/backup-orders.sh). Nastavení hesla,
cronu a ověření obnovy popisuje [návod na zálohy](docs/zalohy.md).

Nastavte vlastní `DJANGO_SECRET_KEY`, `DJANGO_DEBUG=False`, `DJANGO_ALLOWED_HOSTS` a připojení PostgreSQL. Pro HTTPS za reverzní proxy nastavte podle prostředí `DJANGO_CSRF_TRUSTED_ORIGINS`; proxy musí správně předávat a řídit hlavičku `X-Forwarded-Proto`. Produkční nastavení zapíná zabezpečené cookies a standardně přesměrovává HTTP na HTTPS. HSTS se řídí samostatnými proměnnými, výchozí délka je 0.

Před nasazením proveďte zálohu databáze, migrace, `collectstatic` a `check --deploy`. Aplikaci provozujte pomocí WSGI/ASGI serveru a reverzní proxy. Podrobnosti jsou v [bezpečnostním přehledu](docs/security.md).

## Licence

GNU General Public License v3.0 (GPL-3.0), viz [LICENSE](LICENSE).
