"""Převzetí nově přijatých beden do atypického průběhu."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from orders.choices import RovnaniChoice, StavBednyChoice, TryskaniChoice, UvolneniKontrolyChoice, ZinkovaniChoice
from orders.models import KontrolaBedny
from orders.services.evidence_neshod_service import zaznamenat_neshodu


@transaction.atomic
def prevest_na_atypicky_prubeh(queryset, *, user):
    bedny = list(queryset.select_for_update(of=('self',)).order_by('pk'))
    if not bedny:
        raise ValidationError('Vyberte alespoň jednu bednu.')
    if any(bedna.stav_bedny != StavBednyChoice.PRIJATO or bedna.pozastaveno for bedna in bedny):
        raise ValidationError('Atypický průběh lze zahájit pouze u nepozastavených beden ve stavu Přijato.')
    if KontrolaBedny.objects.filter(bedna_id__in=[bedna.pk for bedna in bedny]).exists():
        raise ValidationError('Některá bedna již má kontrolu nebo měření. Akce je nepřepisuje.')

    for bedna in bedny:
        bedna.atypicky_prubeh = True
        bedna.stav_bedny = StavBednyChoice.ZKONTROLOVANO
        bedna.rovnat = RovnaniChoice.NEZADANO
        bedna.tryskat = TryskaniChoice.NEZADANO
        bedna.zinkovat = ZinkovaniChoice.NEZADANO
        bedna.fakturovat = False
        bedna.nefakturovat_kaleni = True
        bedna.nefakturovat_rovnani = True
        bedna.nefakturovat_tryskani = True
        bedna.nefakturovat_zinkovani = True
        bedna.full_clean()
        bedna._history_user = user
        bedna._change_reason = 'Převod na atypický průběh.'
        bedna.save()
        kontrola = KontrolaBedny(
            bedna=bedna, uvolneni=UvolneniKontrolyChoice.NESHODA,
            uvolneni_zmenil=user, uvolneni_zmeneno_at=timezone.now(),
        )
        kontrola._history_user = user
        kontrola.save()
        zaznamenat_neshodu(kontrola, previous_status=UvolneniKontrolyChoice.NEROZHODNUTO, user=user)
    return len(bedny)
