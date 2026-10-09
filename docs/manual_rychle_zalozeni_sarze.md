# Uživatelský manuál: Rychlé založení šarže s bednami

Postup slouží k nakládání existujících beden do šarže na pracovištích 1–6. Vytvoří šarži, první krok Nakládání a rozložení beden do pater roštu. Nové bedny se evidují v zakázkách; zde vybíráte bedny, které už v aplikaci existují.

## 1. Otevření správného pracoviště

1. Přihlaste se a otevřete provozní přehled nakládání (`/provozni-prehledy/`) nebo provozní rozcestník.
2. Vyberte konkrétní pracoviště 1–6. Stejný vstup lze otevřít kódem pracoviště: `/sarze/rychle-zalozeni/pracoviste/1/` (číslo nahraďte požadovaným pracovištěm).
3. Pokud na pracovišti existuje otevřený krok Nakládání, otevře se přehled této šarže a můžete pokračovat v zadávání.
4. Jinak se zobrazí formulář pro založení šarže.

Rychlé založení musí začínat přes konkrétní pracoviště. Na jednom čísle pracoviště může být jen jeden otevřený krok Nakládání; před založením další šarže dokončete předchozí nakládání.

## 2. Založení šarže a prvního kroku

| Pole | Pravidlo |
| --- | --- |
| Číslo přípravku | Povinné celé číslo od 0. |
| Číslo pracoviště | Doplněné podle vstupu, rozsah 1–6; při založení se nemění. |
| Popouštění, poznámka šarže | Volitelné provozní údaje. |
| Datum začátku a začátek | Povinné; předvyplní se aktuální datum a čas. |
| Operátor | Povinný; předvyplní se jméno nebo přihlašovací jméno. |
| Poznámka kroku nakládání | Volitelná. |

Klikněte na **Uložit a pokračovat**. Šarže se uloží ve stavu **Naložená**, vznikne první krok na pracovišti typu Nakládání a otevře se zadání 1. patra. Konec kroku se při založení nezadává.

Uložení hlavičky je samostatný krok. Pozdější zrušení zadávání patra již uloženou šarži nesmaže.

## 3. Zadání beden do patra

1. Vyberte bednu v řádku nebo použijte **Sken**.
2. Ve skenovacím okně použijte kameru, čtečku nebo ruční zadání čísla bedny, URL či kódu a potvrďte **Přidat**.
3. Zkontrolujte bednu a její podíl v části **Rozložení položek v roštu**. Pro každou položku nastavte procenta.
4. Přidejte další řádky podle skutečného rozložení. **Zopakovat první bednu** vloží stejnou bednu do prvního volného řádku; hodí se, když její obsah zabírá více částí roštu.
5. Nepotřebný řádek odeberte tlačítkem **×**.
6. Uložte patro jedním z tlačítek uvedených níže.

Pravidla rychlého zadávání:

- Patra mají čísla 1–6; jedno patro obsahuje nejvýše 5 položek.
- Zadejte alespoň jednu bednu. Každá položka má podíl 5–100 %; součet v patře nesmí překročit 100 %.
- Stejná bedna může být v patře opakovaně nebo ve více patrech; jde o rozdělení obsahu jedné bedny.
- Vybírat lze nepozastavené bedny ve stavech Přijato, K navezení, Navezeno, Ve zpracování, Zakaleno nebo Zkontrolováno.
- Nepřijaté bedny, bedny K expedici a expedované bedny nejsou v nabídce.
- Položky mimo databázi zadávejte přes [deník](manual_denik_pece.md); rychlé zadávání pracuje s bednami z databáze.

Kamera potřebuje povolený přístup v prohlížeči. Když skenování nefunguje, použijte ruční zadání nebo výběr ze seznamu.

## 4. Uložení a pokračování

| Tlačítko | Výsledek |
| --- | --- |
| Uložit a do přehledu šarže | Uloží celé zadávané patro a otevře přehled. |
| Uložit a zadat další patro | Uloží patro a přejde na další. Po 6. patře pokračujte do přehledu. |
| Zrušit | Vrátí se do přehledu bez uložení aktuálních změn patra. |

Při uložení se bedny zařazené do kroku Nakládání přepnou na **Ve zpracování** a jejich skladová pozice se vymaže. Úprava patra nahrazuje jeho uložené rozložení odeslaným formulářem. Před uložením zkontrolujte všechny řádky patra.

## 5. Přehled, opravy a tisk

V přehledu vidíte přípravek, pracoviště, operátora, začátek a rozložení uložených pater.

- **Upravit patro** otevře uložené patro pro změnu beden a rozdělení roštu.
- **Přidat další patro** otevře další patro; nejvyšší povolené číslo je 6.
- **Upravit šarži** umožní opravit hlavičku a první krok nakládání.
- **Náhled tisku** otevře průvodku v nové kartě. Je dostupný po uložení alespoň jedné bedny. Tiskněte před uzavřením nakládání.
- **Smazat patro** je dostupné s příslušným oprávněním a pouze pro poslední uložené patro. Odebrání řádku nebo smazání patra samo nevrací výrobní stav bedny zpět.

## 6. Dokončení nakládání

1. Ověřte uložené bedny a patra, případně vytiskněte průvodku.
2. Klikněte na **Doplnit konec kroku**.
3. Zkontrolujte **Datum konce** a **Konec** a uložte změny.
4. Na pracovišti lze poté založit další šarži. V dalším zpracování pokračujte podle [Průchodu šarže výrobou](manual_pruchod_sarze.md); podrobnou evidenci položek popisuje [manuál deníku](manual_denik_pece.md).

Datum a čas konce se vyplňují společně. Konec nesmí být před začátkem; při práci přes půlnoc zadejte správné datum konce. Konec lze uložit až po přidání alespoň jedné bedny. Uzavřený krok už není dostupný pro zadávání pater a tisk přes tento rychlý přehled.

## 7. Oprávnění a běžné problémy

| Operace | Oprávnění v aplikaci `orders` |
| --- | --- |
| Založení | `add_sarze`, `add_sarzekrok`, `add_sarzekrokbedna` |
| Přehled pracoviště, šarže a tisk | `view_sarzekrok`, `view_sarzekrokbedna` |
| Zadání a úprava patra | `add_sarzekrokbedna`, `change_sarzekrokbedna` |
| Úprava hlavičky a doplnění konce | `change_sarze`, `change_sarzekrok` |
| Smazání posledního patra | Navíc `delete_sarzekrokbedna_patro` |

- **Pracoviště Nakládání nebylo nalezeno jednoznačně:** správce musí opravit číselník pracovišť.
- **Pro pracoviště už existuje otevřený krok:** pokračujte v jeho přehledu nebo doplňte konec původního nakládání.
- **Bedna není v nabídce / kód nelze přidat:** ověřte číslo, výrobní stav a pozastavení bedny.
- **Nastavte rozdělení roštu / součet přesahuje 100 %:** zkontrolujte procenta všech aktivních řádků.
- **Krok pro dané pracoviště není otevřený:** vraťte se do provozního přehledu; původní nakládání už mohlo být uzavřeno.

## 8. Související dokumentace a kód

[Bedny](manual_bedna.md) · [Deník a kroky šarže](manual_denik_pece.md) · [Kontrola beden](manual_kontrola_beden.md) · [README](../README.md)

[Provozní tahák](provozni_tahak.md) · [Průchod šarže výrobou](manual_pruchod_sarze.md)

Implementace: `orders/views.py` (`rychle_zalozeni_sarze_*`), `orders/forms.py` (`RychleZalozeniSarzeForm`, `SarzeKrokPatroPolozkaForm`, `BaseSarzeKrokPatroFormSet`), `orders/models.py` (`SarzeKrokBedna.save()`) a šablony `orders/templates/orders/rychle_zalozeni_sarze*.html`.
