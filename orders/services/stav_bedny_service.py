from django.db.models import Exists, OuterRef

from orders.choices import TryskaniChoice, TypZarizeniChoice
from orders.models import Sarze, SarzeKrokBedna


def vyhodnotit_tryskani_pri_zakaleni(bedna):
    """Vrátí nový stav tryskání a neotryskané šarže pro případné varování.

    Počítá zahájené i dokončené kroky Tryskače obsahující přímo tuto bednu.
    Samotné vyhodnocení nic neukládá; volající uloží stav spolu se Zakalením.
    """
    zahajene_tryskani = SarzeKrokBedna.objects.filter(
        bedna=bedna,
        krok__sarze_id=OuterRef('pk'),
        krok__zarizeni__typ_zarizeni=TypZarizeniChoice.TRYSKAC,
    )
    sarze = list(
        Sarze.objects.filter(kroky__krok_bedny__bedna=bedna)
        .annotate(otryskana=Exists(zahajene_tryskani))
        .order_by('cislo_sarze', 'pk')
        .distinct()
    )
    neotryskane = [item for item in sarze if not item.otryskana]
    if sarze and not neotryskane:
        return TryskaniChoice.OTRYSKANA, []
    if (
        bedna.tryskat == TryskaniChoice.SPINAVA
        and neotryskane
        and len(neotryskane) < len(sarze)
    ):
        return bedna.tryskat, neotryskane
    return bedna.tryskat, []
