# Repository instructions for GitHub Copilot (Django projekt)

> Tyto pokyny mají formovat **Copilot Chat** i návrhy kódu v rámci tohoto repozitáře. Přednostně používej češtinu a respektuj níže uvedené konvence a preference.

---

## 1) Jazyk, styl, formát výstupů

- **Vždy odpovídej česky**.
- V kódu piš **jasné, krátké komentáře česky**. Docstringy přidávej ke testům i veřejným funkcím/metodám.
- U větších změn navrhni celé soubory nebo **kompletní minimální funkční příklady**, ne pouze útržky.
- Když si nejsi jistý detaily, **zvol bezpečný rozumný default**, výchozí předpoklady napiš na začátek jako seznam „Předpoklady“.

## 2) Tech stack & verze

- **Python 3.11+**, **Django 5.2** (nové idiomy upřednostňuj, např. `render()` a moderní CBV patterns).
- Frontend: **Bootstrap 5** (kde dává smysl), **HTMX** pro interaktivní formuláře bez full reloadu.
- Templaty formulářů: využívej **field templates** (např. `text_field.html`) a nepoužívej `{{ form.as_p }}`.
- Testy: `django.test.TestCase` (nebo `pytest-django` pokud je k dispozici), **přidávej docstringy**.
- Lint/format: **Black**, **isort**, **Ruff** (navrhni konfiguraci, pokud chybí).

## 3) Doménový model (slovník)

- Klíčové entity: `Bedna`, `Zakazka`, `Kamion`, `Pozice`, `AuditLog`.
- Stav bedny: `StavBednyChoice` obsahuje např. `PRIJATO`, `K_NAVEZENI`, `NAVEZENO`, `EXPEDOVANO`.
- V názvech proměnných používej běžná latinková česká slova bez diakritiky (např. `cislo_bedny`, `stav_bedny`).

## 4) Django Admin – konvence

- **list_display**: preferuj stručné a užitečné sloupce. Pole v `list_editable` musí být současně i v `list_display` a nesmí být první sloupec.
- **Editace FK v changelistu**: pro `pozice` použij `list_editable=("pozice",)`; zvaž `autocomplete_fields=("pozice",)`. Pokud je klasický select, nastav `empty_label` na `"-"`.
- **Ikony u FK (RelatedFieldWidgetWrapper)**: pokud je nechceme, vypni `can_add_related`, `can_change_related`, `can_delete_related`, `can_view_related` na wrapperu místo ručního odstraňování.
- **Výkon**: přidávej `list_select_related=("pozice",)` a u M2M `prefetch_related`.
- **Admin akce**: v hromadných akcích používej `transaction.atomic()` a u zápisu více entit zamykej přes `select_for_update()`.

### Ukázka – potlačení ikon u FK `pozice`

```python
# v Admin třídě
from django.contrib.admin.widgets import RelatedFieldWidgetWrapper

def formfield_for_dbfield(self, db_field, request, **kwargs):
    formfield = super().formfield_for_dbfield(db_field, request, **kwargs)
    if db_field.name == "pozice" and isinstance(formfield.widget, RelatedFieldWidgetWrapper):
        for attr in ("can_add_related", "can_change_related", "can_delete_related", "can_view_related"):
            if hasattr(formfield.widget, attr):
                setattr(formfield.widget, attr, False)
    return formfield
```

## 5) Validace & business logika

- V modelu `Bedna` při ukládání platí:
  - Pokud je `stav_bedny` v `{K_NAVEZENI, NAVEZENO}`, pozice musí být vyplněná.
  - Při jiných stavech se pozice vynuluje.
- Preferuj validace v `clean()` + bezpečnost v `save()` (idempotentně). Neprováděj **mutace stavu na GET**.

## 6) Vlastní akce „označit k navezení“ – standard

- Formset pro výběr `pozice` na každou `Bedna` ve stavu `PRIJATO`.
- Volitelné přepnutí: **zahrnout všechny** `Bedna` `PRIJATO` ze stejných `Zakazka` (nejen explicitně vybrané).
- Po odeslání validuj kapacity `Pozice`, loguj varování, ale ulož akci atomicky.

## 7) HTMX – formulářové interakce

- Vzory:
  - „Formulář zůstává viditelný po odeslání“ – při validaci znovu vykresli fragment s chybami pod formulář, při úspěchu zobraz výsledek **pod** formulářem.
  - U dynamických seznamů (např. `Zakazka` → `Bedny`) renderuj částečné šablony a používej `hx-target` + `hx-swap`.

## 8) Testy – konvence

- Struktura testů podle typů: **modely / formuláře / view / admin**.
- Každý test s **docstringem** krátce vysvětlujícím případ užití.
- U admin akcí testuj:
  - filtr stavu (`PRIJATO`),
  - zamykání a `transaction.atomic()`,
  - změnu stavu `K_NAVEZENI` a přiřazení `pozice`,
  - chování při překročení kapacity.

## 9) Databáze & prostředí

- Vývoj: **SQLite** je OK. Produkce: **PostgreSQL**. `DATABASES` nastavuj per‑environment (např. přes proměnné prostředí a `django-environ`).
- Migrace: drž je malé a srozumitelné; při refaktorech přidej datové migrace s `RunPython`.

## 10) Logování & audit

- Používej standardní `logging` s vlastním loggerem pro doménu (např. `orders.actions`).
- Loguj důležité změny stavů a exporty (CSV, PDF). Chyby posílej na `ERROR`, očekávané konflikty/porušení kapacity jako `WARNING`.

## 11) Výkon & ORM

- Před načítáním tabulek do adminu používej `only()/defer()` podle potřeby.
- Pro sumace/počty využívej `annotate()`, `aggregate()` a `values()`; dávej pozor na `group by` implicitní chování.

## 12) Bezpečnost

- Nepředpokládej, že uživatel je staff/superuser; u admin akcí respektuj **objektová oprávnění**.
- Žádné citlivé informace do frontendu; validuj data z formsetů (zejména `bedna_id`).

## 13) Dokumentace & Git

- U větších změn navrhni úpravu `README.md` (EN) a stručný `CHANGELOG.md`.
- Commity: smysluplné zprávy v angličtině, imperativ ("Add", "Fix", "Refactor").

---

## 14) Zkratky pro Copilot Chat (interpretuj volně)

- **„Napiš admin akci pro označení k navezení“** → navrhni akci s formsetem, kapacitami, `transaction.atomic()` a `select_for_update()` + šablonu.
- **„Přidej list\_editable pro pozice“** → uprav `list_display`, `list_editable`, vypni Related ikony, nastav `empty_label`.
- **„Udělej testy pro export CSV v AuditLogListView“** → vytvoř integr. test s filtrováním podle roku/měsíce/typu, ověř hlavičky a obsah.
- **„Optimalizuj queryset pro dashboard beden“** → přidej `select_related`, `annotate`, `values`, případně `Prefetch`.

---

## 15) Co nedělat

- Neprováděj změny DB při GET (mimo jasně deklarované idempotentní operace).
- Nespouštěj náročné výpočty synchronně v requestu, pokud hrozí timeout (navrhni alternativu nebo asynchronní řešení).
- Nevracej polovičaté útržky kódu bez kontextu.

---

**Cíl:** Zrychlit každodenní práci v tomto repozitáři, držet jednotný styl a minimalizovat dotazování. Pokud něco není jasné, zvol rozumný default a napiš „Předpoklady“ na začátek odpovědi.

