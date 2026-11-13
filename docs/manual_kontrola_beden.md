# Uživatelský manuál: Kontrola beden

Kontrola propojuje naměřené hodnoty s výstupní kontrolou a rozhodnutím o uvolnění konkrétní bedny. Výrobní stav Zkontrolováno se potvrzuje samostatnou operací.

## Atypický průběh

V admin seznamu Bedny nastavte **Stav bedny = Zkontrolováno** a použijte dynamický filtr **Atypický průběh** za filtrem Uvolnění. Volby jsou Vše, Ano a Ne. Při změně výrobního stavu se tento filtr odstraní.

Bedna s příznakem **Atypický průběh** má v záhlaví upozornění. Používá se pro reklamace a samostatné operace; založení popisuje [manuál beden](manual_bedna.md#atypický-průběh-reklamace-a-samostatné-operace).

- Tvrdost povrchu a jádra lze zadávat i u beden, které nejsou vybrané běžnými pravidly vzorkování. Stejná podmínka platí pro přehled měření v adminu a pro požadavky i rozsah měření ve vyplněné KKK. Tvrdosti zůstávají nepovinné.
- Není povinné měření Ohybu, Krutu, Prohybu po TZ ani zadání obou počtů křivých. Je možné zapsat pouze vybrané zkoušky nebo uvolnit bednu bez měření. Prohyb po koulení a po rovnání je dostupný přímo, i bez vstupního prohybu po TZ. Uzamčení vstupního měření po zadání rovnání platí dál.
- Zadaný prohyb se vyhodnocuje podle dosavadních pravidel včetně povoleného počtu křivých. Pokud nějaký prohyb existuje, potřebuje nastavenou běžnou mez a povolený počet křivých; bez nich nelze potvrdit kontrolu. Bez měření se tato nastavení nevyžadují. Vyhodnocování ostatních zkoušek se touto změnou nezapíná.
- **Neshoda smí být bez důvodu.** U atypické bedny v Neshodě lze ukládat průběžnou kontrolu i bez Čistoty a Uložení a v adminu měnit provozní údaje, například ručně nastavit Tryskání Špinavá. U Uvolněno a QS s odchylkou jsou Čistota i Uložení nadále povinné. U QS je důvod dál povinný. Jiné stále vyžaduje poznámku a Čistota/Uložení NOK vynucují Neshodu a příslušné automatické důvody. Uvolněno důvody vymaže.
- Při uložení kontroly se **Tryskání** nastaví podle vyplněné Čistoty jako u běžné bedny. Pokud Čistota u rozpracované atypické Neshody není zadaná, dosavadní ruční stav Tryskání zůstane zachovaný. **Rovnání** se přednostně vyhodnotí z Prohybu po rovnání: vyhovující vzorek znamená Vyrovnaná, nevyhovující Křivá. Pokud měření po rovnání neexistuje, ale je zadaný **Prohyb po TZ**, vyhovující nebo oranžový QS výsledek nastaví **Rovná** a nevyhovující **Křivá**. Bez obou těchto měření zůstane ruční stav zachovaný; samotný Prohyb po koulení jej nemění. **Zinkování se nemění.** Samotný zápis měření ani provozní úprava v adminu tyto stavy nepotvrzuje; při změně vyhodnocení je nutné uložit kontrolu.
- Příznak neobchází Neshodu, nepotvrzené změny ani požadované technologické stavy pro expedici. Bez prohybu se tedy Rovnání samo nenastaví na Rovná; skutečný stav určete ručně. Před expedicí atypické bedny musí být uložené uvolnění a Čistota i Uložení OK.

Následující požadavky na povinný Ohyb, Krut, Prohyb po TZ a oba počty křivých popisují běžné bedny bez tohoto příznaku. Ostatní pravidla platí i pro atypické bedny, není-li výše uvedeno jinak.

## 1. Otevření kontroly

V administraci **Bedny** upozorňuje červené zvýraznění buňky **Stav bedny**
a malý symbol **⚠** jako horní index těsně před stavem na aktuální Neshodu
i bez filtru Zkontrolováno. Po najetí na buňku nebo symbol se
zobrazí **Neshoda při kontrole**. Samotná Křivost se takto neoznačuje, protože
je patrná v Rovnání; při současném jiném důvodu se varování zobrazí.
Chybějící důvod u Neshody varování neskrývá. Uvolnění, včetně QS s odchylkou,
se takto nezvýrazňuje. Pravidla expedice tato vizuální výjimka nemění.

- V administraci **Bedny** při filtru **Stav bedny = Zkontrolováno** najdete přímo pod ním filtr **Uvolnění**. Volba **Neshoda** zobrazí bedny s tímto rozhodnutím, **Uvolněno** zahrnuje i **Uvolněno QS s odchylkou**. Výchozí **Vše** zahrnuje také nerozhodnuté a bedny bez kontroly. Při změně výrobního stavu se filtr uvolnění odstraní.
- Z **Přehledu kontroly** (`/prehled-kontroly/`) otevřete číslo bedny. Přehled obsahuje bedny ve stavu Zakaleno a šarže železa mimo databázi čekající na kontrolu. Bedny s alespoň jednou uloženou naměřenou hodnotou jsou červeně zvýrazněné a řadí se před ostatní položky. Obě skupiny se řadí podle času **Ke kontrole od**, od nejstarších.
- Naskenujte kartu bedny kamerou nebo čtečkou a v detailu zvolte **Kontrola bedny**.
- Pro postupné zadávání použijte **Další bedna ke kontrole**. Čtečka pro kontrolu je na `/bedny/skener-ctecka/?cil=kontrola`.
- Přímá cesta má tvar `/bedny/scan/123456/kontrola/`; použijte skutečné interní číslo bedny.

Před zápisem ověřte číslo, zákazníka, artikl a rozměr. Pořadí bedny se vztahuje k původní zakázce i po jejím rozdělení při expedici.

## 2. Zadání měření

Sekce **Naměřené hodnoty a jednotlivé zkoušky** nabízí Ohyb, Krut, Prohyb po TZ, Prohyb po koulení, Prohyb po rovnání, Tvrdost povrchu, Tvrdost jádra a Vrstva.

**Prohyb po koulení a Prohyb po rovnání** se nově nabízejí až při červeném výsledku celého vzorku **Prohybu po TZ**, s ohledem na zákaznické meze a povolený počet křivých. Bez měření po TZ, při vyhovujícím nebo oranžovém QS výsledku se prázdné navazující zkoušky nezobrazují. Pokud už konkrétní navazující zkouška má uložené hodnoty, zůstává viditelná. Nabídka se řídí samotným výsledkem po TZ i po následném úspěšném vyrovnání; neřídí se ručně nastaveným stavem Rovnání.

Po uložení alespoň jedné hodnoty **Prohybu po rovnání** se **Prohyb po TZ uzamkne**. Hodnoty zůstávají viditelné, ale nelze je přidávat, upravovat ani mazat; řádek vysvětluje důvod zamčení. Server odmítne i přímé otevření zápisu nebo odeslání formuláře otevřeného před uložením rovnání. Pokud je nutná oprava původního měření, nejprve odstraňte všechny aktuální hodnoty po rovnání; tím se zápis po TZ znovu zpřístupní. Historie původních hodnot a snapshoty neshody zůstávají zachované. Samotné měření po koulení prohyb po TZ nezamyká.

Pod názvem a limitem zkoušky se zobrazuje samostatný řádek s rozsahem měření, například **Min. 5 vzorků**. Ohyb a krut používají minimum mechanických zkoušek, povrch a jádro minimum tvrdosti. Všechny fáze prohybu používají minimum hodnot a celkový počet odebraných vrutů, například **Min. 5 hodnot z 25 vzorků**. V detailu zkoušky je stejný údaj nad zadáváním hodnot doplněný popiskem **Rozsah měření podle zákazníka**. Konkrétní pokyny k odběru z předpisu zůstávají v části **Požadavek z předpisu**. Nevyplněné minimum se nezobrazuje; u vrstvy se nadále používají pouze pokyny z předpisu.

1. U zkoušky klikněte na **Zadat / upravit hodnoty**.
2. Zkontrolujte požadavek. Běžné zkoušky čerpají požadavky z předpisu zakázky; prohyb má meze podle zákazníka a délky.
3. Zadejte jednotlivé hodnoty. Prohyb se zadává v mm, ostatní hodnoty v jednotkách předpisu. Lze použít desetinnou čárku, nejvýše čtyři desetinná místa.
4. Další řádky přidejte pomocí **+ Přidat hodnotu**. Prázdné nové řádky se neuloží; checkbox vlevo označí existující hodnotu ke smazání při uložení.
5. Klikněte na **Uložit hodnoty**. Vrátíte se na kontrolu bedny.

Měření se ukládá samostatně pro každou zkoušku, včetně uživatele a času měření. Při prvním zápisu vznikne kontrola, pokud dosud neexistovala. Odkaz **Zpět na kontrolu bedny** neuloží rozpracované hodnoty.

V běžném průběhu se tvrdost povrchu a jádra nabízí jen u beden vybraných pravidly vzorkování. Pro SSH, SWG a ROT se výběr řídí počtem beden původní zakázky; pro ostatní zákazníky se vybírá první bedna. Chybějící sekce tvrdosti proto může být očekávaná. U atypického průběhu se tvrdosti nabízejí vždy. Položky tvrdosti mají žlutý proužek na levém okraji místo žlutého pozadí. Proužek označuje typ zkoušky, nikoli výsledek posouzení tvrdosti.

## 3. Meze a zvýraznění prohybu

Číselná minima, maxima a maxima QS nově připravená v předpisech pro Ohyb, Krut, Tvrdost povrchu, Tvrdost jádra a Vrstvu zatím do hodnocení kontroly nevstupují. Požadavky těchto zkoušek se nadále zobrazují z původních textů. Jejich doplnění v předpisu samo nemění uvolnění, automatické důvody ani barvy výsledků. Podrobnosti popisuje [manuál číselníků](manual_ciselniky.md#číselné-meze-zkoušek-příprava-vyhodnocování).

`L` znamená délku zakázky v mm. Hodnota přesně na mezi je přípustná.

| Zákazník | Běžná horní mez prohybu |
| --- | --- |
| EUR, HPM, FIS | `0,006 × L` mm |
| SPX, SSH, ROT | `0,004 × L` mm |
| SWG, délka do 300 mm včetně | `0,006 × L` mm |
| SWG, délka nad 300 mm | `1,8` mm |

ROT má pro **prohyb po TZ a po koulení** navíc mez QS s odchylkou `0,006 × L` mm. Jednotlivé hodnoty nad běžnou mezí až do QS meze včetně mají oranžový text. Při překročení QS meze má celé políčko s hodnotou červené pozadí a bílý text. Pokud QS mez není zadaná, červené pozadí s bílým textem označuje hodnoty nad běžnou mezí. **Prohyb po rovnání se u všech zákazníků posuzuje pouze proti běžné horní mezi: hodnota rovná mezi je vyhovující, vyšší je červená a nevyhovující. QS mez se po rovnání nezobrazuje ani nepoužívá; oranžové hodnoty zde nejsou.** Toto označení jednotlivých hodnot zůstává viditelné i u starších fází prohybu. Stejný styl používá přehled měření v administraci. **Ve vyplněné KKK se nevyhovující hodnoty označují pouze červeným písmem bez červeného pozadí**; oranžový text je přípustný pouze ve sloupci po TZ. U zákazníka bez pravidla se mez nezobrazuje.

Maximální povolený počet křivých vrutů se nastavuje v **Administrace → Zákazníci → konkrétní zákazník → Kontrola kvality**, v poli **Maximální počet křivých vrutů při kontrole prohybu**. Nula znamená, že není povolen žádný křivý vrut; prázdné pole znamená, že se omezení uvolnění podle počtu neuplatní. Samotné meze prohybu v mm jsou definované v kódu podle zákazníka a délky, v `Bedna.limity_prohybu`.

V přehledu kontroly bedny se ve všech třech položkách prohybu (po TZ, po koulení a po rovnání) zobrazuje **Max. počet křivých vrutů ve vzorku** podle nastavení zákazníka, včetně hodnoty **0**. Pokud zákazník maximum nemá zadané, zobrazí se **nenastaven**. Údaj je viditelný i před zadáním měření.

Pro omezení uvolnění a barevné pozadí celé položky se posuzují pouze uložené jednotlivé hodnoty rozhodující fáze:

1. Pokud existuje alespoň jedna hodnota **Prohybu po rovnání**, použije se tato fáze a hodnoty po TZ se již nezapočítávají.
2. Jinak se použije **Prohyb po TZ**.
3. **Prohyb po koulení** se do tohoto rozhodnutí nezapočítává.

| Výsledek rozhodujícího měření | Dostupné uvolnění | Pozadí položky měření |
| --- | --- | --- |
| Po rovnání: počet hodnot nad běžnou mezí překročí povolený počet křivých | Pouze **Neshoda**, povinný důvod **Křivost** | Červené |
| Po TZ: počet hodnot nad QS mezí překročí povolený počet křivých; bez QS meze se počítají hodnoty nad běžnou mezí | Pouze **Neshoda**, povinný důvod **Křivost** | Červené |
| Po TZ: předchozí podmínka neplatí, QS mez existuje a počet hodnot nad běžnou mezí překročí povolený počet křivých | **Uvolněno QS s odchylkou** nebo **Neshoda**, povinný důvod **Křivost** | Oranžové |
| Počty nepřekročí povolené maximum | Prohyb výběr uvolnění neomezuje; dostupné je i **Uvolněno** | Bez zvýraznění |

Hodnota přesně na mezi se nepočítá jako překročení. Počet křivých přesně rovný povolenému maximu je přípustný. Pokud chybí maximální povolený počet, zákaznická mez prohybu nebo měření rozhodující fáze, toto omezení se neuplatní a položka nemá barevné pozadí.

Barevné pozadí má vždy nejvýše jedna položka prohybu. Odchylka a neshoda se zvýrazňují pouze barvou pozadí, bez proužku; žlutý proužek vlevo patří pouze položkám tvrdosti. Po zadání měření po rovnání zmizí pozadí položky po TZ; pokud měření po rovnání vyhovuje, nezvýrazní se ani jedna položka. Po smazání všech hodnot po rovnání se znovu posuzuje měření po TZ.

## 4. Výstupní kontrola a rozhodnutí

Vyplňte:

- **Čistota** a **Uložení**: nezadáno, OK nebo NOK.
- **Počet křivých 1. měření / 2. měření**: ručně evidované počty křivých vrutů z kontrolního vzorku. U pole je velikost vzorku nastavená pro zákazníka. Tyto údaje nenahrazují počítání překročených jednotlivých hodnot pro omezení uvolnění.
- **Uvolnění**: nerozhodnuto (`--------`), Neshoda, Uvolněno nebo Uvolněno QS s odchylkou. Při překročení povoleného počtu křivých vrutů se nabídka omezí podle tabulky výše.
- **Poznámka**: vysvětlení výsledku nebo provozní informace.

**Důvody neshody** jsou viditelné při **Uvolněno**, **Uvolněno QS s odchylkou** a **Neshoda**. Skryté jsou pouze při nerozhodnutém uvolnění, i když z dřívějška zůstal uložený důvod. Samotné skrytí ručně zadané důvody nemaže.

**Křivost a Čistota jsou automatické důvody a nelze je měnit ručně.** Křivost je zaškrtnutá při červeném nebo oranžovém celkovém výsledku rozhodující fáze prohybu podle tabulky výše. Při vyhovujícím výsledku nebo chybějícím měření je odškrtnutá. Čistota je zaškrtnutá pouze při **Čistota = NOK**; při OK nebo nezadáno je odškrtnutá. Čistota NOK dovoluje uložit pouze **Neshodu**, i když by samotný oranžový prohyb dovoloval uvolnění QS s odchylkou. Při souběhu jsou zaškrtnuté oba důvody.

**Uložení = NOK** také dovoluje uložit pouze **Neshodu**. Automaticky zaškrtne a zamkne důvod **Jiné**, proto je povinná poznámka s popisem problému uložení. Platí to i při oranžovém prohybu a souběhu s čistotou NOK. Při Uložení OK nebo nezadáno se další omezení nepřidává. Po změně NOK na OK nebo nezadáno se Jiné zpřístupní pro ruční úpravu. Pokud je poznámka prázdná nebo obsahuje jen mezery, Jiné se automaticky odškrtne. S vyplněnou poznámkou zůstane zaškrtnuté, protože může popisovat i jiný problém. Samotné pozdější vymazání poznámky Jiné neodškrtává; rozhodující je přechod Uložení z NOK. Při zbývající Neshodě či uvolnění QS musí stále existovat alespoň jeden důvod.

Při **Neshodě** nebo **Uvolněno QS s odchylkou** musí být vybraný alespoň jeden důvod, automatický nebo ruční. Ostatní důvody (krut, ohyb, tvrdost, vrstva, pomíchané vruty, chyba v procesu a Jiné mimo případ Uložení NOK) lze měnit ručně. U **Jiné** je povinné upřesnění v poznámce. Při **Uvolněno** se všechny důvody odškrtnou a zamknou; při uložení se odstraní také z aktuální kontroly. Poznámka se automaticky nemaže. Starší snapshoty a historie zůstávají zachované.

Při omezení kvůli prohybu formulář zobrazí rozhodující fázi, počet překročených hodnot a povolený počet křivých. V editovatelném formuláři nastaví automatické důvody; pokud dosavadní rozhodnutí není přípustné, předvyplní první povolenou volbu uvolnění. Samotné otevření formuláře tyto změny neukládá. Při pouhém prohlížení bez možnosti editace se zobrazí skutečně uložené rozhodnutí a důvody.

Pokud chybí standardní mez prohybu nebo nastavení maximálního povoleného počtu křivých ve vzorku, zobrazí se upozornění, co není nastavené. Křivost pak nelze automaticky vyhodnotit, důvod zůstává odškrtnutý a uvolnění se podle prohybu neomezuje. **Tento stav neznamená potvrzení vyhovujícího prohybu.** Maximální počet se nastavuje u zákazníka, pravidla standardních mezí jsou popsaná výše.

Při uložení server znovu vyhodnotí aktuálně uložená měření a zaslaný výsledek čistoty a uložení. Automatické důvody přepočítá bez ohledu na zaslané hodnoty políček a nepovolené uvolnění odmítne. Při Uložení NOK vynutí Jiné i povinnou poznámku. Při Uvolněno vymaže všechny důvody i při pokusu odeslat je zaškrtnuté. Uložení samotných naměřených hodnot toto omezení neblokuje a automaticky nepřepisuje dříve uložené rozhodnutí o uvolnění; následně uložte také kontrolu bedny.

Klikněte na **Uložit kontrolu bedny**. U rozhodnutí se eviduje, kdo a kdy stav uvolnění změnil; návrat na nerozhodnuto tyto aktuální údaje vymaže, historie zůstává.

## 5. Potvrzení výrobního stavu

Po prvním uložení výsledků u bedny ve stavu **Zakaleno** použijte **Dokončit kontrolu bedny**:

1. Otevřete navazující formulář.
2. Ověřte zobrazené automaticky vypočtené stavy rovnání a tryskání. Ručně se zde nevybírají.
3. Potvrďte změnu. Bedna přejde do stavu **Zkontrolováno** a současně se uloží vypočtené technologické stavy.

Dokončení kontroly je dostupné pouze pro nepozastavené bedny ve stavu **Zakaleno** s oprávněním `orders.mark_bedna_zkontrolovano`. U již zkontrolované bedny se tlačítko ani blokující panel nezobrazují; původní samostatná akce **Upravit stav rovnání a tryskání** se již nepoužívá. Ani přímé otevření nebo odeslání původní potvrzovací adresy u zkontrolované bedny stavy nezmění.

Ve výstupní kontrole musí být předem uložené tyto údaje:

- **Čistota** a **Uložení**: obě pole musí mít vybranou hodnotu **OK nebo NOK**; výchozí nezadáno nestačí.
- **Uvolnění**: **Uvolněno, Uvolněno QS s odchylkou nebo Neshoda**; výchozí nerozhodnuto nestačí.
- **Ohyb a Krut**: u každé bedny musí být uložená alespoň jedna hodnota každé z obou zkoušek. Chybějící měření hlásí panel jako **Změřte a uložte Ohyb.** nebo **Změřte a uložte Krut.** Rozpracované hodnoty ani měření jiné bedny nestačí. Tato podmínka ověřuje přítomnost měření, nikoli splnění minimálního počtu hodnot či jejich porovnání s předpisem. Platí také při QS s odchylkou nebo Neshodě, při opravě zkontrolované bedny a nastavení Zkontrolováno v adminu.
- **Prohyb po TZ**: alespoň jedna uložená hodnota u každé bedny, i když už existuje měření po rovnání. U zákazníka musí být nastavený **maximální povolený počet křivých ve vzorku** (nula je platná) a pro zákazníka musí existovat pravidlo **standardního maxima prohybu**. **QS maximum je volitelné**; bez něj není oranžová odchylka. Tato podmínka neověřuje úplnost předepsaného počtu hodnot vzorku.
- Při vybraném důvodu neshody **Křivost** také **Počet křivých 1. měření i Počet křivých 2. měření**. Obě pole musí být vyplněná; **nula je přípustná vyplněná hodnota**. Výjimkou je **oranžově zvýrazněná položka Prohyb po TZ**: oba počty mohou zůstat prázdné a pro označení Zkontrolováno není nutné rovnání ani měření po rovnání. Výjimka platí pro všechny zákazníky s příslušnou QS mezí, při kterémkoli uloženém rozhodnutí uvedeném výše a bez ohledu na další důvody neshody. Čistota a Uložení zůstávají povinné. Bez důvodu Křivost se vyplnění počtů pro tuto akci nevyžaduje.

Pokud akce není dostupná, na jejím místě se zobrazí neaktivní informační panel ve tvaru tlačítka s konkrétními důvody. Uvede chybějící oprávnění, pozastavení nebo nepovolený výrobní stav. Pokud tyto překážky nejsou, vypíše chybějící uloženou kontrolu nebo jednotlivé údaje: Čistotu, Uložení, rozhodnutí o uvolnění a případně první či druhý počet křivých. Nula je vyplněná hodnota a oranžový prohyb po TZ vyplnění počtů nevyžaduje. Podmínky se posuzují podle uložených údajů, nikoli rozpracovaných změn ve formuláři. Přímé otevření adresy ani odeslání akce podmínku neobejde: aplikace vrátí uživatele do kontroly bedny s vysvětlením, co má doplnit. Podmínky se znovu ověřují před změnou stavu. Rozpracovanou kontrolu s těmito chybějícími údaji lze dál ukládat, ale nejprve je nutné údaje doplnit a uložit, aby se označení Zkontrolováno zpřístupnilo.

Pokud chybí oba počty křivých, panel je sloučí do jediného řádku: **Při důvodu Křivost doplňte a uložte oba počty křivých.** Při chybějícím jediném počtu uvede konkrétní měření.

Panel uvádí také chybějící měření po TZ, standardní maximum nebo nastavení povoleného počtu křivých. Bez těchto podkladů se přechod do Zkontrolováno neprovede ani při vyplněné Čistotě, Uložení a uvolnění.

Před dokončením se ověřuje i soulad uloženého uvolnění a důvodů s aktuálním měřením a nastavením zákazníka. Pokud se například zpřísní povolený počet křivých a původní Uvolněno už neodpovídá výsledku, nejprve znovu uložte výstupní kontrolu. Samotné předvyplnění správného rozhodnutí na stránce není uložením. Zkontroluje se také povinný důvod při Neshodě/QS, poznámka pro Jiné a automatické důvody Křivost a Čistota.

Hromadná akce pro označení beden jako Zkontrolováno byla odstraněna. Nastavení stavu Zkontrolováno v detailu adminu, inline zakázky i editaci seznamu vyžaduje stejné úplné a aktuální podklady jako dokončení kontroly; nepotvrzená měření nelze tímto zápisem potvrdit. Při přechodu do Zkontrolováno admin také nastaví vypočtené Rovnání a Tryskání.

Oprava již zkontrolované bedny musí splnit stejnou úplnost: nelze vymazat Uložení, Uvolnění ani povinné počty křivých a ponechat kontrolu jako potvrzenou. Neúplný návrh se neuloží a případné čekající potvrzení měření zůstane aktivní. Výjimka pro oranžový prohyb po TZ bez počtů křivých zůstává platná.

**Tryskání se nastaví podle uložené Čistoty:**

| Čistota | Dosavadní Tryskání | Nové Tryskání |
| --- | --- | --- |
| NOK | Libovolné | Špinavá |
| OK | Špinavá nebo Otryskaná | Otryskaná |
| OK | Nezadáno nebo Čistá | Čistá |

**Rovnání se nastaví podle rozhodujícího uloženého měření:**

| Rozhodující měření | Výsledek celého vzorku | Nové Rovnání |
| --- | --- | --- |
| Prohyb po rovnání, pokud existuje | Vyhovuje standardnímu maximu | Vyrovnaná |
| Prohyb po rovnání, pokud existuje | Nevyhovuje standardnímu maximu | Křivá |
| Jinak Prohyb po TZ | Vyhovuje nebo oranžová QS odchylka | Rovná |
| Jinak Prohyb po TZ | Nevyhovuje (červená) | Křivá |

Rozhoduje výsledek celého vzorku s ohledem na povolený počet křivých, ne barva jednotlivé hodnoty. Hodnota rovná maximu je přípustná; po rovnání se QS maximum nepoužívá. Prohyb po koulení se pro tuto automatiku nevyhodnocuje. Používají se všechna aktuálně uložená měření příslušné fáze; opakované tepelné cykly se samostatně nerozlišují.

U bedny ve stavu **Zkontrolováno** se podle stejných tabulek automaticky přepočítají Rovnání a Tryskání při každém úspěšném **Uložit kontrolu bedny**. Platí i při nezměněném rozhodnutí o uvolnění nebo nezměněném formuláři po opravě měření. Například vyhovující měření po rovnání nastaví **Vyrovnaná** a změna Čistoty z NOK na OK u dosavadní Špinavé nastaví **Otryskaná**. Zhoršení výsledků se projeví opačně: nevyhovující prohyb nastaví **Křivá**, Čistota NOK **Špinavá**. Rozhodují výsledky měření a čistoty, nikoli samotná volba Uvolněno nebo Neshoda.

Výpočet používá právě odeslanou Čistotu a aktuálně uložená měření pod zámkem bedny. Zaslané hodnoty Rovnání a Tryskání nepřebírá. Pokud chybí měření po TZ, standardní maximum, povolený počet křivých nebo vyplněná Čistota, oprava výstupní kontroly se neuloží a formulář uvede důvod. Kontrola, případný snapshot neshody a změny technologických stavů se uloží společně v jedné transakci. Změna stavů má historii s autorem; nezměněné stavy nevytvářejí další záznam historie bedny. Zpráva po uložení vypíše změněné stavy. Výrobní stav zůstává **Zkontrolováno** a zinkování se nemění. Hromadné akce v administraci tuto automatiku nepoužívají.

Samotné **uložení měření** Rovnání ani Tryskání nepřepočítá. Pokud se u zkontrolované bedny změní jejich vypočtený stav nebo vyhodnocení kontroly, upozornění vyžádá uložení výstupní kontroly. U bedny Zakaleno se technologické stavy poprvé nastaví až při dokončení kontroly. Samotný zápis měření výrobní stav nemění; od K expedici zůstávají kontrola a měření pouze pro čtení.

Bednu s uloženým **Uvolnění = Neshoda** nelze označit K expedici ani expedovat. Zkontrolováno s Neshodou zůstává přípustné: znamená provedenou kontrolu, ale další postup je potřeba vyřešit před expedicí. Samotný zákaz Neshody nevyžaduje existenci kontroly ani výslovné uvolnění; jiné podmínky pro označení Zkontrolováno uvedené výše tím nejsou dotčeny.

Přípravu k expedici a expedici blokuje také příznak čekajícího potvrzení po změně měření. Platí i při původně uloženém Uvolněno a i přes admin či jiné okno. Nejprve úspěšně uložte úplnou výstupní kontrolu; samotná změna výrobního stavu čekající potvrzení nezruší.

### Neuložené změny a potvrzení po měření

Hodnoty výstupní kontroly odlišné od databáze mají červený rámeček a popisek. Platí to pro ruční změny Čistoty, Uložení, počtů, poznámky a důvodů i pro automaticky změněné uvolnění a zamčené důvody neshody. Porovnává se skutečný stav v databázi před automatickým předvyplněním; červené označení tak může vzniknout už při návratu z měření. Při vrácení na uloženou hodnotu označení příslušného pole zmizí. Červené označení změny formuláře je odlišné od vyhodnocení nevyhovujících naměřených hodnot.

Nad obsahem se zobrazí upozornění na neuložené změny a tlačítko uložení se zvýrazní červeně. Při zápisu měření se porovná vyhodnocení před změnou a po ní: automatické důvody, přípustné uvolnění a u zkontrolované bedny výsledné technologické stavy. Pouze změna tohoto vyhodnocení nebo nesoulad s uloženým výsledkem nastaví v databázi příznak **Měření čekají na potvrzení kontroly**. Změna vrstvy, Ohybu, Krutu, tvrdostí či prohybu po koulení a oprava hodnoty prohybu se stejným výsledkem samy další potvrzení nevyžadují. U zkontrolované bedny se hlídá také odstranění poslední hodnoty povinné zkoušky.

Doplnění Ohybu a Krutu u bedny Zakaleno může rovnou zpřístupnit **Dokončit kontrolu bedny**, pokud už je výstupní kontrola uložená a ostatní podmínky jsou splněné. Nezměněnou kontrolu není nutné znovu ukládat; dokončení vše ověří z aktuálních dat a poprvé nastaví technologické stavy. Naproti tomu změna přípustného uvolnění nebo přidání vyhovujícího měření po rovnání u již zkontrolované bedny vyžaduje potvrzení, i když se nezmění žádné ruční pole kontroly.

Již vzniklé čekání na potvrzení se zachová při obnovení stránky, otevření na jiném počítači, zápisu nesouvisející zkoušky i uložení nezměněných hodnot. Zruší je až úspěšné uložení výstupní kontroly. U bedny Zakaleno blokuje dokončení kontroly. Stejné porovnání bude možné rozšířit o další zkoušky, až se začnou automaticky vyhodnocovat jejich limity.

U bedny **Zkontrolováno** jsou při neuložených změnách nebo čekajícím potvrzení blokované běžné odkazy na další bednu, přehled a jiné stránky. Uložte výstupní kontrolu; po úspěchu se ve stejné transakci uloží výsledky, případný snapshot neshody, Rovnání a Tryskání a zruší čekající potvrzení. Při chybě validace, souběžné úpravě nebo neúspěšném zápisu upozornění zůstane. Již uložená měření se tímto krokem znovu nezapisují.

Na **měření stejné bedny** lze přejít i během rozpracované kontroly. Její rozepsané hodnoty se uchovají v rámci karty prohlížeče odděleně pro uživatele a bednu; po návratu se obnoví a automatické důvody se přepočítají podle aktuálních měření. Zachová se také rozepsané uvolnění, i když původní uložená Čistota nebo Uložení NOK dovolovaly jen Neshodu. Nabídka se nejprve obnoví podle rozepsaných údajů; pokud mezitím vznikl nález, který zvolenému uvolnění brání, použije se povolená volba podle aktuálního vyhodnocení. Pokud prohlížeč uchování rozepsaných hodnot neumožňuje, je nejprve nutné kontrolu uložit. Na stránce měření je před návratem potřeba uložit nově zadané či změněné hodnoty, případně je vrátit na původní. Změna pouze formátu desetinného čísla, prázdný nový řádek nebo smazaný neuložený řádek se za změnu nepovažuje.

Pokud mezitím jiný uživatel uložil jinou kontrolu, rozepsaná kopie se neuloží přes novější data: zobrazí se konflikt. Odkaz či tlačítko **Načíst aktuální údaje** umožní po výslovném potvrzení rozepsanou kopii zahodit a načíst stav z databáze. První vytvoření dosud neexistující prázdné kontroly při vlastním zápisu měření se za konflikt nepovažuje, pokud všechny původní hodnoty zůstaly stejné.

U bedny **Zakaleno** se změny také zvýrazňují, odchod však pouze vyvolá standardní upozornění prohlížeče. Při zavření nebo obnovení karty a použití tlačítek prohlížeče lze odchod pouze varovat; vynucené zavření nebo pád nelze zablokovat. Příznak čekajícího potvrzení měření zůstává v databázi, rozepsané ruční hodnoty jsou uložené jen v rámci dané karty prohlížeče. Samotné otevření stránky nic nezapisuje do databáze.

Technický příznak přidává migrace `0245_kontrola_vyzaduje_potvrzeni`. Starší kontroly dostanou výchozí hodnotu bez čekajícího potvrzení; historie ani snapshoty se nepřepočítávají. Změna příznaku při měření nepřidává záznam výsledků do historie kontroly, vlastní měření mají samostatnou historii.

## 6. Přehled neshod, audit a tisk

Záhlaví sloupce zákazníka v PDF je dvouřádkové: nahoře **Zákazník /**, pod ním celý popis **Rozměr · závit · hlava** bez dalšího zalomení.

V PDF přehledu neshod má sloupec **Zákazník / Rozměr · závit · hlava** v prvním řádku název zákazníka a ve druhém rozměr, označení závitu a typ hlavy oddělené tečkami, například **Ø10 × 100 · SG · SK**. Artikl zakázky se netiskne. Délka se zobrazuje bez koncových desetinných nul (například 100 místo 100,0); nenulová desetinná část zůstává. **SG** znamená částečný závit, **VG** celozávit; údaje se přebírají z aktuální zakázky.

**Přehled neshod** (`/prehled-neshod/`) ukazuje bedny s aktuálním rozhodnutím Neshoda, důvody, poznámku a autora i datum rozhodnutí. Filtruje se podle zákazníka, důvodu a dne. Po změně uvolnění na jinou hodnotu bedna z přehledu zmizí; starší rozhodnutí zůstává v historii.

**Evidence neshod v administraci** (`/admin/orders/zaznamneshody/`) uchovává společný snapshot všech důvodů a měření při prvním uložení Neshody, novém přechodu do Neshody nebo přidání důvodu během trvající Neshody. Kopíruje identifikaci, důvody, poznámku, všechny uložené hodnoty měření a tehdejší požadavky i limity. Odebrání důvodu, samotná úprava poznámky či měření nový snapshot nezakládá. Starší snapshoty se nepřepisují a uvolnění bedny je z evidence neodstraní. Evidence se otevírá v administraci nebo z nabídky přehledů; pod formulářem kontroly se odkazy na jednotlivé snapshoty nezobrazují. Podrobnosti popisuje [Evidence neshod](manual_evidence_neshod.md).

Administrace **Kontroly beden** a **Měření beden** slouží k prohlížení záznamů a historie. Údaje se upravují provozním formulářem, na který vede odkaz v poli **Formulář kontroly bedny**; detail měření má obdobný odkaz v poli **Formulář měření zkoušky**.

Z administrace beden či zakázek lze pro všechny zákazníky použít akci **Vytisknout vyplněné KKK**, případně variantu pro zakázky. Výběr musí patřit jednomu zákazníkovi a každá bedna musí mít uloženou kontrolu. V administraci kamionů je tisk vyplněných KKK dostupný pouze pro kamion výdej; bedny bez kontroly se přeskočí s varováním. Prázdné KKK mají vlastní akci a zákaznické šablony. Před tiskem ověřte měření a uvolnění.

Vyplněné KKK používají jednu společnou šablonu. Hlavní popisy jsou vždy česky, pomocné popisy se řídí polem **Zkratka státu** zákazníka: **D** a **A** přidají němčinu, **I** italštinu, **CZ** zobrazí pouze češtinu. U nevyplněné nebo neznámé zkratky státu se zobrazí pouze čeština. Mezery kolem zkratky a velikost písmen výběr jazyka neovlivňují. Vedle českého stavu uvolnění se za lomítkem zobrazí pomocný překlad stavů Uvolněno, Uvolněno QS s odchylkou a Neshoda. Nerozhodnutý stav pomocný překlad nemá. Za polem OTRYSKANÁ? je pole VYROVNANÁ?: pouze stav Vyrovnaná se zobrazuje jako fajfka v zeleném poli, ostatní stavy rovnání jako pomlčka v šedém poli.

U zákazníka **SPX** se v poli **Bedna** pod zákaznickým a interním číslem bedny a nad pořadím / počtem beden v zakázce tiskne výrobní zakázka bedny na samostatném řádku s pouze německým popiskem **Beleg-Nr.** Pokud výrobní zakázka není vyplněná, řádek se nezobrazí.

Minimální počty zapsaných hodnot a název protokolu se nastavují v detailu zákazníka v části **Kontrola kvality**: **Minimum hodnot mechanických zkoušek**, **Minimum hodnot prohybu**, **Minimum hodnot tvrdosti** a **Název protokolu**. Minimum platí pro každou příslušnou zkoušku zvlášť: ohyb a krut, prováděné fáze prohybu, povrch a jádro. Prázdné minimum znamená, že se popisek netiskne; vyplněné minimum musí být alespoň 1. Popisky se zobrazují česky i ve zvoleném pomocném jazyce. Celkový počet vrutů odebraných z bedny pro kontrolu prohybu je samostatný údaj a může být vyšší než minimum hodnot zapisovaných do KKK. Nastavení minima zatím neblokuje uložení měření, uvolnění ani tisk neúplné karty.

Název protokolu se tiskne v záhlaví. Více označení zadejte na samostatné řádky; při nevyplnění se použije HPM - F XXX. Výchozí nastavení stávajících zákazníků přenáší datová migrace z původního slovníku. Další změny se provádějí u zákazníka a ukládají se do jeho historie.

U mechanických zkoušek a tvrdosti se minimum na kartě uvádí jako počet vzorků, například **Min. 5 vzorků**. Prohyb rozlišuje minimum zapisovaných hodnot a celkový počet odebraných vrutů, například **Min. 5 hodnot z 25 vzorků**. Oba údaje se čtou z nastavení zákazníka. Pokud celkový počet odebraných vrutů není vyplněný, tiskne se pouze **Min. 5 hodnot**. Stejné rozlišení používají i pomocné překlady.

Vyplněná karta tiskne nejvýše prvních 10 hodnot jednotlivých zkoušek bez ohledu na nastavené minimum. Nastavení minima ovlivňuje pouze popisek požadavku. Pro vrstvu se použije první uložená hodnota. Úplný seznam měření je dostupný v aplikaci. Vyplněná KKK nezobrazuje sloupec Po koulení ani jeho naměřené hodnoty a kontrolující; toto měření slouží pouze interně a zůstává uložené v aplikaci. Pokud bedna podle zákaznických pravidel není určena k měření tvrdosti a povrchu a nemá atypický průběh, karta místo minimálního počtu hodnot tvrdosti i předpisu pro povrch a jádro vytiskne pomlčku (—). U atypické bedny se požadavky a nastavený rozsah tvrdostí tisknou i mimo běžný výběr vzorkování.

U zákazníka **SPX** se při rozhodnutí **Uvolněno** nebo **Uvolněno QS s odchylkou** ve sloupci **Krut** místo každé zapsané naměřené hodnoty tiskne **OK**. Prázdná políčka zůstávají prázdná. Při **Neshodě** nebo nerozhodnutém uvolnění se tisknou naměřené hodnoty. Jde pouze o zobrazení na vyplněné KKK; původní měření zůstávají uložená v aplikaci. Zobrazení OK zatím vychází z rozhodnutí o uvolnění, nikoli z porovnání s limitem předpisu.

Pole **Uvolnění** má ve vyplněné KKK zelené pozadí pro **Uvolněno** i **Uvolněno QS s odchylkou** a červené pozadí pro **Neshodu**. Interní přehled kontroly nadále označuje uvolnění QS s odchylkou oranžově.

Ve sloupci s pořadím vzorků 1–10 mají liché řádky bílé pozadí a sudé řádky světle šedé pozadí.

## 7. Oprávnění a souběžné změny

| Úkol | Potřebné oprávnění |
| --- | --- |
| Zobrazení kontroly | `orders.view_bedna` nebo `orders.mark_bedna_zkontrolovano` |
| Zápis kontroly a měření | `orders.mark_bedna_zkontrolovano`; pouze ve stavech Zakaleno a Zkontrolováno |
| Zápis u pozastavené bedny | Navíc `orders.change_pozastavena_bedna` |
| Zápis u bedny K expedici nebo Expedováno | Není povolen ani se zvláštními oprávněními |

Oprávnění k úpravě pozastavené bedny umožňuje zápis výsledků, ale její označení jako Zkontrolováno přes tento postup zůstává blokované.

Ve stavech **K expedici a Expedováno** jsou kontrola i naměřené hodnoty uzamčené. Uložené údaje lze nadále prohlížet v přehledu kontroly bedny, ale nelze je přidávat, měnit ani mazat; neobchází to ani `orders.change_expedovana_bedna` nebo oprávnění správce. Přímé otevření formuláře pro zápis měření ani odeslání dříve otevřeného formuláře změnu nepovolí. Podmínky se znovu ověřují při ukládání.

Pro opravu bedny **K expedici** ji nejprve vraťte na **Zkontrolováno**. U **expedované bedny** nejprve vraťte zakázku z expedice (bedny přejdou na K expedici) a poté příslušnou bednu na Zkontrolováno. Opravte kontrolu a měření a před novým označením K expedici vyřešte případnou Neshodu. Pokud starší data již obsahují expedovanou bednu s Neshodou, návrat zakázky na K expedici se odmítne; tuto nekonzistenci musí individuálně vyřešit správce.

Ve stavech Nepřijato, Přijato, K navezení, Navezeno a Ve zpracování lze kontrolu rovněž pouze zobrazit; zápis není povolen ani se zvláštními oprávněními pro expedované či pozastavené bedny.

Pokud jiný uživatel mezitím změnil kontrolu nebo měření, systém odmítne přepsat jeho údaje. Použijte **Načíst aktuální údaje / hodnoty**, zkontrolujte změny a zadejte úpravu znovu.

## 8. Nejčastější problémy

- **Kontrola je jen pro čtení:** ověřte oprávnění, pozastavení a expedici bedny.
- **Neshoda nejde uložit:** vyberte důvod; u Jiné doplňte poznámku.
- **Nelze vybrat Uvolněno nebo nerozhodnuto:** zkontrolujte upozornění na překročený počet křivých vrutů a výsledky čistoty a uložení. Přípustné volby určuje měření po rovnání, případně po TZ; Čistota NOK i Uložení NOK vždy dovolují pouze Neshodu. Křivost a Čistota se nastavují automaticky, při Uložení NOK také Jiné s povinnou poznámkou.
- **Po rovnání zmizelo červené/oranžové pozadí u prohybu po TZ:** posouzení přešlo na měření po rovnání. Jednotlivé starší hodnoty si své barevné označení ponechávají.
- **Chybí požadavek zkoušky:** zkontrolujte předpis zakázky; prázdný požadavek neznamená automatické vyhovění zkoušky.
- **Místo tlačítka Dokončit kontrolu bedny je vysvětlení blokace:** postupujte podle vypsaných důvodů. Ověřte stav Zakaleno, pozastavení, oprávnění a uloženou Čistotu, Uložení a rozhodnutí o Uvolnění. Při důvodu Křivost musí být uložené také oba počty křivých; prázdné pole nestačí, nula ano. Oba počty se nevyžadují, pokud je položka Prohyb po TZ oranžová; oranžový prohyb po rovnání tuto výjimku neposkytuje. U již zkontrolované bedny se toto tlačítko nezobrazuje, stavy aktualizuje uložení výstupní kontroly.
- **Bedna stále čeká v přehledu kontroly:** uložení výsledků ji nepřepne ze stavu Zakaleno; potvrďte výrobní stav.
- **Vyplněná KKK nejde vytisknout:** ověřte výběr jednoho zákazníka, uloženou kontrolu u každé bedny, hmotnost a předpis zakázky. U kamionu musí jít o jeden kamion výdej.
- **Chybí pomocné popisy na vyplněné KKK:** ověřte pole Zkratka státu zákazníka; pro CZ, nevyplněnou nebo neznámou zkratku se pomocné popisy netisknou.

## 9. Související dokumentace a kód

[Bedny](manual_bedna.md) · [Rychlé založení šarže](manual_rychle_zalozeni_sarze.md) · [Zakázky](manual_zakazka.md) · [README](../README.md)

[Provozní tahák](provozni_tahak.md) · [Průchod šarže výrobou](manual_pruchod_sarze.md)

Implementace: `orders/models.py` (`Zakaznik`, `KontrolaBedny`, `MereniBedny`, `Bedna.limity_prohybu`, `Bedna.limity_prohybu_pro_zkousku`), `orders/forms.py` (`KontrolaBednyForm`, `MereniBednyFormSet`), `orders/views.py` (`bedna_kontrola_view`, `bedna_mereni_zkousky_view`, `bedna_scan_zkontrolovano_view`), `orders/services/mereni_bedny_service.py` a `orders/services/filled_quality_cards_service.py`. Pomocné překlady vyplněných KKK jsou ve slovnících `HELPER_LABELS` v `orders/quality_card_labels.py`; minimální počty zapsaných hodnot a názvy protokolů jsou uložené v modelu `Zakaznik` v polích `min_hodnot_mechanicke`, `min_hodnot_prohyb`, `min_hodnot_tvrdost` a `nazev_protokolu`.
