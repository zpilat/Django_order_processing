# Doplnění historie fakturace po migraci 0250

Migrace `0250_vychozi_fakturace_beden` nastavila fakturační volby existujících
beden, ale nevytvořila odpovídající historické snímky. První pozdější uložení
proto může ukazovat migrační změnu jako změnu pracovníka. Bedna, která od
migrace nebyla uložená, má dosud poslední historii se starými hodnotami.

Příkaz `doplnit_historii_fakturace` doplní chybějící snímky. **Neukládá aktuální
bedny, nemění jejich ceny ani fakturaci a nepřepisuje původní historické řádky.**
Neřeší jiné starší mezery v historii vzniklé například hromadnými akcemi.

## Co se rekonstruuje

- Datum nového snímku je čas dokončení migrace 0250 z `django_migrations`.
  Nejde o přesný čas jednotlivého řádkového zápisu.
- Snímek vychází z poslední známé historie bedny před migrací 0249. Přebírá
  všechna její sledovaná pole a mění pouze čtyři volby `fakturovat_*`.
- U běžné bedny nastaví kalení Ano, rovnání a tryskání podle tehdejšího zákazníka
  a zinkování Ne, přesně podle pravidel 0250. U tehdy atypické bedny jsou
  všechny operace Ne. Hlavní Fakturovat se nemění.
- Tehdejší zákazník a jeho nastavení se dohledají přes historii zakázky a kamionu.
  Dnešní výchozí hodnoty se k rekonstrukci nepoužívají.
- Autor snímku je prázdný (systémový zápis). Důvod obsahuje označení migrace,
  informaci o rekonstrukci a čas skutečného doplnění.
- Původní záznam pracovníka si ponechá jeho skutečné změny. Po doplnění se
  fakturační rozdíl při porovnání zobrazí u systémového snímku migrace.
- Nově vzniklé bedny po migraci se nedoplňují. Pozdější doložené převody
  na atypický průběh a pozdější ruční změny zůstávají zachované.

## Použití

Příkaz vyžaduje PostgreSQL a již provedené migrace 0249 a 0250. Na Windows
spouštějte z kořene projektu přes jeho virtuální prostředí:

```powershell
# Pouze náhled, žádný databázový zápis.
.\venv\Scripts\python.exe manage.py doplnit_historii_fakturace

# Náhled s podrobným CSV; cílový adresář musí existovat.
.\venv\Scripts\python.exe manage.py doplnit_historii_fakturace --csv tmp\historie_fakturace_0250.csv

# Skutečně vyzkouší vložení a ověří výsledek, potom vše vrátí zpět.
.\venv\Scripts\python.exe manage.py doplnit_historii_fakturace --rollback

# Trvale doplní pouze historii.
.\venv\Scripts\python.exe manage.py doplnit_historii_fakturace --apply
```

Na produkci s aktivovaným virtuálním prostředím odpovídá příkazům
`python manage.py doplnit_historii_fakturace ...`. Před zápisem použijte aktuální
zálohu a prohlédněte náhled nebo CSV. Nejde o novou migraci; samotné `migrate`
tuto opravu nespouští.

## Ochrany a ověření

Při nejednoznačném prvním pozdějším snímku, chybějící historické vazbě, historii
přímo v časovém okně migrace nebo rozporném existujícím snímku opravy se
`--apply` i `--rollback` odmítnou celé. Náhled vypíše dotčená ID k posouzení.
Příkaz neodhadne chybějící údaje podle současných hodnot.

Zápis probíhá v jedné transakci. Souběžná spuštění příkazu se serializují
pomocí transakčního advisory locku. Před dokončením se celý návrh znovu ověří.
Při chybě se vrátí všechny vložené snímky. Opakované spuštění již správně
doplněné snímky rozpozná a nevytvoří je podruhé.

Režim `--rollback` používá dočasná záporná ID historie, takže nezanechá řádky
ani neposune sekvenci. Režim `--apply` používá běžná automatická ID.
Při selhání běžného zápisu mohou v sekvenci zůstat mezery, jako u jiných
vrácených PostgreSQL transakcí; čísla beden se nemění.

Po opravě ověřte původně problematické záznamy v historii. U bedny 701322
má záznam 63312 nadále obsahovat přechod Ve zpracování → Zakaleno a
Špinavá → Otryskaná. U bedny 301042 má záznam 63469 zachovat Koulení →
Rovná se. Fakturační změny se mají zobrazit u nového systémového snímku
z okamžiku migrace.

## Ověření na dev databázi 17. 11. 2026

Nad obnoveným produkčním dumpem v místní databázi `orders_dev` byl nejprve
proveden náhled a skutečná zkouška s rollbackem. Otisky obsahu všech 40 tabulek
aplikace i sekvence historie zůstaly po zkoušce shodné s výchozím stavem.

Následný zápis doplnil 6 151 historických snímků: 157 beden již mělo první
pozdější uložení a 5 994 beden dosud nebylo znovu uložených. Počet historie
beden vzrostl z 63 500 na 69 651 řádků. Všechny původní řádky ve všech
40 tabulkách zůstaly beze změny. Počty skutečných přechodů na Zakaleno,
Zkontrolováno, Vyrovnaná a do skupiny zpracování se nezměnily. Opakovaný
`--apply` doplnil 0 záznamů a nezměnil ani sekvenci.

Prošlo 44 testů na PostgreSQL včetně rekonstrukce, historie v adminu a
vyhledávání skutečných historických přechodů. Tato čísla popisují uvedený dev
dump; před případným produkčním zápisem je potřeba načíst nový náhled.

Implementace je v `orders/services/billing_history_repair_service.py`, příkaz
v `orders/management/commands/doplnit_historii_fakturace.py` a regresní testy
v `orders/tests/test_billing_history_repair.py`.
