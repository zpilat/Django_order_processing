# Automatické zálohy produkční databáze

[Skript backup-orders.sh](../deploy/backup-orders.sh) vytváří dump databáze
`orders_prod` každou hodinu při spuštění cronem a po úspěšném uložení maže
automatické dumpy staré alespoň 72 hodin. Při pravidelném provozu tak zůstává
přibližně 72 záloh. Při chybě nové zálohy se starší zálohy nemažou.

Postup je pro **Linux s cronem, Bashem, GNU find a flock**. Skript používá stejné
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
