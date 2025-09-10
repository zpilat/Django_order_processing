# Správa zakázek HPM HEAT SK – prezentace


## 1) Co je to za systém
- Interní webová aplikace pro zpracování zakázek, beden a kamionů
- Postaveno na Django (Python) + Django Admin + Simple History
- Cíl: zrychlit příjem, zpracování a expedici, omezit chyby, podpořit zpětnou sledovatelnost


## 2) Klíčové přínosy
- Rychlý import dodacích listů z Excelu (náhled + validace)
- Automatizované vytváření zakázek a beden, výpočty hmotností
- Jednoznačný workflow stavů (bedny: Přijato → K navezení → … → K expedici/Expedováno)
- Tisk karet beden, karet kvality, dodacích listů a proforma faktur
- Silné filtrování a hromadné akce v administraci
- Historie změn (audit) přes Simple History


## 3) Datový model (zjednodušeně)
- Zákazník, Odběratel
- Kamion (příjem/výdej) → obsahuje Zakázky
- Zakázka → obsahuje Bedny
- Předpis (technologická skupina), Typ hlavy, Pozice (sklad)


## 4) Import z Excelu (kamion – příjem)
- Načtení pouze prvních 200 řádků pro zrychlení importu, zvýraznění chyb/varování
- Normalizace dat (artikl, průměr×délka, typ hlavy, předpis)
- Atomic save, session buffer pro dočasný soubor
- Automatické rozdělení hmotnosti do beden (zaokrouhlení, poslední kus vyrovnání)


## 5) Práce v administraci
- Přehledné seznamy s užitečnými sloupci (Ø, délka, skupina TZ, priorita, datum)
- Inline editace vybraných polí dle stavu a oprávnění
- Odkazy na související objekty (kamiony, předpisy, typy hlav)
- Chytré fieldsety podle stavu (expedováno vs. skladem, Eurotec extra pole)


## 6) Workflow a hromadné akce
- Stavové akce pro bedny (K navezení, Navezeno, Do zpracování, Zakaleno, Zkontrolováno, K expedici…)
- Rovnání (Rovná, Křivá, Rovná se, Vyrovnaná), Tryskání (Čistá, Špinavá, Otryskána)
- Akce seskupené v optgroup pro rychlejší orientaci
- Kontxktové skrývání nepovolených akcí dle filtrů


## 7) Tisk / export
- Karty beden (interní), Karty kontroly kvality
- Dodací list kamionu, Proforma faktura
- PDF výstupy připravené k tisku


## 8) Bezpečnost a audit
- Oprávnění na citlivé operace (expedované/pozastavené položky)
- Historie změn přes Simple History


## 9) UI detaily pro efektivitu
- Zkrácené popisy s title tooltipy
- Automatická čísla beden, přehledné značení kompletnosti zakázky
- Zobrazení využití pozic (progress bar)


## 10) Technologie a provoz
- Python 3.11, Django, Pandas, OpenPyXL
- SQLite v základu (PostgreSQL pro produkci)
- Jednoduché nasazení (venv, collectstatic)

## 11) Shrnutí
- Systém pokrývá end‑to‑end proces: příjem → sklad → zpracování → expedice
- Důraz na rychlost, přesnost a auditovatelnost
- Flexibilní a rozšiřitelný základ na Django
