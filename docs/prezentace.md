# Správa zakázek HPM HEAT SK – prezentace

## Co aplikace pokrývá

Interní webová aplikace propojuje příjem kamionů, zakázky a bedny s nakládáním šarží, tepelným zpracováním, kontrolou kvality a expedicí. Administrace slouží pro evidenci a hromadné operace; provozní obrazovky podporují práci přímo u pracoviště.

## Klíčové přínosy

- Import dodacích listů z Excelu s náhledem a validací omezuje ruční přepisování.
- Čísla beden, kódy na kartách a historie změn umožňují dohledat průchod výrobou.
- Rychlé založení šarže s bednami zjednodušuje zadání pater a rozložení roštu.
- Měření, uvolnění a důvody neshod se evidují u konkrétní bedny.
- Přehledy nakládání, pracovišť a kontroly ukazují aktuální práci a čekající položky.
- PDF karty, průvodky a výdejové doklady navazují na uložené údaje.

## Datový model

| Agenda | Návaznost |
| --- | --- |
| Zákazník a předpis | Určují parametry zakázky, zkoušek a související pravidla. |
| Kamion příjem | Obsahuje přijaté zakázky a jejich bedny. |
| Zakázka | Sdružuje bedny stejného zadání. |
| Bedna | Má výrobní a technologické stavy, kontrolu a měření. |
| Šarže | Sdružuje výrobní kroky na pracovištích. |
| Krok a deník | Určují pracoviště, čas, operátora, patra a položky roštu. |
| Kamion výdej | Sdružuje expedované zakázky a výdejové doklady. |

Deník podporuje také položky mimo databázi pro zpracování železa. Bedna může být rozdělená do více položek jednoho nebo více pater.

## Příjem a importy

1. Založení kamionu příjem.
2. Nahrání XLSX dodacího listu podle formátu zákazníka.
3. Kontrola náhledu, chyb a varování.
4. Potvrzení atomického importu zakázek a beden.
5. Doplnění předpisů a potřebných údajů a přijetí na sklad.

Chemická měření se importují samostatně z JSON exportů Vanta nad kamionem příjem s bednami. Náhled ukáže přiřazení a problémy; zpracované soubory se archivují.

## Výroba a nakládání

Výrobní stavy beden pokrývají Nepřijato, Přijato, K navezení, Navezeno, Ve zpracování, Zakaleno, Zkontrolováno, K expedici a Expedováno. Tryskání, rovnání a zinkování mají vlastní stavy.

Rychlé založení začíná výběrem čísla pracoviště 1–6. Otevřená šarže umožňuje pokračovat; volné pracoviště nabízí založení nové. Obsluha zadá přípravek, začátek, operátora a bedny do pater roštu. Po dokončení doplní datum a čas konce; další průchod eviduje nový krok šarže.

Kamerový skener nebo čtečka otevře bednu či šarži a příslušné provozní operace. Nabídka akcí vychází ze stavu a oprávnění obsluhy.

## Kontrola kvality

- Zápis ohybu, krutu, prohybu po jednotlivých operacích, tvrdosti a vrstvy.
- Zobrazení požadavků předpisu a zákaznických mezí prohybu.
- Výstupní kontrola čistoty, uložení a počtů křivých vrutů.
- Rozhodnutí Neshoda, Uvolněno nebo Uvolněno s odchylkou a evidence autora rozhodnutí.
- Přehled čekajících kontrol a aktuálních neshod s důvody a filtry.

Uložení výsledků a potvrzení výrobního stavu Zkontrolováno jsou samostatné operace. Barevné zvýraznění hodnot podporuje rozhodování obsluhy.

## Expedice a dokumenty

Expedovat lze zakázky nebo vybrané bedny do nového či existujícího kamionu výdej. Nepřipravená část zakázky se může oddělit do nové zakázky.

Tisk zahrnuje karty beden, prázdné KKK, vyplněné KKK pro EUR, průvodky šarží, dodací listy, certifikáty a proforma faktury. Přehled Bedny k navezení má vlastní tisk a PDF export.

## Technologie, oprávnění a provoz

Aplikace používá Django 5.2, pandas, openpyxl, WeasyPrint a django-simple-history. PostgreSQL je standardem pro produkci i lokální vývoj. Historie a oprávnění pokrývají citlivé operace včetně úprav expedovaných a pozastavených beden; zápis měření chrání kontrola souběžných změn.

Provozní nastavení a postup instalace jsou v [README](../README.md), konkrétní ochrany v [bezpečnostním přehledu](security.md).

## Návody pro obsluhu

Pro společný postup použijte [Provozní tahák](provozni_tahak.md) a [Průchod šarže výrobou](manual_pruchod_sarze.md).

[Bedny](manual_bedna.md) · [Zakázky](manual_zakazka.md) · [Kamiony](manual_kamion.md) · [Deník](manual_denik_pece.md) · [Rychlé založení šarže](manual_rychle_zalozeni_sarze.md) · [Kontrola beden](manual_kontrola_beden.md)
