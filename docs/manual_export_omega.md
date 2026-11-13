# Export podkladů pro OMEGU — pilot SPX

Export přenáší položky k fakturaci včetně ceny kalení. Čte databázi a používá stejné příznaky a výpočet jako proforma po bednách; PDF se neparsuje. V OMEZE se soubor načítá jako **dodací list**, ze kterého účetní převezme položky do nové faktury.

**Stav ověření:** generátor a administrace jsou testované na PostgreSQL. Přijetí konkrétní instalací OMEGY, párování partnera a převzetí do výsledné faktury je nutné ověřit v testovací kopii firmy. Stažení souboru není potvrzením jeho importu.

## 1. Rozsah pilotu

- Jeden výdejový kamion zákazníka se zkratkou **SPX**, s proformou po bednách.
- Pouze kalení. Pokud má některá fakturovaná bedna zapnuté rovnání se stavem Vyrovnaná nebo tryskání se stavem Otryskaná, export ji nesmí opomenout a celý export odmítne. Samotné výchozí nastavení zákazníka export neomezuje. Jiní zákazníci zatím nejsou podporovaní.
- Jedna položka za bednu s hlavním **Fakturovat = Ano** a **Fakturovat kalení = Ano**.
- Bedny musí být expedované a mít kladnou hmotnost, výrobní zakázku, artikl a popis. Zákazník příjmu musí odpovídat zákazníkovi výdeje.
- Cena EUR/kg pochází z aktuálního ceníku stejně jako na proformě. Chybějící, nekladná nebo nejednoznačná cena export blokuje. Cena každé bedny se zaokrouhlí na dvě desetinná místa HALF_UP a teprve potom se sčítá.
- Objednávky a artikly jsou text včetně počátečních nul. Nepodporované znaky, řídicí znaky a překročené délky polí export blokují; text se potichu nezkracuje.

Pro budoucí rozšíření platí **jedna operace = jeden řádek** s její fakturovanou hmotností a cenou. Pilot další operace neexportuje.

## 2. Stažení podkladu

1. V administraci otevřete **Kamiony** a nastavte filtr **Výdej**.
2. Vyberte právě jeden kamion SPX.
3. Spusťte **Exportovat podklady pro OMEGU (SPX, kalení)** ve skupině Tisk dokladů.
4. V náhledu porovnejte objednávky, artikly, popisy, rozměry, kg, ceny EUR/kg a součet s proformou.
5. Klikněte na **Stáhnout podklad pro OMEGU (.txt)**. Soubor má název `omega_spx_<cislo-vydeje>.txt`.

Akce vyžaduje aktivní staff účet s přístupem k zobrazení kamionu (`view_kamion`, případně obecné `change_kamion`, které zobrazení také dovoluje). Náhled a stažení znovu čtou aktuální data; změna ceníku nebo beden mezi kroky může změnit soubor. Použitý TXT uschovejte.

Export nemění bedny ani kamion, neukládá historii fakturace a nevystavuje fakturu. Opakovaný export má stejné číslo podkladu, ale aktuální obsah. Zamezení duplicit při importu se nastavuje v OMEZE.

## 3. První ověření v OMEZE

1. Připravte testovací kopii firmy s existujícím partnerem SPAX. Porovnejte jeho název s názvem zákazníka v aplikaci. Model zákazníka aplikace nemá IČO ani IČ DPH; soubor předává název, nikoli nový číselník partnerů.
2. V **Firma → Nastavenia → Všeobecné nastavenia → Prechod/Import/Eshop** ověřte porovnávací kritéria partnera a dokladu. Ověřte také evidenci a výchozí číselnou řadu dodacích listů. Pilot jejich kódy do souboru nezadává; převzetí nelze potvrdit bez zkoušky v OMEZE.
3. Spusťte **Firma → Import → Import z textového súboru**, vyberte TXT a použijte přidávání neexistujících dokladů. Prohlédněte výsledek a případný `.LOG`.
4. V **Fakturácia → Dodacie listy** ověřte partnera, číslo, datum, počet položek, kg, ceny a součet. Číslo a datum pocházejí z výdejového kamionu. Pro tyto volné položky nevytvářejte další skladové výdejky.
5. V **Fakturácia → Odoslané faktúry** založte fakturu pro správného partnera a u přidávání položek vyberte **z dodacieho listu**. Přeneste všechny položky příslušného podkladu.
6. Ověřte obsah a tisk faktury, měnu, DPH, data, splatnost a číslování. Není ověřeno, že OMEGA při převzetí nahradí účetní hodnoty podkladu nastavením faktury. Pilotní TXT nese EUR, kurz 1 a technický nulový rozpis DPH; nejde o určení daňového režimu finální faktury.
7. Před opakováním importu zjistěte, zda už podklad existuje nebo byl použit na faktuře. Při chybě uchovejte LOG a snímek nastavení; aplikace úspěch importu nezná.

Rozhodující je správná výsledná faktura bez přepisování identifikátorů, nikoli samotné přijetí TXT.

## 4. Formát a zobrazení položek

Soubor vychází ze [specifikace KROS ImportExport_28_00_2025.xls](https://ftpkros.sk/files/documents/general/omega/2025/FAQ/ImportExport_28_00_2025.xls), list **Fakturacia**. Používá Windows-1250 bez BOM, tabulátory a konce řádků CRLF.

- `R00`, `T01`: fakturace.
- Jedna hlavička `R01`: číslo výdeje, název partnera, datum výdeje, součty, **typ 2 — dodací list**, EUR a kurz 1.
- Jeden `R02` na fakturovanou bednu: název, kg, jednotka `kg`, cena, technická skupina DPH `0`, **typ V — volná položka**, artikl v poli Volná položka.

Standardní položka nemá samostatné sloupce Order no. a Dimension jako dosavadní tisková sestava SPAX. Název proto zachovává všechny údaje, například:

`Kalení | Obj. 4501539341 | Art. 0641000801600 | SPAX-3 SMK TSP40 TGW | 8x160`

Artikl je také v samostatném volném označení položky. Nepoužívá se jako číslo skladové karty nebo služby. Dosavadní tiskové rozložení faktury se automaticky nereprodukuje; ověřte délku a zalomení názvu v používané sestavě.

KROS popisuje [import TXT](https://podpora.kros.sk/migration/faq/import-%C3%BAdajov-z-in%C3%A9ho-softv%C3%A9ru-pre-rok-2025) i [převzetí položek do faktury](https://akademia.kros.sk/faq/ekonomika-a-podnikanie/suhrnna-faktura-a-hromadne-pridanie-poloziek/). Změny formátu nebo cílové instalace nejprve ověřte na kopii firmy.
