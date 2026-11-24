# Export podkladů pro OMEGU — SPX a EUR

Společná akce **Exportovat podklady pro OMEGU** vybírá pravidla podle zákazníka výdejového kamionu. Nyní podporuje **SPX** a **EUR**, ostatní zákazníky odmítne. Čte databázi a používá stejné příznaky a výpočty jako proforma; PDF se neparsuje. V OMEZE se soubor načítá jako **dodací list**, ze kterého účetní převezme položky do nové faktury.

**Stav ověření:** generátor a administrace jsou testované na PostgreSQL. Uživatel 16. listopadu 2026 potvrdil správné načtení výrobní zakázky do pole Číslo a rozměru do pole Vlastný text v používané OMEZE. Toto potvrzení se týká mapování těchto dvou údajů; samo nepotvrzuje celé párování partnera, účetní nastavení ani výsledný tisk faktury. Při první zkoušce v jiné instalaci použijte testovací kopii firmy. Stažení souboru není potvrzením jeho importu.

Rozšíření EUR ověřené v aplikaci ještě vyžaduje první praktickou zkoušku v OMEZE, zejména převzetí souhrnů tryskání podle sazeb, každý jako `1 ks`.

## 1. Rozsah pilotu

Pro všechny zákazníky se export zastaví, pokud má některá bedna s hlavním **Fakturovat = Ano** také **Fakturovat zinkování = Ano**. Kontrola probíhá před výběrem pravidel zákazníka a platí také pro SPX. Samostatný výpočet ceny a export zinkování zatím není zaveden. Nefakturovaná bedna tuto blokaci nezpůsobí.

Na všech položkách exportu se podle zadaného účetního nastavení výslovně předává **Zaúčtovanie položky → Typ sumy = Osv**. Platí to pro všechny zákazníky, nyní SPX i EUR, a také pro každý souhrn tryskání. Po importu ověřte tento údaj už na dodacím listu a následně při převzetí do faktury.

### SPX — kalení po bednách

- Jeden výdejový kamion zákazníka se zkratkou **SPX**, s proformou po bednách.
- Pouze kalení. Pokud má některá fakturovaná bedna zapnuté rovnání se stavem Vyrovnaná nebo tryskání se stavem Otryskaná, export ji nesmí opomenout a celý export odmítne. Samotné výchozí nastavení zákazníka export neomezuje.
- Jedna položka za bednu s hlavním **Fakturovat = Ano** a **Fakturovat kalení = Ano**.
- Bedny musí být expedované a mít kladnou hmotnost, výrobní zakázku, artikl a popis. Zákazník příjmu musí odpovídat zákazníkovi výdeje.
- Cena EUR/kg pochází z aktuálního ceníku stejně jako na proformě. Chybějící, nekladná nebo nejednoznačná cena export blokuje. Cena každé bedny se zaokrouhlí na dvě desetinná místa HALF_UP a teprve potom se sčítá.
- Objednávky a artikly jsou text včetně počátečních nul. Nepodporované znaky, řídicí znaky a překročené délky polí export blokují; text se potichu nezkracuje.

Další operace SPX se zatím neexportují. Při budoucím rozšíření budou mít samostatné řádky s příslušnou hmotností a cenou.

Výpočet částky bedny a její zahrnutí do kalení sdílí export s ostatní fakturací aplikace. Součet zaokrouhlených řádků se zapisuje do hlavičky dokladu; při dvou bednách po 100,1 kg a sazbě 1,05 EUR/kg je to 210,22 EUR. Fakturace po zakázkách by dala 210,21 EUR a export SPX ji proto odmítá, místo aby změnil seskupení a zaokrouhlení. Viz [pravidla sazeb a částek](manual_bedna.md#ceníkové-sazby-a-účtované-částky).

### EUR — kalení po zakázkách a souhrny tryskání podle sazeb

- Jeden výdej EUR, zákazník musí mít **Proforma po bednách = Ne**. Přepnutí na fakturaci po bednách export zastaví.
- Za každou zakázku s účtovaným kalením vznikne jeden řádek. Hmotnost zahrnuje stejné bedny jako kalení na proformě: hlavní **Fakturovat = Ano** a **Fakturovat kalení = Ano**. Nefakturované bedny ani bedny účtované jen za jinou operaci se do hmotnosti kalení nezahrnou.
- Názov = `zakazka.zkraceny_popis, prumerxdelka`, např. `HSPT SK DAG T40, 8x400`. Koncové desetinné nuly se vynechávají, nenulová desetinná část zůstává s čárkou, např. `8,5x220`.
- Číslo = `zakazka.artikl` jako text do 20 znaků včetně počátečních nul. Cudzí názov a Vlastný text jsou prázdné. Jednotka je `kg`, cena je aktuální jednotková cena kalení dané zakázky. Částka se zaokrouhluje až za celou zakázku.
- Před exportem se kontroluje **cena tryskání všech beden se stavem Otryskaná v kamionu**, včetně nefakturovaných beden nebo beden s vypnutou fakturací tryskání. Sazba musí být jednoznačná a kladná. Není omezena na 0,15 EUR/kg ani na pevný seznam povolených cen; používá se aktuální ceník.
- Do částky tryskání vstupují jen bedny podle pravidel proformy: hlavní Fakturovat, Fakturovat tryskání a stav Otryskaná. Bedny se seskupí podle stejné sazby EUR/kg napříč zakázkami. **Pro každou použitou sazbu vznikne samostatný souhrnný řádek `1 ks`**, jehož jednotková cena i částka jsou součtem tryskání příslušných zakázek z proformy. Řádky jsou seřazeny podle sazby vzestupně. Číslo, Cudzí názov a Vlastný text jsou prázdné.
- Názov souhrnného řádku je např. `Sandblasting of screws (18639kg x 0,15EUR)`, další může být `Sandblasting of screws (250kg x 0,25EUR)` nebo `Sandblasting of screws (100kg x 0,50EUR)`. Měna v názvu se zapisuje textem EUR. Hmotnost v názvu je součet pouze fakturovaných otryskaných beden s danou sazbou. Sazba bez účtovaných beden nevytvoří řádek; bez účtovaného tryskání nevznikne žádný souhrn.
- Součet tryskání se počítá jako na proformě: každá zakázka se zaokrouhlí zvlášť a až potom se částky sečtou do skupiny podle sazby. Součet všech skupin odpovídá celkovému tryskání na proformě. Hmotnost skupiny se znovu nenásobí sazbou. Dvě zakázky po 0,1 kg znamenají při sazbě 0,15 EUR/kg celkem 0,04 EUR, nikoli 0,03 EUR.
- Nenulová částka rovnání na proformě zastaví export. Zapnuté rovnání bez skutečně provedené operace samo o sobě neblokuje. Proforma s chybějícími nebo neplatnými požadovanými cenami export také blokuje.
- Zákazník příjmu musí odpovídat zákazníkovi výdeje, účtované bedny musí být expedované a mít kladnou hmotnost. Zinkování blokuje společná kontrola popsaná výše.

## 2. Stažení podkladu

1. V administraci otevřete **Kamiony** a nastavte filtr **Výdej**.
2. Vyberte právě jeden kamion SPX nebo EUR.
3. Spusťte **Exportovat podklady pro OMEGU** ve skupině Tisk dokladů.
4. V náhledu porovnejte pole položek, množství, jednotky, ceny a součty s proformou. U EUR má každý souhrn tryskání množství 1 a jednotku ks; součet kg kalení v patičce tyto kusy nezahrnuje.
5. Klikněte na **Stáhnout podklad pro OMEGU (.txt)**. Soubor má název `omega_spx_<cislo-vydeje>.txt` nebo `omega_eur_<cislo-vydeje>.txt`.

Akce vyžaduje aktivní staff účet s přístupem k zobrazení kamionu (`view_kamion`, případně obecné `change_kamion`, které zobrazení také dovoluje). Náhled a stažení znovu čtou aktuální data; změna ceníku nebo beden mezi kroky může změnit soubor. Použitý TXT uschovejte.

Export nemění bedny ani kamion, neukládá historii fakturace a nevystavuje fakturu. Opakovaný export má stejné číslo podkladu, ale aktuální obsah. Zamezení duplicit při importu se nastavuje v OMEZE.

## 3. První ověření v OMEZE

1. Připravte testovací kopii firmy s existujícím partnerem SPAX nebo příslušným partnerem EUR. Porovnejte jeho název s názvem zákazníka v aplikaci. Model zákazníka aplikace nemá IČO ani IČ DPH; soubor předává název, nikoli nový číselník partnerů.
2. V **Firma → Nastavenia → Všeobecné nastavenia → Prechod/Import/Eshop** ověřte porovnávací kritéria partnera a dokladu. Ověřte také evidenci a výchozí číselnou řadu dodacích listů. Pilot jejich kódy do souboru nezadává; převzetí nelze potvrdit bez zkoušky v OMEZE.
3. Spusťte **Firma → Import → Import z textového súboru**, vyberte TXT a použijte přidávání neexistujících dokladů. Prohlédněte výsledek a případný `.LOG`.
4. V **Fakturácia → Dodacie listy** ověřte partnera, číslo, datum, počet položek, kg, ceny a součet. V záložce **Nastavenie** zkontrolujte **Zaokrúhlenie výslednej sumy = 0,01**, **Zaokrúhlenie sumy každej položky = 0,01** a **Spôsob zaokrúhlenia = Prirodzene**. Na položkách v nastavení prodejní ceny mají být také dvě desetinná místa a přirozené zaokrouhlení. Číslo a datum pocházejí z výdejového kamionu. Pro tyto volné položky nevytvářejte další skladové výdejky.
5. V **Fakturácia → Odoslané faktúry** založte fakturu pro správného partnera a u přidávání položek vyberte **z dodacieho listu**. Přeneste všechny položky příslušného podkladu.
6. Ověřte obsah a tisk faktury, měnu, DPH, data, splatnost a číslování. Není ověřeno, že OMEGA při převzetí nahradí účetní hodnoty podkladu nastavením faktury. Pilotní TXT nese EUR, kurz 1 a technický nulový rozpis DPH; nejde o určení daňového režimu finální faktury.
7. Před opakováním importu zjistěte, zda už podklad existuje nebo byl použit na faktuře. Při chybě uchovejte LOG a snímek nastavení; aplikace úspěch importu nezná.

Rozhodující je správná výsledná faktura bez přepisování identifikátorů, nikoli samotné přijetí TXT.

## 4. Formát a zobrazení položek

Soubor vychází ze [specifikace KROS ImportExport_28_00_2025.xls](https://ftpkros.sk/files/documents/general/omega/2025/FAQ/ImportExport_28_00_2025.xls), list **Fakturacia**. Používá Windows-1250 bez BOM, tabulátory a konce řádků CRLF.

- `R00`, `T01`: fakturace.
- Jedna hlavička `R01`: číslo výdeje, název partnera, datum výdeje, součty, **typ 2 — dodací list**, EUR a kurz 1.
- `R02`: položky podle pravidel zákazníka, vždy **typ V — volná položka**, s technickou skupinou DPH `0`. SPX má řádek na bednu; EUR řádek na zakázku kalení a případně souhrnný řádek tryskání za každou použitou sazbu.

Export SPX i EUR výslovně nastavuje zaokrouhlení výsledné sumy i sumy každé položky na **0,01** a způsob **Prirodzene**. Nastavení posílá také přímo na každém řádku, včetně souhrnů tryskání. Pozice jsou číslované od 1 včetně `R01` nebo `R02`:

| Záznam | Pozice | Pole OMEGY | Hodnota | Význam |
| --- | --- | --- | --- | --- |
| R01 | 61 | `C221_Zaokruhlenie` | `-2` | Výsledná suma na dvě desetinná místa |
| R01 | 62 | `C222_SposobZaokruhlenia` | `3` | Přirozené zaokrouhlení |
| R01 | 64 | `C225_ZaokruhleniePolozky` | `-2` | Suma každé položky na dvě desetinná místa |
| R02 | 45 | `C105_Zaokruhlenie` | `-2` | Prodejní cena položky na dvě desetinná místa |
| R02 | 46 | `C106_SposobZaokruhlenia` | `3` | Přirozené zaokrouhlení položky |

Hlavička má nyní 64 polí a položka 46; mezilehlá nepoužitá pole jsou prázdná. Starší TXT končily na pozicích 43 a 19 a nastavení zaokrouhlení neposílaly. Uživatel zjistil, že OMEGA již na takto importovaném dodacím listu nastavila zaokrouhlení prodejní ceny na celé jednotky; po převzetí do faktury se pak položky zobrazovaly nesprávně, ačkoli součet byl správný. Nové nastavení je nutné ověřit po importu dodáku i po převzetí do faktury. Již importované doklady změna exportu automaticky neopraví. Výpočet částek a součtů v aplikaci se nemění.

Mapování **SPX** vychází ze snímku editace položky dodaného uživatelem. Názvy sloupců sestavy se liší od názvů polí v editoru. Pozice se počítají od 1 včetně `R02`:

| Sloupec faktury | Pole položky OMEGY | Pozice R02 | Příklad |
| --- | --- | --- | --- |
| Order no. | Číslo: Číslo karty/služby (`C030_KodPolozky`) | 18 | `4501539341` |
| Item no. | Cudzí názov (`C130_CudziNazov`) | 11 | `0641000801600` |
| Description | Názov (`C109_Nazov`) | 2 | `SPAX-3 SMK TSP40 TGW` |
| Dimension | Vlastný text: Volná položka (`C115_Volne`) | 19 | `8x160` |
| Quantity | Množstvo | 3 | `234.0` |
| UM | MJ | 4 | `kg` |
| Unit price without VAT | Jednotková cena bez DPH | 5 | `1.06` |
| Typ sumy | Typ DPH (`C021_Kod(T033_TypCiastka)`) | 30 | `Osv` |

Pole 30 specifikace označuje jako „typ DPH“, v editoru OMEGY odpovídá poli **Zaúčtovanie položky → Typ sumy**. Pro všechny položky obsahuje text `Osv` podle nastavení dodaného uživatelem; dříve bylo prázdné a OMEGA doplňovala vlastní výchozí hodnotu. Sazba DPH v poli 6 zůstává `0`. Změna se uplatní v nově exportovaných TXT, již importované doklady automaticky neopraví. Ověření přijetí kódu Osv v cílové OMEZE je součástí kontroly nového importu.

Názov obsahuje pouze popis. Číslo objednávky, artikl, rozměr ani označení operace se k němu nepřipojují. Výrobní zakázka bedny (`vyrobni_zakazka`) se předává jako text do pole 18, nejvýše 20 znaků, včetně počátečních nul. Pole 17 (JKPOV) zůstává prázdné. Artikl zůstává textem s počátečními nulami v poli Cudzí názov. Číslo výdeje v hlavičce dokladu je samostatný údaj a přenáší se dál.

**Potvrzené přiřazení objednávky a rozměru:** výrobní zakázka se zapisuje do pole 18 (`C030_KodPolozky`, text do 20 znaků), rozměr do pole 19 (`C115_Volne`, text do 50 znaků). Uživatel 16. listopadu 2026 potvrdil správné načtení obou údajů do Číslo a Vlastný text i u volné položky typu V. Specifikace pole 18 označuje jako číslo karty/služby; v tomto použití obsahuje výrobní zakázku bedny. Pole JKPOV se pro rozměr nepoužívá. Výsledný tisk a převzetí do faktury zůstávají samostatnou kontrolou.

Rozměr delší než 50 znaků se odmítne, nikdy se nezkracuje. Při přechodu ze starších zkušebních souborů se mění význam pole 19 na rozměr (dříve obsahovalo artikl nebo objednávku). Nové soubory nejprve ověřte na kopii firmy; u již importovaných podkladů neprovádějte slepé přepsání. Hlavička dodacího listu, výběr beden, ceny a zaokrouhlení se touto změnou nemění.

**EUR** používá pozice: 2 = Názov, 3 = množství, 4 = MJ, 5 = jednotková cena, 18 = Číslo (artikl zakázky u kalení). Pozice 11 a 19 jsou prázdné na všech řádcích. U souhrnného tryskání je prázdná i pozice 18. Pozice 17 (JKPOV) je prázdná u obou zákazníků. Částka v hlavičce je součtem částek všech exportovaných řádků.

KROS popisuje [import TXT](https://podpora.kros.sk/migration/faq/import-%C3%BAdajov-z-in%C3%A9ho-softv%C3%A9ru-pre-rok-2025) i [převzetí položek do faktury](https://akademia.kros.sk/faq/ekonomika-a-podnikanie/suhrnna-faktura-a-hromadne-pridanie-poloziek/). Změny formátu nebo cílové instalace nejprve ověřte na kopii firmy.
