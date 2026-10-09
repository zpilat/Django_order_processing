# Uživatelský manuál: Kontrola beden

Kontrola propojuje naměřené hodnoty s výstupní kontrolou a rozhodnutím o uvolnění konkrétní bedny. Výrobní stav Zkontrolováno se potvrzuje samostatnou operací.

## 1. Otevření kontroly

- Z **Přehledu kontroly** (`/prehled-kontroly/`) otevřete číslo bedny. Přehled obsahuje bedny ve stavu Zakaleno a šarže železa mimo databázi čekající na kontrolu. Čekání alespoň 4 hodiny se zvýrazňuje.
- Naskenujte kartu bedny kamerou nebo čtečkou a v detailu zvolte **Kontrola bedny**.
- Pro postupné zadávání použijte **Další bedna ke kontrole**. Čtečka pro kontrolu je na `/bedny/skener-ctecka/?cil=kontrola`.
- Přímá cesta má tvar `/bedny/scan/123456/kontrola/`; použijte skutečné interní číslo bedny.

Před zápisem ověřte číslo, zákazníka, artikl a rozměr. Pořadí bedny se vztahuje k původní zakázce i po jejím rozdělení při expedici.

## 2. Zadání měření

Sekce **Naměřené hodnoty a jednotlivé zkoušky** nabízí Ohyb, Krut, Prohyb po TZ, Prohyb po koulení, Prohyb po rovnání, Tvrdost povrchu, Tvrdost jádra a Vrstva.

1. U zkoušky klikněte na **Zadat / upravit hodnoty**.
2. Zkontrolujte požadavek. Běžné zkoušky čerpají požadavky z předpisu zakázky; prohyb má meze podle zákazníka a délky.
3. Zadejte jednotlivé hodnoty. Prohyb se zadává v mm, ostatní hodnoty v jednotkách předpisu. Lze použít desetinnou čárku, nejvýše čtyři desetinná místa.
4. Další řádky přidejte pomocí **+ Přidat hodnotu**. Prázdné nové řádky se neuloží; checkbox vlevo označí existující hodnotu ke smazání při uložení.
5. Klikněte na **Uložit hodnoty**. Vrátíte se na kontrolu bedny.

Měření se ukládá samostatně pro každou zkoušku, včetně uživatele a času měření. Při prvním zápisu vznikne kontrola, pokud dosud neexistovala. Odkaz **Zpět na kontrolu bedny** neuloží rozpracované hodnoty.

Tvrdost povrchu a jádra se nabízí jen u beden vybraných pravidly vzorkování. Pro SSH, SWG a ROT se výběr řídí počtem beden původní zakázky; pro ostatní zákazníky se vybírá první bedna. Chybějící sekce tvrdosti proto může být očekávaná.

## 3. Meze a zvýraznění prohybu

`L` znamená délku zakázky v mm. Hodnota přesně na mezi je přípustná.

| Zákazník | Běžná horní mez prohybu |
| --- | --- |
| EUR, HPM, FIS | `0,006 × L` mm |
| SPX, SSH, ROT | `0,004 × L` mm |
| SWG, délka do 300 mm včetně | `0,006 × L` mm |
| SWG, délka nad 300 mm | `1,8` mm |

ROT má navíc mez pro uvolnění s odchylkou `0,006 × L` mm. Hodnoty se zvýrazňují podle běžné meze, meze odchylky a překročení. U zákazníka bez pravidla se mez nezobrazuje.

Zvýraznění pomáhá s posouzením. Automaticky nevolí uvolnění ani nemění výrobní stav bedny. Rozhodnutí zaznamenejte podle výsledků kontroly a příslušného předpisu.

## 4. Výstupní kontrola a rozhodnutí

Vyplňte:

- **Čistota** a **Uložení**: nezadáno, OK nebo NOK.
- **Počet křivých 1. měření / 2. měření**: počty křivých vrutů z kontrolního vzorku. U pole je velikost vzorku nastavená pro zákazníka.
- **Uvolnění**: nerozhodnuto (`--------`), Neshoda, Uvolněno nebo Uvolněno s odchylkou.
- **Poznámka**: vysvětlení výsledku nebo provozní informace.

Při **Neshodě** vyberte alespoň jeden důvod. Lze vybrat více důvodů: čistota, nízký/vysoký krut, nízký ohyb, nízká/vysoká tvrdost povrchu či jádra, vrstva, křivost, pomíchané vruty, chyba v procesu nebo Jiné. U **Jiné** je povinné upřesnění v poznámce.

Klikněte na **Uložit kontrolu bedny**. U rozhodnutí se eviduje, kdo a kdy stav uvolnění změnil; návrat na nerozhodnuto tyto aktuální údaje vymaže, historie zůstává.

## 5. Potvrzení výrobního stavu

Po uložení výsledků použijte **Označit bednu jako zkontrolovanou**:

1. Otevřete navazující formulář.
2. Nastavte stav rovnání a tryskání podle skutečného výsledku.
3. Potvrďte změnu. Bedna přejde do stavu **Zkontrolováno**.

U již zkontrolované bedny se odkaz jmenuje **Upravit stav rovnání a tryskání**. Operace je dostupná pro nepozastavené bedny ve stavech Navezeno, Ve zpracování, Zakaleno a Zkontrolováno s oprávněním `orders.mark_bedna_zkontrolovano`.

Uložení měření nebo uvolnění samo výrobní stav nezmění. Označení Zkontrolováno samo nezapisuje měření ani uvolnění. Před pokračováním zkontrolujte obě části evidence.

## 6. Přehled neshod, audit a tisk

**Přehled neshod** (`/prehled-neshod/`) ukazuje bedny s aktuálním rozhodnutím Neshoda, důvody, poznámku a autora i datum rozhodnutí. Filtruje se podle zákazníka, důvodu a dne. Po změně uvolnění na jinou hodnotu bedna z přehledu zmizí; starší rozhodnutí zůstává v historii.

Administrace **Kontroly beden** a **Měření beden** slouží k prohlížení záznamů a historie. Údaje se upravují provozním formulářem, na který vede odkaz v poli **Formulář kontroly bedny**; detail měření má obdobný odkaz v poli **Formulář měření zkoušky**.

Pro EUR lze z administrace beden, zakázek nebo kamionů příjem použít akci **Vytisknout vyplněné KKK (EUR)**, případně variantu pro zakázky či kamion. Výběr musí patřit jednomu zákazníkovi a každá bedna musí mít uloženou kontrolu. Prázdné KKK mají vlastní akci. Před tiskem ověřte měření a uvolnění; u jiných zákazníků vyplněná varianta zatím není podporovaná.

Vyplněná karta tiskne nejvýše prvních 10 hodnot jednotlivých zkoušek; pro vrstvu použije první uloženou hodnotu. Úplný seznam měření je dostupný v aplikaci.

## 7. Oprávnění a souběžné změny

| Úkol | Potřebné oprávnění |
| --- | --- |
| Zobrazení kontroly | `orders.view_bedna` nebo `orders.mark_bedna_zkontrolovano` |
| Zápis kontroly a měření | `orders.mark_bedna_zkontrolovano` |
| Zápis u pozastavené bedny | Navíc `orders.change_pozastavena_bedna` |
| Zápis u expedované bedny | Navíc `orders.change_expedovana_bedna` |

Oprávnění k úpravě pozastavené bedny umožňuje zápis výsledků, ale její označení jako Zkontrolováno přes tento postup zůstává blokované.

Pokud jiný uživatel mezitím změnil kontrolu nebo měření, systém odmítne přepsat jeho údaje. Použijte **Načíst aktuální údaje / hodnoty**, zkontrolujte změny a zadejte úpravu znovu.

## 8. Nejčastější problémy

- **Kontrola je jen pro čtení:** ověřte oprávnění, pozastavení a expedici bedny.
- **Neshoda nejde uložit:** vyberte důvod; u Jiné doplňte poznámku.
- **Chybí požadavek zkoušky:** zkontrolujte předpis zakázky; prázdný požadavek neznamená automatické vyhovění zkoušky.
- **Chybí tlačítko Zkontrolováno:** ověřte výrobní stav, pozastavení a oprávnění.
- **Bedna stále čeká v přehledu kontroly:** uložení výsledků ji nepřepne ze stavu Zakaleno; potvrďte výrobní stav.
- **Vyplněná KKK nejde vytisknout:** ověřte zákazníka EUR, jednotný výběr a uloženou kontrolu u každé bedny.

## 9. Související dokumentace a kód

[Bedny](manual_bedna.md) · [Rychlé založení šarže](manual_rychle_zalozeni_sarze.md) · [Zakázky](manual_zakazka.md) · [README](../README.md)

[Provozní tahák](provozni_tahak.md) · [Průchod šarže výrobou](manual_pruchod_sarze.md)

Implementace: `orders/models.py` (`KontrolaBedny`, `MereniBedny`, `Bedna.limity_prohybu`), `orders/forms.py` (`KontrolaBednyForm`, `MereniBednyFormSet`), `orders/views.py` (`bedna_kontrola_view`, `bedna_mereni_zkousky_view`, `bedna_scan_zkontrolovano_view`), `orders/services/mereni_bedny_service.py` a `orders/services/filled_quality_cards_service.py`.
