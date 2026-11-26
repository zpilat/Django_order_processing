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
| Přehled kontrolorů | Historie všech dokončení kontrol a přechodů z Neshody do uvolnění | Denní počty za kontrolory za posledních 30 kalendářních dní včetně dneška, včetně opakovaných kontrol stejné bedny. |
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

Přesun šipkou přes okraj pozice přesune bedny zakázky do sousední pozice.
Každá přesunutá bedna má v historii pracovníka, čas a popis přesunu se zdrojovou
a cílovou pozicí. Pozice, historie i nové pořadí se uloží společně. Změna pořadí
uvnitř stejné pozice polohu beden nemění a nový záznam jejich historie nevytváří.

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
- Pro porovnání je dočasně znovu dostupná původní tabulka **Počet naložených šarží a pater včerejších směn**. Zahrnuje všechna pracoviště typu Nakládání. Počítá kroky Nakládání, nikoli jedinečné šarže, a součet různých čísel pater v jednotlivých krocích. Celý krok a všechna jeho aktuální patra přiřadí podle data a času začátku kroku do denní 06:00–18:00 nebo noční 18:00–06:00 směny; konec ani historie uložení pater nerozhodují. Započítá i neukončený krok a krok bez pater (jako jednu šarži a nula pater). Poměrné rozdělení pater a podílů šarží podle časových intervalů zůstává v samostatném **Přehledu časů nakládání a vykládání**. Pod původní tabulkou je odkaz na nový přehled.

### Kalendářní den není totéž co dvojice směn

Souhrn a včerejší produkce vrutů pracují s kalendářním datem **00:00–24:00**. Denní směna má začátky kroků **06:00–17:59**, noční **18:00–05:59 následujícího dne**. Zařazení určuje začátek kroku, nikoli celý čas jeho běhu.

Krok začínající dnes ve 02:00 je proto v noční směně včerejška, ale ne ve včerejším kalendářním souhrnu vsázek. Z tohoto důvodu se součet směn může lišit od denního souhrnu.

### První použití bedny na zařízení

Pro výkon se vybírá první evidovaný průchod bedny **na konkrétním zařízení za celou dostupnou evidenci**, nikoli znovu každý den. Opakované řádky stejné bedny v jednom kroku a její pozdější použití na stejném zařízení se z výkonové hmotnosti vyřadí. Rozhodují datum, čas začátku a pořadí kroku; u opakování v témže kroku také patro a řádek.

Používá se celá současná kladná netto hmotnost bedny, bez násobení procenty roštu a bez omezení na Fakturovat = Ano. Pokud stejná bedna projde poprvé XL1 i XL2, může se její hmotnost započítat jednou u každého zařízení. Celkem tedy nemusí být hmotnost jedinečných beden napříč oběma pecemi.

Čtrnáctidenní historie denní produkce končí včera. Týdenní a dvoutýdenní průměry dělí produkci 7 a 14 kalendářními dny včetně nulových dní; nejde o průměr pouze za odpracované směny.

### Přehled časů nakládání a vykládání

Otevřete v administraci **Přehledy výroby → Přehled časů nakládání a vykládání**, případně stejnou položku v menu **PŘEHLEDY** (`/dashboard/casy-nakladani/`). Přehled má společný výběr dne a nahoře pod sebou směnové souhrny **Nakládání** a **Vykládání**. V každém souhrnu jsou 12hodinové a 8hodinové směny na široké obrazovce vedle sebe, na menší pod sebou. Teprve pod oběma souhrny následují **Podrobnosti nakládání** a **Podrobnosti vykládání**: upozornění k evidenci, rozpisy všech příslušných šarží a pater a vysvětlení výpočtů. Přístup vyžaduje přihlášení, stejně jako ostatní souhrnné dashboardy; vstup do administrace navíc vyžaduje staff. Přehled je pouze ke čtení a nemění oprávnění k výrobní evidenci. Nevytváří novou tabulku ani rozhraní pro opravy časů.

Výchozím dnem je včerejšek. Pole **Den začátku směn** umožní vybrat jiný den nejpozději dnešní. Obě tabulky pokrývají stejný interval **od 06:00 vybraného dne do 06:00 následujícího dne**:

| Režim | Směny |
| --- | --- |
| 12hodinový | Denní 06:00–18:00, noční 18:00–06:00. |
| 8hodinový | Ranní 06:00–14:00, odpolední 14:00–22:00, noční 22:00–06:00. |

Sekce Nakládání zahrnuje všechna pracoviště typu **Nakládání**. Sekce Vykládání zahrnuje společně typy **Vykládání** a **Tryskač**. Obě zahrnují bedny z DB i položky mimo DB. Dva režimy směn v každé sekci představují dva pohledy na stejnou práci a **nesčítají se**. Součet **Celkem 06:00–06:00** je v každé sekci pouze pod 12hodinovými směnami. Nejde o automatické přiřazení výkonu konkrétním pracovníkům podle jejich pracovního úvazku.

**Časový interval patra při nakládání:**

1. Začátek je první uložení položky daného patra v kroku Nakládání, podle `history_date` vytvoření v Simple History. Samotné načtení kódu do neuloženého formuláře se do databáze nezapisuje. Obsluha proto po načtení první bedny patro rovnou uloží a pak začne fyzicky nakládat.
2. Konec je první uložení následujícího patra. Patra se řadí podle čísla.
3. Poslední patro končí evidovaným datem a časem konce kroku Nakládání; konec se doplní ihned po dokončení práce.

**Celá koncová minuta:** Pro přehled a měsíční CSV se konec Nakládání i Vykládání/Tryskače vyhodnocuje jako konec zadané minuty, tedy **HH:MM:59,999999**. Například zadaných 08:10 znamená pro výpočet 08:10:59,999999. Sekundy se nastaví na konec téže minuty i tehdy, pokud je uložený čas už obsahuje; nepřičítá se dalších 59 sekund, které by ho posunuly do následující minuty. Zadané časy v databázi a historii se nemění. Začátky pater a mezilehlé konce podle založení dalšího patra zůstávají přesné.

Pravidlo toleruje první uložení posledního patra až do koncové minuty, například 08:10:59,5 při zadaném konci 08:10. Větší nesoulad nadále vyřadí krok. Kontrola budoucího konce používá původní zadaný údaj, aby právě ukončený krok nebyl chybný jen kvůli dopočteným sekundám do konce minuty. Nulová nebo záporná délka i po této úpravě zůstává neplatná; začátek a konec zadané ve stejné minutě mohou pro přehled tvořit platný interval.

Koncová minuta se rozdělí podle stejných hranic směn jako zbytek práce. Konec zadaný v 18:00 proto zasáhne i noční směnu, konec v 06:00 začátek následujícího dne přehledu. Denní a měsíční okna stále začínají i končí přesně v 06:00. Hodiny a přesné podíly se mohou proti výpočtu bez koncové minuty mírně změnit.

Běžná úprava patra jeho původní začátek neposouvá, i když technicky smaže a znovu vytvoří řádky deníku. Výpočet hledá i mezi historickými záznamy již smazaných řádků. Nové použití tlačítka **Smazat patro** má v historii důvod **Smazání celého patra při nakládání.** Pokud se stejné číslo patra později znovu založí, použije se až jeho nové první uložení. Starší smazání celého patra a neoznačené ruční zásahy v administraci nelze spolehlivě odlišit od technické náhrady řádků; u stejného čísla patra se v takovém případě zachová první dochované vytvoření. Historie se zpětně nepřepisuje.

**Výpočet sloupců pro nakládání:**

- **Patra**: pro každý dokončený interval se započte poměr délky jeho překryvu se směnou k celé délce intervalu. Například u posledního patra 17:40–18:20 se počítá do 18:20:59,999999; přesné podíly jsou přibližně 0,488 denní a 0,512 noční směně, obě zobrazené jako 0,5 patra.
- **Šarže**: podíl pater se pro každý uzavřený krok Nakládání dělí jeho skutečným konečným počtem různých pater. Například 2,4 ze 4 pater představuje 0,6 šarže. Celý platný uzavřený krok se napříč všemi zasaženými dny a směnami sečte na 1,0 šarže. Nepoužívá se pevný dělitel 6, maximální číslo patra ani průměrný počet pater všech šarží. Případné opakované kroky Nakládání stejné šarže se vyhodnocují samostatně.
- **Čas [hod.]**: součet překryvů intervalů nakládání se směnou ze všech pracovišť. Zahrnuje čekání a přestávky uvnitř intervalu. Při souběhu pracovišť může přesáhnout délku směny; nejde o osobní odpracované hodiny.

V obou sekcích se počítá z přesných délek intervalů a zaokrouhluje se až při zobrazení: patra, podíly šarží a hodiny na **jedno desetinné místo**, včetně součtů a hodin v rozpisech. Počet pater celého kroku v rozpisu vykládání je celé číslo. Součty se počítají z nezaokrouhlených hodnot, proto se mohou mírně lišit od součtu zobrazených zaokrouhlených řádků. Hranice směn jsou podle **Europe/Prague**, délky podle skutečně uplynulého času i při změně letního a zimního času. Interval začínající před vybraným obdobím se započte jen částí, která do něj zasahuje; půlnoc sama interval nerozděluje.

U rozpracovaného Nakládání se započtou jen patra se známým koncem. Otevřené poslední patro čeká na další patro nebo konec kroku. **Podíly šarží** se doplní až po uzavření celého Nakládání, protože teprve tehdy je znám konečný počet pater. Dřívější výsledky se proto mohou dodatečně doplnit nebo změnit po opravě evidence.

Pod souhrny je rozpis **Časy nakládání jednotlivých pater** se šarží, krokem, pracovištěm, číslem patra, celým začátkem, **Koncem pro výpočet**, celou délkou intervalu a stavem započtení. U posledního patra je v nápovědě vypočteného konce také původní zadaný konec kroku. Celé intervaly v rozpisu mohou přesahovat vybrané období; souhrny obsahují pouze jejich překryv s obdobím. Prázdné kroky, chybějící první uložení, nerostoucí začátky pater nebo neplatný konec se označí a celý dotčený krok se ze součtů vyřadí. Chybějící časy se neodhadují ze začátku kroku ani z pozdějších úprav. Odkaz na administraci kroku je dostupný pouze staff uživateli s právem `view_sarzekrok`.

**Vykládání na typech Vykládání a Tryskač:**

Procentuální rozdělení vychází z celého intervalu **Datum začátku + Začátek → Datum konce + konec zadané minuty** daného kroku. Práce se považuje za rovnoměrnou na obou typech pracovišť. Časy vytvoření řádků deníku ani historie jednotlivých pater zde začátek neurčují. Počet pater je počet různých čísel pater v obsahu vykládacího kroku; běžný přesun je kopíruje z předchozího kroku. Více beden na stejném patře počet nezvyšuje a nejde o nejvyšší číslo patra.

| Sloupec | Výpočet |
| --- | --- |
| Šarže | Délka překryvu kroku se směnou / celková délka kroku. Celý dokončený krok představuje 1,0 šarže. |
| Patra | Počet různých pater v obsahu kroku × uvedený časový podíl. |
| Čas [hod.] | Délka překryvu celého kroku se směnou; součet ze všech pracovišť, včetně čekání a přestávek uvnitř kroku. |

Například vykládání třípatrové šarže 17:30–19:00 se pro výpočet prodlouží do 19:00:59,999999, tedy na téměř 91 minut. Denní směna dostane podíl za 30 minut a noční za téměř 61 minut; na obrazovce se zobrazí 0,3 a 0,7 šarže a 1,0 a 2,0 patra. Jde o časový odhad pater, protože jejich skutečné dílčí časy nejsou evidované.

**Neukončené vykládání** se zobrazí jako rozpracované. Šarže, patra ani hodiny se nezapočtou, dokud není znám konec celého kroku. Po uzavření se výkon zpětně rozdělí do všech zasažených směn a dní. Krok bez evidovaných pater, bez platného začátku, s neúplným koncem, nulovou nebo zápornou délkou i po započtení koncové minuty nebo původním zadaným koncem v budoucnosti se označí a ze součtů vyřadí. Počet pater se nenahrazuje šestkou ani se neodhaduje podle jiného kroku.

Pokud má šarže více kroků typu Vykládání nebo Tryskač, zobrazí se upozornění a dotčené řádky jsou zvýrazněné. Kontrola hledá všechny tyto kroky šarže, i mimo vybraný den. **Každý platný dokončený krok se započte samostatně**; přehled automaticky neurčuje, který je duplicitní. Ověřte, zda evidence zachycuje skutečné opakované zpracování, nebo vyžaduje opravu duplicity. Počet Šarže je tedy součtem vykládacích průchodů, nikoli počtem jedinečných čísel šarží.

Rozpis **Časy vykládání šarží** obsahuje šarži a krok, pracoviště včetně typu, počet pater celého kroku, celý začátek, **Konec pro výpočet**, celou délku intervalu a stav započtení. V nápovědě vypočteného konce je původní zadaná hodnota. Stejně jako u nakládání souhrny obsahují pouze překryv s vybraným obdobím. Odkaz na administraci kroku má stejná omezení jako u nakládání. Vykládací statistika není vázaná na aktuální výrobní stav šarže ani beden.

**Měsíční export pater do CSV:**

Tlačítko **CSV za MM/RRRR** v horním záhlaví stáhne soubor `patra_smeny_RRRR-MM.csv` za poslední celý uplynulý měsíc směn. Zvolený den v přehledu období exportu nemění. Interval začíná **v 06:00 prvního dne měsíce** a končí **v 06:00 prvního dne následujícího měsíce**. Například říjen zahrnuje 1. 10. 06:00 až 1. 11. 06:00. Nový měsíc je uzavřený teprve po konci poslední noční směny: 1. 12. v 05:59 se stále exportuje říjen, od 06:00 už listopad. Rozhoduje čas **Europe/Prague**.

CSV má jeden řádek pro každý den začátku směn v měsíci, vzestupně a včetně nulových dní. Obsahuje 12 sloupců:

1. **Datum směn** ve formátu DD.MM.RRRR.
2. Dvojici **Naložená patra / Vyložená patra** pro každou směnu v pořadí **12h 06–18, 12h 18–06, 8h 06–14, 8h 14–22, 8h 22–06** (celkem deset číselných sloupců).
3. **Stav evidence**: `OK`, nebo počty známých chybných a neuzavřených kroků Nakládání/Vykládání a šarží s opakovanými vykládacími průchody pro daný den. Více upozornění je v jedné buňce oddělených středníkem.

Noční směna každého řádku končí v 06:00 následujícího dne; u posledního řádku už v dalším měsíci. Export používá přesně stejné výpočty a pravidla započtení jako denní přehled, včetně celé koncové minuty kroku, překryvů z předchozího měsíce, rovnoměrného vykládání, neuzavřených kroků a změny letního a zimního času. Okno měsíce zůstává přesně 06:00–06:00: část koncové minuty ležící za hranicí měsíce už náleží následujícímu měsíci. Hodnoty pater mají **jedno desetinné místo a desetinnou čárku**, nulové hodnoty jsou `0,0`. Oba režimy směn zachycují stejnou práci a při dalším zpracování CSV se nesčítají dohromady.

Soubor používá **UTF-8 s BOM, oddělovač středník a konce řádků CRLF**, aby se správně otevřel v českém Excelu. Export se vytvoří při stažení z aktuální evidence a nemění data ani auditní historii. Po doplnění konců nebo opravě výrobní evidence se mohou hodnoty při opakovaném stažení změnit. Přístup má přihlášený uživatel stejně jako do přehledu; soubor se stáhne do počítače uživatele a automatické měsíční vytváření na serveru není nastavené.

## 7. Historie výroby: průměry, vytížení a prostoje

**Historie výroby** (`/dashboard/vyroba/historie/`) používá stejná zařízení a pravidlo prvního použití bedny jako Přehled výroby. Zvolte rok; přes měsíc otevřete denní detail.

Na mobilu hlavní přehled i měsíční detail využívají celou dostupnou šířku. Pokud se všechny sloupce nevejdou, posouvejte konkrétní tabulku vodorovně uvnitř její karty. Záhlaví a ovládací prvky se přizpůsobují šířce obrazovky.

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

Počty beden a hmotnosti ve skupině Kalení zahrnují pouze bedny s hlavním Fakturovat = Ano a Fakturovat kalení = Ano. Stejně se pro Rovnání a Tryskání uplatní příslušné přepínače bedny a stav Vyrovnaná/Otryskaná. Upozornění na neúplný ceník ověřuje pouze operace skutečně účtované alespoň u jedné bedny dané zakázky zahrnuté do tohoto PDF. Vypnuté operace ani bedny mimo vybraný snímek samy varování nevyvolají; chybějící cena účtované operace se dál ohlásí.

Ocenění respektuje aktuální zákaznickou volbu **Proforma po bednách**. Při Ne se pro každou operaci zakázky násobí součet zahrnutých hmotností ceníkovou sazbou a výsledek se zaokrouhlí na cent HALF_UP. Při Ano se sčítají jednotlivě zaokrouhlené částky zahrnutých beden. Tento režim je uveden i v PDF; u ocenění po bednách může částka řádku zakázky o centy překročit nebo podkročit součin zobrazené hmotnosti a sazby. Souhrn zákazníka vždy sčítá částky řádků zakázek, nepřepočítává je průměrnou sazbou.

Do částek se nesmí přičíst bedny mimo vybraný snímek, ani když patří ke stejné zakázce. Pro shodný výběr beden, stejné aktuální údaje a stejný režim fakturace tak rozpracovanost odpovídá proformě. Podrobná pravidla jsou v [manuálu beden](manual_bedna.md#ceníkové-sazby-a-účtované-částky).

Opětovně vytištěné PDF stejného záznamu se proto může lišit od dříve uloženého PDF. Změna hmotnosti, cen, příznaku Fakturovat nebo navazujících údajů ovlivní výsledek; smazaná bedna už není dostupná jako živá vazba. Při porovnávání uchovávejte vydaný soubor a ověřte čas snímku i čas tisku. To je jiný rozsah uchování než u neměnného případu v Evidenci neshod.

## 12. Aktualizace obrazovek a přístup

| Obrazovka | Nastavené obnovení |
| --- | --- |
| Přehled beden | Automaticky přibližně každých 10 minut. |
| Přehled beden k navezení | Automaticky přibližně každých 60 sekund. |
| Přehled kontrolorů | Automaticky přibližně každých 60 sekund; při obnovení se znovu určí posledních 30 dní. |
| Přehled kamionů, výroby, časů nakládání a vykládání, Historie výroby, Využití roštů dle zákazníků, Historie rovnání a jejich uvedené měsíční detaily | Automaticky přibližně každých 60 minut. |
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

## 14. Přehled kontrolorů

Položka **Přehled kontrolorů** je poslední v menu **PŘEHLEDY**. Nahoře je samostatná karta **Souhrn za posledních 30 dní**: každý kontrolor má jeden řádek s celkovým počtem dokončených kontrol a vyřešených neshod za období. Poslední řádek uvádí součty obou typů za všechny kontrolory.

Pod souhrnem je karta **Denní přehled podle kontrolorů**: každý den tvoří jeden řádek, vlevo je datum a vedle sebe jsou skupiny **Dokončené kontroly beden** a **Vyřešené neshody**. Pod každou skupinou jsou sloupce jednotlivých kontrolorů ve stejném pořadí a sloupec **Celkem** za daný den a typ údaje. Vysvětlení pravidel a omezení starší historie je až pod oběma kartami.

Přehled používá stejné firemní barvy jako ostatní přehledy: modré úvodní záhlaví se žlutým textem, žluté názvy karet a modrá záhlaví sloupců se žlutým textem. Na širokých obrazovkách má omezenou šířku a je vycentrovaný, aby jména a počty zůstaly blízko sebe. Čísla jsou zarovnaná na střed, nuly v denním přehledu mají méně výrazný text. Názvy sloupců a jednotlivé dny oddělují vodorovné čáry. Datum je od dokončených kontrol oddělené stejnou svislou čárou jako obě skupiny údajů od sebe. Denní tabulka zobrazuje všech 30 dní v plné výšce bez vnitřního svislého posouvání; podle potřeby se posouvá celá stránka. Na menších obrazovkách nebo při větším počtu kontrolorů lze tabulku posouvat vodorovně.

Otevřete **PŘEHLEDY → Přehled kontrolorů** nebo v administraci **Přehledy kontroly → Přehled kontrolorů** (`/prehled-kontroloru/`). Odkaz v administraci je za Přehledem neshod a otevírá se v nové kartě. Přístup do samotného přehledu vyžaduje přihlášení, bez dalšího modelového oprávnění, stejně jako ostatní souhrnné dashboardy; vstup do administrace navíc vyžaduje staff. Období je vždy **dnešek a předchozích 29 kalendářních dní**, podle času **Europe/Prague**, včetně víkendů a svátků. Nejde o posledních 720 hodin ani posledních 30 pracovních dní. Filtr období není dostupný.

Sloupce kontrolorů zahrnují každého uživatele, který má v období alespoň jednu započítanou událost libovolného z obou typů. Denní rozpis jde od dneška zpět a obsahuje všech 30 dní, včetně nulových dnů a nulových počtů těchto uživatelů. Uživatelé se rozlišují podle účtu, i když mají stejné jméno. Zobrazuje se současné celé jméno, případně přihlašovací jméno. Chybějící autor patří pod **Neznámý uživatel**; jeho práci nepřebírá zakladatel kontroly ani poslední editor.

| Ukazatel | Pravidlo započtení |
| --- | --- |
| **Dokončené kontroly beden** | Každé skutečné dokončení tlačítkem **Dokončit kontrolu bedny**, tedy úspěšný přechod **Zakaleno → Zkontrolováno**. Počítá se i výsledek Neshoda a opakované dokončení stejné bedny, i ve stejný den. Den a autor pocházejí z příslušného záznamu dokončení, nikoli založení kontroly nebo měření. |
| **Vyřešené neshody** | Každý skutečný přechod **Neshoda → Uvolněno / Uvolněno QS s odchylkou**. Den a autor pocházejí z tohoto přechodu. Jedna bedna může mít po návratu do Neshody více započtených vyřešení, i ve stejný den. |

Přehled měří počet dokončených kontrol, nikoli počet různých beden. Po návratu bedny do výroby a novém dokončení ze Zakaleno na Zkontrolováno se započítá další kontrola podle dne a autora nového dokončení. Platí to i vícekrát ve stejný den nebo pokud předchozí dokončení leží mimo posledních 30 dní. Například pondělní kontrola a nová čtvrteční kontrola po opakovaném zpracování znamenají dvě dokončené kontroly.

Samotný návrat z K expedici na Zkontrolováno, opakované uložení ani oprava výsledků kontroly počet nezvyšují. Založení kontroly, zápis měření, uložení rozhodnutí bez dokončení a neúspěšné potvrzení nejsou dokončením. Automatický převod **Přijato → Zkontrolováno** při zahájení atypického průběhu se nepočítá; pozdější vyřešení jeho Neshody ano.

Samotná změna Uvolněno na QS s odchylkou nebo naopak ani uložení poznámky nezvyšuje počet vyřešených neshod. Počítají se přechody rozhodnutí v historii kontroly, nikoli počet snapshotů Evidence neshod nebo jednotlivých důvodů. Jedno uvolnění bedny s více důvody znamená jedno vyřešení.

**Oba typy údajů se mohou týkat stejné bedny a nesčítají se do celkového počtu beden.** Například první kontrola s Neshodou v pondělí patří dokončujícímu kontrolorovi v pondělí; následné uvolnění ve středu patří uvolňujícímu kontrolorovi ve středu.

### Rozsah starší historie

Nové dokončení tlačítkem má v historii důvod **Dokončení kontroly bedny tlačítkem.** Nové ruční nastavení Zkontrolováno v seznamu nebo detailu administrace má vlastní označení a do dokončených kontrol tohoto přehledu nevstupuje. Historie se zpětně nepřepisuje a změna nevyžaduje datovou migraci.

U starších záznamů bez označení akce se započítá každý přechod Zakaleno → Zkontrolováno v období. Nelze u nich spolehlivě rozlišit tlačítko od stejné ruční změny v administraci. Bez předchozího historického záznamu se přechod neodvozuje; přehled tedy nemůže dopočítat chybějící historii. Započtení se neopírá o současný stav bedny: pozdější expedice dokončenou kontrolu neodstraní.

## 15. Související návody

[Provozní tahák](provozni_tahak.md) · [Stavy a automatická pravidla](manual_stavy_a_pravidla.md) · [Bedny](manual_bedna.md) · [Zakázky](manual_zakazka.md) · [Kamiony](manual_kamion.md) · [Průchod šarže](manual_pruchod_sarze.md) · [Kontrola beden](manual_kontrola_beden.md) · [Evidence neshod](manual_evidence_neshod.md) · [Číselníky](manual_ciselniky.md) · [Role a oprávnění](manual_role_a_opravneni.md)
