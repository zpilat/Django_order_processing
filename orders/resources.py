from import_export import resources, fields

from decimal import Decimal

from django.utils.translation import gettext_lazy as _

from .models import Bedna, Zakazka

class BednaResourceEurotec(resources.ModelResource):
    """
    Resource pro import/export dat modelu Bedna z DL od firmy Eurotec.
    Používá se pro import dat z XLSX souboru do databáze.
    """
    hmotnost = fields.Field(column_name='Gew. Brutto')
    tara = fields.Field(column_name='Tara')
    material = fields.Field(column_name='Material')
    sarze = fields.Field(column_name='Mat.Charge')
    behalter_nr = fields.Field(column_name='Behälter Nr.')
    dodatecne_info = fields.Field(column_name='Sonder / Zusatzinfo')
    dodavatel_materialu = fields.Field(column_name='Lief.')
    vyrobni_zakazka = fields.Field(column_name='Fertigungs-auftrags Nr.')
    operator = fields.Field(column_name='Operator')

    class Meta:
        model = Bedna
        fields = ('zakazka_id', 'hmotnost', 'tara', 'material', 'sarze', 'behalter_nr', 'dodatecne_info',
                  'dodavatel_materialu', 'vyrobni_zakazka', 'operator')

    def __init__(self, *args, kamion=None, **kwargs):
        """
        Inicializuje resource s odkazem na kamion, ke kterému budou bedny přiřazeny.
        :param kamion: Instance modelu Kamion, ke kterému budou bedny přiřazeny.
        """
        if not kamion:
            raise ValueError("Kamion instance must be provided.")
        
        super().__init__(*args, **kwargs)
        self.kamion = kamion
        self.zakazky_cache = {}

    def before_import(self, dataset, using_transactions=True, dry_run=False, **kwargs):
        """
        Před importem dat zkontroluje, zda všechny řádky jsou vyplněny a obsahují potřebná pole.
        Povinná pole zakázky jsou: artikl, rozměr, predpis, typ_hlavy, popis, prubeh, vrstva, povrch.
        Povinná pole bedny jsou: hmotnost, tara, material, sarze, behalter_nr, dodatecne_info,
        dodavatel_materialu, vyrobni_zakazka, operator.
        Dále zkontroluje, zda datum uložené v kamionu odpovídá datu ve všech řádcích.
        :param dataset: Dataset obsahující data pro import.
        """
        for row in dataset.dict:
            if 'datum' not in row or row['datum'] != self.kamion.datum:
                raise ValueError(f"Řádek {row} neodpovídá datu kamionu {self.kamion.datum}.")

        mandatory_fields = [
            'Artikel', 'Abmessung', 'Zeichn.', 'Kopf', 'Bezeichnung', 'Vorgang+', 'Schicht', 'Oberfläche',
            'Gew. Brutto', 'Tara', 'Material', 'Charge', 'Behälter_nr', 'Sonder / Zusatzinfo',
            'Lief.', 'Fertigungs-auftrags Nr.', 'Operator'
        ]

        for row in dataset.dict:
            for field in mandatory_fields:
                if field not in row or not row[field]:
                    raise ValueError(f"Řádek {row} postrádá povinné pole: {field}")

    def before_import_row(self, row, **kwargs):
        """
        Před importem každého řádku zkontroluje, zda existuje zakázka s daným číslem.
        Pokud neexistuje, vytvoří novou zakázku a uloží ji do cache.
        Ve sloupci rozmer rozdělí hodnotu na průměr a délku v datovém formátu decimal a uloží je do sloupců prumer a delka.
        :param row: Řádek dat z XLSX souboru.
        """
        artikl = row['Artikel']
        prumer, delka = [Decimal(x) for x in row['Abmessung'].replace(',', '.').split('x')]      

        if artikl not in self.zakazky_cache:
            zakazka = Zakazka.objects.create(
                kamion_id=self.kamion,
                artikl=artikl,
                prumer=prumer,
                delka=delka,
                predpis=row['Zeichn.'],
                typ_hlavy=row['Kopf'],
                popis=row['Bezeichnung'],
                prubeh=row['Vorgang+'],
                vrstva=row['Schicht'],
                povrch=row['Oberfläche']
            )
            self.zakazky_cache[artikl] = zakazka

        row['zakazka'] = self.zakazky_cache[artikl].pk
