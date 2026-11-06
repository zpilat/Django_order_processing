# Uživatelský manuál: Číselníky a nastavení zákazníka

Návod slouží pracovníkům, kteří připravují zákazníky a společná nastavení pro příjem, výrobu, kontrolu a doklady. Popisuje také dopad změn na existující data. Technologické a obchodní hodnoty zadávejte podle schválených podkladů.

## 1. Kde nastavení najít a kdo je může měnit

V administraci otevřete blok **Číselníky**. Obsahuje zákazníky, odběratele, ceny, typy hlav, předpisy, pletiva a pozice. **Pracoviště** jsou v bloku **Výroba**.

Pro čtení je potřeba aktivní staff účet a oprávnění k zobrazení příslušné agendy; pro založení nebo změnu také odpovídající oprávnění. Například zákazníci používají `orders.view_zakaznik`, `orders.add_zakaznik` a `orders.change_zakaznik`. Přístup ke čtení tohoto návodu sám právo upravovat číselníky nepřiděluje.

Před úpravou používaného záznamu ověřte, které zakázky či bedny na něj navazují. Opravu překlepu a novou technologickou revizi řešte odlišně: nová revize předpisu má dostat vlastní záznam, aby původní zakázky zachovaly původní požadavky.

## 2. Založení zákazníka

1. V **Zákaznících** zvolte **Přidat** a vyplňte název, zkrácený název a zkratku. Všechny tři údaje musí být v daném číselníku jedinečné.
2. Zkratku (nejvýše 3 znaky) dohodněte se správcem před prvním uložením. Administrace ji po založení nabízí pouze pro čtení; aplikace podle ní vybírá některá pravidla a tiskové či importní postupy.
3. Vyplňte adresu, stát, zkratku státu a kontakty. Zkratka státu zákazníka ovlivňuje pomocné popisy vyplněné KKK: **D/A** německy, **I** italsky, **CZ** pouze česky. Prázdná nebo jiná zkratka pomocné popisy nepřidá.
4. Zvolte jedinečnou **Číselnou řadu** pro bedny a ověřte ji se správcem proti již používaným číslům. První bedna zákazníka dostane základ řady + 1; další navazují na jeho nejvyšší existující číslo. Samotná jedinečnost základu nezaručuje, že se rozsahy v budoucnu nepřekryjí.
5. Nastavte podmínky zákazníka a kontrolu kvality podle následujících kapitol.
6. Uložte zákazníka a připravte jeho předpisy a ceny. Před prvním příjmem ověřte požadované funkce na zkušebních datech mimo běžné výrobní zakázky.

**Založení zákazníka samo nezavádí novou importní strategii ani meze prohybu.** XLSX import má implementované strategie pro EUR a SPX. Meze prohybu a výběr beden pro tvrdost se řídí pravidly v kódu podle zkratky zákazníka. U nové zkratky musí správce s vývojářem ověřit podporu; bez známé běžné meze prohybu nelze dokončit kontrolu bedny. Podrobné meze jsou v [návodu kontroly](manual_kontrola_beden.md#3-meze-a-zvýraznění-prohybu).

## 3. Podmínky zákazníka

| Nastavení | Význam a dopad |
| --- | --- |
| Proforma po bednách | Určuje členění proforma faktury po jednotlivých bednách. Po změně zkontrolujte náhled dokladu. |
| Vše tryskat | Při vytvoření nové bedny s délkou zakázky **menší než 900 mm** nastaví Tryskání na Špinavá. U delších dílů ani při délce přesně 900 mm se tento automatický krok neprovede. Změna nastavení nepřepíše existující bedny. |
| Pouze komplet | Omezuje expedici na kompletní zakázky; před zapnutím ověřte, zda se zákazníkem nejsou domluvené dílčí dodávky. |
| Fakturovat rovnání | Zohledňuje rovnání při ceně bedny ve stavu Vyrovnaná. Vyžaduje také odpovídající cenu rovnání. |
| Fakturovat tryskání | Zohledňuje tryskání při ceně bedny ve stavu Otryskaná. Vyžaduje také odpovídající cenu tryskání. |

Fakturační příznaky nenahrazují záznam skutečně provedené operace. Po změně ověřte výpočet a doklady existujících zakázek, kterých se týká.

## 4. Kontrola kvality zákazníka

Otevřete **Zákazníci → konkrétní zákazník → Kontrola kvality**.

| Pole | Co zadat |
| --- | --- |
| Celkový počet vrutů odebraných pro kontrolu prohybu | Velikost odebraného vzorku, při vyplnění nejméně 1. Jde o jiný údaj než minimum zapisovaných hodnot. |
| Maximální počet křivých vrutů při kontrole prohybu | Nejvyšší přípustný počet křivých. **0** znamená žádný povolený křivý vrut. Prázdné pole je nenastavené maximum; dokončení kontroly bedny vyžaduje jeho doplnění. |
| Minimum hodnot mechanických zkoušek | Uváděné minimum zvlášť pro ohyb a pro krut. |
| Minimum hodnot prohybu | Uváděné minimum pro každou prováděnou fázi prohybu; nezaměňujte s celkovou velikostí vzorku. |
| Minimum hodnot tvrdosti | Uváděné minimum zvlášť pro povrch a jádro u beden vybraných k měření tvrdosti. |
| Název protokolu | Označení v záhlaví vyplněné KKK. Více označení napište na samostatné řádky; prázdné pole použije **HPM - F XXX**. |

Všechna tři minima zapisovaných hodnot mohou zůstat prázdná (minimum neuvedeno), ale vyplněná musí být alespoň 1. Jsou podkladem pro zobrazení rozsahu měření a KKK; neberte je jako potvrzení, že systém automaticky vynutí počet všech zapsaných měření.

**Dopad změny:** kontrola a nově generovaná vyplněná KKK používají aktuální zákaznické nastavení. Změna maxima může změnit dostupné rozhodnutí o uvolnění i zvýraznění již uložených měření. Sama znovu neuloží kontroly ani nepřepočítá technologické stavy všech beden. U dotčených rozpracovaných beden ověřte měření a znovu uložte výstupní kontrolu; od K expedici postupujte podle [návodu oprav](manual_mimoradne_situace.md#6-oprava-kontroly-před-expedicí).

Uložené případy v **Evidenci neshod** mají vlastní neměnný snímek tehdejších požadavků a měření. Změna zákazníka jej nepřepíše. Dříve stažené PDF se také nemění; nové vygenerování může mít jiný obsah.

## 5. Předpisy, pletiva a typy hlav

### Založení předpisu

1. V **Předpisech** zvolte **Přidat** a přiřaďte správného zákazníka.
2. Zadejte název podle používaného označení výkresu či předpisu. U importovaných dat zachovejte dohodnutý formát názvu, podle kterého strategie předpis vyhledává.
3. Doplňte skupinu TZ, požadavky na ohyb, krut, povrch, jádro a vrstvy, údaje popouštění a šaržování, případně pletivo a poznámku.
4. Podle používaných tisků doplňte také popisy požadavků. Zaškrtněte **Aktivní**, pokud má být předpis nabízen pro nové přiřazení.
5. V cenách ověřte přiřazení nového předpisu a správné délkové intervaly.

Běžné požadavky zkoušek se čtou z předpisu přiřazeného zakázce. Prohyb má samostatná pravidla podle zákazníka a délky. Prázdný text požadavku není potvrzením vyhovujícího výsledku.

### Nová revize používaného předpisu

Přepsání existujícího předpisu změní požadavky zobrazované i u zakázek, které na něj již odkazují. Pokud má nová technologie platit až pro další zakázky:

1. Otevřete původní předpis a upravte údaje pro novou revizi včetně názvu podle dohodnutého označení.
2. Použijte **Uložit jako novou položku včetně přiřazených cen + deaktivovat původní předpis**.
3. Ověřte nový aktivní předpis, původní neaktivní předpis a vazby cen. Tlačítko připojí nový předpis ke **stejným existujícím cenovým záznamům**; nevytváří samostatnou kopii částek.
4. Nový předpis přiřazujte dalším zakázkám. Existující zakázky zůstávají u původního; jejich případné převedení je samostatné rozhodnutí.

Deaktivace předpis nemaže a zachová vazby starších zakázek. Pro nové přiřazení se běžně nabízejí aktivní předpisy. Při každé revizi používané v importu ověřte náhled, zda strategie nové označení skutečně nalezne.

**Pletiva** obsahují označení A–Z a parametry pletiva. **Typy hlav** obsahují jedinečný název a volitelný popis; musí odpovídat označení používanému při zadávání a importu. Změna společného záznamu se projeví všude, kde je použitý.

## 6. Ceny a délkové intervaly

1. V **Cenách** založte záznam se zákazníkem a srozumitelným popisem.
2. Vyberte předpisy daného zákazníka, na které se má vztahovat. Bez přiřazeného předpisu se cena pro zakázku nenajde.
3. Vyplňte **Délka od (včetně)** a **Délka do (vyjma)**. Například interval 100–200 platí pro délku 100 mm, ale nikoli pro 200 mm.
4. Zadejte cenu kalení v EUR/kg a podle potřeby ceny rovnání a tryskání.
5. Ověřte, že pro zákazníka, předpis a konkrétní délku existuje právě jeden odpovídající cenový záznam. Pro navazující interval použijte například 200–300.
6. Zkontrolujte cenu na zakázce a náhled proformy, včetně příplatků a označení Fakturovat u beden.

Pokud základní cenu nenajde žádný záznam nebo vyhovuje více záznamů, výpočet ceny kalení vrátí **0**; při překryvu také zapíše varování do logu. Překryvy a mezery proto prověřte při každé úpravě.

**Ceny se vyhledávají z aktuálního číselníku.** Změna částek nebo vazeb může ovlivnit i přepočet existujících a expedovaných zakázek a opětovný tisk dokladů. Číselník nemá pole platnosti od/do ani automatickou fixaci ceny k datu příjmu. Před změnou dohodněte rozsah s odpovědným pracovníkem a uschovejte již vydané doklady.

## 7. Odběratelé, pozice a pracoviště

### Odběratelé

Odběratel určuje příjemce dodávky; zákazník je samostatná vazba. V **Odběratelích** vyplňte název, jedinečný zkrácený název a zkratku, adresu a kontakty. Zkratku lze v administraci zadat při vytvoření, poté je jen pro čtení. Odběratele lze určit u zakázky i kamionu výdej; před tiskem zkontrolujte skutečný cíl dodávky. Oprava adresy se může projevit také při opětovném generování staršího dokladu.

### Skladové pozice

V **Pozicích** zkontrolujte kapacitu a aktuální obsazenost. Kód je jedinečné písmeno A–Z. Současná administrace jej nabízí pouze pro čtení i ve formuláři přidání; založení nové pozice nebo změnu kódu řešte se správcem jako řízené doplnění číselníku. U existující pozice lze upravit kapacitu. Její snížení samo nepřesune uložené bedny.

Bedny ve stavech K navezení a Navezeno vyžadují pozici. Při uložení v jiném výrobním stavu se pozice maže. Změna kapacity proto nenahrazuje správné přiřazení a pohyb beden.

### Pracoviště

V **Výroba → Pracoviště** vyplňte jedinečný kód, název, zkrácený název, případně umístění a správný **Typ pracoviště**. Typ ovlivňuje provozní přehledy a vyhodnocení průchodu výrobou, včetně tryskání.

Rychlé založení šarže vyžaduje **právě jeden záznam typu Nakládání** v číselníku. Čísla nakládacích pracovišť 1–6 se zadávají u šarže; pro tuto funkci nezakládejte šest záznamů typu Nakládání. Pokud typ chybí nebo je vícekrát, formulář založení odmítne.

Přejmenování pracoviště ovlivní zobrazení dřívějších kroků, které na něj odkazují. Změnu typu u používaného pracoviště nejprve konzultujte se správcem, protože může změnit i vyhodnocení již evidovaných průchodů.

## 8. Ověření změny a běžné problémy

Po založení zákazníka nebo revizi nastavení zkontrolujte vazby předpisů, náhled importu (je-li podporovaný), požadavky v kontrole bedny, výpočet ceny a potřebné tiskové výstupy. U změny společného nastavení prověřte také dotčené existující zakázky.

| Problém | Co ověřit |
| --- | --- |
| Nový zákazník nemůže importovat Excel | Zda má jeho zkratka implementovanou strategii; založení zákazníka ji nevytváří. |
| Import použil Neznámý předpis | Název a aktivitu očekávaného předpisu; před příjmem opravte přiřazení v zakázce. |
| Nelze dokončit kontrolu | Uložený prohyb po TZ, známou běžnou mez pro zákazníka a vyplněný maximální počet křivých vrutů, včetně přípustné nuly. |
| Cena kalení vychází 0 | Zákazníka, přiřazení předpisu, hranice intervalů, překryvy a zadanou částku. |
| Starší doklad po novém tisku vypadá jinak | Aktuální ceny, adresy, předpis a zákaznické nastavení; porovnejte s dříve vydaným PDF. |
| Číselník nelze smazat | Navazující záznamy a oprávnění. U předpisu ukončeného pro nové použití využijte deaktivaci. |

## 9. Související dokumentace a kód

[Stavy a automatická pravidla](manual_stavy_a_pravidla.md) · [Role a oprávnění](manual_role_a_opravneni.md)

[Mimořádné situace a opravy](manual_mimoradne_situace.md) · [Kamiony a importy](manual_kamion.md) · [Zakázky](manual_zakazka.md) · [Kontrola beden](manual_kontrola_beden.md) · [Bezpečnost a oprávnění](security.md) · [README](../README.md)

Implementace: `orders/models.py` (`Zakaznik`, `Odberatel`, `Predpis`, `Cena`, `Pletivo`, `TypHlavy`, `Pozice`, `Zarizeni`, výpočty `Zakazka` a `Bedna`), `orders/admin.py`, `orders/forms.py`, `orders/import_strategies.py` a `orders/services/filled_quality_cards_service.py`.
