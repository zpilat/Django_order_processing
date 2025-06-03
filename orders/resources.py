from import_export import resources, fields

from decimal import Decimal

from django.utils.translation import gettext_lazy as _

from .models import Bedna, Zakazka

class BednaResourceEurotec(resources.ModelResource):
    """
    Resource pro import/export dat modelu Bedna z DL od firmy Eurotec.
    Používá se pro import dat z XLSX souboru do databáze.
    """
    hmotnost = fields.Field(column_name='Gewicht in kg')
    tara = fields.Field(column_name='Tara kg')
    material = fields.Field(column_name='Material')
    sarze = fields.Field(column_name='Material- charge')
    behalter_nr = fields.Field(column_name='Behälter-Nr.:')
    dodatecne_info = fields.Field(column_name='Sonder / Zusatzinfo')
    dodavatel_materialu = fields.Field(column_name='Lief.')
    vyrobni_zakazka = fields.Field(column_name='Fertigungs-auftrags Nr.')
 
    class Meta:
        model = Bedna
        fields = ('zakazka', 'hmotnost', 'tara', 'material', 'sarze', 'behalter_nr', 'dodatecne_info',
                  'dodavatel_materialu', 'vyrobni_zakazka')

    def __init__(self, *args, kamion=None, **kwargs):
        """
        Inicializuje resource s odkazem na kamion, ke kterému budou bedny přiřazeny.
        :param kamion: Instance modelu Kamion, ke kterému budou bedny přiřazeny.
        """
        if not kamion:
            raise ValueError("Kamion musí být zadán pro import bedny.")
        
        super().__init__(*args, **kwargs)
        self.kamion = kamion
        self.zakazky_cache = {}

    def before_import(self, dataset, using_transactions=True, dry_run=False, **kwargs):
        """
        Před importem:
        - Ukončí zpracování při prvním prázdném řádku (např. bez 'Artikel- nummer').
        - Ověří přítomnost všech povinných polí na každém řádku.
        """
        mandatory_fields = [
            'Artikel- nummer', 'Abmessung', 'n. Zg. / as drg', 'Kopf', 'Bezeichnung',
            'Vorgang+', 'Be-schich-tung', 'Ober- fläche',
            'Gewicht in kg', 'Tara kg', 'Material', 'Material- charge',
            'Behälter-Nr.:', 'Sonder / Zusatzinfo', 'Lief.', 'Fertigungs-auftrags Nr.'
        ]

        cleaned_rows = []
        for i, row in enumerate(dataset.dict):
            first_value = str(row.get('Artikel- nummer', '')).strip()

            if not first_value:
                # Ukonči import na prázdném řádku
                break

            # Zkontroluj povinná pole
            for field in mandatory_fields:
                if field not in row or not str(row[field]).strip():
                    raise ValueError(f"Řádek {i + 1} postrádá povinné pole: {field}")

            cleaned_rows.append(row)

        # Přepiš dataset na vyčištěné řádky
        dataset.dict = cleaned_rows                

    def before_import_row(self, row, **kwargs):
        """
        Před importem každého řádku zkontroluje, zda existuje zakázka s daným číslem.
        Pokud neexistuje, vytvoří novou zakázku a uloží ji do cache.
        Ve sloupci rozmer rozdělí hodnotu na průměr a délku v datovém formátu decimal a uloží je do sloupců prumer a delka.
        :param row: Řádek dat z XLSX souboru.
        """
        artikl = row['Artikel- nummer']
        prumer, delka = [Decimal(x) for x in row['Abmessung'].replace(',', '.').split('x')]      

        if artikl not in self.zakazky_cache:
            zakazka = Zakazka.objects.create(
                kamion_prijem=self.kamion,
                artikl=artikl,
                prumer=prumer,
                delka=delka,
                predpis=row['n. Zg. / as drg'],
                typ_hlavy=row['Kopf'],
                popis=row['Bezeichnung'],
                prubeh=row['Vorgang+'],
                vrstva=row['Be-schich-tung'],
                povrch=row['Ober- fläche']
            )
            self.zakazky_cache[artikl] = zakazka

        row['zakazka'] = self.zakazky_cache[artikl].pk
