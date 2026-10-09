# Uživatelský manuál: Průchod šarže výrobou

Návod propojuje nakládání, průchody pracovišti, kontrolu a ukončení šarže. Konkrétní technologické operace, program a jejich pořadí se řídí předpisem zakázky; níže je postup jejich evidence v aplikaci.

## 1. Šarže, krok a bedna

**Šarže** sdružuje obsah roštu. **Krok** eviduje jeden průchod pracovištěm s operátorem, začátkem a koncem. **Deník kroku** určuje jeho bedny nebo položky mimo databázi, patra a podíly.

Přesun vytváří nový krok stejné šarže a kopíruje do něj položky ze zdrojového kroku. Předchozí kroky zůstávají v historii průchodu. Přesun sám neuzavírá zdrojový krok.

| Údaj | Co popisuje |
| --- | --- |
| Stav šarže | Celkový provozní stav šarže. |
| Datum a čas konce kroku | Dokončení konkrétního průchodu pracovištěm. |
| Stav bedny | Výrobní fázi jednotlivé bedny, například Ve zpracování nebo Zakaleno. |
| Uvolnění kontroly | Rozhodnutí o kvalitě bedny. |
| Rovnání, tryskání, zinkování | Samostatné technologické stavy bedny. |

Ukončená šarže proto sama neznamená, že jsou všechny bedny zkontrolované, uvolněné nebo připravené k expedici.

## 2. Založení a dokončení nakládání

Pro bedny z databáze použijte [Rychlé založení šarže s bednami](manual_rychle_zalozeni_sarze.md):

1. V **Přehledu nakládání** (`/provozni-prehledy/`) vyberte číslo pracoviště 1–6.
2. Založte šarži s přípravkem, datem a časem začátku a operátorem, nebo pokračujte v otevřené šarži.
3. Vyberte či naskenujte bedny, nastavte rozložení a uložte patra.
4. Zkontrolujte obsah a podle potřeby otevřete **Náhled tisku**.
5. Po dokončení nakládání použijte **Doplnit konec kroku**, vyplňte datum i čas konce a uložte.

Rychlé založení uloží stav šarže Naložená. Zařazení bedny do kroku Nakládání nastaví bedně Ve zpracování a vymaže její skladovou pozici.

Pro železo mimo databázi vytvořte šarži a první krok v administraci a zadejte popis, zákazníka a zakázku mimo DB podle [manuálu deníku](manual_denik_pece.md). Při založení šarže v administraci vyplňte také povinné údaje prvního kroku.

## 3. Otevření provozního detailu

Otevřete čtečku šarží na `/sarze/skener-ctecka/` a načtěte kód, případně zadejte číslo. Přijímá například `25`, `00025` nebo `S00025`. Přímý detail má tvar `/sarze/scan/25/`.

Detail ukazuje stav šarže, přípravek a kroky od nejnovějšího. U kroku vidíte pracoviště, operátora, datum, začátek, konec a program; tlačítko **Patra** rozbalí obsah roštu.

Před operací ověřte číslo šarže, zdrojové pracoviště a položky. **Přesunout do dalšího kroku** nahoře pracuje s posledním krokem podle pořadí. **Přesunout** u konkrétního kroku použije tento krok, což se hodí pro pokračování s částí jeho obsahu.

## 4. Přesun na další pracoviště

1. U dokončeného zdrojového kroku nejprve doplňte konec podle následující kapitoly.
2. Klikněte na **Přesunout do dalšího kroku** nebo **Přesunout** u požadovaného zdroje.
3. Zvolte cílové **Pracoviště** podle skutečného postupu.
4. Zkontrolujte **Datum začátku**, **Začátek** a **Operátora**. Při přesunu z provozního detailu se předvyplňuje aktuální datum, čas a přihlášený uživatel.
5. Podle potřeby zadejte **Program**, **Alarm** a **Poznámku**. Datum a čas konce nového kroku ponechte prázdné, pokud ještě probíhá.
6. V části **Kopírované položky** zkontrolujte checkboxy. Výchozí výběr obsahuje všechny řádky zdrojového kroku; pro částečný přesun ponechte jen skutečně přesouvané položky.
7. Potvrďte **Vytvořit další krok** a v detailu šarže ověřte nový krok.

Do nového kroku se přenese obsah vybraných řádků včetně pater, procent a údajů mimo DB. Údaje o pracovišti, časech a operátorovi se berou z nového formuláře. Zdrojový deník zůstává zachovaný. Pokud má zdroj položky, musíte vybrat alespoň jednu.

Jedna bedna může být rozdělená do více řádků roštu. Při přesunu celého jejího obsahu označte všechny příslušné řádky; počet zkopírovaných řádků nemusí odpovídat počtu různých beden.

Pokud u cílového pracoviště vidíte upozornění, že v této šarži už má krok, ověřte záměr. Opakovaný skutečný průchod evidujte novým krokem; překlep v již uloženém kroku opravte přes **Upravit**.

## 5. Dokončení a oprava kroku

V detailu příslušného kroku klikněte na **Doplnit konec kroku** nebo **Upravit**:

1. Zkontrolujte skutečné pracoviště, začátek a operátora.
2. Vyplňte společně **Datum konce** a **Konec**. Odkaz pro doplnění konce může předvyplnit aktuální datum a čas; opravte je podle skutečnosti.
3. Doplňte program, alarm či poznámku, pokud je potřeba.
4. Klikněte na **Uložit změny**.

Konec nesmí předcházet začátku. Například pro začátek 9. 10. ve 22:00 a konec v 01:30 vyplňte datum konce 10. 10. Na každém dokončeném kroku evidujte jeho vlastní konec.

Checkbox **Smazat** u položky odebere po uložení její řádek z tohoto kroku. Jde o opravu evidence; samostatně nevrátí výrobní stav bedny ani neodstraní její záznamy v jiných krocích.

Pokud přesun upozorní na nevyplněný konec, nový krok může přesto vzniknout. Vraťte se ke zdroji a doplňte skutečný konec.

## 6. Zpracování a kontrola beden z databáze

Na každém dalším pracovišti opakujte zadání začátku, kontrolu obsahu a uzavření kroku. Po dokončení příslušného zpracování označte jednotlivé bedny jako **Zakaleno** přes dostupnou akci beden nebo sken.

Přesun šarže na pec či jiné pracoviště sám neoznačuje její bedny jako Zakaleno. Přes sken lze tuto změnu provést u nepozastavených beden ve stavech Navezeno a Ve zpracování s oprávněním `orders.scan_mark_bedna_zakaleno`.

Kontrolor otevře **Přehled kontroly** (`/prehled-kontroly/`), zapíše měření a výstupní kontrolu a uloží uvolnění. Samostatně pak potvrdí **Zkontrolováno** a stav rovnání/tryskání. Podrobnosti jsou v [manuálu kontroly beden](manual_kontrola_beden.md).

Při neshodě uložte důvody a poznámku a předejte věc k rozhodnutí o dalším postupu. Opakované skutečné zpracování zaznamenejte novým krokem a následná měření u příslušné bedny; potřebné změny jejích stavů řešte dostupnými akcemi podle oprávnění.

Rovnání, tryskání a zinkování evidujte podle skutečného výsledku. Dokončení příslušného kroku šarže samo nepotvrzuje tyto technologické stavy bedny.

## 7. Ukončení šarže

### Šarže pouze s bednami z databáze

Při uložení konce kroku na pracovišti typu **Vykládání** nebo **Tryskač** se šarže s obsahem pouze z databáze automaticky přepne na **Ukončená**. Rozhoduje obsah deníku celé šarže; šarže s položkami mimo DB tento postup nepoužívá.

Po uzavření ověřte stav šarže i dokončení jednotlivých beden. Připravené bedny se následně označují K expedici a expedují podle [manuálu beden](manual_bedna.md) a [zakázek](manual_zakazka.md).

### Šarže obsahující železo mimo databázi

Provozní detail nabízí samostatné stavové operace podle aktuálního stavu a oprávnění:

| Výchozí stav | Operace a výsledný stav | Kdo ji provádí |
| --- | --- | --- |
| Zaplánovaná | Označit Naložená → Naložená | Operátor |
| Naložená | Označit zakalená ke kontrole → Zakalená ke kontrole | Operátor |
| Zakalená ke kontrole | Označit na zkontrolovaná k vyložení → Zkontrolovaná k vyložení | Kontrolor |
| Zkontrolovaná k vyložení | Ukončit šarži → Ukončená | Operátor |
| Naložená | Označit vyložená ke kontrole → Vyložená ke kontrole | Operátor |
| Vyložená ke kontrole | Ukončit šarži → Ukončená | Kontrolor |

Větev zvolte podle skutečného postupu: kontrola před vyložením nebo po vyložení. Stavové tlačítko otevře potvrzení změny. Tyto operace jsou dostupné u šarží obsahujících položky mimo DB, včetně smíšených šarží; zápis měření a výrobních stavů případných beden z databáze se řeší samostatně.

## 8. Přehledy, tisk a předání směny

- **Přehled nakládání**: otevřené nakládání pro čísla pracovišť 1–6.
- **Ostatní pracoviště** (`/prehled-pracovist/`): otevřené šarže mimo Nakládání.
- **Přehled kontroly**: bedny ve stavu Zakaleno a šarže s položkami mimo DB čekající na kontrolu.
- Administrace kroků a deníku: filtry **Pracoviště**, **Typ pracoviště** a **Konec: Ne** pomáhají najít neuzavřené průchody.

Průvodku vrutů lze znovu otevřít přes **Náhled tisku** v provozním detailu šarže i po uzavření nakládání. Tisk vychází z prvního kroku: musí být typu Nakládání a obsahovat alespoň jednu bednu z databáze.

Při předání směny ověřte poslední krok, otevřené konce, skutečný obsah roštu a případné alarmy či poznámky. U nedokončené operace předejte číslo šarže, pracoviště a zbývající práci.

## 9. Alternativa v administraci a oprávnění

Přesun lze spustit také v administraci:

- Z **Kroků šarže** vyberte právě jeden krok a akci **Přesunout šarži do dalšího kroku**; kopírují se všechny jeho řádky.
- Z **Deníku** vyberte řádky z jediného kroku a akci **Přesunout šarži do dalšího kroku z vybraných beden**; kopírují se vybrané řádky.

Obě akce otevřou formulář cílového kroku. Před vytvořením vyplňte pracoviště, datum, začátek a operátora. Po potvrzení ověřte vytvořený krok v seznamu. Podrobnosti evidence jsou v [manuálu deníku](manual_denik_pece.md).

| Operace v provozním detailu | Oprávnění v aplikaci `orders` |
| --- | --- |
| Přesun na libovolné nabízené pracoviště | `can_move_sarze` |
| Omezený přesun | `can_move_sarze_limited`; současná nabídka cílových typů zahrnuje pouze Tryskač. |
| Úprava kroku a doplnění konce | `change_sarzekrok` a `change_sarzekrokbedna` |
| Stavové operace operátora pro železo | `change_stav_sarze_operator` |
| Stavové operace kontrolora pro železo | `change_stav_sarze_kontrolor` |
| Náhled průvodky | `view_sarzekrok` a `view_sarzekrokbedna` |

## 10. Související návody

[Provozní tahák](provozni_tahak.md) · [Rychlé založení šarže](manual_rychle_zalozeni_sarze.md) · [Deník](manual_denik_pece.md) · [Kontrola beden](manual_kontrola_beden.md) · [README](../README.md)
