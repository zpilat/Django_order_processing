# Role a přidělování oprávnění

Akce **Převést na atypický průběh, označit zkontrolováno s neshodou** vyžaduje současně `orders.change_bedna` a `orders.mark_bedna_zkontrolovano`. Nové oprávnění ani automatické změny skupin nezavádí. Pracuje pouze s nepozastavenými přijatými bednami bez dosavadní kontroly a vyžaduje potvrzení účinků akce.

Původní reklamační akce Přijato → Zakaleno je odstraněná. Historické oprávnění `orders.mark_bedna_zakaleno` může zůstat ve skupinách uvedených v tomto snímku, ale odstraněnou akci nezpřístupňuje. Pro skenové potvrzení Zakaleno nadále slouží samostatné `orders.scan_mark_bedna_zakaleno`.

Návod slouží správci uživatelů při nástupu pracovníka, změně jeho úkolů a odebrání přístupu. Popisuje **skutečné skupiny a jejich přidělená oprávnění načtené 9. listopadu 2026 z vývojové PostgreSQL `orders_dev` na lokálním portu 5433 po obnově z produkčního dumpu `orders_prod_auto_20261109_080001.dump`**. Produkce se při aktualizaci návodu samostatně nečetla. Jde o snímek nastavení, který se po změně skupin neaktualizuje automaticky. Žádné účty, skupiny ani jejich oprávnění nebyly při přípravě dokumentace měněny.

## 1. Účet, administrace a oprávnění

| Nastavení | Význam |
| --- | --- |
| Aktivní (`is_active`) | Účet může používat běžné přihlášení a oprávnění. Při ukončení přístupu jej deaktivujte. |
| Staff (`is_staff`, v administraci příznak přístupu do administrace) | Umožní vstup do `/admin/`. Samo nepřidělí právo měnit zakázky, bedny ani jiné agendy. |
| Superuser (`is_superuser`) | Aktivní účet získává všechna oprávnění. Pro běžné provozní role tento příznak nezapínejte. |
| Skupiny | Účet získá oprávnění všech přiřazených skupin. Hodí se pro opakovaně používané pracovní role. |
| Přímá oprávnění uživatele | Přidávají se ke skupinám; při změně role je prověřte samostatně. |

Oprávnění se **sčítají**. Odebrání jedné skupiny nepomůže, pokud stejnou možnost ponechává jiná skupina, přímé oprávnění nebo příznak superuser. Skupina bez oprávnění nic nezakazuje.

Členství ve skupině může mít také účinek přímo v kódu, i když skupina nemá přiřazená oprávnění. Takto funguje **Rozšířený filtr TZ**: podle přesného názvu skupiny rozšiřuje nabídku filtru v deníku beden, viz kapitola 2.

Přihlášený pracovník bez staff může používat provozní obrazovky podle kontroly dané operace. Staff se po vstupu na hlavní stránku přesměruje do administrace; provozní rozcestník může otevřít přes `/provozni-prehledy/`. Čtení návodů v aplikaci vyžaduje aktivní staff účet, ale nepotřebuje práva k jednotlivým agendám.

Oprávnění `view_<model>` není plošný zákaz přístupu ke všem datům mimo daný model. Některé provozní přehledy a detaily vyžadují pouze přihlášení, jiné konkrétní právo. Skupiny níže jsou rozdělením pracovních úkolů; nepředstavují oddělení dat podle zákazníků nebo pracovišť.

Pilotní akce **Exportovat podklady pro OMEGU (SPX, kalení)** vyžaduje aktivní staff účet a možnost zobrazit kamion (`orders.view_kamion` nebo obecné `orders.change_kamion`). Pouze čte údaje a ceny; neprovádí expedici ani změny fakturace. Postup je v [manuálu exportu OMEGA](manual_export_omega.md). Nová oprávnění ani automatické změny skupin nezavádí.

## 2. Matice pracovních rolí podle skupin v databázi

V databázi je následujících **9 skupin**. Tabulka shrnuje jejich skutečná práva, nikoli doporučené doplnění. Počet zahrnuje všechna přiřazená oprávnění skupiny, včetně zbylých práv odstraněných modelů; přesný soupis je v [kapitole 8](#8-přesný-soupis-oprávnění-skupin).

| Skupina v databázi | Obrazovky a úkoly podle přidělených práv | Přidělená oprávnění a hranice |
| --- | --- | --- |
| Kontrola | Provozní kontrola beden, měření, rozhodnutí o uvolnění, dokončení kontroly; kontrolorské stavy šarží s položkami mimo DB; souhrnná měření zakázek pro výdej | **9 práv**. view pro bedny, kamiony, zakázky, šarže, kroky a deník; `mark_bedna_zkontrolovano`, `change_stav_sarze_kontrolor`, `change_mereni_zakazky`. Nemá obecné change_bedna ani view_zaznamneshody. |
| Manager | Široká správa provozních agend, číselníků, účtů a skupin, také opravy a mazání v rozsahu přidělených práv; čtení historie beden a Evidence neshod | **96 práv**, včetně všech čtyř standardních práv pro vyjmenované provozní modely a auth modely user, group a permission. Má plný i omezený přesun šarží, kontrolorská a operátorská stavová práva, výjimky pro nepřijaté, pozastavené a expedované bedny a `view_historicalbedna` i `view_zaznamneshody`. Není to automaticky superuser ani skupina se všemi budoucími právy. |
| Mistr | Provozní obrazovky i administrace v rozsahu přidělených práv: rychlé založení šarže, patra, úpravy kroků a hlavičky, průvodka, plné přesuny, navezení a Zakaleno přes sken; operátorské stavy šarží s položkami mimo DB | **16 práv**, přesně shodných se skupinou Operátor. Účet má `is_staff=True`, takže může využívat i administrační seznamy, formuláře a akce podle těchto práv. Má `can_move_sarze`, `mark_bedna_navezeno`, `scan_mark_bedna_zakaleno` a mazání posledního patra. Nemá mark_bedna_zkontrolovano ani change_bedna. |
| Náhled | Čtení beden, zakázek, kamionů, šarží, kroků, deníku, rozpracovanosti, zařízení a vybraných číselníků | **15 práv**, všechna view. Má `view_zarizeni`, nemá práva přidávání, změny ani mazání, `view_predpis` ani `view_zaznamneshody`. Počet zahrnuje také zbylé `view_sarzebedna` pro odstraněný model. Některé provozní stránky mají vlastní podmínky přístupu, viz kapitola 1. |
| Operátor | Provozní obrazovky: nakládání, kroky, plné přesuny, navezení a Zakaleno přes sken | **16 práv**, přesně shodných se skupinou Mistr. Účet má `is_staff=False`, proto nemůže do administrace ani používat její seznamy, formuláře, akce a návody v aplikaci. Provozní operace zůstávají dostupné podle přidělených práv a stavu záznamů. |
| Plánování výroby a rovnání | Čtení provozních dat, změny beden včetně plánování a stavů rovnání v dostupných formulářích, poznámka nepřijaté bedny a práce s notifikacemi | **13 práv**. Změnová práva: `change_bedna`, `change_notification`, `change_poznamka_neprijata_bedna`; dále view pro vyjmenované agendy a `add_historicalsarzekrok`. Nemá can_move_sarze, can_move_sarze_limited, scan_mark_bedna_zakaleno ani mark_bedna_zkontrolovano. Obecné change_bedna zpřístupňuje více operací než pouze rovnání. |
| Předák | Založení šarže, zadání a úprava pater, hlavičky a kroků, Zakaleno přes sken, operátorské stavy šarží s položkami mimo DB; omezené přesuny | **14 práv**. Oproti Mistrovi/Operátorovi má `can_move_sarze_limited` místo plného přesunu a nemá mark_bedna_navezeno ani delete_sarzekrokbedna_patro. Omezený přesun nyní nabízí pouze typ Tryskač. |
| Příjem - Expedice | Příjem a importy, zadávání beden a zakázek, expedice, doklady, změny zákazníků a odběratelů, kapacity pozic a chemický filtr/export | **34 práv**. Má add/change pro bedny, kamiony, zakázky, zákazníky a odběratele; delete pro bedny, kamiony a zakázky; `change_neprijata_bedna`, `change_pozice`, `filter_chemistry_bedna`, `mark_bedna_zakaleno` a vyjmenovaná view práva. Nemá mark_bedna_zkontrolovano, change_mereni_zakazky ani výjimky pro expedované a pozastavené bedny. |
| Rozšířený filtr TZ | Rozšíření nabídky filtru Skupina TZ v administraci Deníku beden v krocích šarže | **0 přiřazených práv**. Členství podle přesného názvu skupiny nabídne všechny skupiny TZ nalezené v předpisech evidovaných beden místo výchozích SK2, SK9, SK14, SK16 a SK19. Samo nezajistí vstup do administrace ani přístup k deníku; kombinuje se s pracovní rolí. |

V této a dalších tabulkách mají oprávnění bez uvedené předpony předponu **`orders.`**. Zápis „view/add/change pro kamion“ znamená `view_kamion`, `add_kamion`, `change_kamion`; není to název jednoho oprávnění.

Členství ve skupině **nenastavuje Aktivní, staff ani superuser**. V běžném provozním nastavení mají **mistři `is_staff=True` a operátoři `is_staff=False`**. Toto rozlišení popisuje pracovní role, bez testovacích účtů. Příznak staff se nastavuje u každého účtu samostatně; není vlastností skupiny. Při doplňující kontrole byli ověřeni členové skupin Mistr a Operátor, u ostatních účtů se příznaky a přímá práva nečetly.

Shodných 16 skupinových oprávnění tedy neznamená stejný rozsah dostupných funkcí: mistr může navíc pracovat v administraci, operátor používá provozní rozhraní. V provozních obrazovkách samotná absence staff operátorova práva nesnižuje; například plný přesun šarží je dostupný oběma rolím. Pro vstup do administrace musí být účet také aktivní a pro každou agendu platí její vlastní kontroly oprávnění.

**Z devíti skupin má `orders.view_zaznamneshody` pouze Manager.** Samotné členství v Kontrole přístup k Evidenci neshod nepřidá. Může jej zajistit také přímé oprávnění, další skupina s tímto právem nebo aktivní superuser; běžný přístup do evidence vyžaduje také staff. Případné doplnění skupin je samostatná změna správy přístupů, kterou tento dokument neprovádí.

**Rozšířený filtr TZ** je doplňková skupina, nikoli samostatná provozní role. Kód v `SkupinaSarzeBednaFilter` kontroluje přímo členství podle názvu, nikoli `has_perm`; samotný příznak superuser tedy tuto podmínku nenahrazuje. Rozšíření nabídky filtru nepředstavuje oddělení dat podle skupin TZ.

Oprávnění `change_bedna`, `change_zakazka` a `change_kamion` slouží více akcím včetně některých návratů a importů. Skupiny představují skutečné sestavy těchto práv, nikoli technické oddělení každé pracovní činnosti. Přítomnost práva historického modelu také sama nezaručuje možnost přímé editace historie; administrační historie je nastavena pouze pro čtení.

## 3. Oprávnění pro bedny a kvalitu

| Úkol | Kontrolované oprávnění a podmínky |
| --- | --- |
| Zobrazit provozní kontrolu bedny | `view_bedna` **nebo** `mark_bedna_zkontrolovano`. |
| Zapsat výstupní kontrolu a jednotlivá měření | `mark_bedna_zkontrolovano`; pouze Zakaleno nebo Zkontrolováno. Samotná obecná práva change_kontrolabedny / change_merenibedny tento provozní přístup nenahrazují. |
| Dokončit kontrolu bedny přes provozní potvrzení | `mark_bedna_zkontrolovano`, stav Zakaleno, nepozastavená bedna a úplné aktuální podklady. |
| Zapsat výsledky u pozastavené bedny | Navíc `change_pozastavena_bedna`; dokončení kontroly přes provozní potvrzení zůstává do zrušení pozastavení blokované. |
| Potvrdit Navezeno přes sken | `mark_bedna_navezeno` **nebo** `change_bedna`; pouze Přijato / K navezení a nepozastavená bedna. |
| Potvrdit Zakaleno přes sken | `scan_mark_bedna_zakaleno`; pouze Navezeno / Ve zpracování a nepozastavená bedna. |
| Převést na atypický průběh, označit zkontrolováno s neshodou | Současně `change_bedna` a `mark_bedna_zkontrolovano`; pouze nepozastavené Přijato bez kontroly a měření. Nahrazuje původní reklamační akci Přijato → Zakaleno. |
| Vrátit Navezeno na Přijato příslušnou admin akcí | `mark_bedna_navezeno`; ověřit skutečný stav a návazný deník. |
| Upravit nepřijatou bednu | `change_neprijata_bedna`; admin posuzuje také přístup do příslušné agendy. |
| Upravit pouze poznámku nepřijaté bedny | `change_poznamka_neprijata_bedna`; bez plného práva k nepřijatým bednám je ostatní obsah jen pro čtení. |
| Upravit expedovanou bednu / zakázku v adminu | `change_expedovana_bedna` / `change_expedovana_zakazka`; některá pole a zápis měření zůstávají uzamčené. |
| Zobrazit Evidenci neshod a její detaily | Aktivní staff účet a `view_zaznamneshody`. Ruční přidávání, úpravy a mazání případů nejsou povolené. |
| Používat filtr chemie a export chemických údajů beden | `filter_chemistry_bedna` vedle přístupu k příslušné admin agendě. Samotné toto právo neopravňuje k importu chemických měření nad kamionem. |
| Doplnit FAUF pro SPX | `change_bedna`; podle stavu navíc `change_neprijata_bedna`, `change_expedovana_bedna` a při pozastavení také `change_pozastavena_bedna`. |

Speciální práva pro pozastavené, nepřijaté a expedované bedny přidělujte podle skutečné potřeby. Přesná kombinace závisí na rozhraní: detail bedny, hromadná akce, inline a režim FAUF nemusí používat totožnou vstupní kontrolu. Ověřte celý zamýšlený postup skutečným účtem bez superuser.

**K expedici a Expedováno dovolují kontrolu a měření pouze číst**, také správci. Opravu proveďte návratem popsaným v [mimořádných situacích](manual_mimoradne_situace.md#6-oprava-kontroly-před-expedicí), nikoli přidáváním dalších práv. Ani dostatečná oprávnění neodstraní blokaci Neshodou nebo nepotvrzenými měřeními.

## 4. Oprávnění pro výrobu a šarže

| Operace v provozních obrazovkách | Potřebná oprávnění |
| --- | --- |
| Přehled pracovišť, rychlý přehled šarže a náhled průvodky | `view_sarzekrok` **a** `view_sarzekrokbedna`. |
| Rychlé založení šarže a prvního kroku | `add_sarze`, `add_sarzekrok`, `add_sarzekrokbedna`. Pro následné zadávání patra doplňte také change_sarzekrokbedna a pro přehled obě view práva. |
| Zadání a úprava patra | `add_sarzekrokbedna` **a** `change_sarzekrokbedna`. |
| Smazání posledního patra v rychlém zadávání | K právům pro úpravu patra navíc `delete_sarzekrokbedna_patro`. Není to běžné delete_sarzekrokbedna. |
| Úprava hlavičky rychlého nakládání a jeho konce | `change_sarze` **a** `change_sarzekrok`. |
| Úprava kroku přes provozní detail šarže | `change_sarzekrok` **a** `change_sarzekrokbedna`, také při pouhém doplnění konce tímto formulářem. |
| Přesun na libovolné nabízené cílové pracoviště | `can_move_sarze`. |
| Omezený přesun | `can_move_sarze_limited`; v současném kódu je cílovým typem pouze **Tryskač**. Pokud má účet i can_move_sarze, platí plná nabídka. |
| Stavové operace operátora u šarží s položkami mimo DB | `change_stav_sarze_operator`. |
| Stavové operace kontrolora u šarží s položkami mimo DB | `change_stav_sarze_kontrolor`. |

Přesun, úprava obsahu kroku a změna stavu šarže jsou samostatné úkoly. Právo přesouvat šarže samo nezajišťuje právo upravovat původní krok a obecné change_sarze nenahrazuje zvláštní stavová oprávnění v provozním detailu. Admin agendy vyžadují navíc staff a práva svých modelů; výše uvedená tabulka popisuje provozní cesty.

## 5. Založení skupiny a nástup pracovníka

Postup provádí správce, který už smí spravovat uživatele a skupiny. Použijte standardní agendy **Skupiny** (`/admin/auth/group/`) a **Uživatelé** (`/admin/auth/user/`); bez odpovídajícího přístupu nejsou dostupné.

1. S vedoucím určete konkrétní úkoly a zda pracovník potřebuje administraci, nebo jen provozní obrazovky.
2. Ve Skupinách ověřte aktuální obsah existujících skupin z kapitoly 2 a vyberte odpovídající sestavu. Pokud žádná nevyhovuje, dohodněte samostatnou úpravu nebo novou skupinu s jednoznačným názvem. V nabídce jsou práva popsaná názvem akce a modelu; zde uvedený kód slouží k přesnému rozlišení. Při změně aktualizujte také tento snímek dokumentace.
3. V Uživatelích založte osobní účet a nastavte přístupové údaje standardním formulářem. Doplňte jméno a příjmení pro dohledatelnost zápisů a předvyplnění operátora.
4. Ponechte účet aktivní, nastavte staff podle pracovní role a přiřaďte dohodnuté skupiny. U mistra staff zapněte, u operátora ponechte vypnuté; u ostatních rolí se řiďte potřebným rozhraním. Pro běžnou roli ponechte superuser vypnuté.
5. Přímá oprávnění přidejte jen pro konkrétní domluvenou výjimku a poznamenejte její účel do evidence správy přístupů používané ve vaší organizaci. Aplikace nemá v tomto návodu zaváděnou automatickou evidenci schvalování rolí.
6. Ověřte přihlášení a celý pracovní postup účtem pracovníka nebo odpovídajícím zkušebním účtem bez superuser. Zápis ověřujte na zkušebních datech mimo běžné výrobní zakázky.

Správu uživatelů nepřidělujte jen kvůli možnosti nastavovat zákazníky a předpisy. Práva měnit uživatele a skupiny mohou umožnit také změny přidělených oprávnění. Běžný pracovník nepotřebuje správu uživatelů, skupin ani katalogu oprávnění.

## 6. Změna role a ukončení přístupu

### Změna úkolů pracovníka

1. Odeberte již nepotřebné skupiny a přidejte nové podle dohodnuté odpovědnosti.
2. Prověřte všechny zbývající skupiny a přímá oprávnění. Zvlášť zkontrolujte výjimky pro expedované a pozastavené bedny, mazání a správu přístupů.
3. Znovu posuďte staff a superuser. Odebrání staff odstraní vstup do administrace a návodů, ale samo nezakáže provozní obrazovky ani nezruší modelová práva.
4. Pro ověření použijte nové přihlášení a zkontrolujte dostupnost potřebných i již nepotřebných operací. Dříve otevřená stránka může mít zastaralou nabídku; rozhodující je výsledek nového požadavku.

### Odchod pracovníka nebo zrušení přístupu

1. V účtu vypněte **Aktivní** a uložte. Samotné odebrání skupiny nebo staff nemusí stačit k zamezení provozního přístupu.
2. Podle interního postupu odeberte skupiny, přímá práva a privilegované příznaky, aby se účet při případné reaktivaci nevrátil k původním výjimkám bez kontroly.
3. Prověřte přiřazení účtu ve skupinách a příjemcích notifikací. Nastavení příjemců notifikací není totéž co oprávnění k práci s daty.
4. Ověřte odmítnutí přístupu při novém požadavku i neúspěšné nové přihlášení. Účet běžně zachovejte deaktivovaný kvůli dohledatelnosti dřívějších zápisů.

## 7. Ověření přístupu a běžné problémy

| Projev | Co ověřit |
| --- | --- |
| Uživatel se nepřihlásí | Aktivitu účtu a správné přihlašovací údaje. |
| Provozní rozcestník funguje, administrace ne | Staff a práva požadované admin agendy. |
| Návody fungují, agenda není v nabídce | Čtení návodů nepotřebuje práva modelů; zkontrolujte příslušná view/change oprávnění. |
| Tlačítko nebo akce chybí | Oprávnění, aktivní filtr, stav a výběr záznamů. Skrytou akci nemusí způsobovat chybějící právo. |
| Kontrolor může číst, ale nemůže uložit měření | mark_bedna_zkontrolovano, výrobní stav a pozastavení; change_bedna samo nestačí. |
| Nelze doplnit konec kroku v provozním detailu | Obě change práva: sarzekrok a sarzekrokbedna. U rychlého nakládání jde o jiný formulář s jinou kombinací. |
| Omezený přesun nabízí i další pracoviště | Účet může mít can_move_sarze z jiné skupiny nebo přímo, případně superuser. |
| Filtr Skupina TZ v deníku nabízí jen SK2, SK9, SK14, SK16 a SK19 | Členství ve skupině s přesným názvem Rozšířený filtr TZ. Po rozšíření se nabízejí skupiny předpisů nalezené u evidovaných beden. |
| Odebrání skupiny neomezilo přístup | Ostatní skupiny, přímá práva, superuser a podmínky konkrétního přehledu. Některé obrazovky vyžadují pouze přihlášení. |
| Správce nemůže změnit expedované měření | Jde o stavové omezení; nejprve vraťte zakázku a bednu podle návodu oprav. |

Při ověření projděte celý navazující úkol: například založení šarže → zadání patra → přehled → tisk → doplnění konce. Jedna dostupná úvodní stránka nepotvrzuje oprávnění pro další kroky. Pro kontrolu rolí nepoužívejte superuser, který běžná chybějící práva zakryje.

## 8. Přesný soupis oprávnění skupin

Snímek z 9. listopadu 2026. V tabulkách zápis `view` u modelu `orders.bedna` označuje právo `orders.view_bedna`; obdobně add, change a delete. Pomlčka znamená, že skupina dané standardní právo nemá. Vlastní oprávnění jsou uvedena samostatně plným kódem. Soupis zahrnuje i uložená práva historických a odstraněných modelů; jejich existence sama neznamená editovatelnou historii ani dostupnou agendu.

### Kontrola (9 práv)

| Model | view | add | change | delete |
| --- | --- | --- | --- | --- |
| `orders.bedna` | Ano | — | — | — |
| `orders.kamion` | Ano | — | — | — |
| `orders.sarze` | Ano | — | — | — |
| `orders.sarzekrok` | Ano | — | — | — |
| `orders.sarzekrokbedna` | Ano | — | — | — |
| `orders.zakazka` | Ano | — | — | — |

**Vlastní oprávnění:** `orders.change_mereni_zakazky`, `orders.change_stav_sarze_kontrolor`, `orders.mark_bedna_zkontrolovano`.

### Manager (96 práv)

| Model | view | add | change | delete |
| --- | --- | --- | --- | --- |
| `auth.group` | Ano | Ano | Ano | Ano |
| `auth.permission` | Ano | Ano | Ano | Ano |
| `auth.user` | Ano | Ano | Ano | Ano |
| `orders.bedna` | Ano | Ano | Ano | Ano |
| `orders.cena` | Ano | Ano | Ano | Ano |
| `orders.historicalbedna` | Ano | — | — | — |
| `orders.historicalsarze` | Ano | — | — | — |
| `orders.historicalsarzekrok` | Ano | — | — | — |
| `orders.historicalsarzekrokbedna` | Ano | — | — | — |
| `orders.kamion` | Ano | Ano | Ano | Ano |
| `orders.kontrolabedny` | Ano | — | — | — |
| `orders.merenibedny` | Ano | — | — | — |
| `orders.notification` | Ano | Ano | Ano | Ano |
| `orders.odberatel` | Ano | Ano | Ano | Ano |
| `orders.pletivo` | Ano | Ano | Ano | Ano |
| `orders.pozice` | Ano | Ano | Ano | Ano |
| `orders.predpis` | Ano | Ano | Ano | Ano |
| `orders.rozpracovanost` | Ano | — | — | — |
| `orders.sarze` | Ano | Ano | Ano | Ano |
| `orders.sarzekrok` | Ano | Ano | Ano | Ano |
| `orders.sarzekrokbedna` | Ano | Ano | Ano | Ano |
| `orders.typhlavy` | Ano | Ano | Ano | Ano |
| `orders.zakazka` | Ano | Ano | Ano | Ano |
| `orders.zakaznik` | Ano | Ano | Ano | Ano |
| `orders.zarizeni` | Ano | Ano | Ano | Ano |
| `orders.zaznamneshody` | Ano | — | — | — |

**Vlastní oprávnění:** `orders.can_move_sarze`, `orders.can_move_sarze_limited`, `orders.change_expedovana_bedna`, `orders.change_expedovana_zakazka`, `orders.change_mereni_zakazky`, `orders.change_neprijata_bedna`, `orders.change_pozastavena_bedna`, `orders.change_poznamka_neprijata_bedna`, `orders.change_stav_sarze_kontrolor`, `orders.change_stav_sarze_operator`, `orders.delete_sarzekrokbedna_patro`, `orders.filter_chemistry_bedna`, `orders.mark_bedna_navezeno`, `orders.mark_bedna_zakaleno`, `orders.mark_bedna_zkontrolovano`, `orders.scan_mark_bedna_zakaleno`.

### Mistr (16 práv)

| Model | view | add | change | delete |
| --- | --- | --- | --- | --- |
| `orders.bedna` | Ano | — | — | — |
| `orders.sarze` | Ano | Ano | Ano | — |
| `orders.sarzekrok` | Ano | Ano | Ano | — |
| `orders.sarzekrokbedna` | Ano | Ano | Ano | — |
| `orders.zarizeni` | Ano | — | — | — |

**Vlastní oprávnění:** `orders.can_move_sarze`, `orders.change_stav_sarze_operator`, `orders.delete_sarzekrokbedna_patro`, `orders.mark_bedna_navezeno`, `orders.scan_mark_bedna_zakaleno`.

### Náhled (15 práv)

| Model | view | add | change | delete |
| --- | --- | --- | --- | --- |
| `orders.bedna` | Ano | — | — | — |
| `orders.cena` | Ano | — | — | — |
| `orders.kamion` | Ano | — | — | — |
| `orders.odberatel` | Ano | — | — | — |
| `orders.pletivo` | Ano | — | — | — |
| `orders.pozice` | Ano | — | — | — |
| `orders.rozpracovanost` | Ano | — | — | — |
| `orders.sarze` | Ano | — | — | — |
| `orders.sarzebedna` | Ano | — | — | — |
| `orders.sarzekrok` | Ano | — | — | — |
| `orders.sarzekrokbedna` | Ano | — | — | — |
| `orders.typhlavy` | Ano | — | — | — |
| `orders.zakazka` | Ano | — | — | — |
| `orders.zakaznik` | Ano | — | — | — |
| `orders.zarizeni` | Ano | — | — | — |

**Vlastní oprávnění:** žádná.

`orders.view_sarzebedna` zůstává přiřazené v databázi, ale model `SarzeBedna` byl odstraněn migrací 0196. Toto právo nenahrazuje `orders.view_sarzekrokbedna` pro současný deník; skupina má obě.

### Operátor (16 práv)

| Model | view | add | change | delete |
| --- | --- | --- | --- | --- |
| `orders.bedna` | Ano | — | — | — |
| `orders.sarze` | Ano | Ano | Ano | — |
| `orders.sarzekrok` | Ano | Ano | Ano | — |
| `orders.sarzekrokbedna` | Ano | Ano | Ano | — |
| `orders.zarizeni` | Ano | — | — | — |

**Vlastní oprávnění:** `orders.can_move_sarze`, `orders.change_stav_sarze_operator`, `orders.delete_sarzekrokbedna_patro`, `orders.mark_bedna_navezeno`, `orders.scan_mark_bedna_zakaleno`.

### Plánování výroby a rovnání (13 práv)

| Model | view | add | change | delete |
| --- | --- | --- | --- | --- |
| `orders.bedna` | Ano | — | Ano | — |
| `orders.historicalsarzekrok` | — | Ano | — | — |
| `orders.kamion` | Ano | — | — | — |
| `orders.notification` | Ano | — | Ano | — |
| `orders.pozice` | Ano | — | — | — |
| `orders.predpis` | Ano | — | — | — |
| `orders.sarzekrok` | Ano | — | — | — |
| `orders.sarzekrokbedna` | Ano | — | — | — |
| `orders.zakazka` | Ano | — | — | — |
| `orders.zakaznik` | Ano | — | — | — |

**Vlastní oprávnění:** `orders.change_poznamka_neprijata_bedna`.

### Předák (14 práv)

| Model | view | add | change | delete |
| --- | --- | --- | --- | --- |
| `orders.bedna` | Ano | — | — | — |
| `orders.sarze` | Ano | Ano | Ano | — |
| `orders.sarzekrok` | Ano | Ano | Ano | — |
| `orders.sarzekrokbedna` | Ano | Ano | Ano | — |
| `orders.zarizeni` | Ano | — | — | — |

**Vlastní oprávnění:** `orders.can_move_sarze_limited`, `orders.change_stav_sarze_operator`, `orders.scan_mark_bedna_zakaleno`.

### Příjem - Expedice (34 práv)

| Model | view | add | change | delete |
| --- | --- | --- | --- | --- |
| `orders.bedna` | Ano | Ano | Ano | Ano |
| `orders.historicalbedna` | Ano | — | — | — |
| `orders.historicalkamion` | Ano | — | — | — |
| `orders.historicalodberatel` | Ano | — | — | — |
| `orders.historicalzakazka` | Ano | — | — | — |
| `orders.historicalzakaznik` | Ano | — | — | — |
| `orders.kamion` | Ano | Ano | Ano | Ano |
| `orders.odberatel` | Ano | Ano | Ano | — |
| `orders.pozice` | Ano | — | Ano | — |
| `orders.predpis` | Ano | — | — | — |
| `orders.sarze` | Ano | — | — | — |
| `orders.sarzekrok` | Ano | — | — | — |
| `orders.sarzekrokbedna` | Ano | — | — | — |
| `orders.typhlavy` | Ano | — | — | — |
| `orders.zakazka` | Ano | Ano | Ano | Ano |
| `orders.zakaznik` | Ano | Ano | Ano | — |
| `orders.zarizeni` | Ano | — | — | — |

**Vlastní oprávnění:** `orders.change_neprijata_bedna`, `orders.filter_chemistry_bedna`, `orders.mark_bedna_zakaleno`.

### Rozšířený filtr TZ (0 práv)

Skupina nemá žádná přiřazená modelová ani vlastní oprávnění. Její účinek je dán přímou kontrolou členství podle názvu v `orders/filters.py`, třída `SkupinaSarzeBednaFilter`. Přístup do agendy musí zajistit jiná skupina, přímá oprávnění a potřebné příznaky účtu.

## 9. Související dokumentace a kód

[Stavy a automatická pravidla](manual_stavy_a_pravidla.md) · [Bezpečnost a audit](security.md) · [Mimořádné situace a opravy](manual_mimoradne_situace.md) · [Číselníky](manual_ciselniky.md) · [Kontrola beden](manual_kontrola_beden.md) · [Rychlé založení šarže](manual_rychle_zalozeni_sarze.md) · [Průchod šarže](manual_pruchod_sarze.md)

Implementace: `orders/models.py` (standardní a vlastní oprávnění), `orders/views.py` (kontroly provozních operací), `orders/filters.py` (rozšíření filtru podle členství ve skupině), `orders/admin.py`, `orders/actions.py` a `order_processing/urls.py` (přístup do dokumentace). Účty a skupiny používají standardní správu uživatelů Djanga.
