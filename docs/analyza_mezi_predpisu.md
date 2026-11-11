# Převod textových požadavků předpisů na číselné meze

Analýza vývojové databáze PostgreSQL ze dne 11. 11. 2026 zahrnuje **226 předpisů**, z toho **217 aktivních** a **83 přiřazených alespoň jedné zakázce**. Zahrnuje i neaktivní předpisy, protože na některé stále odkazují starší zakázky. Stejné textové požadavky byly ověřeny po obnově devu z produkčního dumpu `orders_prod_auto_20261111_090001.dump`. Samotný náhled nemění databázi; výslovně spuštěný převod doplňuje standardní meze a nové záznamy historie předpisů.

## 1. Připravená pole

Každá skupina obsahuje `*_min`, `*_max` a `*_qsmax`:

| Zkouška | Pole | Jednotka |
| --- | --- | --- |
| Ohyb | `ohyb_min`, `ohyb_max`, `ohyb_qsmax` | ° |
| Krut | `krut_min`, `krut_max`, `krut_qsmax` | Nm |
| Tvrdost povrchu | `povrch_min`, `povrch_max`, `povrch_qsmax` | HV podle původní metodiky |
| Tvrdost jádra | `jadro_min`, `jadro_max`, `jadro_qsmax` | HV podle původní metodiky |
| Vrstva | `vrstva_min`, `vrstva_max`, `vrstva_qsmax` | mm |

Jde o nepovinná desetinná pole se čtyřmi desetinnými místy, shodně s přesností zadávaných měření. Vrstva má jednu sadu mezí společnou pro původní `vrstva` i `vrstva_2`. Prázdná mez není nula. Maxima QS zůstávají k ručnímu doplnění; žádné se neodvozují z textu ani ze standardního maxima.

Migrace `0247_predpis_ciselne_meze_zkousek` přidává tato pole do `Predpis` a jeho historie, všechna s hodnotou `NULL`. Neobsahuje datový převod. Současná kontrola, výběr uvolnění, důvody neshody a tisk KKK zůstávají u dosavadních pravidel a textových požadavků.

## 2. Výsledek návrhu převodu

Po zohlednění níže potvrzených významů jsou počty za všechny předpisy následující:

| Zkouška | Navržené číselné meze | Prázdné / výslovně bez meze | Jen metodika bez meze | Ruční kontrola |
| --- | ---: | ---: | ---: | ---: |
| Ohyb | 224 | 2 | 0 | 0 |
| Krut | 223 | 3 | 0 | 0 |
| Tvrdost jádra | 204 | 22 | 0 | 0 |
| Tvrdost povrchu | 219 | 7 | 0 | 0 |
| Vrstva | 37 | 171 | 17 | 1 |

U aktivních předpisů jde o **215** návrhů pro Ohyb, **214** pro Krut, **198** pro Jádro, **213** pro Povrch a **33** pro Vrstvu. Veškeré aktivní číselné požadavky mají po potvrzení výjimek návrh převodu. Sedmnáct aktivních předpisů ROT má pouze pokyn `průběh tvrdosti`: ten je platným pokynem k měření, ale sám neudává číselnou mez vrstvy v mm.

## 3. Pravidla převodu

Převod má vyhodnocovat celý formát požadavku, nikoli jen vyhledat první číslo v textu:

| Původní zápis | Minimum | Maximum |
| --- | ---: | ---: |
| `min. 45°`, `min. 45˚`, `min. 45` | 45 | prázdné |
| `45° - 180°` | 45 | 180 |
| `min. 28,0 Nm`, `min. 28Nm` | 28 | prázdné |
| `25,3 – 31,0 Nm` | 25,3 | 31 |
| `350 – 550 HV0,3` | 350 | 550 |
| `min. 600 HV0,3` | 600 | prázdné |
| `350 - 500 HV5 (HV10)` | 350 | 500 |
| `CHD 550 HV0,3` + druhý řádek `0,1 – 0,3 mm` | 0,1 | 0,3 |
| `min. 0,15 mm` + druhý řádek `CHD 550 HV1` | 0,15 | prázdné |
| Prázdný text, `-`, `neměří se` | prázdné | prázdné |

Desetinné čárky se převedou na přesná desetinná čísla, pomlčky a značky stupňů se sjednotí pro rozpoznání. Původní text se nemění.

U tvrdostí nejsou čísla v označení `HV0,3`, `HV1`, `HV5` nebo `HV10` dalšími mezemi. U vrstvy se nepoužije číslo `550` z `CHD 550 HV0,3` jako maximum vrstvy: musí se dohledat skutečný požadavek v mm v některém ze dvou polí. Žádné převody mezi metodami tvrdosti se neprovádějí; označení a pokyny zůstávají v původních textech.

## 4. Potvrzené výjimky

Významy byly potvrzeny uživatelem při přípravě převodu dne 11. 11. 2026:

- Samostatné hodnoty vrstvy `0,15 mm` a `0,3 mm` představují **minimum**, maximum zůstane prázdné. Týká se EUR `00002_Ø6,3` (ID 461), `02412_Ø7,5` (ID 617) a `02466_Ø7,5` (ID 618).
- Jádro `300 – 400 (350 - 500) HV0,3` u EUR `00829_Ø7,4` (ID 604) a `00829_Ø7,5` (ID 605) má použít **nové meze 350–500**, v souladu s doprovodným popisem. Nejde o převzetí širšího rozsahu 300–500 ani o odvození QS meze.
- Vrstva `min. 0,2 - 0,4 mm` u EUR `00432_Ø7,5` (ID 577) znamená **minimum 0,2 a maximum 0,4 mm**.

U neaktivního EUR `00829_Ø7,5` (ID 569) lze z textu `CHD 450 HV0,3min. 0,1 mm` oddělit jednoznačné minimum **0,1 mm**, protože za označením metody následuje výslovné `min.`. Metodika se neinterpretuje jako další mez.

## 5. Zbývající nejednoznačný předpis

Neaktivní EUR `00002_Ø6,3_starý` (ID 568) obsahuje vrstvu `CHD 400 HV0,30,3 mm`. Dvě navazující desetinná čísla nejsou jednoznačně oddělená, proto se do číselných polí nenavrhuje hodnota. Předpis není v analyzované databázi přiřazen žádné zakázce. Případné doplnění musí vycházet z původního podkladu.

## 6. Doporučené naplnění a další použití

1. Přidat prázdná pole schématovou migrací a zachovat původní texty.
2. Revidovat návrh převodu po jednotlivých předpisech. Přehled vytvořený při této analýze obsahuje zákazníka, ID, název, aktivitu, počet zakázek, původní texty, navržené min/max a vysvětlení převodu.
3. Naplnění provést samostatným krokem nad skutečnými texty cílové databáze. Předpisy se mohou mezi dev a produkcí lišit; pro následné naplnění nepoužívat samotné ID z devu jako důkaz správného obsahu. Ověřit text a zákazníka, nezapisovat nejednoznačné hodnoty a nepřepisovat již ručně doplněné meze.
4. Maxima QS doplnit ručně a ověřit rozsahy. Další krok teprve propojí číselné meze s kontrolou, automatickými důvody a případnými odchylkami.

Převod je dostupný jako samostatný management příkaz, nikoli jako automatická datová migrace. Na Windows z kořene projektu:

```powershell
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py doplnit_meze_predpisu --csv tmp\meze_predpisu_navrh.csv
.\venv\Scripts\python.exe manage.py doplnit_meze_predpisu --apply --csv tmp\meze_predpisu_zapis.csv
```

Na produkci se stejnými soubory a aktivním virtuálním prostředím použijte `python manage.py ...`. Nejprve zkontrolujte náhled proti cílovým datům, potom spusťte variantu s `--apply`. Náhled i zápis vždy znovu vyhodnocují skutečné texty v připojené databázi. Příkaz neimportuje hodnoty z CSV ani nepřebírá primární klíče z devu. Potvrzené výjimky se rozpoznávají podle zákazníka, názvu a textu předpisu; změněný či neznámý formát ponechá k ruční kontrole.

Zápis zamkne předpisy, nepřepisuje žádnou již vyplněnou standardní dvojici min/max (ani částečnou) a nemění maxima QS, původní texty, aktivitu nebo vazby. Stav `hotovo` znamená, že již uložená dvojice odpovídá návrhu; `ponechano` znamená rozdílné nebo částečně ručně vyplněné meze. Obojí zůstává beze změny. Nejednoznačné zápisy (`rucne`), chybějící hranice (`bez_meze`) a samotná metodika (`metodika`) se nenaplňují. CSV uvádí původní i navržené meze a vysvětlení pro každou zkoušku. Všechny zápisy i nové historické záznamy jsou v jedné transakci; chyba zruší celý převod. Opakované spuštění nezměněná data znovu neukládá.

Schématová migrace a převod jsou oddělené: po `migrate` jsou pole stále prázdná. Při převodu vznikne pro každý změněný předpis jeden nový záznam historie s důvodem „Doplnění číselných mezí z textových požadavků předpisu.“ Staré historické záznamy zůstanou prázdné. Výsledky kontrol beden, jejich měření a snapshoty neshod se nepřepočítávají.

### Ověření a provedení v devu 11. 11. 2026

Po obnově uvedeného produkčního dumpu prošla migrace 0247 a náhled převodu. Nejprve byl převod proveden v transakci a po ověření vrácen zpět, následně skutečně zapsán do devu. Doplnil **224 z 226 předpisů**, celkem **907 standardních dvojic min/max** podle tabulky výše; některé dvojice mají pouze jednu vyplněnou hranici. Ostatní případy zůstaly prázdné podle svého významu. Maxima QS zůstala prázdná.

Původních **910 historických záznamů** se nezměnilo; vzniklo **224 nových záznamů** s důvodem převodu. Kontrola porovnala také původní pole a vazby předpisů a obsah kontrol beden, jejich měření a snapshotů neshody před převodem a po něm. Opakované spuštění neprovedlo další zápisy. PostgreSQL test ověřuje i celou cestu ze schématu 0246 přes 0247 a naplnění mezí, zachování původní historie a opakované spuštění; další testy ověřují vrácení celé transakce při chybě zápisu.

Pro budoucí uvolňování hodnot **pod minimem** by samotné `qsmax` nestačilo; bylo by potřeba doplnit i dolní mez pro QS, například `qsmin`. Nynější změna přidává pouze uživatelem požadovaná minima, maxima a maxima QS.

Při zapojení do hodnocení je potřeba zachovat domluvené pravidlo, že nové požadavky nemají zpětně zneplatňovat dokončené kontroly. Samotné přidání prázdných polí toto hodnocení nezapíná. Nové technologické revize používaných předpisů se mají zakládat odděleně podle [manuálu číselníků](manual_ciselniky.md#nová-revize-používaného-předpisu).
