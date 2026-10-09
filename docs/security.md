# Bezpečnost a audit aplikace

Tento dokument popisuje ochrany použité v projektu a nastavení pro jeho provoz. Zdrojové nastavení je v [settings.py](../order_processing/settings.py), řízení operací v adminu, views a formulářích aplikace `orders`.

## Přihlášení a oprávnění

Projekt používá autentizaci a relace Djanga. Administrace vyžaduje účet s příznakem staff a příslušná oprávnění; provozní obrazovky jsou dostupné přihlášeným uživatelům podle oprávnění dané operace.

Speciální oprávnění řídí úpravy expedovaných a pozastavených beden, nepřijatých beden a jejich poznámek, navezení, označení jako zakalené či zkontrolované a řízení šarží. Podrobnosti jsou v [manuálu beden](manual_bedna.md), [kontroly](manual_kontrola_beden.md) a [rychlého založení šarže](manual_rychle_zalozeni_sarze.md).

Hesla spravuje Django; projekt nemá vlastní `PASSWORD_HASHERS`, používá tedy výchozí konfiguraci s PBKDF2. Instalované knihovny Argon2 či bcrypt samy nezmění zvolený algoritmus. Projekt má zapnuté validátory podobnosti hesla, minimální délky, běžných hesel a čistě číselných hesel. Viz [správa hesel v Django 5.2](https://docs.djangoproject.com/en/5.2/topics/auth/passwords/).

## Ochrany požadavků a šablon

- ORM parametrizuje běžné databázové dotazy.
- Django šablony standardně escapují hodnoty při výstupu do HTML; vlastní použití `safe` a `mark_safe` vyžaduje správné zacházení s obsahem.
- `CsrfViewMiddleware` a tokeny ve formulářích chrání změnové požadavky.
- `XFrameOptionsMiddleware` nastavuje ochranu proti vložení stránky do rámce.
- `SecurityMiddleware` zajišťuje nastavené bezpečnostní hlavičky a přesměrování.

Principy a meze těchto ochran popisuje [bezpečnostní dokumentace Django 5.2](https://docs.djangoproject.com/en/5.2/topics/security/).

## Produkční nastavení

Konfigurace se načítá z prostředí a lokálního `.env`. Skutečné klíče a hesla do dokumentace ani repozitáře nevkládejte.

| Nastavení | Použití |
| --- | --- |
| `DJANGO_SECRET_KEY` | Vlastní tajný klíč prostředí; kód nemá pevně zadaný náhradní klíč. |
| `DJANGO_DEBUG=False` | Produkční režim. |
| `DJANGO_ALLOWED_HOSTS` | Povolené hosty oddělené čárkou. |
| `DJANGO_DB_ENGINE=postgres`, `POSTGRES_*` | PostgreSQL v produkci i lokálně; explicitní volba brání přepnutí na SQLite v debug režimu. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Důvěryhodné originy včetně schématu, oddělené čárkou. |
| `DJANGO_SECURE_SSL_REDIRECT` | Při vypnutém debug režimu výchozí `True`. |
| `DJANGO_SECURE_HSTS_SECONDS` | Výchozí 0; HSTS se zapíná výslovně podle nasazení. |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS`, `DJANGO_SECURE_HSTS_PRELOAD` | Výchozí `False`. |
| `DJANGO_X_FRAME_OPTIONS` | V produkci výchozí `DENY`. |
| `DJANGO_SECURE_REFERRER_POLICY` | V produkci výchozí `strict-origin-when-cross-origin`. |

V produkci jsou zapnuté `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` a `SECURE_CONTENT_TYPE_NOSNIFF`. Cookies mají názvy `sessionid_orders` a `csrftoken_orders`.

Nastavení důvěřuje `X-Forwarded-Proto: https` prostřednictvím `SECURE_PROXY_SSL_HEADER`. Reverzní proxy musí tuto hlavičku řídit, aby ji klient nemohl podvrhnout. Před nasazením spusťte z virtuálního prostředí `manage.py check --deploy` nad konfigurací příslušného prostředí.

## Integrita dat a historie

`django-simple-history` a middleware historie evidují změny sledovaných modelů a uživatele. Kontroly a měření beden mají historii; rozhodnutí o uvolnění má také aktuálního autora a čas.

Zápis kontroly i jednotlivých měření porovnává odeslaný stav s aktuálním záznamem. Při souběžné změně jiným uživatelem se uložení odmítne a obsluha načte aktuální údaje. Zápis používá transakce a uzamčení bedny.

Validace hlídá povinné údaje, povolené kombinace stavů, pozastavení beden, podíly pater a datum i čas konce kroku. Mazání je omezené podle výrobního stavu a souvisejících záznamů. Historie doplňuje provozní dohledatelnost; obnovu dat zajišťují zálohy databáze.

## Importy a soubory

XLSX import má náhled, validaci a atomické uložení. Velikost omezuje `EXCEL_UPLOAD_MAX_SIZE_MB` (výchozí 10 MB); limit na reverzní proxy nastavte v souladu s aplikací.

Chemický import pracuje s adresáři `CHEMISTRY_INCOMING_DIR` a `CHEMISTRY_ARCHIVE_DIR`. Synchronizace a kontrola dostupnosti Vanta používají nastavení `VANTA_SMB_*` a soubor přístupových údajů. Přístup k těmto souborům, archivu a provozním logům přidělte podle potřeb služby a správců.

Statické soubory obsluhuje WhiteNoise z výstupu `collectstatic`. Na produkci načítá PDF statické prostředky přes `WEASYPRINT_BASEURL` odvozené ze `STATIC_ROOT`.

## Související dokumentace

[Instalace a testy](../README.md) · [Kamiony a importy](manual_kamion.md) · [Kontrola beden](manual_kontrola_beden.md)
