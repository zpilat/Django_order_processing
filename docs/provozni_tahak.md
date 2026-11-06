# Provozní tahák: od příjmu po expedici

Stručný postup pro obsluhu, vhodný k vytištění. Výrobní operace a jejich pořadí se řídí předpisem zakázky. Podrobné zadávání popisují návody uvedené u jednotlivých kroků.

## Běžný pracovní postup

| Krok | Co udělat v aplikaci | Co ověřit před pokračováním |
| --- | --- | --- |
| **1. Příjem** | Založit kamion příjem, zadat nebo importovat zakázky a bedny, potvrdit příjem na sklad. | Správný zákazník, artikl, rozměr a předpis. Mimo stav Nepřijato musí mít bedna kladné netto, táru a množství. |
| **2. Příprava a nakládání** | Podle postupu označit bedny K navezení / Navezeno a zadat pozici. V přehledu nakládání vybrat pracoviště 1–6 a založit šarži nebo pokračovat v otevřené. | Číslo přípravku, operátor, datum a čas začátku. Bedny musí být nepozastavené a v povoleném stavu. |
| **3. Rozložení roštu** | Vybrat či naskenovat bedny, nastavit podíly a uložit patra. Zkontrolovat průvodku, doplnit datum a čas konce nakládání. | Rychlé zadání: patra 1–6, nejvýše 5 položek na patro, každá 5–100 %, součet nejvýše 100 %. Uložením beden do Nakládání přejdou na Ve zpracování. |
| **4. Průchod výrobou** | V detailu šarže uzavřít dokončený krok a použít Přesunout do dalšího kroku. Vybrat cílové pracoviště, zadat začátek a operátora, ověřit kopírované položky. | Nový krok odpovídá skutečnému průchodu. Každý dokončený krok má datum i čas konce; při práci přes půlnoc správný den. |
| **5. Kontrola** | Po dokončení příslušného zpracování označit bedny jako Zakaleno. Otevřít kontrolu, uložit měření, výstupní kontrolu a rozhodnutí o uvolnění. Poté použít Dokončit kontrolu bedny a ověřit vypočtené rovnání/tryskání. | Správné číslo bedny, požadavky a výsledky. Křivost a Čistota se nastavují automaticky; Čistota NOK i Uložení NOK dovolují pouze Neshodu. Uložení NOK vynutí Jiné s poznámkou. Při Neshodě nebo Uvolněno QS musí být důvod, u Jiné poznámka. Uvolněno důvody vymaže a zamkne. Před označením Zkontrolováno musí být uložená Čistota a Uložení (OK/NOK), rozhodnutí o Uvolnění a při důvodu Křivost oba počty křivých (nula platí jako vyplněná). Je-li položka Prohyb po TZ oranžová, oba počty ani rovnání se pro označení Zkontrolováno nevyžadují; platí i při Neshodě z dalších důvodů. |
| **6. Dokončení beden** | Dokončit požadované rovnání, tryskání či zinkování a zapsat skutečné stavy. Připravené bedny označit K expedici. | Pro K expedici musí být tryskání Čistá/Otryskaná, rovnání Rovná/Vyrovnaná a zinkování Nezinkovat/Uvolněno. Uvolnění nesmí být Neshoda; od K expedici jsou kontrola a měření pouze pro čtení. |
| **7. Expedice** | Vybrat připravené bedny nebo zakázky, provést expedici do kamionu výdej a vytisknout potřebné doklady. | Správný zákazník, výběr a kamion. Po částečné expedici ověřit zbývající bedny a případnou novou zakázku. |

Při potvrzení **Zakaleno přes sken** se Tryskání nastaví na **Otryskaná**, pokud všechny šarže bedny zahájily krok Tryskače s touto bednou; konec kroku není podmínkou. Při částečném otryskání zůstane stav zachovaný; u stavu Špinavá se již před uložením nad tlačítkem zobrazí varování s neotryskanými šaržemi. Přesun lze potvrdit, po uložení se varování neopakuje. Žádná otryskaná šarže nebo žádné šarže znamenají ponechání stavu bez varování.

Tlačítko **Dokončit kontrolu bedny** použijte ve stavu **Zakaleno**. Při potvrzení se automaticky uloží Tryskání podle Čistoty a Rovnání podle prohybu po rovnání, jinak po TZ. Oranžový prohyb po TZ znamená Rovná. Na potvrzovací stránce ověřte vypočtené stavy. Bez uloženého prohybu po TZ, standardního maxima nebo povoleného počtu křivých u zákazníka je potvrzení zablokované; QS maximum zůstává volitelné. U již zkontrolované bedny se rovnání a tryskání přepočítají při **uložení výstupní kontroly**, i bez změny uvolnění. Po opravě měření proto uložte i výstupní kontrolu; samostatné tlačítko pro úpravu stavů již není. Podrobnosti a tabulky stavů jsou v [manuálu kontroly](manual_kontrola_beden.md#5-potvrzení-výrobního-stavu).

## Pět pravidel při každé směně

**Nepotvrzená měření nelze expedovat.** Po změně měření nejprve uložte úplnou výstupní kontrolu. Příprava k expedici i expedice to hlídají na serveru, také v jiném okně. Hromadná akce Zkontrolováno je odstraněná; změna stavu v adminu vyžaduje stejné úplné podklady jako dokončení kontroly. Při zpřísnění limitů znovu uložte rozhodnutí a důvody podle aktuálního výsledku.

**Po opravě měření uložte i výstupní kontrolu.** Červeně označené hodnoty se liší od databáze. U Zkontrolováno nelze běžným odkazem odejít na jinou bednu či přehled do úspěšného uložení; měření stejné bedny je dostupné a rozepsaná kontrola se po návratu obnoví. Samotná změna měření ponechá v databázi čekající potvrzení. Uložením kontroly se potvrdí také automatické Rovnání a Tryskání. U Zakaleno čekající potvrzení blokuje dokončení kontroly.

1. **Nejdřív ověřit číslo bedny nebo šarže.** Při kopírování zkontrolovat také zdrojový krok a vybrané řádky roštu.
2. **Změny vždy uložit.** Přechod na jinou stránku ani tlačítko Zrušit neukládá rozpracovaný formulář.
3. **Konec zapisovat s datem.** Přesun sám neuzavře předchozí krok.
4. **Rozlišovat evidované údaje.** Stav šarže, stav bedny, uvolnění kontroly a zinkování jsou samostatné. Uložení kontroly samo neoznačí bednu jako Zkontrolováno. Uvolnění Neshoda blokuje K expedici i expedici. Od K expedici jsou kontrola a měření pouze pro čtení; pro opravu vraťte bednu na Zkontrolováno, u expedované nejprve vraťte zakázku z expedice.
5. **Na konci směny zkontrolovat otevřené kroky a čekající kontrolu.** Pro předání uvést číslo šarže, aktuální pracoviště a nedokončenou operaci.

## Když se práce zastaví

| Situace | První krok |
| --- | --- |
| Bedna nejde vložit do šarže | Ověřit výrobní stav a pozastavení. Nepřijato, K expedici a Expedováno nejsou pro vložení povolené. |
| Akce chybí nebo není povolená | Ověřit filtr stavu, oprávnění a typ položek šarže. |
| Výsledek kontroly nevyhovuje | Zapsat Neshodu s důvodem a předat k rozhodnutí o dalším postupu. |
| Kontrolu mezitím změnil jiný uživatel | Načíst aktuální údaje, zkontrolovat je a teprve potom znovu uložit úpravu. |
| Nakládací pracoviště je obsazené | Pokračovat v jeho otevřené šarži nebo doplnit konec skutečně dokončeného nakládání. |

## Kde pokračovat

Uživatelé administrace najdou dole v její nabídce blok **Návody a dokumentace**.
Každý návod se otevře v nové záložce přímo v aplikaci. Pro delší texty použijte
**Obsah návodu** nebo odkazy na související návody; odkaz **Zpět na seznam návodů**
vás vrátí na tento blok v administraci. Návody vyžadují aktivní účet s příznakem
staff, bez dalších oprávnění k agendám.

- Nakládání: **Přehled nakládání** — `/provozni-prehledy/`.
- Výroba: **Ostatní pracoviště** — `/prehled-pracovist/`; čtečka šarží — `/sarze/skener-ctecka/`.
- Kontrola: **Přehled kontroly** — `/prehled-kontroly/`; **Přehled neshod** — `/prehled-neshod/`.

Návody: [Kamiony](manual_kamion.md) · [Bedny](manual_bedna.md) · [Rychlé založení šarže](manual_rychle_zalozeni_sarze.md) · [Průchod šarže výrobou](manual_pruchod_sarze.md) · [Kontrola beden](manual_kontrola_beden.md) · [Zakázky](manual_zakazka.md)
