# Provozní tahák: od příjmu po expedici

Stručný postup pro obsluhu, vhodný k vytištění. Výrobní operace a jejich pořadí se řídí předpisem zakázky. Podrobné zadávání popisují návody uvedené u jednotlivých kroků.

## Běžný pracovní postup

| Krok | Co udělat v aplikaci | Co ověřit před pokračováním |
| --- | --- | --- |
| **1. Příjem** | Založit kamion příjem, zadat nebo importovat zakázky a bedny, potvrdit příjem na sklad. | Správný zákazník, artikl, rozměr a předpis. Mimo stav Nepřijato musí mít bedna kladné netto, táru a množství. |
| **2. Příprava a nakládání** | Podle postupu označit bedny K navezení / Navezeno a zadat pozici. V přehledu nakládání vybrat pracoviště 1–6 a založit šarži nebo pokračovat v otevřené. | Číslo přípravku, operátor, datum a čas začátku. Bedny musí být nepozastavené a v povoleném stavu. |
| **3. Rozložení roštu** | Vybrat či naskenovat bedny, nastavit podíly a uložit patra. Zkontrolovat průvodku, doplnit datum a čas konce nakládání. | Rychlé zadání: patra 1–6, nejvýše 5 položek na patro, každá 5–100 %, součet nejvýše 100 %. Uložením beden do Nakládání přejdou na Ve zpracování. |
| **4. Průchod výrobou** | V detailu šarže uzavřít dokončený krok a použít Přesunout do dalšího kroku. Vybrat cílové pracoviště, zadat začátek a operátora, ověřit kopírované položky. Po dokončení příslušného zpracování označit bedny jako Zakaleno. | Nový krok odpovídá skutečnému průchodu. Každý dokončený krok má datum i čas konce; při práci přes půlnoc správný den. |
| **5. Kontrola** | Otevřít kontrolu, uložit měření, výstupní kontrolu a rozhodnutí o uvolnění. Poté použít Dokončit kontrolu bedny a ověřit vypočtené rovnání/tryskání. | Správné číslo bedny, požadavky a výsledky. Křivost a Čistota se nastavují automaticky; Čistota NOK i Uložení NOK dovolují pouze Neshodu. Uložení NOK vynutí Jiné s poznámkou. Při Neshodě nebo Uvolněno QS musí být důvod, u Jiné poznámka. Uvolněno důvody vymaže a zamkne. Před označením Zkontrolováno musí být uložená Čistota a Uložení (OK/NOK), rozhodnutí o Uvolnění a při důvodu Křivost oba počty křivých (nula platí jako vyplněná). Je-li položka Prohyb po TZ oranžová, oba počty ani rovnání se pro označení Zkontrolováno nevyžadují; platí i při Neshodě z dalších důvodů. |
| **6. Dokončení beden** | Dokončit požadované rovnání, tryskání či zinkování a zapsat skutečné stavy. Připravené bedny označit K expedici. | Pro K expedici musí být tryskání Čistá/Otryskaná, rovnání Rovná/Vyrovnaná a zinkování Nezinkovat/Uvolněno. Uvolnění nesmí být Neshoda; od K expedici jsou kontrola a měření pouze pro čtení. |
| **7. Expedice** | Vybrat připravené bedny nebo zakázky, provést expedici do kamionu výdej a vytisknout potřebné doklady. | Správný zákazník, výběr a kamion. Po částečné expedici ověřit zbývající bedny a případnou novou zakázku. |

Při potvrzení **Zakaleno přes sken** se Tryskání nastaví na **Otryskaná**, pokud všechny šarže bedny zahájily krok Tryskače s touto bednou; konec kroku není podmínkou. Při částečném otryskání zůstane stav zachovaný; u stavu Špinavá se již před uložením nad tlačítkem zobrazí varování s neotryskanými šaržemi. Přesun lze potvrdit, po uložení se varování neopakuje. Žádná otryskaná šarže nebo žádné šarže znamenají ponechání stavu bez varování.

Tlačítko **Dokončit kontrolu bedny** použijte ve stavu **Zakaleno**. Při potvrzení se automaticky uloží Tryskání podle Čistoty a Rovnání podle prohybu po rovnání, jinak po TZ. Oranžový prohyb po TZ znamená Rovná. Na potvrzovací stránce ověřte vypočtené stavy. Bez uloženého prohybu po TZ, standardního maxima nebo povoleného počtu křivých u zákazníka je potvrzení zablokované; QS maximum zůstává volitelné. U již zkontrolované bedny se rovnání a tryskání přepočítají při **uložení výstupní kontroly**, i bez změny uvolnění. Pokud oprava měření změní vyhodnocení nebo technologické stavy, potvrďte změnu uložením výstupní kontroly; samostatné tlačítko pro úpravu stavů již není. Podrobnosti a tabulky stavů jsou v [manuálu kontroly](manual_kontrola_beden.md#5-potvrzení-výrobního-stavu).

## Pět pravidel při každé směně

**Koulení a rovnání se nabídnou při červeném prohybu po TZ.** Prázdné navazující zkoušky se předtím nezobrazují; uložené výsledky zůstávají viditelné. Po zadání prohybu po rovnání se původní prohyb po TZ zamkne. Oprava původního měření vyžaduje nejprve odstranění všech aktuálních hodnot po rovnání.

**Ohyb i Krut jsou povinné u každé bedny.** Před dokončením kontroly uložte alespoň jednu hodnotu každé z obou zkoušek. Bez některé z nich nelze kontrolu dokončit ani přes admin; chybějící měření uvede panel místo tlačítka. Podmínka platí také pro opravu již zkontrolované bedny.

**Změněné vyhodnocení kontroly je nutné potvrdit.** Pokud měření změní automatické důvody, přípustné uvolnění nebo technologické stavy, uložte výstupní kontrolu. Čekající potvrzení blokuje přípravu k expedici i expedici na serveru. Starší bedny s papírovou kontrolou se neblokují jen kvůli chybějící kontrole v programu. Hromadná akce Zkontrolováno je odstraněná; nové dokončení kontroly v adminu vyžaduje úplné podklady.

**Kontrolu znovu ukládejte, pokud se změní její vyhodnocení nebo technologické stavy.** Samotný zápis vrstvy, Ohybu, Krutu či tvrdosti další potvrzení nevyžaduje. Červené hodnoty se liší od databáze. U Zkontrolováno běžný odchod blokují neuložené změny nebo čekající potvrzení; při přechodu na měření stejné bedny se rozepsané údaje zachovají. Příznak čekajícího potvrzení přetrvá do úspěšného uložení kontroly, i když následně upravíte jinou zkoušku.

1. **Nejdřív ověřit číslo bedny nebo šarže.** Při kopírování zkontrolovat také zdrojový krok a vybrané řádky roštu.
2. **Změny vždy uložit.** Přechod na jinou stránku ani tlačítko Zrušit neukládá rozpracovaný formulář.
3. **Konec zapisovat s datem.** Přesun sám neuzavře předchozí krok.
4. **Rozlišovat evidované údaje.** Stav šarže, stav bedny, uvolnění kontroly a zinkování jsou samostatné. Uložení kontroly samo neoznačí bednu jako Zkontrolováno. Uvolnění Neshoda blokuje K expedici i expedici. Od K expedici jsou kontrola a měření pouze pro čtení; pro opravu vraťte bednu na Zkontrolováno, u expedované nejprve vraťte zakázku z expedice.
5. **Na konci směny zkontrolovat otevřené kroky a čekající kontrolu.** Pro předání uvést číslo šarže, aktuální pracoviště a nedokončenou operaci.

## Když se práce zastaví

Opravy chybného příjmu, zařazení do šarže, měření nebo již provedené expedice popisují [Mimořádné situace a opravy](manual_mimoradne_situace.md). Chybějící zákaznické požadavky, předpisy a ceny řeší [Číselníky a nastavení zákazníka](manual_ciselniky.md).

Vztahy výrobních a technologických stavů vysvětlují [Stavy a automatická pravidla](manual_stavy_a_pravidla.md). Potřebná oprávnění a přidělování přístupu shrnují [Role a oprávnění](manual_role_a_opravneni.md).

Význam souhrnů skladu, kompletnosti zakázek, výkonů výroby, rovnání a uložené rozpracovanosti vysvětlují [Přehledy a význam ukazatelů](manual_prehledy_a_ukazatele.md), včetně rozdílů mezi jednotlivými obrazovkami.

| Situace | První krok |
| --- | --- |
| Bedna nejde vložit do šarže | Ověřit výrobní stav a pozastavení. Nepřijato, K expedici a Expedováno nejsou pro vložení povolené. |
| Akce chybí nebo není povolená | Ověřit filtr stavu, oprávnění a typ položek šarže. |
| Výsledek kontroly nevyhovuje | Zapsat Neshodu s důvodem a předat k rozhodnutí o dalším postupu. |
| Kontrolu mezitím změnil jiný uživatel | Načíst aktuální údaje, zkontrolovat je a teprve potom znovu uložit úpravu. |
| Nakládací pracoviště je obsazené | Pokračovat v jeho otevřené šarži nebo doplnit konec skutečně dokončeného nakládání. |

## Kde pokračovat

Uživatelé administrace najdou dole v její nabídce blok **Návody a dokumentace**.
První návod z administrace se otevře v nové záložce přímo v aplikaci. Při čtení dokumentace další návody z nabídky i odkazů změní obsah ve stejné záložce. Pro delší texty použijte
**Obsah návodu** nebo odkazy na související návody; odkaz **Zpět na seznam návodů**
vás vrátí na tento blok v administraci. Návody vyžadují aktivní účet s příznakem
staff, bez dalších oprávnění k agendám.

- Nakládání: **Přehled nakládání** — `/provozni-prehledy/`.
- Výroba: **Ostatní pracoviště** — `/prehled-pracovist/`; čtečka šarží — `/sarze/skener-ctecka/`.
- Kontrola: **Přehled kontroly** — `/prehled-kontroly/`; **Přehled neshod** — `/prehled-neshod/`.

Návody: [Kamiony](manual_kamion.md) · [Bedny](manual_bedna.md) · [Rychlé založení šarže](manual_rychle_zalozeni_sarze.md) · [Průchod šarže výrobou](manual_pruchod_sarze.md) · [Kontrola beden](manual_kontrola_beden.md) · [Zakázky](manual_zakazka.md)
