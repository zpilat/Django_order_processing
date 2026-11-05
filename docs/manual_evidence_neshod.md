# Uživatelský manuál: Evidence neshod

Evidence neshod uchovává neměnné záznamy při zjištění neshody a doplnění jejích důvodů. Zakládají se automaticky z kontroly beden. Každý snapshot je společný pro všechny aktuální důvody a měření; nevytváří se samostatně pro jednotlivé důvody. Identifikace, důvody a naměřené hodnoty zůstávají zachované i po opravě nebo uvolnění bedny.

## 1. Založení případu

1. Otevřete **Kontrolu bedny**, zadejte měření a výsledky výstupní kontroly.
2. Vyberte **Uvolnění = Neshoda**, alespoň jeden důvod a případný popis do poznámky. Křivost se nastavuje automaticky podle měření a Čistota podle výsledku čistoty; oba důvody jsou zamčené. Při Uložení NOK se zaškrtne a zamkne také Jiné a lze uložit pouze Neshodu. Ostatní důvody lze zadat ručně. U **Jiné** je poznámka povinná.
3. Zvolte **Uložit kontrolu bedny**. První uložení Neshody, přechod z jiného rozhodnutí do Neshody nebo přidání důvodu během Neshody založí nový společný snapshot.

Při doplnění jednoho nebo více důvodů během trvající Neshody vznikne jeden další záznam se všemi právě platnými důvody a všemi aktuálními měřeními. Platí to také pro automatické přidání Čistoty, Křivosti nebo Jiné při Uložení NOK a pro opětovné přidání dříve odebraného důvodu. Datum a autor nového snapshotu odpovídají tomuto uložení; údaje o původní změně uvolnění u kontroly se tím nemění.

Opakované uložení stejných důvodů, samotná změna poznámky či měření nebo pouhé odebrání důvodu nový snapshot nezakládají. Při současném odebrání jednoho a přidání jiného důvodu nový snapshot vznikne. Původní záznamy se nepřepisují; další úpravy zůstávají také v historii kontroly. Po změně rozhodnutí na jiný stav a pozdějším návratu na Neshodu vznikne další záznam téže bedny. Samotné **Uvolněno QS s odchylkou** nový snapshot nezakládá. **Uvolněno** vymaže aktuální důvody u bedny, nikoli původní snapshoty.

Kontrola a případ se ukládají společně. Při chybě ukládání případu se neuloží ani rozhodnutí kontroly. Chybný formulář ani pokus přepsat souběžnou změnu jiného uživatele případ nezaloží.

Při opravě zkontrolované bedny vzniká snapshot až po automatickém nastavení Rovnání a Tryskání, takže zachycuje výsledné stavy téhož uložení. Kontrola, technologické stavy, snapshot a potvrzení měření jsou v jedné transakci; chyba v kterémkoli zápisu vrátí všechny tyto změny. Starší snapshoty se neopravují ani nepřepisují.

Evidence zachycuje nové přechody do Neshody a přidání důvodu během Neshody po nasazení funkce. Starší případy se nedoplňují z historie ani z Google tabulky. Pokud byla bedna v Neshodě již před nasazením, další uložení stejného stavu bez přidaného důvodu snapshot nezaloží.

## 2. Uložené údaje

Případ má vlastní číslo, nezávislé na čísle bedny. Číslování není roční řada a může mít mezery.

Tabulka obsahuje datum a autora zjištění, skupinu dílů, oddělení, zákazníka, zakázku/artikl, označení bedny, rozměr dílu, šarži materiálu, důvody a popis neshody. Automatické záznamy mají skupinu **Vruty** a oddělení **Výstupní kontrola**. Šarže materiálu pochází z pole bedny **Šarže mat. / Charge**; nejde o číslo výrobní šarže pece.

Detail uchovává také:

- tehdejší identifikaci a stav bedny, materiál, zákaznické označení a údaje zakázky;
- rozhodnutí, čistotu, uložení a počty křivých vrutů včetně nul;
- velikost vzorku a povolený počet křivých vrutů zákazníka;
- označení předpisu, požadavky, popisy, rozsah měření a tehdejší meze prohybu;
- všechny tehdy uložené hodnoty všech typů zkoušek, jejich pořadí, autora a datum. Neplatí omezení na 10 hodnot z tisku KKK; zahrnuje se i interní prohyb po koulení.

Texty důvodů a jména se kopírují. Přejmenování zákazníka, uživatele či předpisu nemění původní údaje. Změna nebo smazání aktuálního měření ani přesun bedny do oddělené zakázky při expedici nemění zachycený stav. Odkaz na bednu slouží k navigaci; evidence zobrazuje uložené údaje případu.

Nové případy zachycují meze samostatně pro každou fázi prohybu. Po rovnání se ukládá pouze běžná horní mez, bez QS meze pro odchylku. Dříve uložené snapshoty zachovávají původní údaje a změna pravidla je nepřepisuje.

## 3. Otevření a filtrování

- **Administrace → Kontrola kvality → Evidence neshod**, přímo `/admin/orders/zaznamneshody/`. Nabídka **PŘEHLEDY → Evidence neshod** vede také do adminu.
- Číslo případu či označení bedny v seznamu otevře detail. Ten obsahuje vedle sebe **Identifikaci při zjištění** a **Neshodu a výsledky kontroly**, pod nimi jednotlivé zkoušky s tehdejšími požadavky a hodnotami. Zkoušky s uloženým měřením jsou rozbalené; ostatní lze rozbalit pro zobrazení požadavků. Odkaz **Aktuální kontrola bedny** vede na dnešní údaje, pokud k nim máte oprávnění.

Hledání v seznamu adminu prochází označení bedny, zákazníka, zakázku/artikl, šarži materiálu a popis. Postranní filtry vybírají zákazníka, důvod, skupinu a datum zjištění. Lišta nad seznamem umožňuje výběr roku, měsíce a dne; data se vyhodnocují v místním čase. Záznamy se řadí od nejnovějšího, po 50 na stránku; stránkování zachovává filtry. Samostatné provozní stránky evidence se nepoužívají.

Nadpis každého postranního filtru zobrazuje vybranou hodnotu, například **Důvod neshody: Křivost**; bez výběru uvádí **Vše**. Datum nabízí volby **Dnes**, **Posledních 7 dní**, **Tento měsíc** a **Tento rok**. Výběr období v postranním filtru nahradí předchozí výběr data v horní liště. Zákazníci v nabídce pocházejí z uložených případů evidence.

**Přehled neshod** (`/prehled-neshod/`) nadále obsahuje pouze aktuálně neshodné bedny. **Evidence neshod** zachovává i případy již uvolněných beden.

## 4. Oprávnění a rozsah první verze

Evidence i detail jsou dostupné pouze v administraci. Uživatel potřebuje účet **staff** (`is_staff`) a oprávnění **Může prohlížet Záznam neshody** (`orders.view_zaznamneshody`), případně účet správce. Samotné oprávnění ke kontrole bedny přístup do evidence nezajišťuje. Uživatel s oprávněním pouze k evidenci může číst snapshoty bez přístupu k aktuální kontrole; odkaz na ni vyžaduje navíc `orders.view_bedna` nebo `orders.mark_bedna_zkontrolovano`. Odkaz v nabídce přehledů se zobrazí pouze uživatelům s přístupem do evidence. Kontrola bedny odkazy na jednotlivé snapshoty neobsahuje.

Záznamy se přes aplikaci neupravují ani nemažou. Aktuální kontrola se upravuje stávajícím formulářem podle jeho oprávnění a omezení; při Uvolněno se její důvody vymažou a při dalších rozhodnutích odpovídají aktuálnímu nálezu. Evidence nemění pravidla expedice a nebarví nové sloupce KKK.

Model počítá i se skupinou **Ostatní** a případy bez vazby na bednu. Ruční zadávání železa/ostatních dílů, průběh řešení, opatření, odpovědné osoby, termíny, uzavření a finance se doplní později. Případ zatím nemá samostatný stav řešení či uzavření.

## 5. Nasazení

Před použitím spusťte běžné migrace projektu:

```powershell
.\venv\Scripts\python.exe manage.py migrate
```

Migrace `0244_evidence_neshod` vytváří novou tabulku. Oprávnění k prohlížení vznikne standardně po migracích. Migrace nemění stávající data ani zpětně nenaplňuje evidenci.
