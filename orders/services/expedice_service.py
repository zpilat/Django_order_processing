import datetime
import logging
from dataclasses import dataclass, field

from django.db import transaction

from ..choices import StavBednyChoice, RovnaniChoice, TryskaniChoice, ZinkovaniChoice, KamionChoice
from ..models import Zakazka, Bedna, Kamion
from .exceptions import ServiceValidationError
from .logging_utils import resolve_actor_name, build_log_context

logger = logging.getLogger("orders")


@dataclass
class ExpediceResult:
    created_kamiony: list[str] = field(default_factory=list)
    moved_bedny_count: int = 0
    touched_zakazky_count: int = 0
    warnings: list[str] = field(default_factory=list)


def validate_expedice_preconditions(*, bedny_qs=None, zakazky_qs=None, check_only_k_expedici=True):
    errors = []

    if bedny_qs is not None:
        if not bedny_qs.exists():
            errors.append("Není vybrána žádná bedna.")
        elif check_only_k_expedici and bedny_qs.exclude(stav_bedny=StavBednyChoice.K_EXPEDICI).exists():
            errors.append("Všechny vybrané bedny musí být ve stavu K_EXPEDICI.")

    if zakazky_qs is not None and not zakazky_qs.exists():
        errors.append("Není vybrána žádná zakázka.")

    if bedny_qs is not None:
        bedny_ke_kontrole = bedny_qs.filter(stav_bedny=StavBednyChoice.K_EXPEDICI)
    elif zakazky_qs is not None:
        bedny_ke_kontrole = Bedna.objects.filter(zakazka__in=zakazky_qs, stav_bedny=StavBednyChoice.K_EXPEDICI)
    else:
        bedny_ke_kontrole = Bedna.objects.none()

    if bedny_ke_kontrole.exists():
        if (
            bedny_ke_kontrole.exclude(rovnat__in=[RovnaniChoice.ROVNA, RovnaniChoice.VYROVNANA]).exists()
            or bedny_ke_kontrole.exclude(tryskat__in=[TryskaniChoice.CISTA, TryskaniChoice.OTRYSKANA]).exists()
            or bedny_ke_kontrole.exclude(zinkovat__in=[ZinkovaniChoice.NEZINKOVAT, ZinkovaniChoice.UVOLNENO]).exists()
        ):
            errors.append(
                "Pro expedici musí být rovnání Rovná/Vyrovnaná, tryskání Čistá/Otryskaná a zinkování Nezinkovat/Uvolněno."
            )

    return errors


def _clone_zakazka_for_expedice(zakazka):
    exclude = {"id", "kamion_vydej", "expedovano"}
    zakazka_data = {}
    puvodni_zakazka = zakazka.puvodni_zakazka or zakazka
    for field in Zakazka._meta.fields:
        if field.name in exclude:
            continue
        if field.is_relation and getattr(field, "many_to_one", False):
            zakazka_data[field.attname] = getattr(zakazka, field.attname)
        else:
            zakazka_data[field.name] = getattr(zakazka, field.name)

    zakazka_data["puvodni_zakazka_id"] = puvodni_zakazka.id
    return Zakazka.objects.create(**zakazka_data)


@transaction.atomic
def expedice_zakazek_do_existujiciho_kamionu(*, zakazky_qs, kamion_vydej, actor=None):
    result = ExpediceResult()
    actor_name = resolve_actor_name(actor)

    for zakazka in zakazky_qs:
        bedny = zakazka.bedny.all()
        bedny_k_expedici = bedny.filter(stav_bedny=StavBednyChoice.K_EXPEDICI)
        bedny_ne_k_expedici = bedny.exclude(stav_bedny=StavBednyChoice.K_EXPEDICI)

        if not bedny_k_expedici.exists():
            result.warnings.append(f"Zakázka {zakazka} nemá žádné bedny ve stavu K_EXPEDICI.")
            continue

        if bedny_ne_k_expedici.exists():
            nova_zakazka = _clone_zakazka_for_expedice(zakazka)
            for bedna in bedny_k_expedici:
                bedna.zakazka = nova_zakazka
                bedna.stav_bedny = StavBednyChoice.EXPEDOVANO
                bedna.save()
                result.moved_bedny_count += 1

            nova_zakazka.kamion_vydej = kamion_vydej
            nova_zakazka.expedovano = True
            nova_zakazka.save()
            result.touched_zakazky_count += 1
        else:
            for bedna in bedny_k_expedici:
                bedna.stav_bedny = StavBednyChoice.EXPEDOVANO
                bedna.save()
                result.moved_bedny_count += 1

            zakazka.kamion_vydej = kamion_vydej
            zakazka.expedovano = True
            zakazka.save()
            result.touched_zakazky_count += 1

    logger.info(
        f"Expedice zakázek do existujícího kamionu dokončena ({build_log_context(actor=actor_name, kamion=kamion_vydej, bedny=result.moved_bedny_count, zakazky=result.touched_zakazky_count)})."
    )
    return result


@transaction.atomic
def expedice_beden_do_existujiciho_kamionu(*, bedny_qs, kamion_vydej, actor=None):
    result = ExpediceResult()
    actor_name = resolve_actor_name(actor)

    zakazky = Zakazka.objects.filter(bedny__in=bedny_qs).distinct()
    for zakazka in zakazky:
        vybrane_bedny = bedny_qs.filter(zakazka=zakazka)
        vybrane_ids = list(vybrane_bedny.values_list("pk", flat=True))

        zbyvajici_ids = list(zakazka.bedny.exclude(pk__in=vybrane_ids).values_list("pk", flat=True))
        zbyvajici_bedny = Bedna.objects.filter(pk__in=zbyvajici_ids)

        if zbyvajici_bedny.exists():
            nova_zakazka = _clone_zakazka_for_expedice(zakazka)
            for bedna in vybrane_bedny:
                bedna.stav_bedny = StavBednyChoice.EXPEDOVANO
                bedna.zakazka = nova_zakazka
                bedna.save()
                result.moved_bedny_count += 1

            nova_zakazka.kamion_vydej = kamion_vydej
            nova_zakazka.expedovano = True
            nova_zakazka.save()
            result.touched_zakazky_count += 1
        else:
            for bedna in vybrane_bedny:
                bedna.stav_bedny = StavBednyChoice.EXPEDOVANO
                bedna.save()
                result.moved_bedny_count += 1

            zakazka.kamion_vydej = kamion_vydej
            zakazka.expedovano = True
            zakazka.save()
            result.touched_zakazky_count += 1

    logger.info(
        f"Expedice beden do existujícího kamionu dokončena ({build_log_context(actor=actor_name, kamion=kamion_vydej, bedny=result.moved_bedny_count, zakazky=result.touched_zakazky_count)})."
    )
    return result


@transaction.atomic
def expedice_beden_do_noveho_kamionu(*, bedny_qs, zakaznici, odberatel, actor=None, today=None):
    if not bedny_qs.exists():
        raise ServiceValidationError("Není vybrána žádná bedna.")

    result = ExpediceResult()
    today = today or datetime.date.today()

    for zakaznik in zakaznici:
        kamion = Kamion.objects.create(
            zakaznik=zakaznik,
            datum=today,
            prijem_vydej=KamionChoice.VYDEJ,
            odberatel=odberatel,
        )
        result.created_kamiony.append(kamion.cislo_dl)

        bedny_zakaznika = bedny_qs.filter(zakazka__kamion_prijem__zakaznik=zakaznik)
        sub_result = expedice_beden_do_existujiciho_kamionu(
            bedny_qs=bedny_zakaznika,
            kamion_vydej=kamion,
            actor=actor,
        )
        result.moved_bedny_count += sub_result.moved_bedny_count
        result.touched_zakazky_count += sub_result.touched_zakazky_count
        result.warnings.extend(sub_result.warnings)

    return result


@transaction.atomic
def expedice_zakazek_do_noveho_kamionu(*, zakazky_qs, zakaznici, odberatel, actor=None, today=None):
    if not zakazky_qs.exists():
        raise ServiceValidationError("Není vybrána žádná zakázka.")

    result = ExpediceResult()
    today = today or datetime.date.today()

    for zakaznik in zakaznici:
        kamion = Kamion.objects.create(
            zakaznik=zakaznik,
            datum=today,
            prijem_vydej=KamionChoice.VYDEJ,
            odberatel=odberatel,
        )
        result.created_kamiony.append(kamion.cislo_dl)

        zakazky_zakaznika = zakazky_qs.filter(kamion_prijem__zakaznik=zakaznik)
        sub_result = expedice_zakazek_do_existujiciho_kamionu(
            zakazky_qs=zakazky_zakaznika,
            kamion_vydej=kamion,
            actor=actor,
        )
        result.moved_bedny_count += sub_result.moved_bedny_count
        result.touched_zakazky_count += sub_result.touched_zakazky_count
        result.warnings.extend(sub_result.warnings)

    return result
