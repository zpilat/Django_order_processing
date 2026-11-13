# Uživatelský manuál: Přehledy a význam ukazatelů

Návod vysvětluje, co jednotlivé přehledy počítají, ke kterému okamžiku údaje patří a proč se jejich výsledky mohou lišit. Hodí se pro předání směny, plánování práce i porovnávání skladu, výroby a expedice. Pravidla samotných stavů popisují [Stavy a automatická pravidla](manual_stavy_a_pravidla.md).

## 1. Nejdřív rozlište stav, událost a uložený snímek

| Přehled | Z čeho vychází | Co z výsledku číst |
| --- | --- | --- |
| Přehled beden | Současné výrobní a technologické stavy beden | Co je právě ve skladu a co potřebuje dokončit. |
| Seznam beden | Současné bedny odpovídající filtrům | Které konkrétní bedny tvoří vybranou část skladu. |
| Komplet v Zakázkách | Současné výrobní stavy beden dané zakázky | Zda jsou její bedny K expedici nebo už Expedováno. |
| Přehled kamionů – příjem a výdej | Datum kamionu, současné přiřazení zakázek a fakturovatelné bedny | Hmotnost příjmů a výdejů za měsíc a rok. |
| Přehled kamionů – Zpracováno | Historie vstupů bedny do skupiny Zkontrolováno / K expedici | Hmotnost při zaznamenaném přechodu a jeho měsíc. |
| Přehled výroby a Historie výroby | Deník kroků na TQF XL1 a TQF XL2 | Evidované vsázky, produkci podle prvního použití bedny na zařízení a vypočtené prostoje. |
| Využití roštů dle zákazníků | Hmotnosti beden a jejich evidované podíly v krocích pecí | Průměr kg na rošt nebo zákaznický podíl roštu. |
| Historie rovnání | Historie změn Rovnání na Vyrovnaná | Počet různých beden, které v období přešly na Vyrovnaná. |
| Rozpracovanosti v administraci | Uložený výběr beden a snímek čtyř stavových polí | Které bedny byly vybrané při pořízení snímku; ostatní údaje nejsou kompletně zmrazené. |

**Současný stav skladu, výkon výroby a výdej za měsíc jsou různé veličiny.** Jedna bedna může být dnes na skladě, mít průchod pecí minulý měsíc a být expedovaná až příští měsíc.

## 2. Přehled beden: souhrny skladu a dokončovací operace

Otevřete **Přehledy zboží → Přehled beden** (`/dashboard/bedny/`). Zobrazuje počty beden a součet jejich **netto hmotnosti v tunách**, po zákaznících i celkem. Nejde o brutto včetně táry ani o počet vrutů v bednách.

| Kategorie | Zahrnuté výrobní stavy nebo podmínky |
| --- | --- |
| Nepřijaté | Nepřijato. Jsou zobrazené samostatně, nevstupují do souhrnu aktuálního skladu. |
| Surové | Přijato, K navezení, Navezeno a Ve zpracování. |
| Zpracované | Zakaleno, Zkontrolováno a K expedici. Tento název neznamená, že mají všechny bedny dokončenou kontrolu. |
| Zakalené ke kontrole | Zakaleno. |
| K tryskání | Tryskání Špinavá a výrobní stav Zakaleno nebo Zkontrolováno. |
| K rovnání | Rovnání Křivá, Koulení nebo Rovná se a výrobní stav Zakaleno nebo Zkontrolováno. Podřádky rozlišují tyto tři stavy. |
| K zinkování | Zinkování Zinkovat, V zinkovně nebo Pozinkováno a výrobní stav Zakaleno nebo Zkontrolováno. Pozinkováno zde znamená ještě k uvolnění. |
| K expedici | Výrobní stav K expedici. |
| K expedici po zakázkách | Bedny K expedici ze zakázek, jejichž **všechny bedny jsou K expedici**. |
| Po exspiraci | Bedny skladem s datem kamionu příjem starším než 28 dní. Rozhoduje datum příjmového kamionu, nikoli poslední změna stavu. |

Souhrn skladu odpovídá **Surové + Zpracované**. Graf jej rozděluje na tři nepřekrývající se části:

```text
Sklad celkem
├─ Surové
├─ Dokončování (Zakaleno a Zkontrolováno)
└─ K expedici
```

**Dokončování = počet Zpracovaných minus počet beden K expedici.** Zpracované už totiž zahrnují i bedny K expedici. Po jejich odečtení zůstávají bedny ve stavech **Zakaleno a Zkontrolováno**. Totéž odečtení platí pro hmotnost. Například 80 Zpracovaných minus 30 K expedici znamená **50 beden v Dokončování**.

Příslušné podíly v grafu se počítají z **počtu beden**, ne z hmotnosti. Těžké a lehké bedny proto mohou mít jiný podíl na počtu a jiný na tunách.

Dokončovací kategorie se překrývají. Stejná bedna může být současně K rovnání, K tryskání a K zinkování; jejich součet není počet různých beden. K expedici je již součástí Zpracovaných a Po exspiraci se překrývá s ostatním skladem.

**Příklad:** Surové 100 beden, Zpracované 80 a K expedici 30 znamená sklad **180 beden**. V grafu bude 100 Surové, 50 Dokončování a 30 K expedici. Přičtením K expedici podruhé by vznikl chybný součet 210.

Přehled nevyřazuje bedny podle příznaků **Pozastaveno** nebo **Fakturovat**. Expedované bedny do skladu nezahrnuje. Zákazník může zůstat v přehledu jen kvůli nepřijatým bednám, i když má aktuální sklad nulový.

## 3. Seznam beden a přehled k navezení

**Seznam beden** (`/bedny/`) je detail aktuálních beden s filtry. Výchozí filtr je **SKLADEM** a **Pozastaveno = Ne**. Pokud jej porovnáváte s Přehledem beden, ověřte i zákazníka, prioritu, skupinu TZ, délku a hledání čísla bedny.

| Filtr v seznamu | Význam |
| --- | --- |
| SKLADEM | Všechny výrobní stavy kromě Nepřijato a Expedováno, dále omezené ostatními filtry. |
| Rozpracováno | Navezeno, Ve zpracování, Zakaleno a Zkontrolováno. Není to stejný výběr jako uložený měsíční snímek rozpracovanosti. |
| Po exspiraci | Neexpedované bedny s datem kamionu příjem starším než 28 dní. Na rozdíl od stejnojmenného souhrnu v Přehledu beden může zahrnout i Nepřijato. |
| Pozastaveno Ano / Ne | Vybere jednu z těchto skupin. Výchozí Ne pozastavené bedny skryje. |

Označení **Po exspiraci** znamená stáří příjmu podle uvedeného pravidla; samo nepotvrzuje technologickou nezpůsobilost výrobku.

**Přehled beden k navezení** (`/bedny/k-navezeni/`) obsahuje pouze bedny K navezení, seskupené podle pozice a zakázky. Zobrazuje také prázdné pozice. Pořadí zakázek a příznak následné práce slouží organizaci navezení; nejsou výrobním stavem ani prioritou zakázky. Při tisku jsou části „nyní“ a následné zakázky oddělené.

## 4. Co přesně znamená Komplet u zakázky

| Indikátor | Význam v administraci Zakázky |
| --- | --- |
| ➖ | Zakázka nemá bedny nebo ještě není uložená. |
| ❌ | Není kompletní a nemá žádnou bednu K expedici. |
| ⏳ | Má alespoň jednu bednu K expedici a část beden ještě není K expedici ani Expedováno. |
| ✔️ | Všechny její bedny jsou K expedici nebo Expedováno. Platí i pro celou již expedovanou zakázku. |

Indikátor hodnotí výrobní stavy, ne samostatně měření, uvolnění, pozastavení či aktuální potvrzení kontroly. Proveditelnost expedice ověřuje až příslušná operace.

**Komplet v Zakázkách a K expedici po zakázkách v Přehledu beden nemají stejnou podmínku.** Například zakázka s jednou bednou K expedici a jednou Expedováno má v adminu ✔️, ale zbývající bedna nevstoupí do souhrnu K expedici po zakázkách, protože tam se požaduje K expedici u všech beden zakázky.

Při částečné expedici může vzniknout oddělená zakázka. Při porovnání ověřte obě části a vazbu na původní zakázku. Podrobnosti jsou v [Zakázkách](manual_zakazka.md).

## 5. Přehled kamionů: příjem, zpracování a výdej

Otevřete **Přehled kamionů** (`/dashboard/kamiony/`) a vyberte rok. Měsíční tabulka uvádí hodnoty v **kg**; horní čtrnáctidenní souhrn používá **tuny**.

| Ukazatel | Zdroj a výpočet |
| --- | --- |
| Příjem | Současná netto hmotnost beden s Fakturovat = Ano u zakázek kamionu příjem. Měsíc určuje **datum kamionu**, nikoli čas importu nebo přepnutí na Přijato. |
| Výdej | Současná netto hmotnost beden s Fakturovat = Ano u zakázek přiřazených ke kamionu výdej. Měsíc určuje **datum výdejového kamionu**. |
| Rozdíl | Příjem − Výdej v daném období. Nejde o aktuální stav celého skladu; chybí počáteční zásoba a liší se také zahrnutí nefakturovaných beden. |
| Zpracováno | Součet historické hmotnosti při skutečném vstupu do skupiny **Zkontrolováno / K expedici**, pokud při přechodu nebyl zapnutý **Atypický průběh**. Období určuje čas zápisu změny do historie. Není zde filtr Fakturovat = Ano. |
| Křivých % ze zpracovaných | Hmotnost při těchto přechodech s Rovnáním Křivá, Koulení, Rovná se nebo Vyrovnaná / celková hmotnost Zpracováno × 100. |
| Křivých % z výdeje | Současná hmotnost fakturovatelných beden výdeje ve stavu **Vyrovnaná** / celková hmotnost výdeje × 100. |

Obě procenta jsou **hmotnostní podíly**, nikoli podíly počtu beden, počty křivých vrutů ve vzorku nebo procenta neshod. Při nulovém jmenovateli se zobrazí pomlčka. Roční procento se počítá z ročních součtů, nikoli jako prostý průměr měsíčních procent.

### Jak se započítává Zpracováno

Přechod Zakaleno → Zkontrolováno se započte. Následný přechod Zkontrolováno → K expedici už ne, protože bedna zůstala uvnitř stejné sledované skupiny. Pouhé uložení jiného pole bez takového vstupu výkon nepřidá. Pokud se bedna vrátí mimo tuto skupinu a později do ní znovu vstoupí, může se započítat další vstup. Není to jedinečný počet beden za celou historii.

Vstupy s příznakem **Atypický průběh** v historickém záznamu se nezapočítávají do Zpracováno ani do hmotnosti křivých ze zpracovaných; výjimka platí pro měsíční i roční součty a odvozená procenta. Posuzuje se příznak při přechodu, nikoli jeho dnešní hodnota. Pozdější přepnutí příznaku tedy nepřepíše dřívější výsledek. Historické případy bez tohoto příznaku se automaticky nepřeznačují. Skladové přehledy, skutečný výkon pecí z deníku a historie provedeného rovnání se touto výjimkou nemění.

Historie počítá změny s existujícím předchozím záznamem; samotné vytvoření bedny rovnou ve sledovaném stavu se jako změna nepočítá. Chybějící historický záznam nelze nahradit jen pohledem na dnešní stav.

Příjem a Výdej se při novém načtení odvozují ze současných vazeb a hmotností. Vrácení expedice, změna data kamionu, příznaku Fakturovat nebo hmotnosti může zpětně změnit dřívější měsíční součet. Naproti tomu hmotnost Zpracováno pochází z příslušného historického záznamu.

### Horní souhrn za posledních 14 dní

Období končí **včera**, zahrnuje 14 kalendářních dní a nezávisí na vybraném roku měsíční tabulky. Průměr / den = součet tun za celé období / 14, včetně víkendů a dní bez příjmu či výdeje.

**Počet kamionů** v tomto souhrnu je přepočet celkové hmotnosti za 14 dní na náklady po **18 tunách**. Není to počet záznamů Kamion ani denní průměr kamionů. Například 36 tun za období znamená 2 přepočtené kamiony bez ohledu na skutečný počet jízd.

## 6. Přehled výroby: vsázky, směny a denní produkce

**Přehled výroby** (`/dashboard/vyroba/`) se standardně vztahuje ke včerejšku. Zahrnuje zařízení s kódy **TQF_XL1 a TQF_XL2**. Nejde o součet všech pracovišť aplikace.

- **Souhrn vsázek** počítá evidované kroky na těchto zařízeních podle data začátku. Konec kroku není podmínkou započtení.
- **Vruty** znamenají kroky obsahující bedny z databáze, **Železo** kroky s položkami mimo DB. Smíšený krok může být v obou kategoriích, takže jejich součet nemusí odpovídat počtu všech vsázek.
- **Výkon vruty** a zákaznický rozpis produkce vycházejí z prvního evidovaného použití bedny na daném zařízení, podle pravidla níže. Hmotnosti položek mimo DB se do tohoto výkonu nepřičítají.
- Počet **šarží v nakládání** ve směnovém přehledu se odvozuje od počtu kroků Nakládání ve směně; počet **pater** je součet různých čísel pater v jednotlivých krocích, nikoli počet řádků deníku.

### Kalendářní den není totéž co dvojice směn

Souhrn a včerejší produkce vrutů pracují s kalendářním datem **00:00–24:00**. Denní směna má začátky kroků **06:00–17:59**, noční **18:00–05:59 následujícího dne**. Zařazení určuje začátek kroku, nikoli celý čas jeho běhu.

Krok začínající dnes ve 02:00 je proto v noční směně včerejška, ale ne ve včerejším kalendářním souhrnu vsázek. Z tohoto důvodu se součet směn může lišit od denního souhrnu.

### První použití bedny na zařízení

Pro výkon se vybírá první evidovaný průchod bedny **na konkrétním zařízení za celou dostupnou evidenci**, nikoli znovu každý den. Opakované řádky stejné bedny v jednom kroku a její pozdější použití na stejném zařízení se z výkonové hmotnosti vyřadí. Rozhodují datum, čas začátku a pořadí kroku; u opakování v témže kroku také patro a řádek.

Používá se celá současná kladná netto hmotnost bedny, bez násobení procenty roštu a bez omezení na Fakturovat = Ano. Pokud stejná bedna projde poprvé XL1 i XL2, může se její hmotnost započítat jednou u každého zařízení. Celkem tedy nemusí být hmotnost jedinečných beden napříč oběma pecemi.

Čtrnáctidenní historie denní produkce končí včera. Týdenní a dvoutýdenní průměry dělí produkci 7 a 14 kalendářními dny včetně nulových dní; nejde o průměr pouze za odpracované směny.

## 7. Historie výroby: průměry, vytížení a prostoje

**Historie výroby** (`/dashboard/vyroba/historie/`) používá stejná zařízení a pravidlo prvního použití bedny jako Přehled výroby. Zvolte rok; přes měsíc otevřete denní detail.

| Ukazatel | Výpočet a výklad |
| --- | --- |
| Průměrný denní výkon [kg/den] | Produkce za období / počet uplynulých **kalendářních dní**. V aktuálním roce se zahrnuje i dnešek; minulý rok se hodnotí celý. |
| Vytížení roštu [kg/rošt] | Produkce / počet různých kroků XL1 a XL2 obsahujících bednu z DB. Jeden krok představuje jeden rošt pro tento výpočet. |
| Cena za rošt | Hmotnost prvních použití × aktuálně nalezená cena kalení za kg, sečteno a děleno počtem uvedených kroků. Nejde o historicky zmrazenou tržbu ani o proforma fakturu včetně příplatků. |
| Prostoj XL1 / XL2 [hod./den] | Součet vypočtených prostojů zařízení / počet dní, ve kterých má zařízení evidovaný krok. Tento jmenovatel se liší od kalendářních dní použitých pro výkon. |
| Prostoj CELKEM [hod./den] | Součet zobrazených denních průměrů XL1 a XL2. Není to jeden společný průměr přes všechny kalendářní dny. |

Týdny běží po blocích pondělí–neděle, na okrajích jsou oříznuté hranicí zvoleného roku. Pro porovnání používejte zobrazený rozsah dat, ne pouze číslo týdne. Budoucí část aktuálního roku se do uplynulých dní nepočítá. Zobrazené průměry a celá kg mohou být zaokrouhlené; nesčítejte měsíční nebo týdenní průměry jako roční výkon.

Hmotnost a cena se pro výrobní historii znovu načítají z dnešní bedny a ceníku. Oprava hmotnosti, cen, vazby na zakázku nebo dřívějšího průchodu může změnit i starší report. Chybějící cena přispěje nulou; pro správné ocenění musí být cenové přiřazení jednoznačné, viz [Číselníky](manual_ciselniky.md#6-ceny-a-délkové-intervaly).

### Jak vzniká prostoj

Prodleva je mezera mezi začátkem daného kroku a koncem předchozího kroku na stejném zařízení typu Víceúčelovka. Prostoji se přičítá **max(prodleva − 10 minut, 0)**. Deset minut je technologická část odečítaná u každé vsázky.

Při chybějícím předchozím konci nebo nevyhodnotitelné prodlevě se prostoj nepřičte. Pokud datum konce předchozího kroku leží před dnem bezprostředně předcházejícím novému začátku, výpočet prodlevy vrátí nulu jako dlouhou odstávku. Překryv časů také nevytvoří kladný prostoj. Nulový údaj proto nemusí znamenat nepřetržitý chod bez odstávky. Prostoje se připisují ke dni začátku následujícího kroku.

## 8. Využití roštů podle zákazníků

**Využití roštů dle zákazníků** (`/dashboard/vyroba/zakaznici-vyuziti/`) uvádí **kg/rošt**, nikoli procento fyzické kapacity pece. Zahrnuje XL1 a XL2, po týdnech a za zvolený rok.

1. Hmotnost zákazníka pochází z prvních použití jeho beden na zařízení, stejně jako ve výrobní historii.
2. V každém kroku se sečtou zadaná procenta všech řádků beden z DB. Zákazník dostane podíl kroku podle svých procent / celkových procent těchto řádků.
3. Za období se sečtou zákaznické podíly kroků. **Kg/rošt zákazníka = jeho hmotnost / jeho součet podílů kroků.** Při nulovém nebo chybějícím podílu výpočet vrátí 0; nulové výsledky tato tabulka zobrazuje pomlčkou.
4. Řádek CELKEM počítá hmotnost všech zákazníků / počet kroků obsahujících bedny z DB. Není součtem ani prostým průměrem zákaznických kg/rošt.

**Příklad:** pokud má zákazník A v jednom kroku součet procent 100 a zákazník B součet 50, přiřadí se jim 2/3 a 1/3 roštu. Neznamená to 150% fyzické naplnění; procenta mohou pocházet z více pater a pro rozdělení kroku se normalizují.

Podíly se odvozují z evidovaných procent řádků beden, nikoli z jejich kg. Položky mimo DB do tohoto rozdělení nevstupují. Opakovaný krok se může podílet na počtu roštů nebo zákaznickém podílu, i když se již použitá bedna do výkonové hmotnosti podruhé nezapočte; průměr kg/rošt pak klesne.

## 9. Historie rovnání: jedinečné bedny za období

**Historie rovnání** (`/dashboard/rovnani/historie/`) vyhledává skutečné historické přechody pole Rovnání na **Vyrovnaná**. Datum výkonu je datum zápisu změny do historie, nikoli datum založení bedny nebo začátku fyzického rovnání.

- V každém dni, týdnu, měsíci a roce se stejná bedna počítá **jen jednou v rámci daného období**.
- Roční součet se proto nemusí rovnat součtu měsíčních a měsíční součet součtu denních. Bedna opakovaně vyrovnaná ve dvou dnech může být v obou denních řádcích, ale měsíčně jen jednou.
- Pouhé uložení už Vyrovnané bedny bez změny Rovnání se nepočítá. Založení bedny rovnou s Vyrovnaná se jako přechod také nepočítá.
- Denní průměr = počet různých beden za období / počet uplynulých dní **pondělí–pátek včetně dneška, bez odečtení svátků**. Události o víkendu do počtu beden vstupují; víkend ale nezvětšuje jmenovatel.
- Údaj je v **bednách a bednách/den**, nikoli kg. Nejde ani o dnešní počet beden, které zůstaly Vyrovnaná; přehled zachovává skutečný historický přechod, i když se dnešní stav změnil.

**Příklad:** stejná bedna přešla na Vyrovnaná 3. a znovu 4. listopadu. Denní detail má v obou dnech po jedné, ale listopadový i roční počet ji zahrne jednou. Když se změna na Vyrovnaná zapíše při potvrzení výstupní kontroly, do historie rovnání vstoupí tento zápis.

## 10. Provozní fronty, pracoviště a neshody

| Přehled | Co znamená položka a její přítomnost |
| --- | --- |
| Nakládání (`/provozni-prehledy/`) | Otevřené nakládání na číslech pracovišť 1–6. Počet řádků nebo pater roštu nemusí odpovídat počtu různých beden. |
| Ostatní pracoviště (`/prehled-pracovist/`) | Kroky mimo Nakládání bez vyplněného konce. Otevřený krok je údaj evidence, ne automatické potvrzení, že zařízení právě fyzicky běží. |
| Přehled kontroly (`/prehled-kontroly/`) | Bedny ve stavu Zakaleno a šarže s položkami mimo DB ve stavech Zakalená ke kontrole nebo Vyložená ke kontrole. Bedny a šarže jsou různé typy položek. |
| Rozkontrolovaná bedna | Má alespoň jedno uložené jednotlivé měření. Samotné uložení výstupní kontroly bez měření tento příznak nevytvoří. |
| Čeká od v přehledu kontroly | Čas posledního evidovaného vstupu do příslušného čekajícího stavu. Pokud přechod v historii chybí, čas nemusí být dostupný. |
| Přehled neshod (`/prehled-neshod/`) | Aktuální kontroly s Uvolnění = Neshoda, s filtry zákazníka, důvodu a data změny uvolnění. Po uvolnění bedna z této fronty zmizí. |
| Evidence neshod v administraci | Uložené neměnné případy s tehdejšími podklady, které zůstávají i po uvolnění. Jedna bedna může mít více případů. |

Aktuální počet neshod, počet historických případů a „Křivých %“ v kamionech proto nejsou zaměnitelné. Bedna může být Vyrovnaná a uvolněná, takže se podílí na příslušném ukazateli výdeje, ale není v aktuální frontě neshod. Více důvodů jedné Neshody také neznamená více různých beden.

## 11. Uložená rozpracovanost a její PDF

V administraci v bloku **Systém → Rozpracovanosti** vybíráte záznam s konkrétním časem pořízení. Při vytvoření standardním příkazem aplikace zahrne bedny s **Fakturovat = Ano** ve stavech **Zakaleno, Zkontrolováno a K expedici** s vazbou na kamion příjem. Příkaz při prázdném výběru nový záznam nevytvoří. Samotná existence funkce nepotvrzuje, kdy a jak pravidelně se snímky pořizují.

Tento výběr se liší od filtru **Rozpracováno** v Seznamu beden: ten zahrnuje Navezeno a Ve zpracování, ale nezahrnuje K expedici a nemá stejné omezení Fakturovat.

| Údaj | Je uchovaný jako tehdejší hodnota? |
| --- | --- |
| Čas pořízení a výběr odkazů na bedny | Ano. Pozdější změna výrobního stavu sama bednu z uloženého výběru nevyřadí. |
| Výrobní stav, Tryskání, Rovnání a Zinkování | Ano, jako samostatná pole snímku; detail je označuje jako snapshot. |
| Netto, tára, množství, údaje zakázky a zákazníka, ceny | Nejsou kompletně zkopírované do snímku; při zobrazení nebo novém tisku se čtou z navázaných aktuálních dat. |

Pro **Vytisknout rozpracovanost (PDF)** vyberte právě jeden záznam. Tisk používá uložený výběr beden, ale znovu jej omezuje současným **Fakturovat = Ano** a používá aktuální hmotnosti, zakázky, ceny, fakturační nastavení i současné stavy Otryskaná/Vyrovnaná pro příplatky. Nejde o úplnou archivní kopii ocenění a stavů v okamžiku snímku.

Počty beden a hmotnosti ve skupině Kalení zahrnují pouze bedny s hlavním Fakturovat = Ano a Fakturovat kalení = Ano. Stejně se pro Rovnání a Tryskání uplatní příslušné přepínače, nastavení zákazníka a stav Vyrovnaná/Otryskaná. Upozornění na neúplný ceník ověřuje pouze operace skutečně účtované alespoň u jedné bedny dané zakázky zahrnuté do tohoto PDF. Vypnuté operace ani bedny mimo vybraný snímek samy varování nevyvolají; chybějící cena účtované operace se dál ohlásí.

Opětovně vytištěné PDF stejného záznamu se proto může lišit od dříve uloženého PDF. Změna hmotnosti, cen, příznaku Fakturovat nebo navazujících údajů ovlivní výsledek; smazaná bedna už není dostupná jako živá vazba. Při porovnávání uchovávejte vydaný soubor a ověřte čas snímku i čas tisku. To je jiný rozsah uchování než u neměnného případu v Evidenci neshod.

## 12. Aktualizace obrazovek a přístup

| Obrazovka | Nastavené obnovení |
| --- | --- |
| Přehled beden | Automaticky přibližně každých 10 minut. |
| Přehled beden k navezení | Automaticky přibližně každých 60 sekund. |
| Přehled kamionů, výroby, Historie výroby, Využití roštů dle zákazníků, Historie rovnání a jejich uvedené měsíční detaily | Automaticky přibližně každých 60 minut. |
| Seznam beden | Kontrola změn beden přibližně každých 30 sekund; nejde o stejný časovač jako v souhrnných dashboardech. |

Interval není zárukou okamžitého načtení: ověřte spojení, otevřenou stránku a zobrazené **Naposledy aktualizováno**. Tento čas je čas sestavení přehledu, nikoli poslední výrobní událost nebo datum zvoleného období. Před porovnáním dvou obrazovek je znovu načtěte a zkontrolujte jejich filtry a jednotky.

Položky menu se mohou skrývat podle oprávnění; přístup konkrétní stránky a možnost otevřít detail či něco uložit se posuzují zvlášť. Čtení tohoto návodu nepřiděluje přístup k agendám. Nastavení účtů a skutečné skupiny popisují [Role a oprávnění](manual_role_a_opravneni.md).

## 13. Když se čísla neshodují

| Pozorovaný rozdíl | Co porovnat jako první |
| --- | --- |
| Přehled beden a Seznam beden mají jiný počet | Pozastaveno, výrobní stav, zákazníka, délku, prioritu, hledání a ostatní filtry. |
| Součet dokončovacích řádků převyšuje sklad | Překryv rovnání, tryskání, zinkování a dalších podskupin. |
| Po exspiraci má v seznamu více beden | Zda seznam zahrnul také Nepřijato; současně zkontrolovat filtr pozastavení. |
| Zakázka má ✔️, ale nepřispívá do K expedici po zakázkách | Kombinaci K expedici a Expedováno a případné oddělené části zakázky. |
| Příjem − Výdej neodpovídá dnešnímu skladu | Počáteční zásobu, jiné období, Fakturovat a aktuální vazby na kamiony. |
| Zpracováno v kamionech je jiné než produkce pecí | Historické vstupy do skupiny stavů versus první použití v deníku; čas zápisu versus datum začátku kroku a případné opakované vstupy. |
| Součet směn se liší od kalendářního dne | Noční začátky mezi půlnocí a 06:00 a návaznost dvou kalendářních dat. |
| Využití roštu kleslo po opakovaném zpracování | Zda přibyl další krok, jehož bedna už byla na daném zařízení dříve započtena do hmotnosti. |
| Počet v Historii rovnání nesouhlasí se součtem denních řádků | Jedinečnost bedny v celém vybraném období a rozdíl mezi dnem a měsícem. |
| Dva denní průměry se liší | Kalendářní dny, dny s evidovaným krokem nebo pondělí–pátek; také zahrnutí dneška a nulových dní. |
| Starší report po novém načtení vypadá jinak | Opravy deníku, aktuální hmotnosti a ceny, změny kamionů či Fakturovat a rozsah uchovaných historických údajů. |

Při ověřování si poznamenejte název přehledu, rok/měsíc nebo rozsah dní, jednotku, filtry a čas aktualizace. Rozdíl ověřte na jedné konkrétní bedně nebo zakázce a teprve poté porovnávejte součty. Pokud evidence neodpovídá skutečnosti, postupujte podle [Mimořádných situací a oprav](manual_mimoradne_situace.md).

## 14. Související návody

[Provozní tahák](provozni_tahak.md) · [Stavy a automatická pravidla](manual_stavy_a_pravidla.md) · [Bedny](manual_bedna.md) · [Zakázky](manual_zakazka.md) · [Kamiony](manual_kamion.md) · [Průchod šarže](manual_pruchod_sarze.md) · [Kontrola beden](manual_kontrola_beden.md) · [Evidence neshod](manual_evidence_neshod.md) · [Číselníky](manual_ciselniky.md) · [Role a oprávnění](manual_role_a_opravneni.md)
