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

Z administrace beden či zakázek lze pro všechny zákazníky použít akci **Vytisknout vyplněné KKK**, případně variantu pro zakázky. Výběr musí patřit jednomu zákazníkovi a každá bedna musí mít uloženou kontrolu. V administraci kamionů je tisk vyplněných KKK dostupný pouze pro kamion výdej; bedny bez kontroly se přeskočí s varováním. Prázdné KKK mají vlastní akci a zákaznické šablony. Před tiskem ověřte měření a uvolnění.

Vyplněné KKK používají jednu společnou šablonu. Hlavní popisy jsou vždy česky, pomocné popisy se řídí polem **Zkratka státu** zákazníka: **D** a **A** přidají němčinu, **I** italštinu, **CZ** zobrazí pouze češtinu. U nevyplněné nebo neznámé zkratky státu se zobrazí pouze čeština. Mezery kolem zkratky a velikost písmen výběr jazyka neovlivňují. Vedle českého stavu uvolnění se za lomítkem zobrazí pomocný překlad stavů Uvolněno, Uvolněno s odchylkou a Neshoda. Nerozhodnutý stav pomocný překlad nemá.

Minimální počty vzorků se čtou z dočasného slovníku `QUALITY_CARD_CONFIG_BY_CUSTOMER` v `orders/quality_card_config.py`. Každý zákazník má čtyři pojmenované položky: `mechanicka_zkouska`, `prohyb`, `tvrdost` a `nazev_protokolu`. Výchozí hodnoty jsou převzaté z požadavků dosavadních zákaznických karet a zobrazují se česky i ve zvoleném pomocném jazyce. Hodnota `None` znamená neuvedené minimum; pomocný text pro takovou skupinu se netiskne. Toto nastavení určuje popis požadovaného minima, nikoli počet vytištěných hodnot. Název protokolu se tiskne v záhlaví: EUR má na dvou řádcích HPM - F 73c a Eurotec - F.3, SSH má HPM - F 11b, HPM má HPM - F 86a a ostatní zákazníci zatím HPM - F XXX. Více řádků názvu se ve slovníku odděluje znakem nového řádku (`\n`).

Vyplněná karta tiskne nejvýše prvních 10 hodnot jednotlivých zkoušek; pro vrstvu použije první uloženou hodnotu. Úplný seznam měření je dostupný v aplikaci. Pokud bedna podle zákaznických pravidel není určena k měření tvrdosti a povrchu, karta místo minimálního počtu vzorků tvrdosti i předpisu pro povrch a jádro vytiskne pomlčku (—).

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
- **Vyplněná KKK nejde vytisknout:** ověřte výběr jednoho zákazníka, uloženou kontrolu u každé bedny, hmotnost a předpis zakázky. U kamionu musí jít o jeden kamion výdej.
- **Chybí pomocné popisy na vyplněné KKK:** ověřte pole Zkratka státu zákazníka; pro CZ, nevyplněnou nebo neznámou zkratku se pomocné popisy netisknou.

## 9. Související dokumentace a kód

[Bedny](manual_bedna.md) · [Rychlé založení šarže](manual_rychle_zalozeni_sarze.md) · [Zakázky](manual_zakazka.md) · [README](../README.md)

[Provozní tahák](provozni_tahak.md) · [Průchod šarže výrobou](manual_pruchod_sarze.md)

Implementace: `orders/models.py` (`KontrolaBedny`, `MereniBedny`, `Bedna.limity_prohybu`), `orders/forms.py` (`KontrolaBednyForm`, `MereniBednyFormSet`), `orders/views.py` (`bedna_kontrola_view`, `bedna_mereni_zkousky_view`, `bedna_scan_zkontrolovano_view`), `orders/services/mereni_bedny_service.py` a `orders/services/filled_quality_cards_service.py`. Pomocné překlady vyplněných KKK jsou ve slovnících `HELPER_LABELS` v `orders/quality_card_labels.py`; minimální počty vzorků a názvy protokolů jsou nastavené v `orders/quality_card_config.py`.
