# Automatické zálohy produkční databáze

[Skript backup-orders.sh](../deploy/backup-orders.sh) vytváří dump databáze
`orders_prod` každou hodinu při spuštění cronem a po úspěšném uložení maže
automatické dumpy staré alespoň 72 hodin. Při pravidelném provozu tak zůstává
přibližně 72 záloh. Při chybě nové zálohy se starší zálohy nemažou.

Nastavení automatických záloh níže je pro **Linux s cronem, Bashem, GNU find a flock**.
Přenos do vývoje na Windows popisuje kapitola
[Přepsání lokální dev databáze produkčním dumpem](#přepsání-lokální-dev-databáze-produkčním-dumpem).
Skript používá stejné
připojení a formát jako ruční příkaz: `127.0.0.1:5432`, role `orders_user`,
databáze `orders_prod`, `pg_dump -F c -b -v`. Potřebuje také `pg_restore`;
použijte klientské nástroje stejné hlavní verze jako produkční PostgreSQL.

## 1. Přihlášení bez zadávání hesla

Následující kroky proveďte pod **stejným linuxovým uživatelem, jehož crontab bude
zálohy spouštět**. Databázová role `orders_user` je samostatný účet PostgreSQL.

```bash
touch ~/.pgpass
chmod 600 ~/.pgpass
nano ~/.pgpass
```

Do souboru doplňte řádek s reálným heslem:

```text
127.0.0.1:5432:orders_prod:orders_user:SEM_PATRI_HESLO
```

Pokud heslo obsahuje `:` nebo `\`, musí být v tomto souboru escapované jako
`\:` a `\\`. Soubor neukládejte do Gitu. PostgreSQL na Linuxu ignoruje soubor,
pokud má přístup i skupina nebo ostatní uživatelé; `chmod 600` je proto nutný.
Skript používá `-w`, takže při nedostupném hesle skončí chybou místo čekání na
vstup. Viz [dokumentace .pgpass](https://www.postgresql.org/docs/current/libpq-pgpass.html)
a [pg_dump](https://www.postgresql.org/docs/current/app-pgdump.html).

## 2. Ruční ověření na produkčním serveru

V příkladech nahraďte `/home/pilat/Django_order_processing` skutečnou absolutní
cestou k repozitáři a `/home/pilat/archiv` cestou ke svému archivu. Zálohy ani
heslo nepatří do adresářů veřejně dostupných přes webový server.

```bash
mkdir -p /home/pilat/archiv
/bin/bash /home/pilat/Django_order_processing/deploy/backup-orders.sh /home/pilat/archiv
ls -lh /home/pilat/archiv/orders_prod_auto_*.dump
```

Uživatel musí mít do archivu právo zápisu. Bez argumentu skript používá
`../archiv` vůči kořeni repozitáře, nezávisle na aktuálním pracovním adresáři.
Nové soubory vytváří s právy pouze pro vlastníka. Zálohy se jmenují
`orders_prod_auto_YYYYMMDD_HHMMSS.dump`; mazání zahrnuje pouze tento formát názvu
přímo v určeném archivu. Ruční dumpy `orders_prod_YYYYMMDD_HHMMSS.dump` spravujte
samostatně.

Zámek brání souběhu dvou spuštění nad stejným archivem. Dump vzniká jako skrytý
soubor `.part`, na konečný název se přejmenuje až po úspěšném `pg_dump` a načtení
obsahu archivu pomocí `pg_restore --list`. Při běžné chybě se dočasný soubor
odstraní. Po výpadku napájení nebo `SIGKILL` může zůstat `.part`; automatické
mazání jej nezahrnuje.

## 3. Spouštění každou hodinu

```bash
crontab -e
```

Do crontabu přidejte (existující úlohy ponechte):

```cron
PATH=/usr/local/bin:/usr/bin:/bin
0 * * * * /bin/bash /home/pilat/Django_order_processing/deploy/backup-orders.sh /home/pilat/archiv >> /home/pilat/archiv/orders_backup.log 2>&1
```

Pokud jsou `pg_dump` a `pg_restore` mimo uvedené adresáře, přidejte jejich
adresář do `PATH`. Každou celou hodinu podle času serveru vznikne nová záloha.
Cron po vypnutí serveru vynechané běhy nedoplňuje. Staré dumpy se uklidí při
dalším úspěšném běhu, takže během výpadku mohou zůstat i déle než tři dny.

Ověřte záznam úlohy a po další celé hodině vznik nového dumpu:

```bash
crontab -l
tail -n 50 /home/pilat/archiv/orders_backup.log
ls -lht /home/pilat/archiv/orders_prod_auto_*.dump | head
```

Úspěšný běh končí řádkem `DONE`. Chyby jsou v témže logu. Log sám skript
nemaže; pro pravidelnou rotaci lze do `/etc/logrotate.d/orders-backup` uložit
(uživatele a skupinu nahraďte vlastními):

```text
/home/pilat/archiv/orders_backup.log {
    su pilat pilat
    daily
    rotate 7
    compress
    missingok
    notifempty
    copytruncate
}
```

## Ověření obnovy a rozsah zálohy

`pg_restore --list` kontroluje čitelnost seznamu obsahu, nikoli úplnou
obnovitelnost dat. Pravidelně ověřte obnovu do **samostatné testovací databáze**,
nikdy přepsáním produkce. Po vytvoření prázdné testovací databáze například:

```bash
pg_restore -h 127.0.0.1 -p 5432 -U orders_user -W --exit-on-error --no-owner --no-privileges \
    -d orders_restore_test /home/pilat/archiv/orders_prod_auto_YYYYMMDD_HHMMSS.dump
```

Testovací databázi musí předem vytvořit oprávněný správce a role `orders_user`
do ní musí mít právo vytvářet objekty. Po obnově ověřte očekávaná data a podle
možností aplikaci připojenou k této testovací databázi.

Dump obsahuje jednu databázi včetně velkých objektů. Role PostgreSQL, soubory
aplikace, nahrané přílohy a konfiguraci zálohujte zvlášť. Ztráta dat mezi dvěma
úspěšnými hodinovými dumpy může být přibližně hodina; při selhávání úloh více.
Pro ochranu při ztrátě serveru ukládejte kopii záloh také mimo tento server.

## Přepsání lokální dev databáze produkčním dumpem

Tento postup slouží k opakované aktualizaci vývojové databáze na novější
produkční data. **Stávající lokální databáze se celá smaže a vytvoří znovu.**
Lokální změny v datech se nezachovávají. Příkazy spouštějte v PowerShellu
na vývojovém počítači s Windows, nikoli v SSH relaci na produkčním serveru.

Obnova probíhá do stejného názvu databáze, který už používá lokální `.env`.
Smazání a nové vytvoření je vhodnější než samotné `pg_restore --clean`, protože
odstraní i lokální tabulky a další objekty, které produkční dump neobsahuje.

### 1. Připravit lokální prostředí

Zastavte lokální `runserver` pomocí Ctrl+C a ukončete další připojení do dev
databáze, například otevřený Django shell nebo dotazovací okno pgAdminu.
Připravte kód odpovídající produkci nebo novější; starší kód nemusí rozumět
schématu v dumpu. Python závislosti nainstalujte podle [README](../README.md).

Potřebujete klientské nástroje PostgreSQL `pg_restore`, `dropdb` a `createdb`.
Použijte stejnou hlavní verzi PostgreSQL jako na produkci, včetně lokálního
databázového serveru. Cesta k nástrojům níže je jen příklad instalace;
nahraďte ji skutečnou cestou a verzí. Pro stažení potřebujete také `scp`
(OpenSSH klient Windows), přístup na server a případně připojenou firemní VPN.

Ve stejném okně PowerShellu nastavte proměnné pro celý postup:

```powershell
Set-Location 'C:\Users\zpilat\Documents\Django_order_processing'
$pgBin = 'C:\Program Files\PostgreSQL\17\bin'
$devPort = '5433'
$devDb = 'orders_dev'
$devRole = 'order_user'
$dbAdmin = 'postgres'
$dumpFile = Join-Path $PWD 'tmp\orders_prod_latest.dump'
& (Join-Path $pgBin 'pg_restore.exe') --version
if ($LASTEXITCODE -ne 0) { throw 'Klientske nastroje PostgreSQL nejsou dostupne.' }
```

Hodnoty `5433`, `orders_dev` a `order_user` odpovídají lokálnímu nastavení
zkontrolovanému 9. 11. 2026. **Na daném počítači je vždy porovnejte s jeho `.env`**:
`POSTGRES_PORT`, `POSTGRES_DB` a `POSTGRES_USER`. Host musí být lokální
`127.0.0.1`. Jiná instalace může používat například port `5432`.
`$dbAdmin` je místní databázový správce s právem databázi smazat a vytvořit;
nemusí se jmenovat `postgres`. Role `$devRole` už musí v místním PostgreSQL
existovat a musíte znát její lokální heslo. Role se dumpem nevytvářejí.

### 2. Stáhnout a zkontrolovat dump před smazáním databáze

Na serveru vyberte dokončený soubor `.dump`, například podle výpisu z kapitoly
Ruční ověření. V následujícím příkazu nahraďte časovou značku, případně také
SSH uživatele, server a cestu. Je-li dump již stažený, nastavte `$dumpFile`
na jeho absolutní cestu a vynechte stahování.

```powershell
New-Item -ItemType Directory -Path (Split-Path -Parent $dumpFile) -Force | Out-Null
scp 'pilat@srv-warehouse:/home/pilat/archiv/orders_prod_auto_YYYYMMDD_HHMMSS.dump' $dumpFile
if ($LASTEXITCODE -ne 0) { throw 'Stazeni dumpu selhalo; databazi nemazte.' }
& (Join-Path $pgBin 'pg_restore.exe') --list $dumpFile
if ($LASTEXITCODE -ne 0) { throw 'Dump nelze precist; databazi nemazte.' }
```

Výpis musí odpovídat očekávané produkční databázi a době zálohy. Kontrola
seznamu ještě nezaručuje úspěšnou obnovu všech dat. Tento postup očekává
archiv vytvořený pomocí `pg_dump -F c`, který používá náš zálohovací skript;
prostý SQL soubor se obnovuje jinak. Dump obsahuje také aplikační uživatele,
jejich heslové hashe, oprávnění a obchodní data; ukládejte jej soukromě.
Adresář `tmp/` je v tomto repozitáři ignorovaný Gitem.

### 3. Smazat dev databázi, vytvořit ji znovu a obnovit data

Zkontrolujte vypsaný cíl: následující příkazy **nevratně přepíšou místní dev**.
Všechna databázová připojení v této kapitole mají výslovně host `127.0.0.1`
a lokální port. Původní produkční databáze ani soubor dumpu se tím nemění.

```powershell
Write-Host "Prepisuji lokalni dev: 127.0.0.1:$devPort / $devDb, vlastnik $devRole"
& (Join-Path $pgBin 'dropdb.exe') -h 127.0.0.1 -p $devPort -U $dbAdmin -W --if-exists $devDb
if ($LASTEXITCODE -ne 0) { throw 'Smazani dev databaze selhalo; nepokracujte.' }
& (Join-Path $pgBin 'createdb.exe') -h 127.0.0.1 -p $devPort -U $dbAdmin -W --owner=$devRole --template=template0 --encoding=UTF8 $devDb
if ($LASTEXITCODE -ne 0) { throw 'Vytvoreni dev databaze selhalo; nepokracujte.' }
& (Join-Path $pgBin 'pg_restore.exe') -h 127.0.0.1 -p $devPort -U $devRole -W --exit-on-error --single-transaction --no-owner --no-privileges --dbname=$devDb $dumpFile
if ($LASTEXITCODE -ne 0) { throw 'Obnova selhala; aplikaci zatim nespoustejte.' }
```

Při mazání a vytváření zadáváte heslo lokálního databázového správce, při
obnově heslo lokální role `$devRole`. Jde o účty PostgreSQL, nikoli přihlášení
do Django administrace. `--no-owner` a `--no-privileges` vynechají produkční
vlastníky a přístupová práva; obnovené objekty vlastní lokální role provádějící
obnovu. `--single-transaction` při chybě vrátí změny obnovy, nevrátí však
původní dev databázi smazanou předchozím příkazem. Při chybě ji můžete znovu
smazat, vytvořit a obnovu opakovat po odstranění příčiny.

### 4. Zkontrolovat `.env` a spustit migrace

Ponechte vlastní lokální `DJANGO_SECRET_KEY` a databázové heslo; produkční
`.env` nekopírujte. Lokální konfigurace pro uvedený příklad obsahuje:

```dotenv
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost
DJANGO_DB_ENGINE=postgres
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5433
POSTGRES_DB=orders_dev
POSTGRES_USER=order_user
POSTGRES_PASSWORD=vase_lokalni_heslo_role_order_user
```

Hodnoty musí odpovídat kroku 1; zástupné heslo nahraďte skutečným lokálním
heslem. Ověřte také, že v prostředí PowerShellu nejsou staré proměnné
`POSTGRES_*` či `DJANGO_*`: již nastavené proměnné mají přednost před `.env`.
Následující příkaz vypíše skutečně použitý cíl bez hesla a ověří připojení:

```powershell
.\venv\Scripts\python.exe manage.py shell -c "from django.db import connection; print(connection.vendor, {k: connection.settings_dict[k] for k in ('HOST', 'PORT', 'NAME', 'USER')}); connection.ensure_connection(); print('Pripojeni OK')"
if ($LASTEXITCODE -ne 0) { throw 'Pripojeni aplikace selhalo.' }
```

Výstup musí ukazovat `postgresql`, `127.0.0.1` a právě obnovenou lokální
databázi. Před dalšími příkazy opravte jakýkoli jiný cíl. Dump už obsahuje
produkční tabulku `django_migrations`; migrace proto spouštějte **až po obnově**,
aby se doplnily pouze změny novějšího lokálního kódu:

```powershell
.\venv\Scripts\python.exe manage.py migrate --plan
if ($LASTEXITCODE -ne 0) { throw 'Plan migraci selhal.' }
.\venv\Scripts\python.exe manage.py migrate
if ($LASTEXITCODE -ne 0) { throw 'Migrace selhaly.' }
.\venv\Scripts\python.exe manage.py check
if ($LASTEXITCODE -ne 0) { throw 'Kontrola aplikace selhala.' }
```

Nepoužívejte `--fake` k zakrytí chyby schématu. Jestliže je kód starší než dump,
nejprve aktualizujte kód a závislosti. Po úspěšné obnově můžete databázi
aktualizovat statistikami pomocí `ANALYZE` z pgAdminu nebo `psql`.

### 5. Spustit aplikaci a ověřit data

```powershell
.\venv\Scripts\python.exe manage.py runserver
```

Otevřete `http://127.0.0.1:8000/admin/` a ověřte několik známých kamionů,
zakázek, beden a poslední data z produkce. Obnoví se i aplikační účty
a oprávnění z dumpu, takže původní lokální účet může zmizet. Pokud potřebujete
vlastní lokální přístup, vytvořte jej příkazem
`.\venv\Scripts\python.exe manage.py createsuperuser`.

Dump nezahrnuje přílohy a další soubory mimo databázi. Chybějící soubory
přeneste samostatně, pokud je pro vývoj potřebujete. Při dalším obnovení
opakujte stejný postup s novějším dumpem; databáze má stále stejný název
a není potřeba pokaždé měnit `.env`.

### Běžné chyby při přenosu

| Chyba | Co udělat |
| --- | --- |
| `pg_restore.exe` nebyl nalezen | Opravte `$pgBin` podle skutečné instalace klientských nástrojů. Samotné Python prostředí nástroje PostgreSQL neobsahuje. |
| `unsupported version in file header` nebo neznámý parametr při obnově | Zkontrolujte verzi nástroje `pg_restore` i lokálního serveru proti produkci a použijte odpovídající verze. |
| `database is being accessed by other users` | Ukončete lokální server, shelly a připojení pgAdminu do dev databáze, poté opakujte mazání. |
| `role ... does not exist` při vytváření databáze | Opravte `$devRole` nebo nechte lokálního správce chybějící roli vytvořit s přihlašováním a heslem. |
| `password authentication failed` nebo `connection refused` | Ověřte lokální službu PostgreSQL, port, roli a její lokální heslo. Port `5433` nemusí platit na jiném počítači. |
| `relation ... already exists` | Obnova míří do neprázdné databáze nebo před ní proběhlo `migrate`. Opakujte krok 3 a migrujte až po obnově. |
| Aplikace stále ukazuje stará data | Zkontrolujte skutečné nastavení příkazem z kroku 4, proměnné prostředí a restartujte lokální server. |

Podrobnosti voleb popisuje oficiální dokumentace PostgreSQL:
[pg_restore](https://www.postgresql.org/docs/current/app-pgrestore.html),
[dropdb](https://www.postgresql.org/docs/current/app-dropdb.html)
a [createdb](https://www.postgresql.org/docs/current/app-createdb.html).
