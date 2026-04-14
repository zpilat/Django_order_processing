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

Speciální akce v `SarzeAdmin` (ne v KamionAdmin):

- přesun šarže na jiné zařízení.

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

Poznámky:

- Používají se importní strategie podle zákazníka (např. EUR, SPX).
- Pokud se objeví chyby, import se neuloží.

## 9. Zadání měření (výdej)

Akce `Zadat / upravit měření` je dostupná jen pro kamion výdej a vyžaduje oprávnění pro změnu měření zakázek.

Workflow:

1. Vyberte právě jeden kamion výdej.
2. Spusťte akci zadání měření.
3. Vyplňte hodnoty ve formuláři.
4. Uložte.

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
