# Uživatelský manuál: Bedny

Tento dokument popisuje praktické ovládání evidence beden v Django administraci.
Je zaměřený na model `Bedna`, admin `BednaAdmin`, související filtry, list editaci, hromadné akce a typické chyby.

## 1. K čemu modul Bedny slouží

Agenda `Bedny` je hlavní pracovní seznam výroby.
Používá se pro:

- evidenci jednotlivých beden v rámci zakázek,
- změnu stavů výroby (od `NEPRIJATO` po `EXPEDOVANO`),
- průběžné úpravy tryskání, rovnání a zinkování,
- přípravu exportů/tisku a expedici.

Pro nakládání existujících beden použijte [Rychlé založení šarže s bednami](manual_rychle_zalozeni_sarze.md). Zápis měření a rozhodnutí o uvolnění popisuje [Kontrola beden](manual_kontrola_beden.md).

## 2. Kde v administraci pracovat

Primární obrazovka je seznam `Bedny` (`BednaAdmin`).

Prakticky:

1. Otevřete seznam `Bedny`.
2. Nejprve nastavte filtr `Stav bedny` (bez něj nejsou dostupné všechny smysluplné akce).
3. Použijte další filtry (zákazník, délka, priorita, zinkování atd.).
4. Označte řádky a proveďte akci, nebo upravujte přímo v listu (pokud je povolena inline editace).

Při **Stav bedny = Zkontrolováno** je za filtrem Uvolnění dostupný dynamický filtr **Atypický průběh: Vše / Ano / Ne**. Ano vybere atypické bedny, Ne běžné a Vše obě skupiny. Při změně na jiný výrobní stav se filtr skryje a jeho parametr se odstraní, aby neomezoval nový výběr.

## 3. Co znamenají hlavní pole bedny

- `cislo_bedny`: interní číslo bedny, generuje se automaticky.
- `hmotnost`: netto kg.
- `tara`: tára kg.
- `stav_bedny`: hlavní výrobní stav.
- `tryskat`, `rovnat`, `zinkovat`: technologické stavy.
- `pozice`: používá se při stavech navezení.
- `pozastaveno`: blokace práce s bednou.
- `fakturovat`: zda se bedna započítává do fakturace.
- `atypicky_prubeh`: individuální postup bez povinné sady měření; zadané výsledky se dál vyhodnocují.
- `fakturovat_kaleni`, `fakturovat_rovnani`, `fakturovat_tryskani`, `fakturovat_zinkovani`: samostatné volby účtování operací. True znamená Ano.
- `fauf`: nepovinné celé nezáporné číslo FAUF pro dodací list SPX. Import ho
  nevyplňuje. V detailu existující bedny SPX je ve Speciálních informacích;
  u ostatních zákazníků je skryté. Při vytváření bedny je dostupné bez omezení
  zákazníka. Změny se ukládají také do historie bedny.

Část **Kontrola kvality** v detailu bedny zobrazuje uložené výsledky a stavy kontroly. Za údajem **Otryskaná?** je **Vyrovnaná?**: zelená fajfka znamená stav Vyrovnaná, ostatní stavy zobrazují pomlčku. Tabulka obsahuje za sloupcem **Předepsáno** samostatný sloupec **Rozsah měření** s minimem vzorků nebo hodnot podle nastavení zákazníka, například **Min. 5 vzorků** či **Min. 5 hodnot z 25 vzorků**. Zápis a úpravy se otevírají odkazem **Otevřít kontrolu a měření**.

### Atypický průběh – reklamace a samostatné operace

Vrácené zboží přijměte jako novou bednu s novým interním číslem. Původní bedna, expedice a měření zůstávají zachované.

Původní akce **Změnit stav bedny z PŘIJATO rovnou do ZAKALENO (při reklamaci)** je odstraněná; použijte postup níže. Přechody s Atypickým průběhem se v přehledu kamionů nepočítají do Zpracováno ani související hmotnosti křivých. Ve skladových přehledech bedny zůstávají.

1. V seznamu Bedny vyberte nepozastavené bedny ve stavu **Přijato**, které ještě nemají kontrolu ani měření.
2. Použijte **Převést na atypický průběh, označit zkontrolováno s neshodou** ve skupině Stav bedny a přečtěte potvrzovací stránku. Potřebujete oprávnění ke změně bedny a **Může převést bednu na atypický průběh** (`orders.mark_bedna_atypicky_prubeh`).
3. Potvrzením se zapne **Atypický průběh**, nastaví **Zkontrolováno** a založí kontrola s **Neshodou bez důvodu**. Rovnání, Tryskání a Zinkování se nastaví na **Nezadáno**. Hlavní **Fakturovat** i fakturace všech jednotlivých operací se nastaví na **Ne**.
4. Vyplňte potřebné zkoušky a výstupní kontrolu. Ohyb, Krut, Prohyb po TZ ani oba počty křivých nejsou povinné. Dokud má atypická bedna **Neshodu**, lze ukládat provozní změny i průběžnou kontrolu bez vyplněné Čistoty a Uložení. Například lze ručně nastavit Tryskání na Špinavá. Čistota a Uložení jsou povinné až pro Uvolněno nebo QS s odchylkou. Podrobnosti uvádí [kontrola atypických beden](manual_kontrola_beden.md#atypický-průběh).
5. Určete skutečné technologické stavy a případnou fakturaci. Neshoda, nepotvrzená měření a Nezadáno v technologických stavech dál blokují přípravu k expedici. Atypická bedna před expedicí vyžaduje uložené uvolnění a Čistotu i Uložení OK; starších běžných beden s papírovou kontrolou se tato podmínka netýká.

Akce je společná transakce pro celý výběr. Při nepřípustné bedně nebo chybě se nepřevede žádná. Existující kontroly a měření nepřepisuje. Změny mají historii s autorem a vznikne počáteční snapshot neshody. Reset stavů a fakturace se neopakuje při dalším ukládání kontroly.

Samostatné oprávnění pro atypický průběh vyžaduje také ruční změna příznaku v detailu bedny; bez něj je pouze pro čtení. Migrace 0251 ho vytvoří, ale žádné skupině ani uživateli ho automaticky nepřidělí. Toto právo nenahrazuje kontrolorské oprávnění pro měření, uvolnění a dokončení kontroly. Podrobnosti jsou v [přehledu oprávnění](manual_role_a_opravneni.md).

Provozní úprava atypické bedny v Neshodě v adminu nepotvrzuje měření ani nepřepočítává technologické stavy; případné čekající potvrzení zůstává aktivní. V seznamu se úplnost kontroly neověřuje u nezměněných řádků, které se neukládají. Rozpracovaná nebo starší kontrola u takového řádku neblokuje uložení změn jiných beden. U změněné běžné bedny se dosavadní podmínky kontroly ověřují dál.

Tvrdost povrchu a jádra je u atypické bedny dostupná i mimo běžný výběr beden ke vzorkování. Výsledky a předepsané hodnoty se zobrazují také v části Kontrola kvality v adminu a ve vyplněné KKK. Tím nevzniká povinnost tvrdost změřit.

V detailu bedny je samostatná část **Fakturace**. Formulář používá kladné popisky **Fakturovat kalení, Fakturovat rovnání, Fakturovat tryskání a Fakturovat zinkování**, vždy s volbou **Ano/Ne**. Hlavní **Fakturovat = Ne** vyřadí celou bednu z proformy; na dodacím listu zůstává s označením nefakturování. Jednotlivé operace zešednou a uzamknou se s vysvětlením. Jejich nastavení se nepřepisuje a zůstává zachované i při uložení bedny. Po zapnutí hlavního přepínače se znovu zpřístupní. Pro placené rovnání například zapněte hlavní Fakturovat, nastavte Fakturovat rovnání na Ano a kalení i tryskání ponechte na Ne.

Při hlavním **Fakturovat = Ano** musí mít alespoň jedna ze čtyř operací volbu **Ano**. Varování se zobrazí pouze při zapnutém hlavním Fakturovat a všech operacích na Ne; uložení se v této kombinaci odmítne i na serveru. Při hlavním Ne nebo po výběru alespoň jedné operace varování zmizí. Přepínače se automaticky nepřepisují; zvolte požadovanou operaci nebo hlavní Fakturovat nastavte na Ne. Podmínka ověřuje zvolené operace, nikoli kladnou výslednou cenu; ta dál závisí na ceníku, nastavení zákazníka a provedených operacích.

Nastavení Fakturovat rovnání, tryskání a zinkování u zákazníka slouží pouze jako výchozí hodnoty nových beden. Při založení bedny v adminu se převezmou automaticky; upravují se následně v detailu uložené bedny. Kalení má výchozí Ano. Další změna zákazníka ani nové uložení bedny volby nepřepíše. Ruční Ano u bedny platí i při zákaznickém výchozím Ne. Proformy, tisk rozpracovanosti a kontrola cen vycházejí z uložených voleb beden, hlavního Fakturovat a skutečného stavu Vyrovnaná/Otryskaná; ceny se nadále načítají z ceníku. Sloupce příplatků se zobrazí podle zahrnutých beden. Zakázka bez fakturovaných beden se vynechá. Zinkování je pouze evidenční přepínač bez ceny a částky na proformě.

Nasazená migrace `0248_atypicky_prubeh_a_fakturace` se nemění. Nová `0249_kladna_fakturace_schema` přejmenuje záporná pole na kladná a přidá výchozí zinkování zákazníka (Ne). Samostatná datová migrace `0250_vychozi_fakturace_beden` nastaví současné běžné bedny podle zákazníků: kalení Ano, rovnání a tryskání podle zákazníka, zinkování Ne. Atypickým bednám ponechá všechny operace Ne. Hlavní Fakturovat se nemění. V historii se pouze obrátí význam přejmenovaných příznaků; nepřepisuje se podle dnešního zákazníka. Převod je jednorázový a byl testován na PostgreSQL. Při nasazení zastavte aplikaci před migracemi a spusťte ji až po jejich dokončení, protože se mění názvy sloupců i význam hodnot.

#### Nasazení migrací fakturace na produkci

Tento postup je pro migrace **0249 a 0250**, které navazují na již nasazenou 0248. Nejprve změny commitněte a pushněte na GitHub, včetně obou nových migrací. Příkazy níže jsou pro Bash na produkčním serveru `srv-warehouse` pod uživatelem `pilat`, v repozitáři `~/Django-orders`.

**Příkazy provádějte postupně; při chybě nepokračujte k dalšímu kroku.** Aplikace musí být zastavená během aktualizace kódu i migrací, protože starý kód používá původní názvy sloupců.

1. Připravte pracovní adresář, aktivujte prostředí a zastavte aplikaci:

   ```bash
   cd ~/Django-orders
   source venv/bin/activate
   sudo systemctl stop django-orders
   ```

2. Vytvořte aktuální zálohu databáze podle [návodu na zálohy](zalohy.md). Pokud používáte již nastavený skript a archiv `/home/pilat/archiv`, spusťte:

   ```bash
   /bin/bash deploy/backup-orders.sh /home/pilat/archiv
   ```

   Pokračujte až po ověření úspěšné zálohy; úspěšný běh končí hlášením `DONE`. Hlášení `SKIP` znamená souběžný běh a samo nepotvrzuje dokončenou zálohu.

3. Stáhněte připravené změny, zkontrolujte plán a proveďte migrace i aktualizaci statických souborů:

   ```bash
   git pull --ff-only
   python manage.py migrate --plan
   python manage.py migrate
   python manage.py collectstatic --noinput
   python manage.py check --deploy
   ```

   Plán má obsahovat migrace `0249_kladna_fakturace_schema` a `0250_vychozi_fakturace_beden`, pokud ještě nebyly aplikovány. Migrace 0250 jednorázově nastaví současné bedny podle pravidel popsaných výše; nejde pouze o přidání prázdných polí.

4. Po úspěšném dokončení spusťte službu a zkontrolujte její stav:

   ```bash
   sudo systemctl start django-orders
   sudo systemctl status django-orders --no-pager
   ```

   V aplikaci otevřete nastavení zákazníka a detail běžné i atypické bedny. Ověřte kladné názvy fakturačních voleb, výchozí zinkování Ne a zachované hlavní Fakturovat.

Při neúspěšné migraci službu nespouštějte se smíšenou verzí kódu a databáze. Návrat řešte jako společný návrat odpovídajícího kódu a databáze; samotné vrácení Gitu po přejmenování sloupců nestačí.

## 4. Důležitá validační pravidla

### 4.1 Povinnosti mimo stav NEPRIJATO

Pokud bedna není ve stavu `NEPRIJATO`, musí být vyplněno a > 0:

- `hmotnost`,
- `tara`,
- `mnozstvi`.

Zakázka musí mít také platný předpis; předpis s názvem `Neznámý předpis` pro tyto stavy nestačí.

### 4.2 Omezení pro stavy K_EXPEDICI / EXPEDOVANO

Pro tyto stavy musí být:

- `tryskat` = Čistá nebo Otryskaná,
- `rovnat` = Rovná nebo Vyrovnaná,
- `zinkovat` = Nezinkovat nebo Uvolněno.

Příslušná výstupní kontrola nesmí mít **Uvolnění = Neshoda**. Pravidlo platí také pro hromadné označení K expedici, expedici beden i zakázek do nového či existujícího kamionu a vrácení z expedice na K expedici. Pokud vybrané bedny obsahují neshodu, označení K expedici ani expedice se neprovede; hlášení uvede čísla nevyhovujících beden. Při vracení z expedice se odmítne příslušná zakázka.

Toto pravidlo samo nevyžaduje existenci kontroly ani výslovné uvolnění: chybějící kontrola nebo nerozhodnuté uvolnění jím nejsou blokovány. Uvolněno i Uvolněno QS s odchylkou jsou přípustné.

Samostatně se blokují **nepotvrzené změny měření**. Dokud po změně měření úspěšně neuložíte výstupní kontrolu, nelze bednu označit K expedici ani expedovat, a to ani v jiném okně či přes hromadnou akci. Ochrana platí v adminu, expedičních službách i při vracení zakázky z expedice; hlášení uvede dotčené bedny. Původní uložené Uvolněno a staré technologické stavy čekající potvrzení nenahrazují.

Hromadná akce **Změna stavu bedny na Zkontrolováno** již není dostupná. Detail bedny, inline v zakázce i editace seznamu dovolí uložit Zkontrolováno pouze s úplnou kontrolou odpovídající aktuálním výsledkům a limitům, bez čekajícího potvrzení měření. Jde o stejné věcné podmínky jako u tlačítka Dokončit kontrolu bedny. Při přechodu do Zkontrolováno se zároveň automaticky nastaví Rovnání a Tryskání. Chybějící údaje je nutné nejprve uložit ve výstupní kontrole.

Ve stavech **K expedici a Expedováno** jsou kontrola i naměřené hodnoty pouze pro čtení, a to i se zvláštním oprávněním pro expedované bedny. Pro opravu vraťte bednu K expedici na Zkontrolováno; u expedované bedny nejprve vraťte zakázku z expedice a poté bednu na Zkontrolováno. Podrobnosti jsou v [manuálu kontroly beden](manual_kontrola_beden.md).

### 4.3 Omezení pro K_NAVEZENI / NAVEZENO

Pro stavy `K_NAVEZENI` a `NAVEZENO` musí být vyplněna `pozice`.

### 4.4 Zinkování V ZINKOVNĚ

Pokud je `zinkovat = V ZINKOVNĚ`, bedna musí být ve stavu `ZKONTROLOVANO`.

### 4.5 Mazání bedny

Smazat lze jen bednu ve stavu `NEPRIJATO`.

## 5. Oprávnění a blokace úprav

Systém rozlišuje speciální oprávnění:

- `change_expedovana_bedna` pro expedované bedny,
- `change_pozastavena_bedna` pro pozastavené bedny,
- `change_neprijata_bedna` pro běžné úpravy nepřijatých beden,
- `change_poznamka_neprijata_bedna` pro úpravu pouze poznámky u nepřijatých beden,
- `mark_bedna_navezeno` pro část operací kolem navezení.

Pokud uživatel nemá potřebné oprávnění, pole jsou read-only nebo se akce vůbec nezobrazí.

## 6. Inline editace v seznamu (list_editable)

Inline editace je dynamická podle filtru a oprávnění.

Zjednodušeně:

- Bez filtru nebo v nevhodném stavu se editace omezí.
- Ve stavu `NEPRIJATO` může být editace velmi omezená podle oprávnění.
- Ve stavu `K_EXPEDICI` se naopak některá pole (hmotnost/rovnat/tryskat) z inline editace schválně odeberou.

Poznámka: seznam také obsahuje polling změn (automatická kontrola nových změn v intervalu).

Rozpracované změny v seznamu nejprve uložte tlačítkem Uložit. Při odchodu ze seznamu může aplikace upozornit na neuložené úpravy; samotná změna filtru nebo spuštění jiné obrazovky údaje neukládá.

### Doplňování FAUF pro SPX

Z detailu kamionu SPX otevřete **Doplnit FAUF**. Jde o běžný seznam beden
omezený na daný kamion, s parametrem `fauf=1`; u kamionu výdej se přidává
`stav_bedny=EX`. Sloupec **FAUF** je hned za Zakázkou, Poznámka HPM je skrytá.
Místo čísla bedny zákazníka se vedle interního čísla bedny zobrazuje
**FA / Bestell-Nr.** (`vyrobni_zakazka`), podle kterého lze bednu dohledat
na zákaznických průvodkách. Výrobní zakázka je pouze pro čtení.
Bez výběru konkrétního stavu režim FAUF zahrnuje všechny stavy, včetně
Nepřijato a Expedováno; výchozí omezení běžného seznamu na sklad zde neplatí.
Editovat lze pouze FAUF a více řádků uložit najednou tlačítkem **Uložit**.
Políčko má prostor pro celé osmimístné číslo; prázdnou hodnotu lze uložit také.

Platí běžné oprávnění ke změně bedny a příslušná zvláštní oprávnění:
u Nepřijato `change_neprijata_bedna` (oprávnění pouze k poznámce nestačí),
u Expedováno `change_expedovana_bedna`, u pozastavené bedny také
`change_pozastavena_bedna`. Oprávnění se kontroluje u jednotlivých řádků
i před uložením aktuálního záznamu. Běžný seznam Expedováno zůstává
needitovatelný. Na mobilu ani při filtru Pozastaveno není inline editace dostupná.

Odkaz **Ukončit doplňování FAUF** odstraní jen parametr režimu; ostatní filtry
zůstanou zachované. Přechod na **Chemie** ukončí FAUF a zapne chemický pohled.
Před změnou pohledu či stránky rozpracované hodnoty nejprve uložte.
Podrobnosti o tisku a upozornění na chybějící čísla jsou v [manuálu kamionů](manual_kamion.md).

## 7. Filtry v BednaAdmin

V seznamu se aktuální **Uvolnění = Neshoda** označuje červeným zvýrazněním
buňky **Stav bedny** a malým symbolem **⚠** jako horním indexem těsně před
stavem, nezávisle na zvolených filtrech. Po najetí na buňku nebo symbol
se zobrazí **Neshoda při kontrole**. Pokud je jediným důvodem neshody
**Křivost**, varování se nezobrazuje; tuto informaci ukazuje Rovnání. Při
souběhu Křivosti s jiným důvodem varování zůstává. Neshoda bez zadaného důvodu
se také zvýrazní. Po uvolnění bedny varování zmizí. Jde pouze o upozornění;
pravidla práce s bednou a blokace expedice, včetně samotné Křivosti, se nemění.

Nejpoužívanější filtry:

- `Stav bedny` (`StavBednyFilter`) - obsahuje i virtuální volby `RO` (Rozpracováno) a `PE` (Po exspiraci).
- `Uvolnění` (`UvolneniBednyFilter`) - zobrazí se přímo pod filtrem `Stav bedny` pouze při volbě **Zkontrolováno**. Nabízí **Vše** (včetně nerozhodnutých uvolnění a beden bez kontroly), **Neshoda** a **Uvolněno** (společně Uvolněno a Uvolněno QS s odchylkou). Titulek ukazuje vybranou volbu, například **Uvolnění: Uvolněno**. Při přepnutí na jiný stav bedny se filtr uvolnění odstraní a přestane omezovat výsledky.
- `Tryskání`, `Rovnání`, `Zinkování` - mají i agregované volby typu "hotovo".
- `Zákazník`, `Typ hlavy`, `Celozávit`, `Skupina TZ`, `Délka`, `Priorita`, `Pozastaveno`, `Odběratel`, `Notifikace`.

Důležité:

- Dostupnost části filtrů se podle stavu bedny mění (admin je záměrně schovává/zobrazuje podle kontextu).

## 8. Hromadné akce - jak se orientovat

Akce jsou v UI seskupené do kategorií:

- `Stav bedny`
- `Tisk`
- `Export`
- `Rovnání`
- `Tryskání`
- `Zinkování`
- `Expedice`

### 8.1 Typické akce podle skupiny

Stav bedny:

- Přijmout vybrané bedny na sklad.
- Změna stavu na `K_NAVEZENI`, `NAVEZENO`, `DO ZPRACOVÁNÍ`, `ZAKALENO`, `ZKONTROLOVÁNO`, `K_EXPEDICI`.
- Vracení stavů zpět (`K_NAVEZENI -> PRIJATO`, `NAVEZENO -> PRIJATO`, rozpracovanost -> `PRIJATO`).

Rovnání:

- Změna na `ROVNÁ`, `KŘIVÁ`, `ROVNÁ SE`, `VYROVNANÁ`, přesun na `KOULENÍ`.

Tryskání:

- Změna na `ČISTÁ`, `ŠPINAVÁ`, `OTRYSKANÁ`.

Zinkování:

- Změna na `ZINKOVAT`, `POZINKOVÁNO`, `UVOLNĚNO`.
- Označit `V ZINKOVNĚ` + export DL.
- Export beden se stavem `V ZINKOVNĚ`.

Expedice:

- Expedice vybraných beden.
- Expedice vybraných beden do existujícího kamionu.

Tisk a export:

- Export do CSV (interní, pro zákazníka, pro vložení do DL).
- Export do CSV pro zákazníka **EUR** mimo rovnání má sloupce v pořadí **Vorgang+**, **Artikel-Nr.**, **Materialcharge**, **Fertigungsauftrags-Nr.**, **Behälter-Nr.**, **Abmessung**, **Kopf**, **Bezeichnung**, **HPM-Nr.**, **kg**. Vorgang+ je údaj zakázky, Materialcharge šarže materiálu bedny a Fertigungsauftrags-Nr. výrobní zakázka bedny. Nevyplněné údaje mají prázdnou buňku; při zapnuté CHEMII následují chemické sloupce na konci. Export pro rovnání ani exporty ostatních zákazníků se tím nemění.
- Tisk karet bedny, KKK a kombinovaný tisk.
- Tisk vyplněných KKK: dostupný pro všechny zákazníky; výběr musí patřit jednomu zákazníkovi a všechny bedny musí mít uloženou kontrolu. Společná šablona má české popisy a pomocné popisy podle zkratky státu zákazníka (D/A německy, I italsky, CZ pouze česky).
- Chemický pohled umožňuje prohlížet chemická měření a použít jejich export.
- Při zapnutém přepínači **CHEMIE** (`chemie=1`, vyžaduje oprávnění `orders.filter_chemistry_bedna`) přidá akce **Export vybraných beden do CSV pro zákazníka** na konec za sloupec **kg** sloupce **Ca [%]**, **P [%]** a **Zn [%]**. Platí pro všechny zákazníky i export pro rovnání. Hodnoty používají desetinnou čárku, chybějící měření mají prázdnou buňku. Při vypnutém přepínači se tyto tři sloupce neexportují.

## 9. Jak systém zpřístupňuje akce

Akce nejsou vždy dostupné. `BednaAdmin.get_actions()` je zapíná/vypíná hlavně podle:

- aktuálního filtru `stav_bedny`,
- filtru `rovnani`,
- filtru `tryskani`,
- filtru `zinkovani`,
- oprávnění uživatele.

Praktický dopad:

- Když nevidíte akci, nejdřív zkontrolujte filtr stavu bedny.
- Potom ověřte oprávnění uživatele.

## 10. Doporučený pracovní postup

1. Nastavit `Stav bedny` filtr na aktuální fázi práce.
2. Dofiltrovat zákazníka / délku / technologii.
3. Vybrat bedny.
4. Spustit příslušnou hromadnou akci pro další krok výroby.
5. Průběžně kontrolovat notifikační indikátor a případná varování.

## 11. Nejčastější chyby a řešení

### Chyba: nelze uložit bednu mimo NEPRIJATO

Zkontrolujte vyplnění `hmotnost`, `tara`, `mnozstvi` a vazbu na platný předpis.

### Chyba: nelze přepnout na K_EXPEDICI / EXPEDOVANO

Zkontrolujte kombinaci `tryskat`, `rovnat`, `zinkovat` a rozhodnutí o uvolnění v kontrole bedny. **Neshoda** přechod i expedici blokuje.

### Chyba: nelze přepnout na K_NAVEZENI / NAVEZENO

Doplňte `pozice`.

### Chyba: nelze mazat bednu

Bedna není ve stavu `NEPRIJATO`.

### Akce není vidět

Upravte filtr `Stav bedny` na odpovídající kontext a ověřte oprávnění uživatele.

## 12. Skenování a návazné provozní postupy

V kontrole bedny se prázdné zkoušky prohybu po koulení a po rovnání nabídnou až při červeném výsledku prohybu po TZ; oranžová QS odchylka je nezpřístupňuje. Již uložené navazující výsledky zůstávají viditelné. Po prvním uloženém měření po rovnání je prohyb po TZ pouze pro čtení; oprava vyžaduje nejprve odstranění všech aktuálních hodnot po rovnání. Viz [zadávání měření](manual_kontrola_beden.md#2-zadání-měření).

Dokončení kontroly a nastavení Zkontrolováno v adminu vyžaduje u každé bedny alespoň jednu uloženou hodnotu **Ohybu i Krutu**. Stejná podmínka platí při uložení opravy již zkontrolované bedny. Při chybějícím měření aplikace uvede, kterou zkoušku je nutné změřit a uložit. Jde o přítomnost obou zkoušek, nikoli vynucení minimálního počtu hodnot vzorku. Rozpracovanou výstupní kontrolu ve stavu Zakaleno lze dál průběžně ukládat.

1. Otevřete kamerový skener na `/bedny/skener/` nebo čtečku na `/bedny/skener-ctecka/`.
2. Načtěte kód z karty bedny, případně zadejte interní číslo ručně.
3. V detailu ověřte bednu a zvolte dostupnou operaci: navezení, označení jako zakalené, kontrolu nebo pohyb bedny.
4. Pro kontrolu přejděte do formuláře měření a uvolnění podle [samostatného návodu](manual_kontrola_beden.md).

Navezení přes sken je dostupné s `orders.mark_bedna_navezeno` nebo `orders.change_bedna` pro nepozastavené bedny ve stavech Přijato a K navezení. Označení jako zakalené vyžaduje `orders.scan_mark_bedna_zakaleno` a stav Navezeno nebo Ve zpracování. Další podmínky a povinné údaje kontroluje navazující formulář.

Zařazením do kroku Nakládání přejde bedna automaticky na Ve zpracování a vymaže se její skladová pozice. Opakovaný výskyt bedny v roštu představuje rozdělení jejího obsahu, nikoli vytvoření nové bedny.

Při potvrzení **Zakaleno přes sken** se zároveň vyhodnotí Tryskání podle všech šarží, ve kterých je bedna evidovaná:

- Pokud má každá šarže zahájený krok na typu pracoviště **Tryskač** obsahující přímo tuto bednu, nastaví se **Otryskaná**.
- Pokud jej mají pouze některé šarže, Tryskání se nezmění. U dosavadního stavu **Špinavá** se již na potvrzovací stránce nad tlačítkem zobrazí varování s čísly neotryskaných šarží. Označení jako Zakaleno je přesto možné; po uložení se varování znovu nezobrazuje.
- Pokud jej nemá žádná šarže nebo bedna nemá žádné šarže, Tryskání se ponechá bez varování.

Stačí zahájený krok; datum a čas konce nejsou podmínkou. Tryskání jiných beden v téže šarži se nezapočítává. Opakované řádky jedné šarže se počítají pouze jednou. Vyhodnocení proběhne při potvrzení změny; Rovnání se touto akcí nemění. Hromadné akce v administraci tuto automatiku nepoužívají.

Výrobní stav Zkontrolováno, uvolnění v kontrole a stav zinkování jsou samostatné údaje. Uložení kontroly automaticky nezmění výrobní stav ani zinkování. Při filtru Zkontrolováno se v seznamu zobrazuje také uvolnění kontroly.

Akce **Dokončit kontrolu bedny** je dostupná ve stavu **Zakaleno** a nastaví **Zkontrolováno**. Rovnání a Tryskání se vypočítají automaticky z uložených výsledků. Čistota NOK nastaví Špinavá; Čistota OK u dosavadní Špinavé/Otryskané nastaví Otryskaná, jinak Čistá. Prohyb po rovnání má přednost a nastaví Vyrovnaná/Křivá; jinak prohyb po TZ nastaví Rovná při vyhovujícím nebo oranžovém výsledku, Křivá při červeném. Rozhoduje celý vzorek a povolený počet křivých. Měření po TZ, standardní maximum a povolený počet křivých jsou pro potvrzení povinné; QS maximum není povinné. Na potvrzovací stránce se stavy již nevybírají ručně, pouze se zobrazí jejich výsledek.

U bedny ve stavu **Zkontrolováno** se Rovnání a Tryskání přepočítají při každém úspěšném uložení **výstupní kontroly**, i bez změny uvolnění. Samostatné tlačítko pro úpravu těchto stavů se nezobrazuje. Uložení samotného měření přepočet neprovede; kontrolu znovu uložte při změně vyhodnocení nebo technologických stavů. Chybějící podklady pro výpočet zabrání uložení opravy kontroly s vysvětlením ve formuláři. Výrobní stav a zinkování se nemění. Další podmínky uvádí [manuál kontroly](manual_kontrola_beden.md#5-potvrzení-výrobního-stavu).

Při opravě kontroly již zkontrolované bedny se červeně označují hodnoty odlišné od databáze a běžný odchod na jinou bednu nebo přehled je do uložení zablokovaný. Po měření se potvrzení vyžaduje pouze při změně vyhodnocení nebo výsledných technologických stavů; běžná oprava vrstvy či mechanických zkoušek se stejným vyhodnocením je nevyvolá. Uložení kontroly potvrdí také automatické Rovnání a Tryskání. Rozepsaná kontrola se při přechodu na měření stejné bedny zachová. Podrobnosti jsou v [manuálu kontroly](manual_kontrola_beden.md#neuložené-změny-a-potvrzení-po-měření).

## 13. Technická mapa (kde je logika v kódu)

- `orders/models.py`
  - `Bedna`
  - validace `Bedna.clean()`
  - přechodové volby `get_allowed_*_choices`

- `orders/admin.py`
  - `BednaAdmin`
  - dynamika listu (`get_list_display`, `get_list_editable`, `get_actions`)
  - polling změn

- `orders/filters.py`
  - `StavBednyFilter`
  - `TryskaniFilter`
  - `RovnaniFilter`
  - `ZinkovaniFilter`
  - další filtry pro zákazníka, prioritu, délku, pozastavení, notifikace

- `orders/actions.py`
  - stavové, technologické, tiskové, exportní a expediční akce pro bedny

- `orders/templates/admin/orders/bedna/change_list.html`
  - konfigurace pollingu změn v seznamu

- `orders/views.py`, `orders/forms.py`
  - skenování, kontrola bedny a jednotlivá měření
- `orders/services/filled_quality_cards_service.py`
  - tisk vyplněných KKK pro všechny zákazníky

[Zakázky](manual_zakazka.md) · [Kamiony](manual_kamion.md) · [Deník](manual_denik_pece.md) · [README](../README.md)
