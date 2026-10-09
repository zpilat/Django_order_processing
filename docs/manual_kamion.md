# Uživatelský manuál: Kamiony

Tento dokument popisuje praktické ovládání agendy kamionů v Django administraci.
Je zaměřený na model `Kamion`, admin `KamionAdmin`, filtry, akce a návaznost na zakázky/bedny.

## 1. K čemu modul Kamiony slouží

Agenda `Kamiony` řeší vstup a výstup zakázek ze skladu:

- `Příjem` kamionů (import/přijetí zakázek a beden na sklad),
- `Výdej` kamionů (expedice, tisk dokladů, měření).

Je to hlavní rozhraní pro práci s dodacími listy, importem a tiskem navázaných dokumentů.

## 2. Kde v administraci pracovat

Primární obrazovka je seznam `Kamiony` (`KamionAdmin`).

Prakticky:

1. Otevřete seznam `Kamiony`.
2. Nastavte filtr typu kamionu (`PrijemVydejFilter`).
3. Vyberte kamion a použijte odpovídající akci.
4. Zakázky uvnitř kamionu řešte přes inline tabulky v detailu kamionu.

## 3. Typy kamionů a stavy

Filter a zobrazení rozlišují zejména:

- Příjem - bez zakázek,
- Příjem - nepřijatý,
- Příjem - komplet přijatý,
- Příjem - vyexpedovaný,
- Výdej.

Podle toho se mění dostupné akce.

## 4. Co je důležité na detailu kamionu

- U příjmu se pracuje s inline zakázkami příjmu.
- U výdeje se pracuje s inline zakázkami výdeje.
- Pro výdej je dostupné zadání měření zakázek.
- V detailu je možné zobrazit strukturu kamionu (zakázky + bedny).

## 5. Filtry v KamionAdmin

Nejpoužívanější filtry:

- `Zákazník` (`ZakaznikKamionuFilter`),
- `Typ kamiónu` (`PrijemVydejFilter`).

Doporučení:

- Před spuštěním akce vždy nejprve nastavte správný typ kamionu, jinak akci často neuvidíte.

## 6. Hromadné akce v KamionAdmin

Typické akce:

- `Importovat dodací list pro vybraný kamion příjem bez zakázek`.
- `Přijmout kamion na sklad`.
- `Vytisknout karty beden` / `Vytisknout KKK` pro kamion příjem.
- `Tisk přehledu zakázek` pro kamion příjem.
- `Vytisknout dodací list vybraného kamionu výdej`.
- `Vytisknout certifikát 3.1 kamionu výdej`.
- `Vytisknout proforma fakturu vybraného kamionu výdej`.
- `Zadat / upravit měření vybraného kamionu výdej`.
- `Importovat chemická měření beden` pro kamion příjem s bednami.
- `Vytisknout vyplněné KKK z vybraného kamionu výdej (EUR)`.

Pro tisk vyplněných karet výdeje vyberte právě jeden kamion ve filtru `Výdej`.
PDF obsahuje karty všech jeho beden s uloženou kontrolou kvality, včetně expedovaných beden,
ve stejném vzoru jako tisk vyplněných KKK v administraci beden.
Pokud některé bedny nemají uloženou kontrolu, v novém panelu se nejprve zobrazí varování
s jejich počtem a čísly (nejvýše prvních 20). Tlačítkem „Otevřít PDF dostupných karet“
vytisknete karty beden s kontrolou; ostatní se přeskočí. Pokud žádná bedna nemá kontrolu,
PDF se nevytvoří a zobrazí se chyba.

Výroba a přesuny šarží se řeší samostatně v [deníku](manual_denik_pece.md) a [rychlém založení šarže](manual_rychle_zalozeni_sarze.md).

## 7. Jak systém zpřístupňuje akce

`KamionAdmin.get_actions()` dynamicky skrývá akce podle filtru `PrijemVydejFilter`.

Praktický dopad:

- Pokud akci nevidíte, obvykle je špatně zvolený typ kamionu.
- Některé akce jsou dostupné pouze pro příjem, jiné pouze pro výdej.

## 8. Import zakázek z Excelu

Importní workflow:

1. Nahrání `.xlsx` souboru.
2. Náhled dat bez zápisu do DB.
3. Potvrzení importu.
4. Atomické uložení (all-or-nothing).

Vyberte právě jeden kamion příjem bez zakázek a spusťte import dodacího listu. V náhledu zkontrolujte hlavičky, artikly, rozměry, předpisy a rozdělení do beden. Soubor zůstává dostupný mezi náhledem a potvrzením; po opravě vstupního Excelu nahrajte jeho novou verzi.

Poznámky:

- Používají se importní strategie podle zákazníka (např. EUR, SPX).
- Pokud se objeví chyby, import se neuloží.
- Podporovaný formát je `.xlsx`; výchozí limit souboru je 10 MB, měnit jej může správce pomocí `EXCEL_UPLOAD_MAX_SIZE_MB`.
- Artikl se normalizuje na text bez nežádoucí koncovky `.0`. Počet načítaných řádků závisí na strategii zákazníka.

### Import chemických měření beden

1. Vyberte právě jeden kamion příjem, který už obsahuje bedny.
2. Spusťte **Importovat chemická měření beden**.
3. Zkontrolujte dostupnost exportů Vanta a náhled přiřazení JSONů k bednám, včetně chyb a varování.
4. Pokud náhled dovolí import, potvrďte jej.
5. Zkontrolujte hlášení o aktualizovaných bednách, záznamech beze změny a zpracovaných souborech.

Tato akce čte soubory z adresáře exportů na počítači/serveru aplikace; není to další nahrání dodacího listu. Po zpracování se JSONy přesouvají do archivu. Pokud se objeví chyba archivace, ověřte se správcem stav souborů; výsledky už mohly být uložené.

Adresáře určuje `CHEMISTRY_INCOMING_DIR` a `CHEMISTRY_ARCHIVE_DIR` v nastavení. V debug režimu se používá lokální adresář, v produkci adresář serveru. Dostupnost analyzátoru kontroluje služba Vanta podle proměnných `VANTA_SMB_*`. Přístup k adresářům a synchronizaci řeší správce.

## 9. Zadání měření (výdej)

Akce `Zadat / upravit měření` je dostupná jen pro kamion výdej a vyžaduje oprávnění pro změnu měření zakázek.

Workflow:

1. Vyberte právě jeden kamion výdej.
2. Spusťte akci zadání měření.
3. Vyplňte hodnoty ve formuláři.
4. Uložte.

Jde o souhrnné hodnoty zakázek pro výdejové doklady. Jednotlivá měření a rozhodnutí o uvolnění bedny zapisujte podle [manuálu kontroly beden](manual_kontrola_beden.md); oba formuláře mají jiný účel.

Vyplněné KKK pro EUR tiskněte až po uložení kontrol všech příslušných beden. Samostatné akce pro prázdné KKK zůstávají dostupné podle kontextu.

## 10. Mazání kamionů - omezení

Mazání je chráněné:

- Příjem kamion nelze mazat, pokud obsahuje bedny mimo stav `NEPRIJATO`.
- Výdej kamion nelze mazat, pokud je přiřazen k zakázkám.

Při hromadném mazání se smažou jen povolené položky, ostatní se vypíšou s důvodem.

## 11. Doporučený pracovní postup

1. Vytvořit/načíst příjem kamion.
2. Naimportovat nebo ručně zadat zakázky.
3. Přijmout kamion na sklad.
4. Pracovat se zakázkami a bednami v navazujících agendách.
5. Při expedici použít výdej kamion a tisk dokladů.

## 12. Nejčastější problémy a řešení

### Akce nejde spustit

Zkontrolujte, zda je vybraný správný typ kamionu a správný počet záznamů (některé akce vyžadují přesně jeden kamion).

### Import neprojde

Zkontrolujte formát `.xlsx`, validaci hlaviček a chybová hlášení z náhledu.

### Nejde mazat kamion

Zkontrolujte, zda neobsahuje nepovolené návaznosti (zakázky/bedny ve stavu mimo pravidla).

## 13. Technická mapa (kde je logika v kódu)

- `orders/models.py`
  - `Kamion`

- `orders/admin.py`
  - `KamionAdmin`
  - inliny zakázek pro příjem/výdej
  - import view + zadání měření

- `orders/filters.py`
  - `PrijemVydejFilter`
  - `ZakaznikKamionuFilter`

- `orders/actions.py`
  - import, příjem kamionu, tisk dokladů a navazující akce

- `orders/services/chemistry_import_service.py`, `orders/services/vanta_probe_service.py`
  - náhled, import, archivace a dostupnost chemických exportů
- `orders/services/filled_quality_cards_service.py`
  - vyplněné KKK pro EUR

[Zakázky](manual_zakazka.md) · [Bedny](manual_bedna.md) · [README](../README.md)
