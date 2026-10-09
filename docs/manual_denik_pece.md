# Uživatelský manuál: Deník beden v krocích šarže

Deník sleduje, co se zpracovávalo v jednotlivých krocích šarže, na jakém pracovišti a s jakým rozložením pater. Pro běžné nakládání beden je připravený [samostatný návod rychlého založení šarže](manual_rychle_zalozeni_sarze.md).

Celý pracovní postup popisuje [Průchod šarže výrobou](manual_pruchod_sarze.md); stručný přehled pro směnu je v [provozním taháku](provozni_tahak.md).

## 1. Co je co

- **Šarže**: výrobní celek s číslem, datem založení, přípravkem, číslem pracoviště a stavem.
- **Krok šarže**: průchod přes konkrétní pracoviště, s pořadím, operátorem a začátkem i koncem.
- **Deník / Bedna v kroku šarže**: položka roštu s bednou nebo údaji mimo databázi, patrem a podílem využití.

Číslo pracoviště šarže pro nakládání (1–6) a pracoviště konkrétního kroku jsou dva související údaje. Při přesunu na další pracoviště zůstává zachovaná šarže a vzniká nový krok.

## 2. Běžný postup v administraci

1. Otevřete Deník a použijte rychlý odkaz **Šarže: Přidat**.
2. Vyplňte šarži a v inline prvního kroku datum začátku, pracoviště, čas začátku a operátora.
3. Uložte tlačítkem **Uložit a přidat bedny do kroku šarže**; otevře se detail prvního kroku.
4. Přidejte řádky deníku s patry a procenty.
5. Po dokončení kroku doplňte datum a čas konce.
6. Pro pokračování použijte přesun z vybraných řádků deníku nebo přesun celého kroku.
7. Na novém kroku zadejte pracoviště, datum, začátek a operátora.

Pro nakládání existujících beden na pracovištích 1–6 lze místo ručního zadávání použít [rychlé založení](manual_rychle_zalozeni_sarze.md). Položky mimo databázi zadávejte v administraci.

## 3. Šarže a krok

Datum založení šarže se při vytvoření doplní automaticky. Seznam šarží umožňuje filtrovat aktivní šarže.

Při založení šarže v administraci vyplňte povinné údaje prvního kroku. Při vytváření dalšího kroku přes přesun se datum začátku, pracoviště, začátek a operátor zadávají v navazujícím formuláři před uložením.

**Datum konce** a **Konec** vyplňujte společně. Konec nesmí předcházet datu a času začátku. U práce přes půlnoc zadejte datum následujícího dne. Přesun z kroku bez konce zobrazí varování; konec doplňte na původním kroku.

## 4. Řádky deníku a rozložení patra

Každý řádek představuje buď bednu z databáze, nebo položku mimo databázi:

| Větev zadání | Povinné údaje |
| --- | --- |
| Bedna z databáze | Vybraná bedna a patro. |
| Položka mimo databázi | Popis mimo DB, zákazník mimo DB, zakázka mimo DB a patro; číslo bedny mimo DB je volitelné. |

Bednu a údaje mimo databázi nelze kombinovat v jednom řádku. Samotný zákazník, zakázka nebo číslo bedny mimo DB bez popisu nestačí.

Bedna z databáze musí být nepozastavená a ve stavu Přijato, K navezení, Navezeno, Ve zpracování, Zakaleno nebo Zkontrolováno. Bedny Nepřijato, K expedici a Expedováno nejsou pro tento postup povolené.

Procenta v deníku mohou být nevyplněná; vyplněný podíl má rozsah 0–100 %. Součet v jednom kroku a patře nesmí přesáhnout 100 %. Rychlé zadávání pater má přísnější pravidla: podíl 5–100 %, nejvýše 5 položek a patra 1–6.

Stejná bedna se smí v jednom patře i ve více patrech opakovat, pokud je její obsah rozdělený do více částí roštu. Kombinace krok + bedna + patro proto nemusí být jedinečná.

Při přidání bedny do kroku typu Nakládání se její výrobní stav automaticky nastaví na **Ve zpracování** a vymaže se skladová pozice. Odebrání položky z deníku samo výrobní stav bedny zpět nevrací.

## 5. Přesun do dalšího kroku

### Z vybraných řádků deníku

1. Označte řádky z jednoho zdrojového kroku.
2. Spusťte **Přesunout šarži do dalšího kroku z vybraných beden**.
3. Ve formuláři cílového kroku vyplňte pracoviště, datum začátku, čas a operátora a potvrďte vytvoření.

Vznikne nový krok stejné šarže, do kterého se zkopírují pouze vybrané řádky. Údaje pracoviště a obsluhy zdrojového kroku se nepřenášejí.

### Z přehledu kroků

1. Označte právě jeden krok.
2. Spusťte **Přesunout šarži do dalšího kroku**.
3. Ve formuláři vyplňte údaje cílového kroku a potvrďte vytvoření.

Do nového kroku stejné šarže se zkopírují všechny řádky zdrojového kroku. Původní krok a jeho deník zůstávají zachované jako evidence předchozího průchodu.

## 6. Provozní přehledy a skenování

- **Přehled nakládání** (`/provozni-prehledy/`) ukazuje otevřené nakládání na číslech pracovišť 1–6.
- **Ostatní pracoviště** (`/prehled-pracovist/`) ukazují otevřené šarže mimo Nakládání.
- Čtečka šarží (`/sarze/skener-ctecka/`) otevře provozní detail šarže. Nabízené stavové operace, přesun a úprava kroku závisejí na stavu a oprávněních.
- **Přehled kontroly** (`/prehled-kontroly/`) obsahuje také šarže s položkami mimo databázi čekající na kontrolu; jejich řízení vyžaduje oprávnění `orders.change_stav_sarze_kontrolor`.

Skenování ani přesun nenahrazují vyplnění skutečného začátku a konce kroku. Výrobní stav šarže a výrobní stav jednotlivé bedny jsou samostatné údaje.

## 7. Filtry a běžné chyby

V přehledu kroků i deníku použijte filtry **Pracoviště**, **Typ pracoviště** a **Konec: Ano/Ne**. Hodnota Konec: Ne pomáhá dohledat neuzavřené kroky.

| Hlášení nebo problém | Řešení |
| --- | --- |
| Vyberte záznamy pouze z jednoho kroku šarže | Zúžte výběr deníku na jeden zdrojový krok. |
| Vyberte právě jeden krok šarže | Pro přesun celého kroku označte jen jeden záznam. |
| Musí být vyplněna buď bedna, nebo popis mimo DB | Vyplňte jednu větev zadání. |
| Nelze vyplnit současně bednu i pole mimo DB | Odstraňte údaje druhé větve. |
| Součet procent v patře překračuje 100 % | Opravte všechny podíly v příslušném kroku a patře. |
| Původní krok nemá vyplněný konec | Na původním kroku doplňte datum a čas konce. |
| Bednu nelze zařadit | Ověřte její výrobní stav a pozastavení. |

## 8. Související dokumentace a kód

[Bedny](manual_bedna.md) · [Rychlé založení šarže](manual_rychle_zalozeni_sarze.md) · [Kontrola beden](manual_kontrola_beden.md) · [README](../README.md)

Implementace: `orders/models.py` (`Sarze`, `SarzeKrok`, `SarzeKrokBedna`), `orders/admin.py` (`SarzeAdmin`, `SarzeKrokAdmin`, `SarzeKrokBednaAdmin`), `orders/actions.py`, `orders/forms.py` a `orders/views.py`.
