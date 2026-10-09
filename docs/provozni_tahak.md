# Provozní tahák: od příjmu po expedici

Stručný postup pro obsluhu, vhodný k vytištění. Výrobní operace a jejich pořadí se řídí předpisem zakázky. Podrobné zadávání popisují návody uvedené u jednotlivých kroků.

## Běžný pracovní postup

| Krok | Co udělat v aplikaci | Co ověřit před pokračováním |
| --- | --- | --- |
| **1. Příjem** | Založit kamion příjem, zadat nebo importovat zakázky a bedny, potvrdit příjem na sklad. | Správný zákazník, artikl, rozměr a předpis. Mimo stav Nepřijato musí mít bedna kladné netto, táru a množství. |
| **2. Příprava a nakládání** | Podle postupu označit bedny K navezení / Navezeno a zadat pozici. V přehledu nakládání vybrat pracoviště 1–6 a založit šarži nebo pokračovat v otevřené. | Číslo přípravku, operátor, datum a čas začátku. Bedny musí být nepozastavené a v povoleném stavu. |
| **3. Rozložení roštu** | Vybrat či naskenovat bedny, nastavit podíly a uložit patra. Zkontrolovat průvodku, doplnit datum a čas konce nakládání. | Rychlé zadání: patra 1–6, nejvýše 5 položek na patro, každá 5–100 %, součet nejvýše 100 %. Uložením beden do Nakládání přejdou na Ve zpracování. |
| **4. Průchod výrobou** | V detailu šarže uzavřít dokončený krok a použít Přesunout do dalšího kroku. Vybrat cílové pracoviště, zadat začátek a operátora, ověřit kopírované položky. | Nový krok odpovídá skutečnému průchodu. Každý dokončený krok má datum i čas konce; při práci přes půlnoc správný den. |
| **5. Kontrola** | Po dokončení příslušného zpracování označit bedny jako Zakaleno. Otevřít kontrolu, uložit měření, výstupní kontrolu a rozhodnutí o uvolnění. Poté samostatně potvrdit Zkontrolováno a stav rovnání/tryskání. | Správné číslo bedny, požadavky a výsledky. Při Neshodě vybrat důvod, u Jiné doplnit poznámku. |
| **6. Dokončení beden** | Dokončit požadované rovnání, tryskání či zinkování a zapsat skutečné stavy. Připravené bedny označit K expedici. | Pro K expedici musí být tryskání Čistá/Otryskaná, rovnání Rovná/Vyrovnaná a zinkování Nezinkovat/Uvolněno. Ověřit také výsledky kontroly. |
| **7. Expedice** | Vybrat připravené bedny nebo zakázky, provést expedici do kamionu výdej a vytisknout potřebné doklady. | Správný zákazník, výběr a kamion. Po částečné expedici ověřit zbývající bedny a případnou novou zakázku. |

## Pět pravidel při každé směně

1. **Nejdřív ověřit číslo bedny nebo šarže.** Při kopírování zkontrolovat také zdrojový krok a vybrané řádky roštu.
2. **Změny vždy uložit.** Přechod na jinou stránku ani tlačítko Zrušit neukládá rozpracovaný formulář.
3. **Konec zapisovat s datem.** Přesun sám neuzavře předchozí krok.
4. **Rozlišovat evidované údaje.** Stav šarže, stav bedny, uvolnění kontroly a zinkování jsou samostatné. Uložení kontroly samo neoznačí bednu jako Zkontrolováno.
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

- Nakládání: **Přehled nakládání** — `/provozni-prehledy/`.
- Výroba: **Ostatní pracoviště** — `/prehled-pracovist/`; čtečka šarží — `/sarze/skener-ctecka/`.
- Kontrola: **Přehled kontroly** — `/prehled-kontroly/`; **Přehled neshod** — `/prehled-neshod/`.

Návody: [Kamiony](manual_kamion.md) · [Bedny](manual_bedna.md) · [Rychlé založení šarže](manual_rychle_zalozeni_sarze.md) · [Průchod šarže výrobou](manual_pruchod_sarze.md) · [Kontrola beden](manual_kontrola_beden.md) · [Zakázky](manual_zakazka.md)
