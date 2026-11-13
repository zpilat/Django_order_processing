# Uživatelský manuál: Mimořádné situace a opravy

Návod řeší opravy napříč příjmem, výrobou, kontrolou a expedicí. Běžný průchod popisuje [provozní tahák](provozni_tahak.md); zde vždy nejprve zjistěte, co se skutečně stalo a co už je uložené v aplikaci.

## 1. Než začnete opravovat

1. Ověřte číslo bedny, zakázku, kamion a případně šarži. Rozlišujte interní číslo bedny, číslo obalu zákazníka, materiálovou šarži a výrobní šarži aplikace.
2. Zjistěte současný výrobní stav, pozastavení, rozhodnutí kontroly a již provedené fyzické operace. U šarže ověřte všechny navazující kroky a řádky dotčené bedny.
3. Domluvte opravu s pracovníkem odpovědným za danou agendu, pokud se dotýká jeho měření, výrobní evidence nebo vydaných dokladů.
4. Použijte odpovídající postup níže a po uložení znovu otevřete záznam. U hromadné akce přečtěte všechna hlášení: některé operace mohou část výběru přeskočit.

Výrobní stav bedny, stav šarže, jednotlivé kroky, kontrola a technologické stavy jsou samostatné údaje. Návrat jednoho stavu automaticky nevrací ostatní záznamy ani skutečně provedenou operaci. Historie pomáhá dohledat změnu, ale není univerzálním tlačítkem Zpět.

## 2. Chyba v příjmu nebo importu dodacího listu

**Skutečná reklamace nebo vrácení zboží od zákazníka** je nový příjem s novým interním číslem bedny. Původní expedici kvůli němu nevracejte. Pro reklamaci, samostatné rovnání či přeposlání do zinkovny použijte [Atypický průběh](manual_bedna.md#atypický-průběh-reklamace-a-samostatné-operace); původní výsledky zůstanou u původní bedny. Postupy oprav a vracení expedice níže slouží k opravě evidence původní dodávky.

### Chyba před potvrzením importu

V náhledu zkontrolujte zákazníka, artikly, rozměry, předpisy a bedny. Pokud nesouhlasí, import nepotvrzujte. Opravte vstupní XLSX a nahrajte novou verzi; při chybně zvoleném kamionu se vraťte do seznamu a vyberte správný kamion příjem bez zakázek. Náhled sám zakázky ani bedny neukládá.

### Import už byl potvrzený

Nejprve otevřete kamion a ověřte uložené zakázky a bedny. Po přerušení spojení nebo ztracené odpovědi prohlížeče nelze z chybějícího hlášení určit, zda zápis proběhl. XLSX import ukládá zakázky a bedny atomicky, ale opakování do nového kamionu může založit duplicity.

| Zjištěný stav | Postup |
| --- | --- |
| Kamion stále nemá zakázky | Ověřte původní chybu a náhled; poté lze znovu použít import nad tímto prázdným kamionem. |
| Zakázky existují a chyba je jen v jednotlivém údaji | Opravte konkrétní zakázku nebo bednu s potřebným oprávněním a ověřte navazující požadavky a doklady. |
| Je chybný celý import a všechny bedny jsou Nepřijato | Správce agendy s právem mazání může po kontrole vazeb odstranit chybná data standardní administrací a import zopakovat. Před potvrzením mazání zkontrolujte seznam souvisejících záznamů. |
| Některá bedna už byla přijata nebo zpracována | Mazání kamionu či zakázky je omezené. Opravu řešte se správcem podle skutečného průchodu; nevytvářejte náhradní duplicitní příjem. |

Pokud import přiřadil **Neznámý předpis**, doplňte správný aktivní předpis zákazníka v zakázce před přijetím. Mimo Nepřijato musí mít bedna také kladné netto, táru a množství.

Chybně přijatá bedna nemá obecnou akci pro kompletní zrušení příjmu včetně všech návazností. Je-li potřeba jen oprava údajů, opravte je v dostupném formuláři. Návrat do Nepřijato nebo změnu zákazníka u kamionu s navázanými daty řešte se správcem; změna zákazníka může ovlivnit předpisy, ceny i kontrolní pravidla.

Oprava nepřijaté bedny vyžaduje oprávnění `orders.change_neprijata_bedna`; samotné právo k poznámce nestačí. Podrobnosti jsou v [návodu kamionů](manual_kamion.md#8-import-zakázek-z-excelu) a [návodu beden](manual_bedna.md).

## 3. Chybná pozice nebo návrat z přípravy výroby

- **Nesprávná pozice:** u bedny K navezení nebo Navezeno vyberte správnou pozici a uložte. Zkontrolujte její kapacitu a skutečné umístění bedny.
- **Zrušený požadavek na navezení:** použijte **Vrátit bedny ze stavu K NAVEZENÍ do stavu PŘIJATO**. Vyžaduje oprávnění ke změně beden.
- **Bedna byla omylem označena Navezeno:** použijte **Vrátit bedny ze stavu NAVEZENO do stavu PŘIJATO**. Vyžaduje `orders.mark_bedna_navezeno`.
- **Návrat z rozpracovanosti:** akce **Vrátit bedny z rozpracovanosti do stavu PŘIJATO** pracuje se stavy Navezeno, Ve zpracování, Zakaleno a Zkontrolováno. Použijte ji až po ověření skutečného stavu a návazné evidence.

Návrat na Přijato vymaže skladovou pozici, ale sám neodstraní řádky deníku, kroky šarže, měření ani kontrolu a nevrátí technologické stavy. Pokud už proběhlo fyzické zpracování, musí správnost opravy posoudit odpovědný pracovník výroby. Pozastavené bedny tyto návratové akce blokují; jejich uvolnění řeší kapitola níže.

## 4. Bedna je ve špatné šarži nebo patře

### Nakládání je ještě otevřené

1. V přehledu rychlého založení šarže zvolte **Upravit patro**.
2. Opravte bednu, odeberte chybný řádek nebo upravte podíl. Zkontrolujte všechny řádky patra; uložením se nahrazuje celé jeho rozložení.
3. Je-li chybné celé poslední patro, použijte **Smazat patro**, pokud máte navíc `orders.delete_sarzekrokbedna_patro`.
4. Ověřte obsah roštu a případně znovu vytiskněte průvodku. Správnou bednu přidejte tam, kde je její obsah skutečně naložený.

Úprava patra vyžaduje `orders.add_sarzekrokbedna` a `orders.change_sarzekrokbedna`. Odebrání chybné bedny samo nevrací její stav z Ve zpracování ani neobnovuje původní skladovou pozici. Pokud bedna fyzicky zůstala na příjmu, opravte také její stav podle předchozí kapitoly.

### Nakládání je uzavřené nebo šarže pokračovala

Použijte detail příslušného kroku a jeho **Upravit**, případně administraci deníku s odpovídajícím oprávněním. Checkbox **Smazat** u položky po uložení odebere řádek pouze z tohoto kroku. Oprava zdrojového kroku nepřepíše jeho již zkopírované položky v dalších krocích.

S odpovědným pracovníkem výroby ověřte každý dotčený krok, všechny části bedny a skutečný průchod. Bedna může mít více řádků v různých patrech i více šarží. Pokud záměna zasáhla záznam tepelného zpracování nebo tryskání, zahrňte do kontroly také výrobní a technologické stavy bedny. Podrobnosti: [rychlé založení šarže](manual_rychle_zalozeni_sarze.md) a [deník](manual_denik_pece.md).

## 5. Chybné pracoviště, čas nebo opakovaný přesun

**Překlep v kroku:** v detailu šarže u správného kroku použijte **Upravit**, opravte pracoviště, operátora, datum a čas a uložte. Provozní formulář vyžaduje oprávnění `orders.change_sarzekrok` a `orders.change_sarzekrokbedna`. Datum a čas konce zadávejte společně; při průchodu přes půlnoc patří konec do následujícího dne. Konec nesmí předcházet začátku.

**Po přesunu chybí konec zdroje:** nový krok už mohl vzniknout. Otevřete detail šarže, ověřte jej a doplňte skutečný konec původního kroku. Nespouštějte znovu přesun jen kvůli doplnění času.

**Podezření na dvojí přesun:** nejprve porovnejte pořadí, pracoviště, časy a položky kroků. Opakovaný skutečný průchod patří do dalšího kroku. Omylem založený krok řešte se správcem výroby podle jeho návazností; aplikace nemá obecnou operaci, která vrátí přesun i všechny následné kroky najednou.

Pokud je chybná hlavička otevřeného nakládání, použijte **Upravit šarži**; změna hlavičky a prvního kroku vyžaduje `orders.change_sarze` a `orders.change_sarzekrok`. Viz [průchod šarže výrobou](manual_pruchod_sarze.md#5-dokončení-a-oprava-kroku).

## 6. Oprava kontroly před expedicí

### Bedna je Zakaleno nebo Zkontrolováno

1. Otevřete kontrolu správné bedny a u příslušné zkoušky **Zadat / upravit hodnoty**.
2. Opravte chybnou hodnotu, případně označte nesprávný řádek ke smazání, a uložte měření.
3. Po návratu zkontrolujte čistotu, uložení, počty křivých vrutů, rozhodnutí o uvolnění a důvody neshody. Uložte také **výstupní kontrolu**.
4. Ve stavu Zakaleno dokončete kontrolu tlačítkem **Dokončit kontrolu bedny**, pokud jsou splněné podmínky. U již zkontrolované bedny se rovnání a tryskání přepočítají při úspěšném uložení výstupní kontroly.
5. Ověřte výsledný stav a podle potřeby znovu vytiskněte vyplněnou KKK.

Samotné uložení měření nestačí: nastaví čekající potvrzení kontroly, které blokuje přípravu k expedici i expedici také v jiném okně. Změna měření sama nepřepočítá rovnání a tryskání. Důvody Křivost a Čistota systém odvozuje z výsledků; při Uložení NOK vynutí Jiné s poznámkou. Neshodu řešte podle skutečného nálezu a schváleného rozhodnutí.

### Bedna je K expedici

Kontrola a měření jsou pouze pro čtení. Oprávněný pracovník vrátí bednu v administraci z **K expedici** na **Zkontrolováno** a poté provede předchozí postup. Po opravě ověřte rovnání, tryskání, zinkování a uvolnění a znovu ji připravte k expedici. Je-li bedna Expedováno, nejprve postupujte podle další kapitoly.

### Konflikt nebo neuložené změny

Červeně označené hodnoty v rozepsaném formuláři ještě nejsou potvrzené v databázi. Při změně od jiného uživatele aplikace zápis odmítne. Zkontrolujte hlášení, domluvte správné údaje a použijte nabízené načtení aktuálního stavu s výslovným zahozením rozepsané kopie; potřebné vlastní údaje si předtím poznamenejte. Poté opravu zadejte proti aktuálním datům a znovu uložte.

Pokud problém vyvolala změna předpisu či zákaznického nastavení, ověřte její správnost také s pracovníkem spravujícím [číselníky](manual_ciselniky.md). Podrobné podmínky a oprávnění jsou v [kontrole beden](manual_kontrola_beden.md#7-oprávnění-a-souběžné-změny).

## 7. Oprava po expedici nebo špatný kamion výdej

Nejprve zjistěte, zda již proběhla skutečná nakládka či předání zboží a zda byly vydané doklady. Opravu evidence domluvte s expedicí; změna v aplikaci sama neřeší fyzické vrácení dodávky ani výměnu již předaných dokumentů.

1. V **Zakázkách** nastavte filtr **Skladem → Expedováno** a vyberte dotčené zakázky. Akce vrací celou vybranou zakázku, ne jednotlivě označenou bednu.
2. Použijte **Vrácení vybraných zakázek z expedice** s oprávněním ke změně zakázek. Všechny bedny vracené zakázky musí být Expedováno. Kontrola Neshoda nebo čekající potvrzení měření vrácení blokuje; taková nekonzistentní starší data řešte se správcem.
3. Přečtěte hlášení pro každou zakázku. Při hromadném výběru může jedna uspět a jiná zůstat beze změny.
4. Ověřte nové vazby: běžně se zruší příznak Expedováno a přiřazení kamionu výdej a bedny přejdou na **K expedici**. Pokud jde o oddělenou zakázku a její původní zakázka ještě nebyla expedována, bedny se mohou vrátit do původní zakázky a oddělená zakázka se smaže.
5. Pro opravu měření vraťte příslušnou bednu z K expedici na Zkontrolováno a postupujte podle předchozí kapitoly.
6. Po opravě zkontrolujte všechny bedny a proveďte expedici do správného nového či existujícího kamionu výdej. Ověřte zákazníka, odběratele a znovu vygenerujte potřebné doklady.

Vrácení zakázky samo neodstraní původní kamion výdej. Před případným odstraněním ověřte, zda na něj neodkazují jiné zakázky; výdej s přiřazenými zakázkami nelze smazat.

Speciální oprávnění k úpravám expedovaných beden a zakázek nezpřístupňuje zápis měření v expedovaném stavu. Použijte popsaný návratový postup. Pokud chybí pouze **FAUF u SPX**, lze jej s příslušným oprávněním doplnit přes **Doplnit FAUF** v detailu kamionu a znovu vytisknout dodací list; samotné doplnění FAUF nevyžaduje vrácení celé expedice. Viz [kamiony](manual_kamion.md#ruční-doplnění-fauf-pro-spx) a [zakázky](manual_zakazka.md).

## 8. Opakovaný chemický import nebo chyba archivace

Chemický import z Vanty je samostatný postup. Po chybě zkontrolujte současné chemické údaje beden, hlášení o aktualizovaných a nezměněných záznamech a stav souborů ve vstupním adresáři a archivu.

Při chybě archivace už mohou být výsledky uložené v databázi. Nevracejte soubory z archivu do vstupu bez ověření. Správce prověří dostupnost Vanty, synchronizaci a práva adresářů, potom s obsluhou zkontroluje nový náhled přiřazení JSONů. Import potvrďte až po vyřešení chyb a vysvětlení varování. Archivovaný soubor dokládá vstup; není zálohou celé databáze.

Pro změnu chemických údajů používejte příslušnou agendu, jednotlivá mechanická měření opravujte v kontrole bedny. Podrobnosti jsou v [návodu kamionů](manual_kamion.md#import-chemických-měření-beden).

## 9. Pozastavená bedna a evidence neshod

Pozastavení bedny a **Uvolnění = Neshoda** jsou odlišné údaje. Zrušení pozastavení nevyřeší neshodu a uložení Uvolněno samo neruší pozastavení.

- Úpravy a uvolnění pozastavené bedny vyžadují `orders.change_pozastavena_bedna`; nejprve musí být vyřešen skutečný důvod pozastavení.
- Neshoda blokuje přípravu k expedici i expedici. Po nápravě zapište aktuální měření a rozhodnutí výstupní kontroly.
- Případ v **Evidenci neshod** je neměnný snímek. Uvolnění bedny jej nemaže a pozdější oprava měření jej nepřepíše. Opravu provádějte v aktuální kontrole; původní případ zachovává tehdejší podklady.

Viz [evidence neshod](manual_evidence_neshod.md) a [kontrola beden](manual_kontrola_beden.md).

## 10. Kdy předat případ správci a co mu dodat

Správce přizvěte, pokud formulář opravu nenabízí, vrácení blokují nekonzistentní data, chyba zasahuje více výrobních kroků, potřebujete napravit smazaná data nebo se mění společná pravidla pro více zakázek. Chybějící oprávnění řešte přidělením odpovídající role nebo opravou provedenou oprávněným pracovníkem.

Připravte:

- interní čísla beden, identifikaci zakázky, kamionu a šarže;
- popis skutečného stavu, chybných údajů a požadované opravy;
- přesné znění chyby, čas a jméno uživatele, případně snímek obrazovky;
- poslední provedené operace a informaci, zda někdo pracuje ve stejném záznamu;
- u importu název vstupního souboru a výsledek náhledu, u expedice také již vydané doklady.

Historie pomůže dohledat změnu, provozní logy vyšetřit chybu a zálohy obnovit data. Obnova databáze není běžnou opravou jedné bedny: správce nejprve ověří podklady v odděleném prostředí a posoudí dopad na novější zápisy. Viz [bezpečnost a audit](security.md) a [zálohy a obnova](zalohy.md).

## 11. Související dokumentace a kód

[Stavy a automatická pravidla](manual_stavy_a_pravidla.md) · [Role a oprávnění](manual_role_a_opravneni.md)

[Číselníky a nastavení zákazníka](manual_ciselniky.md) · [Provozní tahák](provozni_tahak.md) · [Bedny](manual_bedna.md) · [Kamiony](manual_kamion.md) · [Zakázky](manual_zakazka.md) · [Průchod šarže](manual_pruchod_sarze.md) · [Kontrola beden](manual_kontrola_beden.md)

Implementace: `orders/admin.py`, `orders/actions.py`, `orders/models.py`, `orders/views.py` a služby `orders/services/expedice_service.py`, `orders/services/mereni_bedny_service.py`, `orders/services/chemistry_import_service.py`, `orders/services/evidence_neshod_service.py`.
