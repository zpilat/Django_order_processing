# Uživatelský manuál: Zakázky

Tento dokument popisuje praktické ovládání agendy zakázek v Django administraci.
Je zaměřený na model `Zakazka`, admin `ZakazkaAdmin`, související filtry, akce a běžné pracovní postupy.

## 1. K čemu modul Zakázky slouží

Agenda `Zakázky` je střed workflow mezi příjmem kamionu a expedicí.
Používá se pro:

- evidenci základních parametrů zakázky (artikl, průměr, délka, předpis, typ hlavy),
- kontrolu kompletnosti zakázky podle stavů beden,
- příjem zakázek na sklad,
- expedici zakázek (včetně expedice do existujícího kamionu),
- tisk karet beden a KKK.

## 2. Kde v administraci pracovat

Primární obrazovka je seznam `Zakázky` (`ZakazkaAdmin`).

Prakticky:

1. Otevřete seznam `Zakázky`.
2. Nastavte filtr `Skladem` (klíčový filtr pro dostupné akce).
3. Dofiltrujte zákazníka, odběratele, prioritu, typ hlavy apod.
4. Vyberte zakázky a spusťte akci.
5. Detaily beden řešte přes inline `BednaInline` přímo v detailu zakázky.

## 3. Co je důležité na detailu zakázky

- Zakázka má vazby na `kamion_prijem` a volitelně `kamion_vydej`.
- Pole `expedovano` určuje, zda je zakázka považovaná za expedovanou.
- Na detailu je inline tabulka beden (`BednaInline`).
- U expedovaných zakázek jsou úpravy omezené oprávněním.

## 4. Význam indikátoru „Komplet“

V adminu se zobrazuje stav kompletnosti:

- `➖` - zakázka bez beden,
- `❌` - žádná bedna není `K_EXPEDICI`,
- `⏳` - část beden je `K_EXPEDICI`,
- `✔️` - všechny bedny jsou `K_EXPEDICI` nebo `EXPEDOVANO`.

Tento indikátor je důležitý hlavně před expedicí.

## 5. Filtry v ZakazkaAdmin

Nejpoužívanější filtry:

- `Skladem` (`SklademZakazkaFilter`) - klíčový filtr (`Vše skladem`, `Nepřijato`, `Bez beden`, `Po exspiraci`, `Expedováno`).
- `Zákazník`.
- `Odběratel`.
- `Kompletní`.
- `Priorita`.
- `Typ hlavy`, `Celozávit`.

Poznámka:

- Podle filtru `Skladem` se dynamicky mění dostupné akce i některé sloupce seznamu.

## 6. Hromadné akce v ZakazkaAdmin

Typicky dostupné akce:

- `Přijmout vybrané zakázky na sklad`.
- `Expedice vybraných zakázek`.
- `Expedice vybraných zakázek do existujícího kamiónu`.
- `Vrácení vybraných zakázek z expedice`.
- `Vytisknout karty beden z vybraných zakázek`.
- `Vytisknout KKK z vybraných zakázek`.

Akce jsou seskupené v UI podle typu (Příjem, Tisk, Expedice).

## 7. Jak systém zpřístupňuje akce

`ZakazkaAdmin.get_actions()` zapíná/vypíná akce hlavně podle filtru `Skladem`.

Praktický dopad:

- Když akce není vidět, nejprve zkontrolujte aktivní hodnotu filtru `Skladem`.
- Některé akce se úmyslně skryjí v kontextech, kde by dávaly nesmyslný výsledek (např. expedice u nevyhovujících stavů).

## 8. Doporučený pracovní postup

1. Po příjmu kamionu filtrujte zakázky podle `Skladem`.
2. Přijměte zakázky na sklad.
3. Pracujte s bednami v inline tabulce zakázky (technologické stavy, hmotnosti).
4. Před expedicí ověřte `Komplet`.
5. Spusťte expedici zakázek.
6. Tiskněte potřebné karty/KKK.

## 9. Nejčastější problémy a řešení

### Akce expedice není dostupná

Zkontrolujte filtr `Skladem` a stavy beden v zakázkách.

### Zakázka nejde smazat

Zakázka obsahuje bedny mimo stav `NEPRIJATO`; mazání je blokované.

### Zakázka je read-only

Může být expedovaná a uživatel nemá potřebné oprávnění pro změnu expedovaných zakázek.

## 10. Technická mapa (kde je logika v kódu)

- `orders/models.py`
  - `Zakazka`
  - výpočtové property (hmotnosti, ceny, počty)

- `orders/admin.py`
  - `ZakazkaAdmin`
  - `BednaInline`

- `orders/filters.py`
  - `SklademZakazkaFilter`
  - `KompletZakazkaFilter`
  - další filtry pro zakázky

- `orders/actions.py`
  - příjem, expedice, tisk a návratové akce pro zakázky
