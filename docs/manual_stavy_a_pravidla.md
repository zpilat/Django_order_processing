# Přehled stavů a automatických pravidel

Tento přehled vysvětluje, jak spolu souvisejí výrobní stav bedny, rozhodnutí kontroly, rovnání, tryskání, zinkování a stav šarže. Slouží pro orientaci při předání směny i při hledání důvodu blokace. Podrobné zadávání popisují jednotlivé návody.

## 1. Které údaje se sledují samostatně

**Atypický průběh** umožňuje přijatou bednu převzít rovnou do Zkontrolováno s Neshodou bez důvodu. Akce resetuje všechny tři technologické stavy a vypne účtování. Při následném uložení kontroly se Tryskání řídí vyplněnou Čistotou a Rovnání přednostně měřením po rovnání, jinak po TZ. Bez těchto měření zůstane ruční stav Rovnání zachovaný. Zinkování zůstává ruční. Povinná měření se nevyžadují, ale zadané výsledky se vyhodnocují a Neshoda stále blokuje expedici. Viz [postup atypické bedny](manual_bedna.md#atypický-průběh-reklamace-a-samostatné-operace). Níže uvedené povinnosti kompletní sady měření platí pro běžný průběh.

| Údaj | Na co odpovídá | Příklad |
| --- | --- | --- |
| Výrobní stav bedny | Kde je bedna v procesu od příjmu po expedici? | Zakaleno, Zkontrolováno, K expedici |
| Uvolnění kontroly | Jaké je rozhodnutí o kvalitě? | Uvolněno, Uvolněno QS s odchylkou, Neshoda |
| Rovnání | V jakém stavu je rovnost a případná náprava? | Křivá, Rovná se, Vyrovnaná |
| Tryskání | Jaká je čistota a stav tryskání? | Špinavá, Čistá, Otryskaná |
| Zinkování | V jaké fázi je požadované zinkování? | Nezinkovat, V zinkovně, Uvolněno |
| Pozastavení bedny | Je další práce s bednou pozastavená? | Ano / Ne |
| Stav šarže | V jaké fázi je šarže jako celek? | Naložená, Zakalená ke kontrole, Ukončená |
| Začátek a konec kroku | Kdy proběhl konkrétní průchod pracovištěm? | Datum a čas nakládání nebo tryskání |

**Zkontrolováno není totéž co Uvolněno.** Bedna může mít dokončenou kontrolu a současně Neshodu. Stejně tak ukončená šarže neznamená, že jsou všechny její bedny připravené k expedici. Uvolněno u zinkování je jiný údaj než Uvolněno ve výstupní kontrole.

## 2. Běžná cesta bedny

Schéma ukazuje obvyklé pořadí práce. Jednotlivá rozhraní mohou nabízet i přímé přechody a návraty; vždy platí validace a oprávnění příslušné operace.

```text
Nepřijato → Přijato → K navezení → Navezeno
                                      ↓
                               Ve zpracování
                                      ↓
                                  Zakaleno
                                      ↓
                               Zkontrolováno
                                      ↓
                                K expedici
                                      ↓
                                 Expedováno
```

| Stav | Význam a typický vstup | Co ještě zbývá ověřit |
| --- | --- | --- |
| Nepřijato | Bedna je založená ručně nebo importem, příjem nebyl potvrzen. | Správné údaje a předpis, kladné netto, tára a množství před přijetím. |
| Přijato | Příjem na sklad potvrzený akcí nad bednami, zakázkami nebo kamionem. | Přípravu k výrobě podle skutečné situace. |
| K navezení | Požadavek na navezení se zadanou pozicí. | Skutečné navezení a správnou pozici. |
| Navezeno | Potvrzené navezení, stále se zadanou pozicí. | Zařazení do výrobního průchodu. Přes sken lze potvrdit také přímo z Přijato. |
| Ve zpracování | Bedna je ve výrobě; při uložení položky do Nakládání se nastaví automaticky. | Úplnou evidenci skutečných kroků a následné označení Zakaleno. |
| Zakaleno | Potvrzené zpracování; bedna je připravena pro zápis kontroly. | Uložit měření i výstupní kontrolu a dokončit kontrolu bedny. |
| Zkontrolováno | Kontrola byla dokončena nebo byl stav nastaven v adminu při splnění stejných podmínek úplnosti. | Výsledek uvolnění a případné dokončení rovnání, tryskání a zinkování. |
| K expedici | Bedna je označená k expedici po splnění podmínek níže. | Správný výběr dodávky, zákazníka a kamionu. Kontrola a měření jsou pouze pro čtení. |
| Expedováno | Expedice přiřadila bednu přes zakázku ke kamionu výdej. | Doklady a fyzické předání; opravy řešit návratovým postupem. |

Mimo Nepřijato se vyžaduje kladné netto, tára a množství a platný předpis; označení **Neznámý předpis** nestačí. Pozice je povinná pro K navezení a Navezeno; při uložení bedny v jiném stavu se vymaže.

Skenování **Zakaleno** je povolené z Navezeno nebo Ve zpracování a vyžaduje `orders.scan_mark_bedna_zakaleno`. Původní přímá administrační akce Přijato → Zakaleno pro reklamaci byla odstraněna. Pro reklamace a samostatné operace slouží **Převést na atypický průběh, označit zkontrolováno s neshodou**, která nastaví Zkontrolováno s Neshodou. Nabídka přechodů v adminu sama nepotvrzuje, že jsou pro uložení splněné všechny podmínky.

## 3. Kdy se co změní automaticky

| Spouštěč | Automatický výsledek | Co se tím neprovede |
| --- | --- | --- |
| Vytvoření nové bedny | Přidělí se číslo v řadě zákazníka. Při Vše tryskat a délce menší než 900 mm se Tryskání nastaví na Špinavá. | Přijetí bedny na sklad a kontrola kvality. |
| Uložení bedny do kroku Nakládání | Výrobní stav přejde na Ve zpracování a skladová pozice se vymaže. | Dokončení zpracování nebo kontrola. Odebrání řádku nevrátí původní stav. |
| Potvrzení Zakaleno přes sken | Vyhodnotí se průchody bedny tryskáním podle následující kapitoly. | Dokončení kontroly a automatické ukončení všech kroků. |
| Skutečná změna uložených měření | Kontrola začne čekat na potvrzení; příprava k expedici i expedice se zablokují. | Změna dosavadního rozhodnutí o uvolnění nebo přepočet rovnání a tryskání. |
| Uložení výstupní kontroly | Vyhodnotí se aktuální měření, čistota, uložení, uvolnění a důvody. Úspěšný zápis zruší čekající potvrzení. | U bedny Zakaleno se ještě nenastaví Zkontrolováno. |
| Dokončit kontrolu bedny ve stavu Zakaleno | Po splnění podmínek se nastaví Zkontrolováno a vypočítané Rovnání a Tryskání. | Uvolnění nevyhovující bedny ani dokončení zinkování. |
| Uložení výstupní kontroly již zkontrolované bedny | Ve stejném zápisu se znovu vypočítají Rovnání a Tryskání. | Samostatná změna zinkování. |
| Přechod kontroly do Neshody nebo přidání důvodu během Neshody | Vznikne společný neměnný snímek důvodů, měření a tehdejších požadavků v Evidenci neshod. | Každé další uložení nezakládá nový případ; uvolnění starší případy nemaže. |
| Uložení konce kroku Vykládání nebo Tryskač u šarže pouze s bednami z DB | Šarže se automaticky nastaví na Ukončená. | Automatické dokončení kontrol a expedice jednotlivých beden. |

Změna číselníku zákazníka nebo předpisu může změnit aktuálně zobrazované požadavky a posouzení. Sama hromadně nepotvrdí kontroly ani nepřepočítá technologické stavy beden. Postup je v [číselnících](manual_ciselniky.md).

## 4. Tryskání při označení Zakaleno přes sken

Pro každou šarži, ve které je bedna evidovaná, se hledá krok na pracovišti typu **Tryskač obsahující tuto bednu**. Konec tohoto kroku není podmínkou; do vyhodnocení vstupují i zahájené kroky.

| Evidované průchody | Výsledek |
| --- | --- |
| Všechny šarže bedny obsahují její průchod Tryskačem | Tryskání se nastaví na **Otryskaná**. |
| Pouze část šarží má takový průchod a bedna je Špinavá | Stav zůstane Špinavá; před potvrzením se ukáže varování s neotryskanými šaržemi. Označení Zakaleno lze potvrdit. |
| Pouze část šarží má průchod a bedna má jiný stav tryskání | Dosavadní stav se zachová bez tohoto varování. |
| Žádná šarže nemá průchod nebo bedna nemá žádné šarže | Dosavadní stav se zachová bez varování. |

Při rozdělení obsahu bedny do více šarží ověřte všechny její části. Otryskaná je výsledek evidence průchodů, nikoli náhrada skutečné kontroly čistoty; při následném dokončení kontroly může Čistota NOK znovu nastavit Špinavá.

## 5. Rozhodnutí kontroly a výpočet technologických stavů

### Uvolnění a důvody

| Zjištění | Pravidlo při uložení výstupní kontroly |
| --- | --- |
| Čistota NOK | Pouze **Neshoda**; automatický důvod Čistota. |
| Uložení NOK | Pouze **Neshoda**; automatický důvod Jiné a povinná upřesňující poznámka. |
| Nevyhovující rozhodující prohyb | Pouze **Neshoda**; automatický důvod Křivost. |
| Prohyb v pásmu QS s odchylkou | **Uvolněno QS s odchylkou** nebo **Neshoda**; automatický důvod Křivost. Čistota NOK či Uložení NOK nadále dovolují jen Neshodu. |
| Uvolněno | Aktuální důvody neshody se vymažou a jejich políčka jsou zamčená. Historie a starší případy neshod zůstávají. |
| Neshoda nebo Uvolněno QS s odchylkou | Alespoň jeden důvod; u Jiné také neprázdná poznámka. |

Rozhodující prohyb je **po rovnání**, pokud má uložené hodnoty; jinak **po TZ**. Prohyb po koulení se pro omezení uvolnění nepoužije. Počítají se jednotlivé hodnoty nad mezí proti maximálnímu povolenému počtu křivých vrutů zákazníka. Hodnota přesně na mezi není překročení a počet přesně rovný maximu je přípustný. QS mez se po rovnání nepoužívá.

Chybějící mez, povolený počet nebo měření znamenají, že prohyb nelze tímto pravidlem vyhodnotit; nejde o potvrzení vyhovujícího výsledku. Podrobné zákaznické meze a barvy jsou v [kontrole beden](manual_kontrola_beden.md#3-meze-a-zvýraznění-prohybu).

### Výpočet při dokončení kontroly a opravě zkontrolované bedny

| Podklad | Výsledný technologický stav |
| --- | --- |
| Čistota NOK | Tryskání = **Špinavá**. |
| Čistota OK a dosavadní Tryskání Špinavá nebo Otryskaná | Tryskání = **Otryskaná**. |
| Čistota OK a jiný dosavadní stav tryskání | Tryskání = **Čistá**. |
| Rozhodující prohyb je nevyhovující | Rovnání = **Křivá**. |
| Rozhodující prohyb není nevyhovující a existuje měření po rovnání | Rovnání = **Vyrovnaná**. |
| Rozhodující prohyb není nevyhovující a není měření po rovnání | Rovnání = **Rovná**, také při oranžovém prohybu po TZ. |

Tyto výpočty se provádějí při **Dokončit kontrolu bedny** a při uložení výstupní kontroly bedny již ve stavu **Zkontrolováno**. Uložení jednotlivého měření je nespouští. Samostatné tlačítko pro opravu rovnání a tryskání se nepoužívá.

Pro dokončení kontroly se vyžaduje stav Zakaleno, nepozastavená bedna, oprávnění kontrolora a úplné aktuální podklady: uložená Čistota a Uložení OK/NOK, rozhodnutí o uvolnění, alespoň jedno měření prohybu po TZ, běžná mez a maximální počet křivých u zákazníka. Při Křivosti se požadují také oba počty křivých, včetně přípustné nuly. Výjimkou je oranžová položka Prohyb po TZ, kdy oba počty nejsou pro dokončení povinné. QS maximum je volitelné. Stejné podmínky úplnosti a souladu se ověřují při opravě zkontrolované bedny a při nastavení Zkontrolováno v adminu.

## 6. Co blokuje přípravu k expedici a expedici

| Podmínka | Co má být splněno |
| --- | --- |
| Tryskání | **Čistá** nebo **Otryskaná**. |
| Rovnání | **Rovná** nebo **Vyrovnaná**. |
| Zinkování | **Nezinkovat** nebo **Uvolněno**. Samotné Pozinkováno nestačí. |
| Výstupní kontrola | Nesmí mít uložené **Uvolnění = Neshoda** ani čekat na potvrzení po změně měření. |
| Pozastavení | Expediční akce odmítají pozastavené bedny. |
| Výběr pro expedici | Expedované bedny musí být K expedici; zkontrolujte zákazníka a cílový kamion výdej. |
| Pouze komplet u zákazníka | Ověřit kompletnost podle podmínek expediční operace; nepřipravená část zakázky může expedici blokovat. |

Připravenost neodvozujte jen z barvy řádku nebo indikátoru **Komplet**. Komplet vychází z výrobních stavů, nikoli z úplného posouzení měření. Server při expedici znovu kontroluje uloženou Neshodu a čekající potvrzení.

Od **K expedici** jsou kontrola a měření pouze pro čtení. Pro opravu vraťte bednu na Zkontrolováno; u Expedováno nejprve vraťte celou zakázku z expedice. Oprávnění správce ani právo upravovat expedované bedny tento zákaz zápisu měření neruší. Viz [opravy](manual_mimoradne_situace.md#7-oprava-po-expedici-nebo-špatný-kamion-výdej).

Zinkování **V zinkovně** lze zadat pouze u bedny Zkontrolováno. Jednotlivé fáze zinkování evidujte podle skutečnosti; dokončení kontroly zinkování samo nemění.

## 7. Stav šarže a ukončení kroků

Stav šarže a konec konkrétního kroku nejsou zaměnitelné. Přesun vytvoří nový krok a zkopíruje zvolené položky; zdrojový deník zůstane zachovaný. Chybějící konec zdroje může vyvolat varování i přesto, že nový krok vznikl. Ověřte výsledek a doplňte skutečný konec, místo opakování přesunu.

| Situace | Změna stavu šarže |
| --- | --- |
| Ruční založení | Výchozí stav **Vytvořená**. |
| Zaplánovat šarži do výroby | Vytvořená → **Zaplánovaná**. |
| Rychlé založení s prvním krokem Nakládání | Vytvoří **Naloženou** šarži. |
| Uložení konce Vykládání nebo Tryskače, obsah pouze z DB | Automaticky **Ukončená**. |
| Obsah zahrnuje položky mimo DB, včetně smíšené šarže | Používají se níže uvedené stavové operace podle oprávnění. |

Pro šarže s položkami mimo DB existují dvě běžné větve:

```text
Zaplánovaná → Naložená → Zakalená ke kontrole
                              ↓
                   Zkontrolovaná k vyložení → Ukončená

              Naložená → Vyložená ke kontrole → Ukončená
```

Naložená, Zakalená ke kontrole a Vyložená ke kontrole se potvrzují operátorem. Kontrolor mění Zakalená ke kontrole na Zkontrolovaná k vyložení, případně ukončuje z Vyložená ke kontrole. Zkontrolovaná k vyložení se ukončuje operátorem. Konkrétní oprávnění uvádějí [role](manual_role_a_opravneni.md#4-oprávnění-pro-výrobu-a-šarže).

Číselník stavů šarže obsahuje také **Pozastavená** a **Zrušená**. Nejde o příznak pozastavení jednotlivé bedny ani o automatické odstranění jejích řádků. Jejich použití řešte jako řízenou změnu evidence; provozní tlačítka pro výše uvedené větve je nenabízejí jako univerzální návrat.

## 8. Související dokumentace a kód

[Přehledy a význam ukazatelů](manual_prehledy_a_ukazatele.md) vysvětlují, jak se tyto stavy promítají do souhrnů skladu, kompletnosti a historických výkonů.

[Provozní tahák](provozni_tahak.md) · [Bedny](manual_bedna.md) · [Kontrola beden](manual_kontrola_beden.md) · [Průchod šarže](manual_pruchod_sarze.md) · [Mimořádné situace a opravy](manual_mimoradne_situace.md) · [Číselníky](manual_ciselniky.md) · [Role a oprávnění](manual_role_a_opravneni.md)

Implementace: `orders/choices.py`, `orders/models.py`, `orders/views.py`, `orders/actions.py` a služby `orders/services/stav_bedny_service.py`, `orders/services/mereni_bedny_service.py`, `orders/services/expedice_service.py`, `orders/services/evidence_neshod_service.py`.
