# Uživatelský manuál: Deník pece

Tento dokument popisuje praktické ovládání Deníku pece v Django administraci.
Je zaměřený na model `SarzeBedna` (řádky deníku), admin `SarzeBednaAdmin` (přehled deníku) a související části (`SarzeAdmin`, filtr zařízení, akce přesunu šarže).

## 1. K čemu Deník pece slouží

Deník pece eviduje, co bylo v konkrétní šarži zpracováno:

- standardní bedny z databáze (`bedna`),
- nebo položky mimo databázi (tzv. "železo") přes textová pole (`popis`, `zakaznik_mimo_db`, `zakazka_mimo_db`, `cislo_bedny_mimo_db`).

Každý řádek deníku je jedna položka modelu `SarzeBedna`.

## 2. Kde v administraci pracovat

Používejte hlavně dvě obrazovky:

- `Šarže` (`SarzeAdmin`) - zde se šarže vytváří a upravuje.
- `Deník pece` (`SarzeBednaAdmin`) - zde je přehled všech řádků napříč šaržemi.

Prakticky:

1. Otevřete seznam `Deník pece`.
2. Klikněte na tlačítko `Šarže: Přidat`.
3. Vyplňte hlavičku šarže (zařízení, datum, časy, operátor...).
4. V inline tabulce přidejte položky deníku (bedny nebo "železo").
5. Uložte.

Poznámka: V samotném `SarzeBednaAdmin` jsou pole read-only, je to hlavně přehled. Editace probíhá přes detail šarže.

## 3. Jak přidat položku deníku správně

U každého řádku platí režim "buď anebo":

- Režim A: vyberu `bedna` z databáze.
- Režim B: vyplním `popis` + `zakaznik_mimo_db` + `zakazka_mimo_db` (volitelně i `cislo_bedny_mimo_db`).

Nesmí být současně vyplněno:

- `bedna` a textová pole pro "železo".

Povinné společné pole je `patro`.

Doporučení:

- Pokud jde o běžnou výrobu vrutů, používejte režim A (výběr bedny).
- Režim B používejte jen pro položky mimo systém.

## 4. Validace a pravidla (co hlídá systém)

### 4.1 Pravidla pro výběr bedny

Pokud je vyplněna `bedna`, musí být ve stavu "skladem" (tj. v povolených stavech pro sklad).

To se kontroluje:

- na úrovni modelu `SarzeBedna.clean()`,
- a zároveň v inline formsetu při ukládání šarže.

### 4.2 Pravidla pro položky "železo"

Pokud vyplníte `popis`, musíte vyplnit i:

- `zakaznik_mimo_db`,
- `zakazka_mimo_db`.

### 4.3 Unikátnost v šarži

Je hlídané unikátní omezení `(sarze, bedna, patro)`.

To znamená, že stejná bedna nemůže být v jedné šarži dvakrát na stejném patře.

## 5. Ovládání seznamu Deníku pece (`SarzeBednaAdmin`)

### 5.1 Sloupce

V přehledu uvidíte mimo jiné:

- šarži, zařízení, datum, časy, operátora,
- číslo bedny nebo číslo bedny mimo DB,
- zákazníka,
- patro,
- číslo přípravku, program,
- poznámku, alarm,
- prodlevu, takt,
- indikátor `První?` (první použití bedny na daném zařízení).

### 5.2 Filtr

- Dostupný filtr: `Zařízení` (`ZarizeniSarzeBednaFilter`).

### 5.3 Vyhledávání

- Hledá podle `sarze__cislo_sarze` a `bedna__cislo_bedny`.

### 5.4 Vizuální orientace

- Řádky jsou vizuálně oddělené při změně šarže (JS group separator), takže je rychle vidět blok jedné šarže.

## 6. Akce související s deníkem

### 6.1 Na `SarzeBednaAdmin`

- Není definovaná vlastní doménová hromadná akce pro deník pece.
- Slouží primárně jako přehled.

### 6.2 Na `SarzeAdmin`

- Akce `Přesunout šarži na jiné zařízení` (pokud má uživatel oprávnění `orders.can_move_sarze`).
- Při přesunu se šarže na cílovém zařízení přečísluje na další volné číslo.
- Akce vyžaduje vybrat právě jednu šarži.

## 7. Typický pracovní postup (doporučený)

1. Vytvořit šarži v `SarzeAdmin`.
2. Přidat řádky deníku přes inline tabulku.
3. Uložit.
4. Otevřít `Deník pece` (`SarzeBednaAdmin`) a zkontrolovat výsledek (filtr zařízení, vyhledání čísla bedny).
5. Pokud je potřeba přesunout šarži, použít akci v `SarzeAdmin`.

## 8. Nejčastější problémy a rychlé řešení

### Chyba: "Musí být vyplněna buď bedna nebo popis"

- Řádek je prázdný nebo nebyla zvolena žádná varianta.

### Chyba: "Nelze vyplnit současně bednu i popis"

- Smí být vyplněná jen jedna větev (bedna, nebo železo).

### Chyba: "Vybraná bedna musí být ve stavu skladem"

- Vybraná bedna není ve stavu, který je povolený pro zařazení do šarže.

### Chyba při ukládání duplicity

- Už existuje stejná kombinace `sarze + bedna + patro`.

## 9. Co je dobré vědět o oprávněních

- Přesun šarže mezi zařízeními vyžaduje oprávnění `orders.can_move_sarze`.
- Bez tohoto oprávnění se akce přesunu v nabídce akcí neukáže.

## 10. Technická mapa (kde je logika v kódu)

- `orders/models.py`
  - `Sarze`
  - `SarzeBedna`
  - validace `SarzeBedna.clean()`

- `orders/admin.py`
  - `SarzeAdmin`
  - `SarzeBednaInline`
  - `SarzeBednaInlineFormSet`
  - `SarzeBednaAdmin`

- `orders/filters.py`
  - `ZarizeniSarzeFilter`
  - `ZarizeniSarzeBednaFilter`

- `orders/templates/admin/orders/sarzebedna/change_list.html`
  - tlačítko `Šarže: Přidat`
