# Uživatelský manuál: Bedny

Tento dokument popisuje praktické ovládání evidence beden v Django administraci.
Je zaměřený na model `Bedna`, admin `BednaAdmin`, související filtry, list editaci, hromadné akce a typické chyby.

## 1. K čemu modul Bedny slouží

Agenda `Bedny` je hlavní pracovní seznam výroby.
Používá se pro:

- evidenci jednotlivých beden v rámci zakázek,
- změnu stavů výroby (od `NEPRIJATO` po `EXPEDOVANO`),
- průběžné úpravy tryskání, rovnání a zinkování,
- přípravu exportů/tisku a expedici.

## 2. Kde v administraci pracovat

Primární obrazovka je seznam `Bedny` (`BednaAdmin`).

Prakticky:

1. Otevřete seznam `Bedny`.
2. Nejprve nastavte filtr `Stav bedny` (bez něj nejsou dostupné všechny smysluplné akce).
3. Použijte další filtry (zákazník, délka, priorita, zinkování atd.).
4. Označte řádky a proveďte akci, nebo upravujte přímo v listu (pokud je povolena inline editace).

## 3. Co znamenají hlavní pole bedny

- `cislo_bedny`: interní číslo bedny, generuje se automaticky.
- `hmotnost`: netto kg.
- `tara`: tára kg.
- `stav_bedny`: hlavní výrobní stav.
- `tryskat`, `rovnat`, `zinkovat`: technologické stavy.
- `pozice`: používá se při stavech navezení.
- `pozastaveno`: blokace práce s bednou.
- `fakturovat`: zda se bedna započítává do fakturace.

## 4. Důležitá validační pravidla

### 4.1 Povinnosti mimo stav NEPRIJATO

Pokud bedna není ve stavu `NEPRIJATO`, musí být vyplněno a > 0:

- `hmotnost`,
- `tara`,
- `mnozstvi`.

### 4.2 Omezení pro stavy K_EXPEDICI / EXPEDOVANO

Pro tyto stavy musí být:

- `tryskat` = Čistá nebo Otryskaná,
- `rovnat` = Rovná nebo Vyrovnaná,
- `zinkovat` = Nezinkovat nebo Uvolněno.

### 4.3 Omezení pro K_NAVEZENI / NAVEZENO

Pro stavy `K_NAVEZENI` a `NAVEZENO` musí být vyplněna `pozice`.

### 4.4 Zinkování V ZINKOVNĚ

Pokud je `zinkovat = V ZINKOVNĚ`, bedna musí být ve stavu `ZKONTROLOVANO`.

### 4.5 Mazání bedny

Smazat lze jen bednu ve stavu `NEPRIJATO`.

## 5. Oprávnění a blokace úprav

Systém rozlišuje speciální oprávnění:

- `change_expedovana_bedna` pro expedované bedny,
- `change_pozastavena_bedna` pro pozastavené bedny,
- `change_neprijata_bedna` pro běžné úpravy nepřijatých beden,
- `change_poznamka_neprijata_bedna` pro úpravu pouze poznámky u nepřijatých beden,
- `mark_bedna_navezeno` pro část operací kolem navezení.

Pokud uživatel nemá potřebné oprávnění, pole jsou read-only nebo se akce vůbec nezobrazí.

## 6. Inline editace v seznamu (list_editable)

Inline editace je dynamická podle filtru a oprávnění.

Zjednodušeně:

- Bez filtru nebo v nevhodném stavu se editace omezí.
- Ve stavu `NEPRIJATO` může být editace velmi omezená podle oprávnění.
- Ve stavu `K_EXPEDICI` se naopak některá pole (hmotnost/rovnat/tryskat) z inline editace schválně odeberou.

Poznámka: seznam také obsahuje polling změn (automatická kontrola nových změn v intervalu).

## 7. Filtry v BednaAdmin

Nejpoužívanější filtry:

- `Stav bedny` (`StavBednyFilter`) - obsahuje i virtuální volby `RO` (Rozpracováno) a `PE` (Po exspiraci).
- `Tryskání`, `Rovnání`, `Zinkování` - mají i agregované volby typu "hotovo".
- `Zákazník`, `Typ hlavy`, `Celozávit`, `Skupina TZ`, `Délka`, `Priorita`, `Pozastaveno`, `Odběratel`, `Notifikace`.

Důležité:

- Dostupnost části filtrů se podle stavu bedny mění (admin je záměrně schovává/zobrazuje podle kontextu).

## 8. Hromadné akce - jak se orientovat

Akce jsou v UI seskupené do kategorií:

- `Stav bedny`
- `Tisk`
- `Export`
- `Rovnání`
- `Tryskání`
- `Zinkování`
- `Expedice`

### 8.1 Typické akce podle skupiny

Stav bedny:

- Přijmout vybrané bedny na sklad.
- Změna stavu na `K_NAVEZENI`, `NAVEZENO`, `DO ZPRACOVÁNÍ`, `ZAKALENO`, `ZKONTROLOVÁNO`, `K_EXPEDICI`.
- Vracení stavů zpět (`K_NAVEZENI -> PRIJATO`, `NAVEZENO -> PRIJATO`, rozpracovanost -> `PRIJATO`).

Rovnání:

- Změna na `ROVNÁ`, `KŘIVÁ`, `ROVNÁ SE`, `VYROVNANÁ`, přesun na `KOULENÍ`.

Tryskání:

- Změna na `ČISTÁ`, `ŠPINAVÁ`, `OTRYSKANÁ`.

Zinkování:

- Změna na `ZINKOVAT`, `POZINKOVÁNO`, `UVOLNĚNO`.
- Označit `V ZINKOVNĚ` + export DL.
- Export beden se stavem `V ZINKOVNĚ`.

Expedice:

- Expedice vybraných beden.
- Expedice vybraných beden do existujícího kamionu.

Tisk a export:

- Export do CSV (interní, pro zákazníka, pro vložení do DL).
- Tisk karet bedny, KKK a kombinovaný tisk.

## 9. Jak systém zpřístupňuje akce

Akce nejsou vždy dostupné. `BednaAdmin.get_actions()` je zapíná/vypíná hlavně podle:

- aktuálního filtru `stav_bedny`,
- filtru `rovnani`,
- filtru `tryskani`,
- filtru `zinkovani`,
- oprávnění uživatele.

Praktický dopad:

- Když nevidíte akci, nejdřív zkontrolujte filtr stavu bedny.
- Potom ověřte oprávnění uživatele.

## 10. Doporučený pracovní postup

1. Nastavit `Stav bedny` filtr na aktuální fázi práce.
2. Dofiltrovat zákazníka / délku / technologii.
3. Vybrat bedny.
4. Spustit příslušnou hromadnou akci pro další krok výroby.
5. Průběžně kontrolovat notifikační indikátor a případná varování.

## 11. Nejčastější chyby a řešení

### Chyba: nelze uložit bednu mimo NEPRIJATO

Zkontrolujte vyplnění `hmotnost`, `tara`, `mnozstvi` a vazbu na platný předpis.

### Chyba: nelze přepnout na K_EXPEDICI / EXPEDOVANO

Zkontrolujte kombinaci `tryskat`, `rovnat`, `zinkovat`.

### Chyba: nelze přepnout na K_NAVEZENI / NAVEZENO

Doplňte `pozice`.

### Chyba: nelze mazat bednu

Bedna není ve stavu `NEPRIJATO`.

### Akce není vidět

Upravte filtr `Stav bedny` na odpovídající kontext a ověřte oprávnění uživatele.

## 12. Technická mapa (kde je logika v kódu)

- `orders/models.py`
  - `Bedna`
  - validace `Bedna.clean()`
  - přechodové volby `get_allowed_*_choices`

- `orders/admin.py`
  - `BednaAdmin`
  - dynamika listu (`get_list_display`, `get_list_editable`, `get_actions`)
  - polling změn

- `orders/filters.py`
  - `StavBednyFilter`
  - `TryskaniFilter`
  - `RovnaniFilter`
  - `ZinkovaniFilter`
  - další filtry pro zákazníka, prioritu, délku, pozastavení, notifikace

- `orders/actions.py`
  - stavové, technologické, tiskové, exportní a expediční akce pro bedny

- `orders/templates/admin/orders/bedna/change_list.html`
  - konfigurace pollingu změn v seznamu
