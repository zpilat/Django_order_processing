# Uživatelský návod: Deník beden v krocích šarže

Tento návod je určen pro běžnou obsluhu v administraci. Popisuje praktický postup práce se šarží, krokem šarže a deníkem pece.

## 1. Co je co

1. Šarže: výrobní celek, který má své číslo a datum.
2. Krok šarže: konkrétní průchod šarže přes pracoviště.
3. Deník beden v krocích šarže: jednotlivé řádky v kroku šarže (bedny nebo položky mimo DB) s patrem a procentem využití.

## 2. Běžný pracovní postup

1. Otevřete Deník beden v krocích šarže.
2. Klikněte na rychlý odkaz Šarže: Přidat.
3. Uložte šarži tlačítkem Uložit a přidat bedny do kroku šarže.
4. Otevře se detail prvního kroku šarže.
5. Doplňte údaje kroku (zejména pracoviště, začátek, operátor).
6. Přidejte řádky deníku beden v krocích šarže.
7. Pokud potřebujete navazující krok, použijte jednu z akcí Přesunout šarži do dalšího kroku.
8. Na novém kroku doplňte pracoviště, začátek, operátora a uložte.

## 3. Vyplnění šarže

1. Při vytvoření šarže se datum založení doplní automaticky.
2. Filtr v seznamu šarží je zaměřený na aktivní šarže.
3. Po uložení šarže můžete pokračovat rovnou do kroku šarže.

## 4. Vyplnění kroku šarže

1. Pole pracoviště, operátor a začátek:
	- při založení kroku mohou být prázdná,
	- při editaci existujícího kroku jsou povinná.
2. Pole konec doporučujeme vyplnit hned po dokončení kroku.
3. Pokud konec není vyplněn a provedete přesun do dalšího kroku, systém zobrazí varování.

## 5. Vyplnění řádku deníku beden v krocích šarže

Pro každý řádek platí:

1. Vyplňte buď bednu z databáze, nebo popis mimo DB.
2. Není možné vyplnit bednu i data mimo DB současně.
3. Pokud vyplníte popis mimo DB, vyplňte i zákazníka mimo DB a zakázku mimo DB.
4. U bedny z databáze musí být bedna ve stavu skladem.
5. Kombinace krok + bedna + patro musí být unikátní.
6. V rámci jednoho kroku a jednoho patra nesmí součet procent přesáhnout 100 %.

## 6. Akce pro navazující krok

### 6.1 Přesunout šarži do dalšího kroku z vybraných beden

Použití:

1. Označte vybrané řádky v deníku beden v krocích šarže.
2. Spusťte akci Přesunout šarži do dalšího kroku z vybraných beden.

Co se stane:

1. Všechny vybrané řádky musí patřit do jednoho zdrojového kroku.
2. Vytvoří se nový krok stejné šarže.
3. Do nového kroku se přenese jen vazba na šarži, ostatní údaje kroku se nekopírují.
4. Zkopírují se vybrané řádky deníku.
5. Systém vás přesměruje na detail nového kroku.

### 6.2 Přesunout šarži do dalšího kroku

Použití:

1. V přehledu kroků šarže označte právě jeden krok.
2. Spusťte akci Přesunout šarži do dalšího kroku.

Co se stane:

1. Vytvoří se nový krok stejné šarže.
2. Do nového kroku se přenese jen vazba na šarži.
3. Zkopírují se všechny řádky deníku ze zdrojového kroku.
4. Systém vás přesměruje na detail nového kroku.

## 7. Filtry, které se hodí v praxi

1. Přehled Krok šarže:
	- Pracoviště
	- Typ pracoviště
	- Konec: Ano/Ne
2. Přehled Deník beden v krocích šarže:
	- Pracoviště
	- Typ pracoviště
	- Konec: Ano/Ne

Tip: Filtr Konec: Ne pomáhá najít nedokončené kroky.

## 8. Nejčastější hlášky a co s nimi

1. Vyberte záznamy pouze z jednoho kroku šarže.
	- Označili jste řádky z více kroků. Vyberte jen jeden krok.
2. Vyberte právě jeden krok šarže.
	- Pro akci z přehledu kroků musí být označený přesně jeden krok.
3. Musí být vyplněna buď bedna, nebo popis mimo DB.
	- Vyplňte jen jednu větev zadání.
4. Nelze vyplnit současně bednu i pole mimo DB.
	- Pokud je vybraná bedna, smažte mimo-DB pole.
5. Původní krok šarže nemá vyplněný konec, nezapomeňte jej vyplnit.
	- Doplňte konec na zdrojovém kroku, aby evidence byla kompletní.
6. Součet procent v rámci jednoho patra nesmí překročit 100 %.
	- Upravte procenta řádků ve stejném patře.

## 9. Doporučení pro čistá data

1. Po dokončení každého kroku doplňte pole konec.
2. Používejte poznámku jen pro opravdu důležité provozní informace.
3. Průběžně kontrolujte krokové přehledy filtrem Konec: Ne.
4. Před přesunem do dalšího kroku zkontrolujte, že řádky patří do správného zdrojového kroku.
