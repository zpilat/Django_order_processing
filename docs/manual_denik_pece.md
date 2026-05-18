# Uživatelský manuál: Deník pece

Tento dokument popisuje praktické ovládání Deníku pece v Django administraci.
Je zaměřený na modely `SarzeKrok` (kroky šarže) a `SarzeKrokBedna` (řádky deníku), admin `SarzeKrokBednaAdmin` (přehled deníku) a související části (`SarzeAdmin`, `SarzeKrokAdmin`, filtry zařízení, akce přesunu do dalšího zařízení).

## 1. K čemu Deník pece slouží

Deník pece eviduje, co bylo v konkrétním kroku šarže zpracováno:

- standardní bedny z databáze (`bedna`),
- nebo položky mimo databázi (tzv. "železo") přes textová pole (`popis_mimo_db`, `zakaznik_mimo_db`, `zakazka_mimo_db`, `cislo_bedny_mimo_db`).

Každý řádek deníku je jedna položka modelu `SarzeKrokBedna`.

## 2. Kde v administraci pracovat

Používejte hlavně tři obrazovky:

- `Šarže` (`SarzeAdmin`) - hlavička šarže.
- `Kroky šarže` (`SarzeKrokAdmin`) - zařízení a průběh jednotlivých kroků.
- `Deník pece` (`SarzeKrokBednaAdmin`) - přehled všech řádků napříč kroky.

Prakticky:

1. Otevřete seznam `Deník pece`.
2. Klikněte na tlačítko `1) Šarže: Přidat`.
3. Přidejte alespoň jeden krok šarže (`2) Krok: Přidat`).
4. Přidejte položky deníku (`3) Deník pece: Přidat záznam`) nebo přes inline tabulku kroku.
5. Uložte.

Poznámka: V `SarzeKrokBednaAdmin` jsou při editaci existujícího záznamu pole read-only; při přidání nového záznamu jsou editovatelná.

## 3. Jak přidat položku deníku správně

U každého řádku platí režim "buď anebo":

- Režim A: vyberu `bedna` z databáze.
- Režim B: vyplním `popis_mimo_db` + `zakaznik_mimo_db` + `zakazka_mimo_db` (volitelně i `cislo_bedny_mimo_db`).

Nesmí být současně vyplněno:

- `bedna` a textová pole pro "železo".

Povinné společné pole je `patro`.

## 4. Validace a pravidla (co hlídá systém)

### 4.1 Pravidla pro výběr bedny

Pokud je vyplněna `bedna`, musí být ve stavu "skladem" (tj. v povolených stavech pro sklad).

To se kontroluje:

- na úrovni modelu `SarzeKrokBedna.clean()`,
- a zároveň v inline formsetu při ukládání kroku.

### 4.2 Pravidla pro položky mimo DB

Pokud vyplníte `popis_mimo_db`, musíte vyplnit i:

- `zakaznik_mimo_db`,
- `zakazka_mimo_db`.

Současně platí, že zákazník/zakázka/číslo bedny mimo DB nelze vyplnit bez `popis_mimo_db`.

### 4.3 Unikátnost v kroku

Je hlídané unikátní omezení `(krok, bedna, patro)`.

To znamená, že stejná bedna nemůže být v jednom kroku dvakrát na stejném patře.

## 5. Ovládání seznamu Deníku pece (`SarzeKrokBednaAdmin`)

### 5.1 Sloupce

V přehledu uvidíte mimo jiné:

- šarži, pořadí kroku, zařízení, datum, časy, operátora,
- číslo bedny nebo číslo bedny mimo DB,
- zákazníka,
- patro,
- číslo přípravku, program,
- poznámku, alarm,
- prodlevu, takt,
- indikátor `První?` (první použití bedny na daném zařízení).

### 5.2 Filtry

- `Zařízení` (`ZarizeniSarzeBednaFilter`)
- `Typ zařízení` (`TypZarizeniSarzeBednaFilter`)

### 5.3 Vyhledávání

- Hledá podle čísla šarže a čísla bedny.

## 6. Akce související s deníkem

### 6.1 Na `SarzeKrokBednaAdmin`

- Akce `Do dalšího zařízení` přesune vybrané řádky do navazujícího kroku stejné šarže.
- Ochranná pravidla akce:
  - přeskočí záznam bez navazujícího kroku,
  - přeskočí bednu mimo stav skladem,
  - přeskočí záznam, pokud by v cílovém kroku vznikla duplicita.

### 6.2 Na `SarzeAdmin`

- Přesun celé šarže na jiné zařízení je odstraněn.

## 7. Typický pracovní postup (doporučený)

1. Vytvořit šarži v `SarzeAdmin`.
2. Přidat kroky v `SarzeKrokAdmin`.
3. Přidat řádky deníku přes inline tabulku kroku nebo přes `SarzeKrokBednaAdmin`.
4. Otevřít `Deník pece` (`SarzeKrokBednaAdmin`) a zkontrolovat výsledek (filtry zařízení, vyhledání čísla bedny).
5. Pokud je potřeba postoupit položky dál, použít akci `Do dalšího zařízení`.

## 8. Nejčastější problémy a rychlé řešení

### Chyba: "Musí být vyplněna buď bedna nebo popis"

- Řádek je prázdný nebo nebyla zvolena žádná varianta.

### Chyba: "Nelze vyplnit současně bednu i popis"

- Smí být vyplněná jen jedna větev (bedna, nebo železo).

### Chyba: "Vybraná bedna musí být ve stavu skladem"

- Vybraná bedna není ve stavu, který je povolený pro zařazení do kroku.

### Chyba při ukládání duplicity

- Už existuje stejná kombinace `krok + bedna + patro`.

## 9. Co je dobré vědět o oprávněních

- Pro hromadnou akci přesunu je nutné oprávnění měnit záznamy deníku pece.

## 10. Technická mapa (kde je logika v kódu)

- `orders/models.py`
  - `Sarze`
  - `SarzeKrok`
  - `SarzeKrokBedna`
  - validace `SarzeKrokBedna.clean()`

- `orders/admin.py`
  - `SarzeAdmin`
  - `SarzeKrokAdmin`
  - `SarzeKrokBednaInline`
  - `SarzeKrokBednaInlineFormSet`
  - `SarzeKrokBednaAdmin`

- `orders/filters.py`
  - `ZarizeniSarzeFilter`
  - `ZarizeniSarzeKrokFilter`
  - `ZarizeniSarzeBednaFilter`

- `orders/templates/admin/orders/sarzebedna/change_list.html`
  - tlačítka pro řízené založení šarže, kroku a řádku deníku
