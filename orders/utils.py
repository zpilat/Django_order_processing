from .models import Kamion
from .resources import BednaResourceEurotec
from tablib import Dataset

def get_verbose_name_for_column(model, field_chain):
    """
    Vrátí verbose_name (popisek) i pro zanořené (řetězené) pole včetně FK (např. 'zakazka_id__komplet').
    """
    fields = field_chain.split('__')
    current_model = model
    for i, field_name in enumerate(fields):
        field = current_model._meta.get_field(field_name)
        if i == len(fields) - 1:
            return field.verbose_name.capitalize()
        current_model = field.remote_field.model
    return field_chain  # fallback

def import_dodaci_list_eurotec(csv_file, zakaznik, datum_prijmu, cislo_dl):
    dataset = Dataset().load(csv_file.read().decode('utf-8'), format='csv')

    kamion = Kamion.objects.create(
        zakaznik=zakaznik,
        datum_prijmu=datum_prijmu,
        cislo_dl=cislo_dl,
    )

    resource = BednaResourceEurotec(kamion=kamion)
    result = resource.import_data(dataset, dry_run=False)
    return result