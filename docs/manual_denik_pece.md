# Uživatelský manuál: Deník pece (aktuální stav)

Tento manuál popisuje aktuální fungování po úpravách v této větvi pro tyto části:
- Šarže (Sarze)
- Krok šarže (SarzeKrok)
- Deník pece (SarzeKrokBedna)

## 1. Jak jsou části navázané

1. Šarže je hlavička výrobního celku.
2. Každá šarže má jeden nebo více kroků šarže.
3. Každý krok šarže má řádky deníku pece.
4. Řádek deníku je konkrétní bedna nebo položka mimo databázi na konkrétním patře.

Pracovní pořadí v UI:
1. Založit šarži.
2. Otevřít nebo založit krok šarže.
3. Vyplnit řádky deníku pece.

## 2. Šarže (Sarze)

### 2.1 Co uživatel vidí

1. V seznamu šarží je filtr pouze Aktivní.
2. Při vytvoření šarže se pole datum založení nezobrazuje.
3. Na detailu šarže je standardní tlačítko Uložit.
4. Na formuláři přidání šarže je speciální tlačítko Uložit a přidat bedny do kroku šarže.

### 2.2 Co dělá systém

1. Datum založení se při vytvoření doplní automaticky na dnešní lokální datum.
2. Po použití tlačítka Uložit a přidat bedny do kroku šarže se provede přesměrování na první krok této šarže.
3. Pokud první krok nelze najít, systém uloží šarži a zobrazí varování.

## 3. Krok šarže (SarzeKrok)

### 3.1 Co uživatel vidí

1. Krok má pole zařízení, operátor a začátek.
2. Na formuláři vytvoření kroku tato pole mohou zůstat prázdná.
3. Na formuláři editace kroku jsou tato pole povinná.
4. Na detailu kroku je tlačítko Uložit a zpět do deníku pece.

### 3.2 Co dělá systém

1. Při novém kroku dopočítá pořadí automaticky v rámci šarže.
2. Pokud není vyplněné datum kroku, doplní se z data založení šarže.
3. U kroku se počítají metriky prodleva a takt, pokud jsou k dispozici potřebná data a zařízení je příslušného typu.

## 4. Deník pece (SarzeKrokBedna)

### 4.1 Co uživatel vidí

1. Seznam deníku zobrazuje řádky napříč kroky.
2. Sloupec Krok je odkaz na detail kroku.
3. Nahoře jsou rychlé odkazy:
- 1) Šarže: Přidat
- 2) Krok: Přidat
- 3) Deník pece: Přidat záznam
4. V seznamu je vizuální oddělení mezi různými kroky podle ID kroku.

### 4.2 Co dělá systém

1. Řádky se seskupují a oddělují podle odlišného kroku (ID SarzeKrok).
2. Validace řádku vyžaduje buď bednu, nebo popis mimo DB.
3. Nesmí být současně vyplněna bedna a data mimo DB.
4. Pokud je vyplněn popis mimo DB, musí být vyplněn i zákazník a zakázka mimo DB.
5. Je hlídaná unikátnost kombinace krok + bedna + patro.
6. U bedny z DB musí být bedna ve stavu skladem.

## 5. Akce pro kopírování do nového kroku

### 5.1 Akce z Deníku pece

Název: Vytvořit nový krok šarže z vybraných řádků deníku

Průběh:
1. Uživatel označí řádky deníku.
2. Systém ověří, že všechny řádky patří do jednoho zdrojového kroku.
3. Vytvoří nový krok stejné šarže.
4. U nového kroku záměrně nastaví zařízení, operátor a začátek na prázdno.
5. Zkopíruje vybrané řádky deníku.
6. Přesměruje na detail nového kroku.

### 5.2 Akce z Kroku šarže

Název: Vytvořit nový krok šarže jako kopii vybraného kroku

Průběh:
1. Uživatel označí právě jeden krok.
2. Systém vytvoří nový krok stejné šarže.
3. U nového kroku záměrně nastaví zařízení, operátor a začátek na prázdno.
4. Zkopíruje všechny řádky deníku ze zdrojového kroku.
5. Přesměruje na detail nového kroku.

## 6. Doporučený pracovní postup pro obsluhu

1. Otevřít Deník pece.
2. Založit šarži přes odkaz 1) Šarže: Přidat.
3. Uložit šarži tlačítkem Uložit a přidat bedny do kroku šarže.
4. V detailu kroku zkontrolovat data a doplnit řádky deníku.
5. Pokud je potřeba navazující krok, použít akci kopie z deníku nebo z kroku.
6. Na novém kroku doplnit zařízení, operátora a začátek.
7. Uložit krok tlačítkem Uložit a zpět do deníku pece.

## 7. Nejčastější chyby a řešení

1. Chyba při kopii z deníku: Vyberte záznamy pouze z jednoho kroku šarže.
Řešení: Označit pouze řádky ze stejného kroku.

2. Chyba validace: Musí být vyplněna buď bedna, nebo popis mimo DB.
Řešení: Vyplnit přesně jednu variantu.

3. Chyba validace: Nelze vyplnit současně bednu i pole mimo DB.
Řešení: Vyčistit jednu větev dat.

4. Chyba validace: Při popisu mimo DB chybí zákazník nebo zakázka mimo DB.
Řešení: Dovyplnit obě povinná pole.

5. Chyba duplicity kombinace krok + bedna + patro.
Řešení: Změnit patro nebo nepřidávat duplicitní řádek.

## 8. Kde je logika v kódu

1. Admin logika:
- orders/admin.py

2. Akce kopírování kroků:
- orders/actions.py

3. Datový model a validace:
- orders/models.py

4. Šablony tlačítek a odkazy:
- orders/templates/admin/orders/sarze/submit_line.html
- orders/templates/admin/orders/sarzekrok/submit_line.html
- orders/templates/admin/orders/sarzebedna/change_list.html

5. Seskupování řádků v deníku:
- orders/static/orders/js/admin_sarzebedna_group_separator.js
