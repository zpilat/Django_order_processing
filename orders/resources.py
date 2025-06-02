from import_export import resources
from .models import Bedna, Zakazka

class BednaResourceEurotec(resources.ModelResource):
    def __init__(self, *args, kamion=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.kamion = kamion
        self.zakazky_cache = {}

    def before_import_row(self, row, **kwargs):
        cislo = row['cislo_zakazky']
        if cislo not in self.zakazky_cache:
            zakazka = Zakazka.objects.create(
                kamion=self.kamion,
                cislo=cislo,
                nazev=row['nazev_zakazky'],
            )
            self.zakazky_cache[cislo] = zakazka

        row['zakazka'] = self.zakazky_cache[cislo].pk

    class Meta:
        model = Bedna
        fields = ("nazev_dilu", "mnozstvi", "zakazka")
