from django.contrib.auth.mixins import LoginRequiredMixin, PermissionRequiredMixin
from django.contrib.auth.decorators import login_required, permission_required
from django.contrib.auth import logout as auth_logout
from django import forms as django_forms
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.views.generic import ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView
from django.views.generic.detail import DetailView
from django.views.decorators.http import require_POST
from django.urls import reverse, reverse_lazy
from django.db.models import Q, Max, Sum, Count, F, Exists, OuterRef, Subquery, DecimalField, ExpressionWrapper, Value
from django.db.models.functions import Coalesce
from django.core.exceptions import PermissionDenied
from django.utils.translation import gettext_lazy as _
import django.utils.timezone as timezone
from datetime import datetime, timedelta, time, date
import calendar
import uuid
from django.db import transaction
from django.contrib import messages
from django.contrib.staticfiles import finders
from django.http import HttpResponseBadRequest, HttpResponse, JsonResponse
from django.conf import settings
from django.utils.text import slugify
from django.utils.http import url_has_allowed_host_and_scheme
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django_user_agents.utils import get_user_agent

from .utils import get_verbose_name_for_column, utilita_tisk_dl_a_proforma_faktury, format_cislo_bedny, format_skupina_TZ, build_fake_skupina_TZ_annotation
from .models import (
    Bedna, Zakazka, Kamion, Zakaznik, TypHlavy, Predpis, Odberatel, Cena, Pozice, PoziceZakazkaOrder,
    Sarze, SarzeKrok, SarzeKrokBedna
)
from .forms import (
    RychleZalozeniSarzeForm,
    SarzeKrokActionInitForm,
    SarzeScanKrokChangeForm,
    get_sarze_krok_patro_formset,
)
from .actions import _build_sarzekrokbedna_preview_rows, _create_sarzekrok_and_copy_rows
from .choices import (
    StavBednyChoice, RovnaniChoice, TryskaniChoice, PrioritaChoice, KamionChoice, TypZarizeniChoice,
    ZinkovaniChoice, STAV_BEDNY_ROZPRACOVANOST, STAV_BEDNY_SKLADEM
)
from weasyprint import HTML, CSS

import logging
logger = logging.getLogger('orders')


def _safe_return_url(request, fallback_url):
    next_url = request.POST.get('next') or request.GET.get('next') or request.META.get('HTTP_REFERER')
    if next_url and url_has_allowed_host_and_scheme(
        next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return next_url
    return fallback_url


def _build_provozni_prehledy_context(user):
    return {
        'db_table': 'home',
    }


def _otevreny_krok_pracoviste(cislo_pracoviste):
    """
    Vrátí otevřený krok šarže pro dané pracoviště, pokud existuje.
    """
    return (
        SarzeKrok.objects
        .filter(
            sarze__isnull=False,
            sarze__cislo_pracoviste=cislo_pracoviste,
            zarizeni__typ_zarizeni=TypZarizeniChoice.NAKLADANI,
            konec__isnull=True,
        )
        .order_by('-pk')
        .first()
    )


def _cislo_pracoviste_z_query(request):
    try:
        cislo_pracoviste = int(request.GET.get('cislo_pracoviste'))
    except (TypeError, ValueError):
        return None

    if cislo_pracoviste < 1 or cislo_pracoviste > 6:
        return None
    return cislo_pracoviste


def _redirect_invalid_rychle_zalozeni(request, message):
    messages.error(request, message)
    return redirect('provozni_prehledy')


def _redirect_invalid_rychle_zalozeni_patro(request, krok, message):
    messages.error(request, message)
    return redirect('rychle_zalozeni_sarze_prehled', krok_id=krok.pk)


def _redirect_invalid_rychle_zalozeni_krok(request, krok, message, target):
    if target == 'prehled':
        return _redirect_invalid_rychle_zalozeni_patro(request, krok, message)
    return _redirect_invalid_rychle_zalozeni(request, message)


def _validate_rychle_zalozeni_krok(request, krok, action_label, invalid_target):

    cislo_pracoviste = krok.sarze.cislo_pracoviste
    if cislo_pracoviste is None or cislo_pracoviste < 1 or cislo_pracoviste > 6:
        logger.warning(
            f"Uživatel {request.user} se pokusil {action_label} šarže {krok.sarze} "
            f"pro neplatné pracoviště {cislo_pracoviste}."
        )
        return _redirect_invalid_rychle_zalozeni_krok(
            request,
            krok,
            'Číslo pracoviště musí být v rozsahu 1 až 6.',
            invalid_target,
        )

    if krok.zarizeni.typ_zarizeni != TypZarizeniChoice.NAKLADANI:
        logger.warning(
            f"Uživatel {request.user} se pokusil {action_label} šarže {krok.sarze} "
            f"pro krok ID {krok.pk}, který není pro pracoviště Nakládání."
        )
        return _redirect_invalid_rychle_zalozeni_krok(
            request,
            krok,
            'Neplatný krok pro pracoviště Nakládání.',
            invalid_target,
        )

    if _otevreny_krok_pracoviste(cislo_pracoviste) != krok:
        logger.warning(
            f"Uživatel {request.user} se pokusil {action_label} šarže {krok.sarze} "
            f"pro krok ID {krok.pk}, který není otevřený pro pracoviště Nakládání."
        )
        return _redirect_invalid_rychle_zalozeni_krok(
            request,
            krok,
            'Krok pro dané pracoviště není otevřený.',
            invalid_target,
        )

    return None


def _validate_rychle_zalozeni_krok_base(request, krok, action_label):
    cislo_pracoviste = krok.sarze.cislo_pracoviste
    if cislo_pracoviste is None or cislo_pracoviste < 1 or cislo_pracoviste > 6:
        logger.warning(
            f"Uživatel {request.user} se pokusil {action_label} šarže {krok.sarze} "
            f"pro neplatné pracoviště {cislo_pracoviste}."
        )
        return _redirect_invalid_rychle_zalozeni(
            request,
            'Číslo pracoviště musí být v rozsahu 1 až 6.',
        )

    if krok.zarizeni.typ_zarizeni != TypZarizeniChoice.NAKLADANI:
        logger.warning(
            f"Uživatel {request.user} se pokusil {action_label} šarže {krok.sarze} "
            f"pro krok ID {krok.pk}, který není pro pracoviště Nakládání."
        )
        return _redirect_invalid_rychle_zalozeni(
            request,
            'Neplatný krok pro pracoviště Nakládání.',
        )

    return None


@require_POST
def logout_view(request):
    auth_logout(request)
    return redirect('login')


@login_required
def home_view(request):
    """
    Zobrazí provozní rozcestník pro neadmin uživatele.
    Pokud je uživatel staff, přesměruje ho na admin rozhraní.
    """
    if request.user.is_staff:
        return redirect('admin:index')

    return render(
        request,
        'orders/home.html',
        _build_provozni_prehledy_context(request.user),
    )


@login_required
def provozni_prehledy_view(request):
    """
    Zobrazí provozní rozcestník i uživatelům, kteří se běžně po vstupu na home přesměrují do adminu.
    """
    return render(
        request,
        'orders/home.html',
        _build_provozni_prehledy_context(request.user),
    )


def _yes_no(value):
    return 'Ano' if value else 'Ne'


def _display_value(value):
    if value is None or value == '':
        return '-'
    return value


def _bedna_scan_can_mark_navezeno(user, bedna):
    """
    Kontroluje, zda má uživatel oprávnění označit bednu jako navezenou.
    """
    has_permission = (
        user.has_perm('orders.mark_bedna_navezeno')
        or user.has_perm('orders.change_bedna')
    )
    return (
        has_permission
        and not bedna.pozastaveno
        and bedna.stav_bedny in [StavBednyChoice.PRIJATO, StavBednyChoice.K_NAVEZENI]
    )


def _bedna_scan_can_mark_zkontrolovano(user, bedna):
    """
    Kontroluje, zda má uživatel oprávnění označit bednu jako zkontrolovanou.
    """
    return (
        user.has_perm('orders.change_bedna')
        and not bedna.pozastaveno
        and bedna.stav_bedny in STAV_BEDNY_ROZPRACOVANOST
    )


def _include_current_choice(choices, current_value, all_choices):
    choice_values = {choice for choice, _label in choices}
    choice_values.add(current_value)
    choice_labels = dict(all_choices)
    choice_labels.update(dict(choices))

    return [
        (choice, choice_labels[choice])
        for choice, _label in all_choices
        if choice in choice_values
    ]


class BednaScanZkontrolovanoForm(django_forms.Form):
    rovnat = django_forms.ChoiceField(label='Rovnání')
    tryskat = django_forms.ChoiceField(label='Tryskání')

    def __init__(self, *args, bedna, **kwargs):
        super().__init__(*args, **kwargs)
        # Kontrolor má pro označení jako zkontrolované vybrat jen finální hodnotu,
        # ale aktuální hodnotu zobrazíme, aby bylo vidět, z čeho se mění.
        allowed_rovnat_choices = [
            (choice, label)
            for choice, label in RovnaniChoice.choices
            if choice in [RovnaniChoice.ROVNA, RovnaniChoice.KRIVA]
        ]
        allowed_rovnat_choices = _include_current_choice(allowed_rovnat_choices, bedna.rovnat, RovnaniChoice.choices)
        self.fields['rovnat'].choices = allowed_rovnat_choices
        self.fields['rovnat'].initial = bedna.rovnat
        self.fields['rovnat'].widget.attrs.update({'class': 'form-select scan-position-select'})
        allowed_tryskat_choices = bedna.get_allowed_tryskat_choices()
        # Pro kontrolora nechceme, aby mohl nastavit hodnotu NEZADANO, musí určitě, zda je bedna čistá, špinavá nebo otryskaná.
        allowed_tryskat_choices = [(choice, label) for choice, label in allowed_tryskat_choices if choice != TryskaniChoice.NEZADANO]
        allowed_tryskat_choices = _include_current_choice(allowed_tryskat_choices, bedna.tryskat, TryskaniChoice.choices)
        self.fields['tryskat'].choices = allowed_tryskat_choices
        self.fields['tryskat'].initial = bedna.tryskat
        self.fields['tryskat'].widget.attrs.update({'class': 'form-select scan-position-select'})


def _bedna_scan_sections(bedna):
    """
    Vytvoří seznam sekcí a řádků pro zobrazení detailu bedny.
    """
    zakazka = bedna.zakazka
    kamion_prijem = zakazka.kamion_prijem if zakazka else None
    zakaznik = kamion_prijem.zakaznik if kamion_prijem else None

    sections = [
        (
            'Základní údaje',
            [
                ('Číslo bedny', bedna.cislo_bedny),
                ('Č. b. zákazníka', bedna.behalter_nr),
                ('Zákazník', zakaznik),
                ('Zakázka', zakazka),
                ('Artikl', zakazka.artikl if zakazka else None),
                ('Rozměr', f'{zakazka.prumer} x {zakazka.delka}' if zakazka else None),
                ('Zkrácený popis', zakazka.zkraceny_popis if zakazka else None),
                ('Materiál', bedna.material),
                ('Šarže mat. / Charge', bedna.sarze),
                ('Poznámka', bedna.poznamka),
            ],
        ),
        (
            'Hmotnost a množství',
            [
                ('Netto kg', bedna.hmotnost),
                ('Tára kg', bedna.tara),
                ('Brutto kg', bedna.hmotnost_brutto),
                ('Množství ks', bedna.mnozstvi),
            ],
        ),
        (
            'Stavy bedny',
            [
                ('Stav bedny', bedna.get_stav_bedny_display()),
                ('Tryskání', bedna.get_tryskat_display()),
                ('Rovnání', bedna.get_rovnat_display()),
                ('Zinkování', bedna.get_zinkovat_display()),
                ('Pozastaveno', _yes_no(bedna.pozastaveno)),
                ('Fakturovat', _yes_no(bedna.fakturovat)),
                ('Odfosfatovat', _yes_no(bedna.odfosfatovat)),
                ('Postup výroby', f'{bedna.postup_vyroby} %'),
            ],
        ),
        (
            'K navezení',
            [
                ('Pozice', bedna.pozice),
            ],
        ),
        (
            'Zakázka a předpis',
            [
                ('Kamion příjem', kamion_prijem),
                ('Datum příjmu', kamion_prijem.datum if kamion_prijem else None),
                ('Předpis', zakazka.predpis if zakazka else None),
                ('Typ hlavy', zakazka.typ_hlavy if zakazka else None),
                ('Celozávit', _yes_no(zakazka.celozavit) if zakazka else None),
                ('Priorita', zakazka.get_priorita_display() if zakazka else None),
                ('Skupina TZ', bedna.fake_skupina_TZ),
                ('Popis', zakazka.popis if zakazka else None),
            ],
        ),
        (
            'Speciální informace',
            [
                ('Sonder / Zusatzinfo', bedna.dodatecne_info),
                ('Lief.', bedna.dodavatel_materialu),
                ('FA / Bestell-Nr.', bedna.vyrobni_zakazka),
            ],
        ),
    ]

    if bedna.stav_bedny in STAV_BEDNY_SKLADEM:
        sections.append(
            (
                'Prodejní cena',
                [
                    ('Cena kalení EUR/kg', bedna.cena_za_kg),
                    ('Cena kalení EUR/bedna', bedna.cena_za_bednu),
                    ('Cena rovnání EUR/kg', bedna.cena_rovnani_za_kg),
                    ('Cena rovnání EUR/bedna', bedna.cena_rovnani_za_bednu),
                    ('Cena tryskání EUR/kg', bedna.cena_tryskani_za_kg),
                    ('Cena tryskání EUR/bedna', bedna.cena_tryskani_za_bednu),
                ],
            )
        )

    return [
        (
            title,
            [(label, _display_value(value)) for label, value in rows],
        )
        for title, rows in sections
    ]


@login_required
def bedna_scan_view(request, cislo_bedny: int):
    """
    Zobrazuje detail bedny pro skenování.
    """
    bedna_qs = Bedna.objects.select_related(
        'zakazka',
        'zakazka__kamion_prijem',
        'zakazka__kamion_prijem__zakaznik',
        'zakazka__predpis',
        'zakazka__typ_hlavy',
        'pozice',
    )

    bedna = get_object_or_404(bedna_qs, cislo_bedny=cislo_bedny)
    context = {
        'bedna': bedna,
        'sections': _bedna_scan_sections(bedna),
        'can_mark_navezeno': _bedna_scan_can_mark_navezeno(request.user, bedna),
        'has_mark_navezeno_permission': (
            request.user.has_perm('orders.mark_bedna_navezeno')
            or request.user.has_perm('orders.change_bedna')
        ),
        'can_mark_zkontrolovano': _bedna_scan_can_mark_zkontrolovano(request.user, bedna),
        'has_mark_zkontrolovano_permission': request.user.has_perm('orders.change_bedna'),
        'db_table': 'bedna_scan',
    }
    return render(request, 'orders/bedna_scan_detail.html', context)


@login_required
def bedna_scan_navezeni_view(request, cislo_bedny: int):
    """
    Zobrazuje stránku pro označení bedny jako navezené.
    """
    bedna_qs = Bedna.objects.select_related(
        'zakazka',
        'zakazka__kamion_prijem',
        'zakazka__kamion_prijem__zakaznik',
        'pozice',
    )
    bedna = get_object_or_404(bedna_qs, cislo_bedny=cislo_bedny)
    pozice_list = Pozice.objects.order_by('kod')
    aktualni_pozice = bedna.pozice if bedna.pozice else None

    if not (
        request.user.has_perm('orders.mark_bedna_navezeno')
        or request.user.has_perm('orders.change_bedna')
    ):
        raise PermissionDenied
    if bedna.pozastaveno:
        messages.error(request, f'Bedna {bedna.cislo_bedny} je pozastavená a nelze ji označit jako navezenou.')
        return redirect('bedna_scan', cislo_bedny=bedna.cislo_bedny)
    if bedna.stav_bedny not in [StavBednyChoice.PRIJATO, StavBednyChoice.K_NAVEZENI]:
        messages.error(request, f'Bedna {bedna.cislo_bedny} není ve stavu Přijato nebo K navezení.')
        return redirect('bedna_scan', cislo_bedny=bedna.cislo_bedny)


    if request.method == 'POST':
        if request.POST.get('action') != 'mark_navezeno':
            return HttpResponseBadRequest('Neplatná akce.')
        pozice_id = request.POST.get('pozice_id')
        if not pozice_id:
            messages.error(request, 'Vyberte pozici pro navezení.')
            return redirect('bedna_scan_navezeni', cislo_bedny=cislo_bedny)
        with transaction.atomic():
            bedna = get_object_or_404(
                Bedna.objects.select_for_update(),
                cislo_bedny=cislo_bedny,
            )
            pozice = get_object_or_404(Pozice, pk=pozice_id)

            if bedna.stav_bedny not in [StavBednyChoice.PRIJATO, StavBednyChoice.K_NAVEZENI]:
                messages.error(request, f'Bedna {bedna.cislo_bedny} není ve stavu Přijato nebo K navezení.')
                return redirect('bedna_scan', cislo_bedny=bedna.cislo_bedny)

            bedna.stav_bedny = StavBednyChoice.NAVEZENO
            bedna.pozice = pozice
            bedna.save(update_fields=['stav_bedny', 'pozice'])

        messages.success(request, f'Bedna {cislo_bedny} byla navezena na pozici {pozice.kod}.')
        logger.info(
            f"Uživatel {request.user} označil přes QR scan bednu {cislo_bedny} jako NAVEZENO."
        )
        user_agent = get_user_agent(request)
        if user_agent.is_mobile or user_agent.is_tablet:
            return redirect('bedna_skener')
        return redirect('bedna_scan', cislo_bedny=cislo_bedny)

    context = {
        'bedna': bedna,
        'pozice_list': pozice_list,
        'aktualni_pozice': aktualni_pozice,
        'db_table': 'bedna_scan_navezeni',
    }

    return render(
        request,
        'orders/bedna_scan_navezeni.html',
        context
    )


@login_required
def bedna_scan_zkontrolovano_view(request, cislo_bedny: int):
    """
    Zobrazuje stránku pro označení bedny jako zkontrolované a úpravu rovnání/tryskání.
    """
    bedna_qs = Bedna.objects.select_related(
        'zakazka',
        'zakazka__kamion_prijem',
        'zakazka__kamion_prijem__zakaznik',
    )
    bedna = get_object_or_404(bedna_qs, cislo_bedny=cislo_bedny)

    if not request.user.has_perm('orders.change_bedna'):
        raise PermissionDenied
    if bedna.pozastaveno:
        logger.warning(
            f"Uživatel {request.user} se pokusil označit přes scan bednu {bedna.cislo_bedny} jako zkontrolovanou, "
            f"ale bedna je pozastavená."
        )
        messages.error(request, f'Bedna {bedna.cislo_bedny} je pozastavená a nelze ji označit jako zkontrolovanou.')
        return redirect('bedna_scan', cislo_bedny=bedna.cislo_bedny)
    if bedna.stav_bedny not in STAV_BEDNY_ROZPRACOVANOST:
        logger.warning(
            f"Uživatel {request.user} se pokusil označit přes scan bednu {bedna.cislo_bedny} jako zkontrolovanou, "
            f"ale bedna není ve stavu rozpracovanosti."
        )
        messages.error(request, f'Bedna {bedna.cislo_bedny} není ve stavu rozpracovanosti.')
        return redirect('bedna_scan', cislo_bedny=bedna.cislo_bedny)

    if request.method == 'POST':
        if request.POST.get('action') != 'mark_zkontrolovano':
            return HttpResponseBadRequest('Neplatná akce.')

        with transaction.atomic():
            bedna = get_object_or_404(
                Bedna.objects.select_for_update().select_related(
                    'zakazka',
                    'zakazka__kamion_prijem',
                    'zakazka__kamion_prijem__zakaznik',
                ),
                cislo_bedny=cislo_bedny,
            )
            if bedna.pozastaveno:
                logger.warning(
                    f"Uživatel {request.user} se pokusil označit přes scan bednu {bedna.cislo_bedny} jako zkontrolovanou, "
                    f"ale bedna je pozastavená."
                )
                messages.error(request, f'Bedna {bedna.cislo_bedny} je pozastavená a nelze ji označit jako zkontrolovanou.')
                return redirect('bedna_scan', cislo_bedny=bedna.cislo_bedny)
            if bedna.stav_bedny not in STAV_BEDNY_ROZPRACOVANOST:
                logger.warning(
                    f"Uživatel {request.user} se pokusil označit přes scan bednu {bedna.cislo_bedny} jako zkontrolovanou, "
                    f"ale bedna není ve stavu rozpracovanosti."
                )
                messages.error(request, f'Bedna {bedna.cislo_bedny} není ve stavu rozpracovanosti.')
                return redirect('bedna_scan', cislo_bedny=bedna.cislo_bedny)

            form = BednaScanZkontrolovanoForm(request.POST, bedna=bedna)
            if form.is_valid():
                bedna.stav_bedny = StavBednyChoice.ZKONTROLOVANO
                bedna.rovnat = form.cleaned_data['rovnat']
                bedna.tryskat = form.cleaned_data['tryskat']
                rovnat_bool = bedna.rovnat in [RovnaniChoice.KRIVA, RovnaniChoice.ROVNA]
                tryskat_bool = bedna.tryskat in [TryskaniChoice.SPINAVA, TryskaniChoice.CISTA, TryskaniChoice.OTRYSKANA]
                if not rovnat_bool or not tryskat_bool:
                    if not rovnat_bool:
                        logger.warning(
                            f"Uživatel {request.user} se pokusil označit přes scan bednu {bedna.cislo_bedny} jako zkontrolovanou, "
                            f"ale bedna má nastaveno rovnání na hodnotu '{bedna.rovnat}', což není povolená hodnota."
                        )
                        messages.error(request, f'Bedna {bedna.cislo_bedny} má nastaveno rovnání na hodnotu "{bedna.rovnat}", což není povolená hodnota pro označení bedny jako zkontrolované.')
                    if not tryskat_bool:
                        logger.warning(
                            f"Uživatel {request.user} se pokusil označit přes scan bednu {bedna.cislo_bedny} jako zkontrolovanou, "
                            f"ale bedna má nastaveno tryskání na hodnotu '{bedna.tryskat}', což není povolená hodnota."
                        )
                        messages.error(request, f'Bedna {bedna.cislo_bedny} má nastaveno tryskání na hodnotu "{bedna.tryskat}", což není povolená hodnota pro označení bedny jako zkontrolované.')
                    return render(
                        request,
                        'orders/bedna_scan_zkontrolovano.html',
                        {
                            'bedna': bedna,
                            'form': form,
                            'db_table': 'bedna_scan_zkontrolovano',
                        }
                    )
                bedna.save(update_fields=['stav_bedny', 'rovnat', 'tryskat'])
            else:
                return render(
                    request,
                    'orders/bedna_scan_zkontrolovano.html',
                    {
                        'bedna': bedna,
                        'form': form,
                        'db_table': 'bedna_scan_zkontrolovano',
                    }
                )

        messages.success(request, f'Bedna {cislo_bedny} byla označena jako zkontrolovaná.')
        logger.info(
            f"Uživatel {request.user} označil přes scan bednu {cislo_bedny} jako ZKONTROLOVANO."
        )
        user_agent = get_user_agent(request)
        if user_agent.is_mobile or user_agent.is_tablet:
            return redirect('bedna_skener')
        return redirect('bedna_scan', cislo_bedny=cislo_bedny)

    form = BednaScanZkontrolovanoForm(bedna=bedna)
    context = {
        'bedna': bedna,
        'form': form,
        'db_table': 'bedna_scan_zkontrolovano',
    }
    return render(request, 'orders/bedna_scan_zkontrolovano.html', context)


@login_required
def bedna_scan_pohyb_view(request, cislo_bedny: int):
    """
    Zobrazuje detail bedny pro skenování pohybu.
    """
    bedna = get_object_or_404(
        Bedna.objects.select_related(
            'zakazka',
            'zakazka__kamion_prijem',
            'zakazka__kamion_prijem__zakaznik',
        ),
        cislo_bedny=cislo_bedny,
    )
    krok_ids = list(
        SarzeKrokBedna.objects
        .filter(bedna=bedna)
        .values_list('krok_id', flat=True)
        .distinct()
    )
    pohyb = []
    pohyb_by_sarze = {}
    pohyb_by_krok = {}
    polozky = (
        SarzeKrokBedna.objects
        .filter(krok_id__in=krok_ids)
        .select_related('krok', 'krok__sarze', 'krok__zarizeni', 'bedna', 'bedna__zakazka')
        .order_by('krok__datum', 'krok__zacatek', 'krok__sarze__cislo_sarze', 'krok__poradi', 'patro', 'bedna__cislo_bedny', 'pk')
    )
    for polozka in polozky:
        krok_group = pohyb_by_krok.get(polozka.krok_id)
        if krok_group is None:
            sarze_group = pohyb_by_sarze.get(polozka.krok.sarze_id)
            if sarze_group is None:
                sarze_group = {
                    'sarze': polozka.krok.sarze,
                    'kroky': [],
                }
                pohyb_by_sarze[polozka.krok.sarze_id] = sarze_group
                pohyb.append(sarze_group)

            krok_group = {
                'krok': polozka.krok,
                'patra': [],
                'patra_by_number': {},
            }
            pohyb_by_krok[polozka.krok_id] = krok_group
            sarze_group['kroky'].append(krok_group)

        patro_group = krok_group['patra_by_number'].get(polozka.patro)
        if patro_group is None:
            patro_group = {
                'patro': polozka.patro,
                'polozky': [],
            }
            krok_group['patra_by_number'][polozka.patro] = patro_group
            krok_group['patra'].append(patro_group)

        patro_group['polozky'].append(polozka)

    for sarze_group in pohyb:
        for krok_group in sarze_group['kroky']:
            krok_group.pop('patra_by_number', None)

    return render(
        request,
        'orders/bedna_scan_pohyb.html',
        {
            'bedna': bedna,
            'pohyb': pohyb,
            'db_table': 'bedna_scan_pohyb',
        },
    )


def _can_move_sarze_scan(user):
    """
    Kontroluje, zda má uživatel oprávnění přesunout šarži.
    """
    return user.has_perms((
        'orders.add_sarzekrok',
        'orders.add_sarzekrokbedna',
    ))

def _can_change_sarze_scan(user):
    """
    Kontroluje, zda má uživatel oprávnění změnit šarži.
    """
    return user.has_perms((
        'orders.change_sarzekrok',
        'orders.change_sarzekrokbedna',
    ))


def _style_sarze_scan_move_form(form):
    """
    Aplikuje stylování na formulář pro přesun šarže.
    """
    form.fields['datum'].widget = django_forms.DateInput(
        attrs={'class': 'form-control', 'type': 'date'},
        format='%Y-%m-%d',
    )
    form.fields['zacatek'].widget = django_forms.TimeInput(
        attrs={'class': 'form-control', 'type': 'time'},
        format='%H:%M',
    )
    form.fields['konec'].widget = django_forms.TimeInput(
        attrs={'class': 'form-control', 'type': 'time'},
        format='%H:%M',
    )
    form.fields['zarizeni'].widget.attrs.update({'class': 'form-select'})
    for field_name in ('operator', 'program', 'alarm', 'poznamka'):
        form.fields[field_name].widget.attrs.update({'class': 'form-control'})


def _build_sarze_scan_move_preview_rows(source_rows, selected_row_ids):
    """
    Vytvoří náhledové řádky pro přesun šarže.
    """
    preview_rows = _build_sarzekrokbedna_preview_rows(source_rows)
    for preview_row, source_row in zip(preview_rows, source_rows):
        preview_row['id'] = source_row.pk
        preview_row['selected'] = source_row.pk in selected_row_ids
    return preview_rows


@login_required
def sarze_scan_view(request, cislo_sarze: int):
    """
    Zobrazuje detail šarže při naskenování čárového kódu.
    """
    sarze = get_object_or_404(Sarze, cislo_sarze=cislo_sarze)
    kroky = list(
        SarzeKrok.objects
        .filter(sarze=sarze)
        .select_related('sarze', 'zarizeni')
        .order_by('poradi', 'datum', 'zacatek', 'pk')
    )
    krok_groups = []
    krok_groups_by_id = {}
    for krok in kroky:
        krok_group = {
            'krok': krok,
            'patra': [],
            'patra_by_number': {},
        }
        krok_groups_by_id[krok.pk] = krok_group
        krok_groups.append(krok_group)

    polozky = (
        SarzeKrokBedna.objects
        .filter(krok__sarze=sarze)
        .select_related('krok', 'krok__zarizeni', 'bedna', 'bedna__zakazka')
        .order_by('krok__poradi', 'patro', 'bedna__cislo_bedny', 'pk')
    )
    for polozka in polozky:
        krok_group = krok_groups_by_id.get(polozka.krok_id)
        if krok_group is None:
            continue

        patro_group = krok_group['patra_by_number'].get(polozka.patro)
        if patro_group is None:
            patro_group = {
                'patro': polozka.patro,
                'polozky': [],
            }
            krok_group['patra_by_number'][polozka.patro] = patro_group
            krok_group['patra'].append(patro_group)

        patro_group['polozky'].append(polozka)

    for krok_group in krok_groups:
        krok_group.pop('patra_by_number', None)

    return render(
        request,
        'orders/sarze_scan_detail.html',
        {
            'sarze': sarze,
            'kroky': krok_groups,
            'last_krok': kroky[-1] if kroky else None,
            'can_move_sarze': _can_move_sarze_scan(request.user),
            'can_change_sarze': _can_change_sarze_scan(request.user),
            'db_table': 'sarze_scan',
        },
    )


@login_required
@permission_required('orders.add_sarzekrok', raise_exception=True)
@permission_required('orders.add_sarzekrokbedna', raise_exception=True)
def sarze_scan_presunout_view(request, cislo_sarze: int, krok_id: int):
    """
    Zobrazuje stránku pro přesun šarže do dalšího kroku.
    """
    source_krok = get_object_or_404(
        SarzeKrok.objects.select_related('sarze', 'zarizeni'),
        pk=krok_id,
        sarze__cislo_sarze=cislo_sarze,
    )
    source_rows = list(
        SarzeKrokBedna.objects
        .filter(krok=source_krok)
        .select_related('bedna', 'bedna__zakazka')
        .order_by('pk')
    )
    action_token = request.POST.get('_sarzekrok_action_token') or uuid.uuid4().hex
    selected_source_row_ids = {row.pk for row in source_rows}

    if not source_krok.konec:
        messages.warning(
            request,
            'Původní krok šarže nemá vyplněný konec, nezapomeňte jej vyplnit.',
        )

    if request.method == 'POST':
        form = SarzeKrokActionInitForm(request.POST, sarze=source_krok.sarze)
        _style_sarze_scan_move_form(form)
        selected_source_row_ids = {
            int(row_id)
            for row_id in request.POST.getlist('source_row_ids')
            if row_id.isdigit()
        }
        selected_source_rows = [
            row for row in source_rows if row.pk in selected_source_row_ids
        ]
        if source_rows and not selected_source_rows:
            form.add_error(None, 'Vyberte alespoň jednu položku ke kopírování.')
        if form.is_valid():
            target_krok, copied_count, created = _create_sarzekrok_and_copy_rows(
                source_krok,
                selected_source_rows,
                datum=form.cleaned_data['datum'],
                zarizeni=form.cleaned_data['zarizeni'],
                zacatek=form.cleaned_data['zacatek'],
                konec=form.cleaned_data['konec'],
                operator=form.cleaned_data['operator'],
                program=form.cleaned_data['program'],
                alarm=form.cleaned_data['alarm'],
                poznamka=form.cleaned_data['poznamka'],
                action_token=action_token,
            )
            if created:
                messages.success(
                    request,
                    f'Vytvořen krok {target_krok.poradi} šarže {target_krok.sarze} a zkopírováno {copied_count} řádků.',
                )
                logger.info(
                    f"Uživatel {request.user} vytvořil přes scan nový krok šarže {target_krok.sarze} "
                    f"(zdrojový krok ID {source_krok.pk}, nový krok ID {target_krok.pk}, "
                    f"zkopírováno {copied_count} z {len(selected_source_rows)} vybraných řádků)."
                )
            else:
                messages.warning(
                    request,
                    f'Opakované odeslání bylo ignorováno. Používá se již vytvořený krok {target_krok.poradi}.',
                )
                logger.warning(
                    f"Uživatel {request.user} opakovaně odeslal scan přesun šarže {target_krok.sarze}; "
                    f"použit existující krok ID {target_krok.pk} pro token {action_token}."
                )
            return redirect('sarze_scan', cislo_sarze=source_krok.sarze.cislo_sarze)
        logger.warning(
            f"Uživatel {request.user} odeslal neplatný formulář pro scan přesun šarže "
            f"{source_krok.sarze} ze zdrojového kroku ID {source_krok.pk}. Chyby: {form.errors.as_json()}"
        )
    else:
        form = SarzeKrokActionInitForm(
            initial={'datum': timezone.localdate()},
            sarze=source_krok.sarze,
        )
        _style_sarze_scan_move_form(form)

    predicted_poradi = (
        SarzeKrok.objects
        .filter(sarze=source_krok.sarze)
        .aggregate(max_poradi=Max('poradi'))['max_poradi'] or 0
    ) + 1

    return render(
        request,
        'orders/sarze_scan_presunout.html',
        {
            'sarze': source_krok.sarze,
            'source_krok': source_krok,
            'form': form,
            'source_row_preview': _build_sarze_scan_move_preview_rows(source_rows, selected_source_row_ids),
            'source_row_count': len(source_rows),
            'predicted_poradi': predicted_poradi,
            'action_token': action_token,
            'db_table': 'sarze_scan_presunout',
        },
    )


@login_required
@permission_required('orders.change_sarzekrok', raise_exception=True)
@permission_required('orders.change_sarzekrokbedna', raise_exception=True)
def sarze_scan_change_krok_view(request, cislo_sarze: int, krok_id: int):
    """
    Zobrazuje stránku pro změnu kroku šarže.
    """
    krok = get_object_or_404(
        SarzeKrok.objects.select_related('sarze', 'zarizeni'),
        pk=krok_id,
        sarze__cislo_sarze=cislo_sarze,
    )
    polozky = list(
        SarzeKrokBedna.objects
        .filter(krok=krok)
        .select_related('bedna', 'bedna__zakazka', 'bedna__zakazka__kamion_prijem__zakaznik')
        .order_by('patro', 'bedna__cislo_bedny', 'pk')
    )

    if request.method == 'POST':
        form = SarzeScanKrokChangeForm(request.POST, instance=krok)
        delete_row_ids = {
            int(row_id)
            for row_id in request.POST.getlist('delete_row_ids')
            if row_id.isdigit()
        }
        if form.is_valid():
            with transaction.atomic():
                form.save()
                deleted_count = 0
                if delete_row_ids:
                    deleted_count, _ = (
                        SarzeKrokBedna.objects
                        .filter(krok=krok, pk__in=delete_row_ids)
                        .delete()
                    )
            message = f'Krok {krok.poradi} šarže {krok.sarze} byl uložen.'
            if delete_row_ids:
                message = f'{message} Smazáno položek: {deleted_count}.'
            messages.success(request, message)
            logger.info(
                f"Uživatel {request.user} upravil přes scan krok ID {krok.pk} šarže {krok.sarze} "
                f"(smazáno položek {deleted_count}, požadováno ke smazání {len(delete_row_ids)})."
            )
            return redirect('sarze_scan', cislo_sarze=krok.sarze.cislo_sarze)
        logger.warning(
            f"Uživatel {request.user} odeslal neplatný formulář pro scan úpravu kroku ID {krok.pk} "
            f"šarže {krok.sarze}. Chyby: {form.errors.as_json()}"
        )
    else:
        form = SarzeScanKrokChangeForm(instance=krok)

    return render(
        request,
        'orders/sarze_scan_change_krok.html',
        {
            'sarze': krok.sarze,
            'krok': krok,
            'form': form,
            'polozky': polozky,
            'db_table': 'sarze_scan_change_krok',
        },
    )


@login_required
def bedna_skener_view(request):
    """
    Zobrazuje stránku pro skenování bedny.
    """
    return render(
        request,
        'orders/bedna_skener.html',
        {
            'db_table': 'bedna_skener',
        },
    )


@login_required
@permission_required('orders.add_sarze', raise_exception=True)
@permission_required('orders.add_sarzekrok', raise_exception=True)
@permission_required('orders.add_sarzekrokbedna', raise_exception=True)
def rychle_zalozeni_sarze_view(request):
    """
    Zobrazuje stránku pro rychlé založení šarže a jejího prvního kroku.
    """
    cancel_url = _safe_return_url(request, reverse('provozni_prehledy'))
    cislo_pracoviste = _cislo_pracoviste_z_query(request)
    if cislo_pracoviste is None:
        return _redirect_invalid_rychle_zalozeni(
            request,
            'Rychlé založení šarže spusťte přes konkrétní pracoviště.',
        )

    if request.method == 'POST':
        form = RychleZalozeniSarzeForm(
            request.POST,
            locked_cislo_pracoviste=cislo_pracoviste,
        )
        if form.is_valid():
            sarze, krok = form.save()
            messages.success(request, f'Šarže {sarze} a první krok byly uloženy.')
            logger.info(
                f"Uživatel {request.user} vytvořil šarži {sarze} a její první krok {krok.pk}."
            )
            return redirect('rychle_zalozeni_sarze_patro', krok_id=krok.pk, patro=1)
    else:
        initial = {
            'operator': request.user.get_full_name() or request.user.username,
            'cislo_pracoviste': cislo_pracoviste,
        }
        form = RychleZalozeniSarzeForm(
            initial=initial,
            locked_cislo_pracoviste=cislo_pracoviste,
        )

    return render(
        request,
        'orders/rychle_zalozeni_sarze.html',
        {
            'form': form,
            'db_table': 'rychle_zalozeni_sarze',
            'cancel_url': cancel_url,
        },
    )


@login_required
@permission_required('orders.view_sarzekrok', raise_exception=True)
@permission_required('orders.view_sarzekrokbedna', raise_exception=True)
def rychle_zalozeni_sarze_pracoviste_prehled_view(request, cislo_pracoviste):
    """
    Pokud existuje otevřený krok nakládání pro zadané číslo pracoviště,
    přesměruje na přehled šarže, jinak přesměruje na stránku pro rychlé založení šarže.
    Vhodné pro použití při skenování čárového kódu pracoviště, kdy se uživatel dostane přímo na stránku pro založení šarže,
    pokud ještě žádná šarže na daném pracovišti není otevřená nebo do přehledu aktuálně nakládané šarže.
    """
    if cislo_pracoviste < 1 or cislo_pracoviste > 6:
        return _redirect_invalid_rychle_zalozeni(
            request,
            'Neplatné číslo pracoviště.',
        )

    otevreny_krok = _otevreny_krok_pracoviste(cislo_pracoviste)
    
    if otevreny_krok is None:
        return redirect(f"{reverse('rychle_zalozeni_sarze')}?cislo_pracoviste={cislo_pracoviste}")

    return redirect(
        'rychle_zalozeni_sarze_prehled',
        krok_id=otevreny_krok.pk,
    )


@login_required
@permission_required('orders.add_sarzekrokbedna', raise_exception=True)
@permission_required('orders.change_sarzekrokbedna', raise_exception=True)
def rychle_zalozeni_sarze_patro_view(request, krok_id, patro):
    """
    Zobrazuje stránku pro rychlé založení nebo úpravu patra šarže.
    Kontroluje, jestli je daný krok pro pracoviště Nakládání a
    jestli je pro daný krok šarže otevřené pracoviště nakládání.
    """
    krok = get_object_or_404(
        SarzeKrok.objects.select_related('sarze', 'zarizeni'),
        pk=krok_id,
    )

    invalid_krok_response = _validate_rychle_zalozeni_krok(request, krok, 'upravit patro', 'prehled')
    if invalid_krok_response is not None:
        return invalid_krok_response
    
    if patro < 1 or patro > 6:
        logger.warning(
            f"Uživatel {request.user} se pokusil upravit patro šarže {krok.sarze} "
            f"na neplatné číslo patra {patro}."
        )
        return _redirect_invalid_rychle_zalozeni_patro(
            request,
            krok,
            'Číslo patra musí být mezi 1 a 6.',
        )

    existing_items = list(
        krok.krok_bedny
        .filter(patro=patro)
        .select_related('bedna')
        .order_by('pk')
    )
    max_patro = krok.krok_bedny.aggregate(max_patro=Max('patro'))['max_patro']
    user_can_delete_patro = request.user.has_perm('orders.delete_sarzekrokbedna_patro')
    is_last_patro = bool(existing_items) and max_patro == patro
    can_delete_patro = user_can_delete_patro and is_last_patro
    initial = [
        {
            'bedna': item.bedna_id,
            'procent_z_patra': item.procent_z_patra,
        }
        for item in existing_items
    ]
    visible_rows = 5
    extra_rows = max(visible_rows - len(initial), 0)
    PatroFormSet = get_sarze_krok_patro_formset(extra=extra_rows)

    if request.method == 'POST':
        if request.POST.get('action') == 'delete_floor':
            if not user_can_delete_patro:
                raise PermissionDenied

            with transaction.atomic():
                locked_krok = SarzeKrok.objects.select_for_update().get(pk=krok.pk)
                current_max_patro = locked_krok.krok_bedny.aggregate(max_patro=Max('patro'))['max_patro']
                if current_max_patro != patro:
                    messages.error(request, 'Smazat lze pouze poslední patro kroku šarže.')
                    return redirect('rychle_zalozeni_sarze_patro', krok_id=krok.pk, patro=patro)

                deleted_count, _ = locked_krok.krok_bedny.filter(patro=patro).delete()

            messages.success(request, f'{patro}. patro bylo smazáno.')
            logger.info(
                f"Uživatel {request.user} smazal {patro}. patro kroku {krok.pk} šarže {krok.sarze} "
                f"(smazáno položek {deleted_count})."
            )
            return redirect('rychle_zalozeni_sarze_prehled', krok_id=krok.pk)

        if request.POST.get('action') == 'finish':
            return redirect('rychle_zalozeni_sarze_prehled', krok_id=krok.pk)

        formset = PatroFormSet(request.POST, prefix='polozky', form_kwargs={'bedna_only': True})
        if formset.is_valid():
            with transaction.atomic():
                locked_krok = SarzeKrok.objects.select_for_update().get(pk=krok.pk)
                locked_krok.krok_bedny.filter(patro=patro).delete()

                for item_form in formset.active_forms():
                    data = item_form.cleaned_data
                    item = SarzeKrokBedna(
                        krok=locked_krok,
                        bedna=data.get('bedna'),
                        patro=patro,
                        procent_z_patra=data['procent_z_patra'],
                    )
                    item.full_clean()
                    item.save()

            if request.POST.get('action') == 'next':
                messages.success(request, f'{patro}. patro bylo uloženo.')
                logger.info(
                    f"Uživatel {request.user} uložil {patro}. patro kroku {krok.pk} šarže {krok.sarze} "
                    f"a pokračuje na další patro."
                )
                return redirect(
                    'rychle_zalozeni_sarze_patro',
                    krok_id=krok.pk,
                    patro=patro + 1,
                )

            messages.success(request, f'Byla vytvořena nebo upravena šarže {krok.sarze}.')
            logger.info(
                f"Uživatel {request.user} uložil {patro}. patro kroku {krok.pk} šarže {krok.sarze} "
                f"a dokončil úpravu patra."
            )
            return redirect('rychle_zalozeni_sarze_prehled', krok_id=krok.pk)
    else:
        formset = PatroFormSet(initial=initial, prefix='polozky', form_kwargs={'bedna_only': True})

    return render(
        request,
        'orders/rychle_zalozeni_sarze_patro.html',
        {
            'formset': formset,
            'krok': krok,
            'patro': patro,
            'show_delete_patro_button': user_can_delete_patro and bool(existing_items),
            'can_delete_patro': can_delete_patro,
            'is_last_patro': is_last_patro,
            'max_patro': max_patro,
            'db_table': 'rychle_zalozeni_sarze',
        },
    )


@login_required
@permission_required('orders.view_sarzekrok', raise_exception=True)
@permission_required('orders.view_sarzekrokbedna', raise_exception=True)
def rychle_zalozeni_sarze_prehled_view(request, krok_id):
    """
    Zobrazuje přehled šarže a jejích pater.
    """
    krok = get_object_or_404(
        SarzeKrok.objects.select_related('sarze', 'zarizeni'),
        pk=krok_id,
    )
    invalid_krok_response = _validate_rychle_zalozeni_krok(request, krok, 'zobrazit přehled', 'provozni')
    if invalid_krok_response is not None:
        return invalid_krok_response

    items = (
        krok.krok_bedny
        .select_related('bedna')
        .order_by('-patro', 'pk')
    )
    nove_patro = (items.aggregate(max_patro=Max('patro'))['max_patro'] or 0) + 1
    sarze_s_bednami = bool(
        krok.krok_bedny
        .filter(bedna__isnull=False)
        .exists()
    )

    return render(
        request,
        'orders/rychle_zalozeni_sarze_prehled.html',
        {
            'krok': krok,
            'items': items,
            'nove_patro': nove_patro,
            'sarze_s_bednami': sarze_s_bednami,
            'db_table': 'rychle_zalozeni_sarze',
        },
    )


@login_required
@permission_required('orders.view_sarzekrok', raise_exception=True)
@permission_required('orders.view_sarzekrokbedna', raise_exception=True)
def rychle_zalozeni_sarze_tisk_view(request, krok_id):
    """
    Zobrazuje stránku pro tisk šarže a jejích pater.
    """
    krok = get_object_or_404(
        SarzeKrok.objects.select_related('sarze', 'zarizeni'),
        pk=krok_id,
    )
    invalid_krok_response = _validate_rychle_zalozeni_krok(request, krok, 'vytisknout průvodku', 'provozni')
    if invalid_krok_response is not None:
        return invalid_krok_response

    items = (
        krok.krok_bedny
        .select_related('bedna', 'bedna__zakazka', 'bedna__zakazka__predpis')
        .order_by('-patro', 'pk')
    )

    fake_skupiny = set()
    for item in items:
        if item.bedna:
            fake_skupina = item.bedna.fake_skupina_TZ
            fake_skupiny.add(fake_skupina)
        else:
            fake_skupiny.add(None)
    spolecna_skupina_TZ = next(iter(fake_skupiny)) if len(fake_skupiny) == 1 else None

    context = {
        'krok': krok,
        'items': items,
        'spolecna_skupina_TZ': spolecna_skupina_TZ,
        'generated_at': timezone.now(),
    }
    html_string = render_to_string(
        'orders/print/rychle_zalozeni_sarze_print.html',
        context,
    )
    base_url = getattr(settings, 'WEASYPRINT_BASEURL', None) or request.build_absolute_uri('/')
    pdf_bytes = HTML(string=html_string, base_url=base_url).write_pdf()

    filename = f"sarze_{krok.sarze_id}_krok_{krok.pk}.pdf"
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'
    response['Content-Length'] = str(len(pdf_bytes))
    return response


@login_required
@permission_required('orders.change_sarze', raise_exception=True)
@permission_required('orders.change_sarzekrok', raise_exception=True)
def rychle_zalozeni_sarze_upravit_view(request, krok_id):
    """
    Zobrazuje stránku pro rychlé založení nebo úpravu patra šarže.
    """
    krok = get_object_or_404(
        SarzeKrok.objects.select_related('sarze', 'zarizeni'),
        pk=krok_id,
        poradi=1,
    )
    invalid_krok_response = _validate_rychle_zalozeni_krok_base(request, krok, 'upravit krok')
    if invalid_krok_response is not None:
        return invalid_krok_response

    sarze = krok.sarze
    fallback_cancel_url = reverse('rychle_zalozeni_sarze_prehled', args=[krok.pk])
    cancel_url = _safe_return_url(request, fallback_cancel_url)
    if request.method == 'POST':
        form = RychleZalozeniSarzeForm(request.POST, sarze=sarze, krok=krok)
        if form.is_valid():
            sarze, krok = form.save()
            messages.success(request, f'Byla upravena šarže {sarze}.')
            logger.info(
                f"Uživatel {request.user} upravil šarži {sarze} a její první krok {krok.pk}."
            )
            if krok.konec is not None:
                return redirect('provozni_prehledy')
            return redirect('rychle_zalozeni_sarze_prehled', krok_id=krok.pk)
    else:
        form = RychleZalozeniSarzeForm(sarze=sarze, krok=krok)

    return render(
        request,
        'orders/rychle_zalozeni_sarze.html',
        {
            'form': form,
            'krok': krok,
            'is_edit': True,
            'db_table': 'rychle_zalozeni_sarze',
            'cancel_url': cancel_url,
        },
    )

 
def _format_hours(hours_value):
    return f"{hours_value:.1f}".replace('.', ',')


def _format_tuny(value):
    if value is None:
        return '0'
    return f"{value / 1000:.1f}".replace('.', ',')


def _kg_to_int(value):
    if value is None:
        return 0
    try:
        return int(Decimal(value).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    except Exception:
        logger.warning("Nepodařilo se převést hodnotu na celé kg.", exc_info=True)
        return 0


def _format_kg(value):
    return f"{_kg_to_int(value):,}".replace(',', ' ')


def _format_price(value):
    try:
        return f"{Decimal(value or 0).quantize(Decimal('1'), rounding=ROUND_HALF_UP):,}".replace(',', ' ')
    except Exception:
        logger.warning("Nepodařilo se naformátovat cenu.", exc_info=True)
        return '0'


def _calc_prostoj_minutes(kroky_list):
    """
    Vypočítá celkový prostoj v minutách pro seznam kroků.
    Pro každou prodlevu se odečte 10 minut, pokud je prodleva větší než 10 minut.
    """
    total_minutes = 0
    for krok in kroky_list:
        prodleva = krok.prodleva
        if isinstance(prodleva, int):
            total_minutes += max(prodleva - 10, 0)
    return total_minutes


def _first_use_sarzekrokbedna_qs(target_date, device_codes):
    """
    Vrací queryset pro první použití bedny v daném dni a na daných zařízeních.
    """
    sarze_krok_bedny = (
        SarzeKrokBedna.objects
        .filter(
            krok__datum=target_date,
            krok__zarizeni__kod_zarizeni__in=device_codes,
            bedna__isnull=False,
            bedna__hmotnost__isnull=False,
            bedna__hmotnost__gt=0,
        )
        .select_related('krok', 'krok__sarze', 'krok__zarizeni', 'bedna')
    )

    prior_exists = SarzeKrokBedna.objects.filter(
        bedna_id=OuterRef('bedna_id'),
        krok__zarizeni_id=OuterRef('krok__zarizeni_id'),
    ).exclude(pk=OuterRef('pk')).filter(
        Q(krok__datum__lt=OuterRef('krok__datum'))
        | Q(
            krok__datum=OuterRef('krok__datum'),
            krok__zacatek__lt=OuterRef('krok__zacatek'),
        )
        | Q(
            krok__datum=OuterRef('krok__datum'),
            krok__zacatek=OuterRef('krok__zacatek'),
            krok__poradi__lt=OuterRef('krok__poradi'),
        )
    )

    same_krok_prior_exists = SarzeKrokBedna.objects.filter(
        krok_id=OuterRef('krok_id'),
        bedna_id=OuterRef('bedna_id'),
    ).exclude(pk=OuterRef('pk')).filter(
        Q(patro__lt=OuterRef('patro'))
        | Q(patro=OuterRef('patro'), pk__lt=OuterRef('pk'))
    )

    return sarze_krok_bedny.annotate(
        has_prior=Exists(prior_exists),
        has_same_krok_prior=Exists(same_krok_prior_exists),
    ).filter(
        has_prior=False,
        has_same_krok_prior=False,
    )


def _first_use_sarzekrokbedna_range_qs(start_date, end_date, device_codes):
    """
    Vrací queryset pro první použití bedny v daném rozsahu dat a na daných zařízeních.
    """
    sarze_krok_bedny = (
        SarzeKrokBedna.objects
        .filter(
            krok__datum__gte=start_date,
            krok__datum__lte=end_date,
            krok__zarizeni__kod_zarizeni__in=device_codes,
            bedna__isnull=False,
            bedna__hmotnost__isnull=False,
            bedna__hmotnost__gt=0,
        )
        .select_related('krok', 'krok__zarizeni', 'bedna')
    )

    prior_exists = SarzeKrokBedna.objects.filter(
        bedna_id=OuterRef('bedna_id'),
        krok__zarizeni_id=OuterRef('krok__zarizeni_id'),
    ).exclude(pk=OuterRef('pk')).filter(
        Q(krok__datum__lt=OuterRef('krok__datum'))
        | Q(
            krok__datum=OuterRef('krok__datum'),
            krok__zacatek__lt=OuterRef('krok__zacatek'),
        )
        | Q(
            krok__datum=OuterRef('krok__datum'),
            krok__zacatek=OuterRef('krok__zacatek'),
            krok__poradi__lt=OuterRef('krok__poradi'),
        )
    )

    same_krok_prior_exists = SarzeKrokBedna.objects.filter(
        krok_id=OuterRef('krok_id'),
        bedna_id=OuterRef('bedna_id'),
    ).exclude(pk=OuterRef('pk')).filter(
        Q(patro__lt=OuterRef('patro'))
        | Q(patro=OuterRef('patro'), pk__lt=OuterRef('pk'))
    )

    return sarze_krok_bedny.annotate(
        has_prior=Exists(prior_exists),
        has_same_krok_prior=Exists(same_krok_prior_exists),
    ).filter(
        has_prior=False,
        has_same_krok_prior=False,
    )


def _avg_kg_per_day_int(total_kg, day_count):
    if day_count <= 0:
        return 0
    try:
        return _kg_to_int(Decimal(total_kg) / Decimal(day_count))
    except Exception:
        logger.warning("Nepodařilo se spočítat průměr kg/den.", exc_info=True)
        return 0


def _get_vyroba_available_years(device_codes, today_value=None):
    """
    Vrací seznam let, ve kterých jsou dostupná data pro výrobu na daných zařízeních.
    """
    today = today_value or timezone.localdate()
    years_with_data = sorted(
        {
            y.year
            for y in SarzeKrok.objects.filter(
                zarizeni__kod_zarizeni__in=device_codes,
                krok_bedny__bedna__isnull=False,
                krok_bedny__bedna__hmotnost__gt=0,
            ).dates('datum', 'year')
        },
        reverse=True,
    )
    if today.year not in years_with_data:
        years_with_data.append(today.year)
        years_with_data = sorted(set(years_with_data), reverse=True)
    return years_with_data

def _kg_per_rost_int(total_kg, step_count):
    """
    Vrací průměrné kg na rošt.
    """
    if step_count <= 0:
        return 0
    try:
        return _kg_to_int(Decimal(total_kg) / Decimal(step_count))
    except Exception:
        logger.warning("Nepodařilo se spočítat vytížení roštu.", exc_info=True)
        return 0


def _build_vyroba_historie_context(year_value=None, month_value=None, today_value=None):
    """
    Vytváří kontext pro historii výroby na základě zadaného roku, měsíce a dnešního data.
    """
    today = today_value or timezone.localdate()
    device_codes = ["TQF_XL1", "TQF_XL2"]

    years_with_data = _get_vyroba_available_years(device_codes, today_value=today)

    try:
        selected_year = int(year_value) if year_value is not None else years_with_data[0]
    except (TypeError, ValueError):
        selected_year = years_with_data[0]
    if selected_year not in years_with_data:
        selected_year = years_with_data[0]

    selected_month = None
    try:
        if month_value is not None and str(month_value).strip() != '':
            month_int = int(month_value)
            if 1 <= month_int <= 12:
                selected_month = month_int
    except (TypeError, ValueError):
        selected_month = None

    year_start = date(selected_year, 1, 1)
    year_end = date(selected_year, 12, 31)
    elapsed_end = min(today, year_end) if selected_year == today.year else year_end
    if elapsed_end < year_start:
        elapsed_end = None

    first_use_year_qs = _first_use_sarzekrokbedna_range_qs(year_start, year_end, device_codes)

    cena_za_kg_sq = Cena.objects.filter(
        zakaznik=OuterRef('bedna__zakazka__kamion_prijem__zakaznik'),
        delka_min__lte=OuterRef('bedna__zakazka__delka'),
        delka_max__gt=OuterRef('bedna__zakazka__delka'),
        predpis=OuterRef('bedna__zakazka__predpis'),
    ).values('cena_za_kg')[:1]

    first_use_year_qs = first_use_year_qs.annotate(
        cena_za_kg_ann=Coalesce(
            Subquery(cena_za_kg_sq, output_field=DecimalField(max_digits=10, decimal_places=2)),
            Value(Decimal('0.00')), output_field=DecimalField(max_digits=10, decimal_places=2),
        ),
    ).annotate(
        cena_bedny_ann=ExpressionWrapper(
            F('bedna__hmotnost') * F('cena_za_kg_ann'),
            output_field=DecimalField(max_digits=14, decimal_places=2),
        ),
    )

    grouped = (
        first_use_year_qs
        .values('krok__datum', 'krok__zarizeni__kod_zarizeni')
        .annotate(
            total_kg=Sum('bedna__hmotnost'),
            total_price=Sum('cena_bedny_ann'),
        )
    )

    day_data = {}
    price_day_data = {}
    for row in grouped:
        row_date = row['krok__datum']
        code = row['krok__zarizeni__kod_zarizeni']
        total_kg = row['total_kg'] or Decimal('0')
        total_price = row['total_price'] or Decimal('0')
        bucket = day_data.setdefault(
            row_date,
            {
                'xl1': Decimal('0'),
                'xl2': Decimal('0'),
                'total': Decimal('0'),
            },
        )
        if code == 'TQF_XL1':
            bucket['xl1'] += total_kg
        elif code == 'TQF_XL2':
            bucket['xl2'] += total_kg
        bucket['total'] += total_kg

        price_bucket = price_day_data.setdefault(
            row_date,
            {
                'xl1': Decimal('0'),
                'xl2': Decimal('0'),
                'total': Decimal('0'),
            },
        )
        if code == 'TQF_XL1':
            price_bucket['xl1'] += total_price
        elif code == 'TQF_XL2':
            price_bucket['xl2'] += total_price
        price_bucket['total'] += total_price

    krok_grouped = (
        SarzeKrok.objects
        .filter(
            datum__gte=year_start,
            datum__lte=year_end,
            zarizeni__kod_zarizeni__in=device_codes,
            krok_bedny__bedna__isnull=False,
        )
        .values('datum')
        .annotate(step_count=Count('id', distinct=True))
    )
    krok_data = {row['datum']: (row['step_count'] or 0) for row in krok_grouped}

    prostoj_day_data = {}
    work_day_data = {}
    prostoj_kroky = (
        SarzeKrok.objects
        .filter(
            datum__gte=year_start,
            datum__lte=year_end,
            zarizeni__kod_zarizeni__in=device_codes,
        )
        .select_related('zarizeni')
    )
    for krok in prostoj_kroky:
        row_date = krok.datum
        code = krok.zarizeni.kod_zarizeni
        prodleva = krok.prodleva
        prostoj_minutes = max(prodleva - 10, 0) if isinstance(prodleva, int) else 0

        work_bucket = work_day_data.setdefault(
            row_date,
            {
                'xl1': False,
                'xl2': False,
                'total': False,
            },
        )
        if code == 'TQF_XL1':
            work_bucket['xl1'] = True
        elif code == 'TQF_XL2':
            work_bucket['xl2'] = True
        work_bucket['total'] = True

        bucket = prostoj_day_data.setdefault(
            row_date,
            {
                'xl1': 0,
                'xl2': 0,
                'total': 0,
            },
        )
        if code == 'TQF_XL1':
            bucket['xl1'] += prostoj_minutes
        elif code == 'TQF_XL2':
            bucket['xl2'] += prostoj_minutes
        bucket['total'] += prostoj_minutes

    month_labels = [
        '01 Leden', '02 Únor', '03 Březen', '04 Duben', '05 Květen', '06 Červen',
        '07 Červenec', '08 Srpen', '09 Září', '10 Říjen', '11 Listopad', '12 Prosinec',
    ]

    def _sum_day_range(start_day, end_day):
        """
        Sčítá hodnoty pro zadaný rozsah dní.
        """
        out = {
            'xl1': Decimal('0'),
            'xl2': Decimal('0'),
            'total': Decimal('0'),
        }
        if start_day and end_day and end_day >= start_day:
            day = start_day
            while day <= end_day:
                row = day_data.get(day)
                if row:
                    out['xl1'] += row['xl1']
                    out['xl2'] += row['xl2']
                    out['total'] += row['total']
                day += timedelta(days=1)
        return out

    def _sum_price_day_range(start_day, end_day):
        """
        Sčítá hodnoty cen pro zadaný rozsah dní.
        """
        out = {
            'xl1': Decimal('0'),
            'xl2': Decimal('0'),
            'total': Decimal('0'),
        }
        if start_day and end_day and end_day >= start_day:
            day = start_day
            while day <= end_day:
                row = price_day_data.get(day)
                if row:
                    out['xl1'] += row['xl1']
                    out['xl2'] += row['xl2']
                    out['total'] += row['total']
                day += timedelta(days=1)
        return out

    def _sum_step_range(start_day, end_day):
        """
        Sčítá počet kroků pro zadaný rozsah dní.
        """
        total_steps = 0
        if start_day and end_day and end_day >= start_day:
            day = start_day
            while day <= end_day:
                total_steps += krok_data.get(day, 0)
                day += timedelta(days=1)
        return total_steps

    def _sum_prostoj_minutes_range(start_day, end_day):
        """
        Sčítá hodnoty prostoje pro zadaný rozsah dní.
        """
        out = {'xl1': 0, 'xl2': 0, 'total': 0}
        if start_day and end_day and end_day >= start_day:
            day = start_day
            while day <= end_day:
                row = prostoj_day_data.get(day)
                if row:
                    out['xl1'] += row['xl1']
                    out['xl2'] += row['xl2']
                    out['total'] += row['total']
                day += timedelta(days=1)
        return out

    def _sum_work_days_range(start_day, end_day):
        """
        Sčítá počet pracovních dní pro zadaný rozsah dní.
        """
        out = {'xl1': 0, 'xl2': 0, 'total': 0}
        if start_day and end_day and end_day >= start_day:
            day = start_day
            while day <= end_day:
                row = work_day_data.get(day)
                if row:
                    if row['xl1']:
                        out['xl1'] += 1
                    if row['xl2']:
                        out['xl2'] += 1
                    if row['total']:
                        out['total'] += 1
                day += timedelta(days=1)
        return out

    def _avg_prostoj_hours_display(total_minutes, work_day_count):
        """
        Vrací průměrný počet hodin prostoje na pracovní den.
        """
        if work_day_count <= 0:
            return '0,0'
        return _format_hours((total_minutes / 60) / work_day_count)

    def _sum_hours_display(left_display, right_display):
        """
        Sčítá hodnoty hodin pro zadané zobrazení.
        """
        try:
            left = float((left_display or '0').replace(',', '.'))
            right = float((right_display or '0').replace(',', '.'))
            return _format_hours(left + right)
        except Exception:
            logger.warning("Nepodařilo se sečíst hodnoty prostoje XL1 a XL2.", exc_info=True)
            return '0,0'

    def _price_per_rost(total_price, step_count):
        """
        Vypočítá cenu za rošt na základě celkové ceny a počtu kroků.
        """
        if step_count <= 0:
            return Decimal('0.00')
        try:
            return (Decimal(total_price) / Decimal(step_count)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except Exception:
            logger.warning("Nepodařilo se spočítat cenu za rošt.", exc_info=True)
            return Decimal('0.00')

    if elapsed_end is None:
        elapsed_days_year = 0
        year_totals = {'xl1': Decimal('0'), 'xl2': Decimal('0'), 'total': Decimal('0')}
        year_prices = {'xl1': Decimal('0'), 'xl2': Decimal('0'), 'total': Decimal('0')}
        year_step_count = 0
        year_prostoj_minutes = {'xl1': 0, 'xl2': 0, 'total': 0}
        year_work_days = {'xl1': 0, 'xl2': 0, 'total': 0}
    else:
        elapsed_days_year = (elapsed_end - year_start).days + 1
        year_totals = _sum_day_range(year_start, elapsed_end)
        year_prices = _sum_price_day_range(year_start, elapsed_end)
        year_step_count = _sum_step_range(year_start, elapsed_end)
        year_prostoj_minutes = _sum_prostoj_minutes_range(year_start, elapsed_end)
        year_work_days = _sum_work_days_range(year_start, elapsed_end)

    yearly_avg = {
        'xl1': _avg_kg_per_day_int(year_totals['xl1'], elapsed_days_year),
        'xl2': _avg_kg_per_day_int(year_totals['xl2'], elapsed_days_year),
        'total': _avg_kg_per_day_int(year_totals['total'], elapsed_days_year),
    }
    yearly_rost_utilization = _kg_per_rost_int(year_totals['total'], year_step_count)
    yearly_price_per_rost = _price_per_rost(year_prices['total'], year_step_count)
    yearly_xl1_prostoj = _avg_prostoj_hours_display(year_prostoj_minutes['xl1'], year_work_days['xl1'])
    yearly_xl2_prostoj = _avg_prostoj_hours_display(year_prostoj_minutes['xl2'], year_work_days['xl2'])
    yearly_prostoj_avg = {
        'xl1_display': yearly_xl1_prostoj,
        'xl2_display': yearly_xl2_prostoj,
        'total_display': _sum_hours_display(yearly_xl1_prostoj, yearly_xl2_prostoj),
    }

    monthly_rows = []
    for month_no in range(1, 13):
        month_start = date(selected_year, month_no, 1)
        month_end = date(selected_year, month_no, calendar.monthrange(selected_year, month_no)[1])
        if elapsed_end is None or month_start > elapsed_end:
            elapsed_days = 0
            totals = {'xl1': Decimal('0'), 'xl2': Decimal('0'), 'total': Decimal('0')}
            prices = {'xl1': Decimal('0'), 'xl2': Decimal('0'), 'total': Decimal('0')}
            step_count = 0
            prostoj_minutes = {'xl1': 0, 'xl2': 0, 'total': 0}
            work_days = {'xl1': 0, 'xl2': 0, 'total': 0}
        else:
            month_elapsed_end = min(month_end, elapsed_end)
            elapsed_days = (month_elapsed_end - month_start).days + 1
            totals = _sum_day_range(month_start, month_elapsed_end)
            prices = _sum_price_day_range(month_start, month_elapsed_end)
            step_count = _sum_step_range(month_start, month_elapsed_end)
            prostoj_minutes = _sum_prostoj_minutes_range(month_start, month_elapsed_end)
            work_days = _sum_work_days_range(month_start, month_elapsed_end)

        avg_xl1 = _avg_kg_per_day_int(totals['xl1'], elapsed_days)
        avg_xl2 = _avg_kg_per_day_int(totals['xl2'], elapsed_days)
        avg_total = _avg_kg_per_day_int(totals['total'], elapsed_days)
        rost_utilization = _kg_per_rost_int(totals['total'], step_count)
        price_per_rost = _price_per_rost(prices['total'], step_count)

        month_xl1_prostoj = _avg_prostoj_hours_display(prostoj_minutes['xl1'], work_days['xl1'])
        month_xl2_prostoj = _avg_prostoj_hours_display(prostoj_minutes['xl2'], work_days['xl2'])

        monthly_rows.append(
            {
                'month': month_no,
                'label': month_labels[month_no - 1],
                'elapsed_days': elapsed_days,
                'avg': {
                    'xl1': avg_xl1,
                    'xl2': avg_xl2,
                    'total': avg_total,
                    'xl1_display': _format_kg(avg_xl1),
                    'xl2_display': _format_kg(avg_xl2),
                    'total_display': _format_kg(avg_total),
                },
                'vytizeni_rostu': {
                    'value': rost_utilization,
                    'display': _format_kg(rost_utilization),
                },
                'cena_za_rost': {
                    'value': price_per_rost,
                    'display': _format_price(price_per_rost),
                },
                'prostoj_avg': {
                    'xl1_display': month_xl1_prostoj,
                    'xl2_display': month_xl2_prostoj,
                    'total_display': _sum_hours_display(month_xl1_prostoj, month_xl2_prostoj),
                },
            }
        )

    weekly_rows = []
    week_start = year_start - timedelta(days=year_start.weekday())
    week_no = 1
    while week_start <= year_end:
        week_end = week_start + timedelta(days=6)
        in_year_start = max(week_start, year_start)
        in_year_end = min(week_end, year_end)

        if elapsed_end is None or in_year_start > elapsed_end:
            elapsed_days = 0
            totals = {'xl1': Decimal('0'), 'xl2': Decimal('0'), 'total': Decimal('0')}
            prices = {'xl1': Decimal('0'), 'xl2': Decimal('0'), 'total': Decimal('0')}
            step_count = 0
            prostoj_minutes = {'xl1': 0, 'xl2': 0, 'total': 0}
            work_days = {'xl1': 0, 'xl2': 0, 'total': 0}
        else:
            week_elapsed_end = min(in_year_end, elapsed_end)
            elapsed_days = (week_elapsed_end - in_year_start).days + 1
            totals = _sum_day_range(in_year_start, week_elapsed_end)
            prices = _sum_price_day_range(in_year_start, week_elapsed_end)
            step_count = _sum_step_range(in_year_start, week_elapsed_end)
            prostoj_minutes = _sum_prostoj_minutes_range(in_year_start, week_elapsed_end)
            work_days = _sum_work_days_range(in_year_start, week_elapsed_end)

        avg_xl1 = _avg_kg_per_day_int(totals['xl1'], elapsed_days)
        avg_xl2 = _avg_kg_per_day_int(totals['xl2'], elapsed_days)
        avg_total = _avg_kg_per_day_int(totals['total'], elapsed_days)
        rost_utilization = _kg_per_rost_int(totals['total'], step_count)
        price_per_rost = _price_per_rost(prices['total'], step_count)

        week_xl1_prostoj = _avg_prostoj_hours_display(prostoj_minutes['xl1'], work_days['xl1'])
        week_xl2_prostoj = _avg_prostoj_hours_display(prostoj_minutes['xl2'], work_days['xl2'])

        weekly_rows.append(
            {
                'week_no': week_no,
                'label': f'{week_no:02d}',
                'date_range': f"{in_year_start.strftime('%d.%m.')} - {in_year_end.strftime('%d.%m.')}",
                'elapsed_days': elapsed_days,
                'avg': {
                    'xl1': avg_xl1,
                    'xl2': avg_xl2,
                    'total': avg_total,
                    'xl1_display': _format_kg(avg_xl1),
                    'xl2_display': _format_kg(avg_xl2),
                    'total_display': _format_kg(avg_total),
                },
                'vytizeni_rostu': {
                    'value': rost_utilization,
                    'display': _format_kg(rost_utilization),
                },
                'cena_za_rost': {
                    'value': price_per_rost,
                    'display': _format_price(price_per_rost),
                },
                'prostoj_avg': {
                    'xl1_display': week_xl1_prostoj,
                    'xl2_display': week_xl2_prostoj,
                    'total_display': _sum_hours_display(week_xl1_prostoj, week_xl2_prostoj),
                },
            }
        )
        week_no += 1
        week_start += timedelta(days=7)

    month_detail = None
    if selected_month is not None:
        month_start = date(selected_year, selected_month, 1)
        month_end = date(selected_year, selected_month, calendar.monthrange(selected_year, selected_month)[1])
        detail_end = None
        if elapsed_end is not None and month_start <= elapsed_end:
            detail_end = min(month_end, elapsed_end)

        day_rows = []
        if detail_end is not None:
            d = month_start
            while d <= detail_end:
                totals = day_data.get(
                    d,
                    {'xl1': Decimal('0'), 'xl2': Decimal('0'), 'total': Decimal('0')},
                )
                prices = price_day_data.get(
                    d,
                    {'xl1': Decimal('0'), 'xl2': Decimal('0'), 'total': Decimal('0')},
                )
                xl1_int = _kg_to_int(totals['xl1'])
                xl2_int = _kg_to_int(totals['xl2'])
                total_int = _kg_to_int(totals['total'])
                step_count = krok_data.get(d, 0)
                rost_utilization = _kg_per_rost_int(totals['total'], step_count)
                price_per_rost = _price_per_rost(prices['total'], step_count)
                day_prostoj = prostoj_day_data.get(d, {'xl1': 0, 'xl2': 0, 'total': 0})
                day_rows.append(
                    {
                        'date': d,
                        'label': d.strftime('%d.%m.%Y'),
                        'xl1': xl1_int,
                        'xl2': xl2_int,
                        'total': total_int,
                        'xl1_display': _format_kg(xl1_int),
                        'xl2_display': _format_kg(xl2_int),
                        'total_display': _format_kg(total_int),
                        'vytizeni_rostu': {
                            'value': rost_utilization,
                            'display': _format_kg(rost_utilization),
                        },
                        'cena_za_rost': {
                            'value': price_per_rost,
                            'display': _format_price(price_per_rost),
                        },
                        'prostoj_avg': {
                            'xl1_display': _avg_prostoj_hours_display(day_prostoj['xl1'], 1),
                            'xl2_display': _avg_prostoj_hours_display(day_prostoj['xl2'], 1),
                            'total_display': _sum_hours_display(
                                _avg_prostoj_hours_display(day_prostoj['xl1'], 1),
                                _avg_prostoj_hours_display(day_prostoj['xl2'], 1),
                            ),
                        },
                    }
                )
                d += timedelta(days=1)

        month_detail = {
            'month': selected_month,
            'label': month_labels[selected_month - 1],
            'rows': day_rows,
        }

    return {
        'vyroba_historie': {
            'title': 'Přehled výroby historie',
            'selected_year': selected_year,
            'available_years': years_with_data,
            'selected_month': selected_month,
            'yearly': {
                'elapsed_days': elapsed_days_year,
                'avg': {
                    'xl1': yearly_avg['xl1'],
                    'xl2': yearly_avg['xl2'],
                    'total': yearly_avg['total'],
                    'xl1_display': _format_kg(yearly_avg['xl1']),
                    'xl2_display': _format_kg(yearly_avg['xl2']),
                    'total_display': _format_kg(yearly_avg['total']),
                },
                'vytizeni_rostu': {
                    'value': yearly_rost_utilization,
                    'display': _format_kg(yearly_rost_utilization),
                },
                'cena_za_rost': {
                    'value': yearly_price_per_rost,
                    'display': _format_price(yearly_price_per_rost),
                },
                'prostoj_avg': yearly_prostoj_avg,
            },
            'monthly_rows': monthly_rows,
            'weekly_rows': weekly_rows,
            'month_detail': month_detail,
        },
        'db_table': 'dashboard_vyroba',
        'current_time': timezone.now(),
    }


def _build_vyroba_zakaznici_vyuziti_context(year_value=None, today_value=None):
    """
    Vytváří kontext pro využití zákazníků výroby na základě zadaného roku a dnešního data.
    """
    device_codes = ["TQF_XL1", "TQF_XL2"]
    today = today_value or timezone.localdate()
    years_with_data = _get_vyroba_available_years(device_codes, today_value=today)

    try:
        selected_year = int(year_value) if year_value is not None else years_with_data[0]
    except (TypeError, ValueError):
        selected_year = years_with_data[0]
    if selected_year not in years_with_data:
        selected_year = years_with_data[0]

    year_start = date(selected_year, 1, 1)
    year_end = date(selected_year, 12, 31)
    elapsed_end = min(today, year_end) if selected_year == today.year else year_end
    if elapsed_end < year_start:
        elapsed_end = None

    first_use_rows = list(
        _first_use_sarzekrokbedna_range_qs(year_start, year_end, device_codes)
        .values(
            'krok__datum',
            'bedna__zakazka__kamion_prijem__zakaznik__zkraceny_nazev',
        )
        .annotate(total_kg=Sum('bedna__hmotnost'))
    )

    customer_day_data = {}
    for row in first_use_rows:
        row_date = row['krok__datum']
        customer = row['bedna__zakazka__kamion_prijem__zakaznik__zkraceny_nazev'] or '-'
        total_kg = row['total_kg'] or Decimal('0')
        bucket = customer_day_data.setdefault(row_date, {})
        customer_bucket = bucket.setdefault(
            customer,
            {
                'kg': Decimal('0'),
                'step_share': Decimal('0'),
            },
        )
        customer_bucket['kg'] += total_kg

    step_share_qs = SarzeKrokBedna.objects.filter(
        krok__datum__gte=year_start,
        krok__datum__lte=year_end,
        krok__zarizeni__kod_zarizeni__in=device_codes,
        bedna__isnull=False,
    )
    step_total_percents = {
        row['krok_id']: row['total_percent'] or Decimal('0')
        for row in (
            step_share_qs
            .values('krok_id')
            .annotate(total_percent=Sum('procent_z_patra'))
        )
    }
    step_share_rows = (
        step_share_qs
        .values(
            'krok_id',
            'krok__datum',
            'bedna__zakazka__kamion_prijem__zakaznik__zkraceny_nazev',
        )
        .annotate(percent_sum=Sum('procent_z_patra'))
    )
    for row in step_share_rows:
        step_total_percent = step_total_percents.get(row['krok_id'], Decimal('0'))
        percent_sum = row['percent_sum'] or Decimal('0')
        if step_total_percent <= 0 or percent_sum <= 0:
            continue
        row_date = row['krok__datum']
        customer = row['bedna__zakazka__kamion_prijem__zakaznik__zkraceny_nazev'] or '-'
        step_share = Decimal(percent_sum) / Decimal(step_total_percent)
        bucket = customer_day_data.setdefault(row_date, {})
        customer_bucket = bucket.setdefault(
            customer,
            {
                'kg': Decimal('0'),
                'step_share': Decimal('0'),
            },
        )
        customer_bucket['step_share'] += step_share

    krok_data = {
        row['datum']: (row['step_count'] or 0)
        for row in (
            SarzeKrok.objects
            .filter(
                datum__gte=year_start,
                datum__lte=year_end,
                zarizeni__kod_zarizeni__in=device_codes,
                krok_bedny__bedna__isnull=False,
            )
            .values('datum')
            .annotate(step_count=Count('id', distinct=True))
        )
    }

    def _sum_customer_range(customer, start_day, end_day):
        """
        Sčítá hodnoty pro zadaný rozsah dní pro konkrétního zákazníka.
        """
        total_kg = Decimal('0')
        total_step_share = Decimal('0')
        if start_day and end_day and end_day >= start_day:
            day = start_day
            while day <= end_day:
                row = customer_day_data.get(day, {}).get(customer)
                if row:
                    total_kg += row['kg']
                    total_step_share += row['step_share']
                day += timedelta(days=1)
        return {
            'kg': total_kg,
            'step_share': total_step_share,
        }

    def _sum_all_customer_kg_range(start_day, end_day):
        total = Decimal('0')
        if start_day and end_day and end_day >= start_day:
            day = start_day
            while day <= end_day:
                total += sum(
                    (row['kg'] for row in customer_day_data.get(day, {}).values()),
                    Decimal('0'),
                )
                day += timedelta(days=1)
        return total

    def _sum_step_range(start_day, end_day):
        """
        Sčítá počet kroků pro zadaný rozsah dní.
        """
        total_steps = 0
        if start_day and end_day and end_day >= start_day:
            day = start_day
            while day <= end_day:
                total_steps += krok_data.get(day, 0)
                day += timedelta(days=1)
        return total_steps

    def _kg_per_customer_rost(total_kg, step_share):
        """
        Vypočítá využití roštu podle zákazníků na základě celkové hmotnosti a podílu kroků.
        """
        if step_share <= 0:
            return 0
        try:
            return _kg_to_int(Decimal(total_kg) / Decimal(step_share))
        except Exception:
            logger.warning("Nepodařilo se spočítat využití roštu podle zákazníků.", exc_info=True)
            return 0

    def _kg_per_rost(total_kg, step_count):
        """
        Vypočítá celkové využití roštu na základě celkové hmotnosti a počtu kroků.
        """
        if step_count <= 0:
            return 0
        try:
            return _kg_to_int(Decimal(total_kg) / Decimal(step_count))
        except Exception:
            logger.warning("Nepodařilo se spočítat celkové využití roštu.", exc_info=True)
            return 0

    def _format_usage(value):
        return _format_kg(value) if value else '-'

    customers = sorted(
        {
            customer
            for day_data in customer_day_data.values()
            for customer in day_data.keys()
        }
    )

    if elapsed_end is None:
        year_step_count = 0
        year_total_kg = Decimal('0')
    else:
        year_step_count = _sum_step_range(year_start, elapsed_end)
        year_total_kg = _sum_all_customer_kg_range(year_start, elapsed_end)

    weeks = []
    customer_week_values = {customer: [] for customer in customers}
    total_week_values = []
    week_start = year_start - timedelta(days=year_start.weekday())
    week_no = 1
    while week_start <= year_end:
        week_end = week_start + timedelta(days=6)
        in_year_start = max(week_start, year_start)
        in_year_end = min(week_end, year_end)

        if elapsed_end is None or in_year_start > elapsed_end:
            elapsed_days = 0
            step_count = 0
            week_elapsed_end = None
        else:
            week_elapsed_end = min(in_year_end, elapsed_end)
            elapsed_days = (week_elapsed_end - in_year_start).days + 1
            step_count = _sum_step_range(in_year_start, week_elapsed_end)

        weeks.append({
            'week_no': week_no,
            'label': f'{week_no:02d}',
            'date_range': f"{in_year_start.strftime('%d.%m.')} - {in_year_end.strftime('%d.%m.')}",
            'elapsed_days': elapsed_days,
            'step_count': step_count,
        })

        week_total_kg = Decimal('0')
        for customer in customers:
            customer_data = {'kg': Decimal('0'), 'step_share': Decimal('0')} if week_elapsed_end is None else _sum_customer_range(
                customer,
                in_year_start,
                week_elapsed_end,
            )
            week_total_kg += customer_data['kg']
            usage = _kg_per_customer_rost(customer_data['kg'], customer_data['step_share'])
            customer_week_values[customer].append({
                'value': usage,
                'display': _format_usage(usage),
            })

        total_usage = _kg_per_rost(week_total_kg, step_count)
        total_week_values.append({
            'value': total_usage,
            'display': _format_usage(total_usage),
        })

        week_no += 1
        week_start += timedelta(days=7)

    customer_rows = []
    for customer in customers:
        customer_year_data = {'kg': Decimal('0'), 'step_share': Decimal('0')} if elapsed_end is None else _sum_customer_range(
            customer,
            year_start,
            elapsed_end,
        )
        total_usage = _kg_per_customer_rost(customer_year_data['kg'], customer_year_data['step_share'])
        customer_rows.append({
            'customer': customer,
            'weeks': customer_week_values[customer],
            'total': {
                'value': total_usage,
                'display': _format_usage(total_usage),
            },
        })

    yearly_usage = _kg_per_rost(year_total_kg, year_step_count)

    return {
        'vyroba_zakaznici_vyuziti': {
            'title': 'Přehled využití roštů podle zákazníků',
            'selected_year': selected_year,
            'available_years': years_with_data,
            'yearly': {
                'step_count': year_step_count,
                'vytizeni_rostu': {
                    'value': yearly_usage,
                    'display': _format_usage(yearly_usage),
                },
            },
            'weeks': weeks,
            'customer_rows': customer_rows,
            'total_row': {
                'label': 'CELKEM',
                'weeks': total_week_values,
                'total': {
                    'value': yearly_usage,
                    'display': _format_usage(yearly_usage),
                },
            },
        },
        'db_table': 'dashboard_vyroba_zakaznici_vyuziti',
        'current_time': timezone.now(),
    }


def _build_vyroba_dashboard_context(date_value=None):
    """
    Vytváří kontext pro dashboard výroby na základě zadaného data.
    """
    date_value = date_value or (timezone.localdate() - timedelta(days=1))
    today = date_value + timedelta(days=1)
    device_codes = ["TQF_XL1", "TQF_XL2"]

    base_qs = SarzeKrok.objects.filter(
        datum=date_value,
        zarizeni__kod_zarizeni__in=device_codes,
    ).select_related('sarze', 'zarizeni')

    bedna_exists = SarzeKrokBedna.objects.filter(
        krok=OuterRef('pk'),
        bedna__isnull=False,
    )
    manual_exists = SarzeKrokBedna.objects.filter(
        krok=OuterRef('pk'),
        bedna__isnull=True,
    ).filter(
        popis_mimo_db__isnull=False,
    )

    qs = base_qs.annotate(
        has_vruty=Exists(bedna_exists),
        has_zelezo=Exists(manual_exists),
    )

    def _calc_vykon_vruty_kg(code: list[str]):
        first_use_qs = _first_use_sarzekrokbedna_qs(date_value, code)

        return first_use_qs.aggregate(total=Sum('bedna__hmotnost')).get('total') or 0

    def _calc_daily_total_kg(target_day):
        return _first_use_sarzekrokbedna_qs(target_day, device_codes).aggregate(total=Sum('bedna__hmotnost')).get('total') or 0

    def _device_stats(code: list[str]):
        dqs = qs.filter(zarizeni__kod_zarizeni__in=code)
        total = dqs.count()
        vruty = dqs.filter(has_vruty=True).count()
        zelezo = dqs.filter(has_zelezo=True).count()
        prostoj_minutes = _calc_prostoj_minutes(list(dqs))
        prostoj_hours = _format_hours(prostoj_minutes / 60) if prostoj_minutes else '0,0'
        vykon_vruty_tuny = _format_tuny(_calc_vykon_vruty_kg(code))
        return {
            'total': total,
            'vruty': vruty,
            'zelezo': zelezo,
            'prostoj_hours': prostoj_hours,
            'vykon_vruty_tuny': vykon_vruty_tuny,
        }

    xl1 = _device_stats([device_codes[0]])
    xl2 = _device_stats([device_codes[1]])
    summary = _device_stats(device_codes)

    def _shift_stats(shift_qs):
        """
        Vypočítá statistiky pro zadaný queryset směny.
        """
        xl1_qs = shift_qs.filter(zarizeni__kod_zarizeni=device_codes[0])
        xl2_qs = shift_qs.filter(zarizeni__kod_zarizeni=device_codes[1])

        xl1_count = xl1_qs.count()
        xl2_count = xl2_qs.count()
        total_count = xl1_count + xl2_count

        xl1_minutes = _calc_prostoj_minutes(list(xl1_qs))
        xl2_minutes = _calc_prostoj_minutes(list(xl2_qs))
        total_minutes = xl1_minutes + xl2_minutes

        return {
            'counts': {
                'xl1': xl1_count,
                'xl2': xl2_count,
                'total': total_count,
            },
            'prostoje': {
                'xl1': _format_hours(xl1_minutes / 60) if xl1_minutes else '0,0',
                'xl2': _format_hours(xl2_minutes / 60) if xl2_minutes else '0,0',
                'total': _format_hours(total_minutes / 60) if total_minutes else '0,0',
            },
        }

    day_qs = base_qs.filter(zacatek__gte=time(7, 0), zacatek__lt=time(19, 0))
    night_qs = SarzeKrok.objects.filter(
        zarizeni__kod_zarizeni__in=device_codes,
    ).filter(
        Q(datum=date_value, zacatek__gte=time(19, 0))
        | Q(datum=today, zacatek__lt=time(7, 0))
    ).select_related('sarze', 'zarizeni')

    dashboard = {
        'date_label': date_value.strftime('%d.%m.%Y'),
        'devices': {
            'xl1': xl1,
            'xl2': xl2,
            'celkem': summary,
        },
        'shifts': {
            'day': _shift_stats(day_qs),
            'night': _shift_stats(night_qs),
        },
    }

    # Včerejší produkce vrutů (zakalené) 0:00-24:00 - pouze první použití bedny
    yesterday_first_use = _first_use_sarzekrokbedna_qs(date_value, device_codes)
    customer_totals = list(
        yesterday_first_use
        .values('bedna__zakazka__kamion_prijem__zakaznik__zkraceny_nazev')
        .annotate(total_kg=Sum('bedna__hmotnost'))
        .order_by('bedna__zakazka__kamion_prijem__zakaznik__zkraceny_nazev')
    )
    customer_items = [
        {
            'name': item['bedna__zakazka__kamion_prijem__zakaznik__zkraceny_nazev'] or '-',
            'kg': _kg_to_int(item['total_kg']),
            'kg_display': _format_kg(item['total_kg']),
        }
        for item in customer_totals
    ]
    customer_rows = []
    for idx in range(0, len(customer_items), 3):
        row = customer_items[idx:idx + 3]
        while len(row) < 3:
            row.append(None)
        customer_rows.append(row)

    dashboard['vcerejsi_produkce_vrutu'] = {
        'total_kg': _kg_to_int(_calc_daily_total_kg(date_value)),
        'total_kg_display': _format_kg(_calc_daily_total_kg(date_value)),
        'customer_rows': customer_rows,
    }

    # Historie produkce vrutů (posledních 14 dní), pouze první použití bedny
    day_labels = ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"]
    history_rows = []
    for back in range(13, -1, -1):
        day = date_value - timedelta(days=back)
        daily_kg_int = _kg_to_int(_calc_daily_total_kg(day))
        history_rows.append({
            'date': day,
            'den_label': f"{day_labels[day.weekday()]} {day.strftime('%d.%m.%Y')}",
            'daily_kg': daily_kg_int,
            'daily_kg_display': _format_kg(daily_kg_int),
            'weekly_avg_display': '',
            'biweekly_avg_display': '',
        })

    first_week = [row['daily_kg'] for row in history_rows[:7]]
    second_week = [row['daily_kg'] for row in history_rows[7:14]]
    all_days = [row['daily_kg'] for row in history_rows]

    week1_avg = int(round(sum(first_week) / len(first_week))) if first_week else 0
    week2_avg = int(round(sum(second_week) / len(second_week))) if second_week else 0
    biweekly_avg = int(round(sum(all_days) / len(all_days))) if all_days else 0

    if history_rows:
        history_rows[0]['weekly_avg_display'] = _format_kg(week1_avg)
        history_rows[0]['biweekly_avg_display'] = _format_kg(biweekly_avg)
    if len(history_rows) > 7:
        history_rows[7]['weekly_avg_display'] = _format_kg(week2_avg)

    dashboard['historie_produkce_vrutu'] = {
        'rows': history_rows,
    }

    return {'vyroba_dashboard': dashboard, 'current_time': timezone.now()}

@login_required
def dashboard_bedny_view(request):
    """
    Přehled stavu beden dle zákazníků.
    """
    def get_stav_data(filter_kwargs):
        """
        Získává data o stavech beden pro dané filtry.
        """
        data = Bedna.objects.filter(**filter_kwargs).values(
            'zakazka__kamion_prijem__zakaznik__zkraceny_nazev'
        ).annotate(
            pocet=Count('id'),
            hmotnost=Sum('hmotnost')/1000 # převod na tuny (z kg)
        )
        data_dict = {
            item['zakazka__kamion_prijem__zakaznik__zkraceny_nazev']: (item['pocet'], item['hmotnost']) for item in data
        }
        total = Bedna.objects.filter(**filter_kwargs).aggregate(
            pocet=Count('id'),
            hmotnost=Sum('hmotnost')/1000  # také převod na tuny pro řádek CELKEM
        )
        data_dict['CELKEM'] = (
            total['pocet'] or 0,
            (total['hmotnost'] or 0)  # už v tunách
        )
        return data_dict

    kompletni_zakazky = (
        Zakazka.objects
        .annotate(
            pocet_beden_celkem=Count('bedny'),
            pocet_beden_k_expedici=Count(
                'bedny',
                filter=Q(bedny__stav_bedny=StavBednyChoice.K_EXPEDICI),
            ),
        )
        .filter(
            pocet_beden_celkem__gt=0,
            pocet_beden_celkem=F('pocet_beden_k_expedici'),
        )
    )

    stavy = {
        'Nepřijaté': ({'stav_bedny': StavBednyChoice.NEPRIJATO}, 'gray'),
        'Surové': ({'stav_bedny__in': [StavBednyChoice.PRIJATO, StavBednyChoice.K_NAVEZENI, StavBednyChoice.NAVEZENO, StavBednyChoice.DO_ZPRACOVANI]}, "red"),
        '-> K navezení': ({'stav_bedny': StavBednyChoice.K_NAVEZENI}, 'red'),
        '-> Navezené': ({'stav_bedny': StavBednyChoice.NAVEZENO}, 'red'),
        'Zpracované': ({'stav_bedny__in': [StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO, StavBednyChoice.K_EXPEDICI]}, 'orange'),
        '-> Ke kontrole': ({'stav_bedny': StavBednyChoice.ZAKALENO}, 'orange'),
        '-> K tryskání': ({'tryskat': TryskaniChoice.SPINAVA, 'stav_bedny__in': [StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO]}, 'yellowgreen'),
        '-> Křivé': ({'rovnat': RovnaniChoice.KRIVA, 'stav_bedny__in': [StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO]}, 'blue'),
        '-> Koulení': ({'rovnat': RovnaniChoice.KOULENI, 'stav_bedny__in': [StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO]}, 'blue'),
        '-> Rovná se': ({'rovnat': RovnaniChoice.ROVNA_SE, 'stav_bedny__in': [StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO]}, 'blue'),
        '-> Zinkovat': ({'zinkovat': ZinkovaniChoice.ZINKOVAT, 'stav_bedny__in': [StavBednyChoice.ZAKALENO, StavBednyChoice.ZKONTROLOVANO]}, 'violet'),
        '-> V zinkovně': ({'zinkovat': ZinkovaniChoice.V_ZINKOVNE}, 'violet'),
        '-> K exp. po bednách': ({'stav_bedny': StavBednyChoice.K_EXPEDICI}, 'green'),
        '--> K exp. po zakáz.': ({'stav_bedny': StavBednyChoice.K_EXPEDICI, 'zakazka__in': kompletni_zakazky}, 'green'),
        'Po exspiraci': ({'stav_bedny__in': STAV_BEDNY_SKLADEM, 'zakazka__kamion_prijem__datum__lt': timezone.now().date() - timezone.timedelta(days=28)}, '#ff66b3'),
    }

    zakaznici = list(Zakaznik.objects.values_list('zkraceny_nazev', flat=True).order_by('zkraceny_nazev')) + ['CELKEM']
    prehled_beden_zakaznika = {zak: {stav: (0, 0, '') for stav in stavy} for zak in zakaznici}

    for stav, (filter_kwargs, color) in stavy.items():
        stav_data = get_stav_data(filter_kwargs)
        for zak in zakaznici:
            prehled_beden_zakaznika[zak][stav] = (stav_data.get(zak, (0, 0)) + (color,))

    stavy_bedny_list = list(stavy.keys())

    context = {
        'prehled_beden_zakaznika': prehled_beden_zakaznika,
        'stavy_bedny_list': stavy_bedny_list,
        'db_table': 'dashboard_bedny',
        'current_time': timezone.now(),
    }

    if request.htmx:
        return render(request, "orders/partials/dashboard_bedny_content.html", context)
    return render(request, 'orders/dashboard_bedny.html', context)

@login_required
def dashboard_kamiony_view(request):
    """
    Zobrazení přehledu příjmů a výdejů kamionů za jednotlivé měsíce v roce.
    Umožňuje filtrovat podle roku a zobrazuje celkovou hmotnost beden pro jednotlivé zákazníky.
    V případě HTMX požadavku vrací pouze část obsahu pro aktualizaci.
    """
    zakaznici = Zakaznik.objects.all().order_by('zkratka')
    rok = request.GET.get('rok', timezone.now().year)
    kamiony_prijem_rok = Kamion.objects.filter(prijem_vydej='P', datum__year=rok)
    kamiony_vydej_rok = Kamion.objects.filter(prijem_vydej='V', datum__year=rok)

    kamiony_prijem = kamiony_prijem_rok.values(
        'datum__month', 'zakaznik__zkratka'
    ).annotate(
        celkova_hmotnost=Sum(
            'zakazky_prijem__bedny__hmotnost',
            filter=Q(zakazky_prijem__bedny__fakturovat=True),
        )
    )

    kamiony_vydej = kamiony_vydej_rok.values(
        'datum__month', 'zakaznik__zkratka'
    ).annotate(
        celkova_hmotnost=Sum(
            'zakazky_vydej__bedny__hmotnost',
            filter=Q(zakazky_vydej__bedny__fakturovat=True),
        ),
        hmotnost_krivych=Sum(
            'zakazky_vydej__bedny__hmotnost',
            filter=Q(
                zakazky_vydej__bedny__fakturovat=True,
                zakazky_vydej__bedny__rovnat=RovnaniChoice.VYROVNANA,
            ),
        ),
    )

    # Inicializace slovníku pro měsíční pohyby
    mesicni_pohyby = {}
    # Přidání všech měsíců do slovníku, aby se zajistilo, že budou zobrazeny i prázdné měsíce
    mesice = ('leden / január', 'únor / február', 'březen / marec',
              'duben / apríl', 'květen / máj', 'červen / jún',
              'červenec / júl', 'srpen / august', 'září / september',
              'říjen / október', 'listopad / november', 'prosinec / december')
    for mesic in range(1, 13):
        # Inicializace prázdného slovníku pro každý měsíc
        mesicni_pohyby[mesic] = {}
        # Přidání všech zákazníků do každého měsíce, aby se zajistilo, že budou zobrazeny i zákazníci bez pohybu v daném měsíci
        for zakaznik in zakaznici:
            mesicni_pohyby[mesic][zakaznik.zkratka] = {
                'prijem': 0,
                'vydej': 0,
                'hmotnost_krivych': 0,
            }

    # Sčítání příjmů a výdejů pro jednotlivé měsíce a zákazníky
    for kamion_prijem in kamiony_prijem:
        mesic = kamion_prijem['datum__month']
        zakaznik = kamion_prijem['zakaznik__zkratka']
        mesicni_pohyby[mesic][zakaznik]['prijem'] += kamion_prijem['celkova_hmotnost'] or 0

    for kamion_vydej in kamiony_vydej:
        mesic = kamion_vydej['datum__month']
        zakaznik = kamion_vydej['zakaznik__zkratka']
        mesicni_pohyby[mesic][zakaznik]['vydej'] += kamion_vydej['celkova_hmotnost'] or 0
        mesicni_pohyby[mesic][zakaznik]['hmotnost_krivych'] += kamion_vydej['hmotnost_krivych'] or 0

    # Přidání celkových součtů pro každý měsíc
    for mesic, zakaznici_pohyby in mesicni_pohyby.items():
        celkovy_prijem = sum(pohyby['prijem'] for pohyby in zakaznici_pohyby.values())
        celkovy_vydej = sum(pohyby['vydej'] for pohyby in zakaznici_pohyby.values())
        celkova_hmotnost_krivych = sum(pohyby['hmotnost_krivych'] for pohyby in zakaznici_pohyby.values())
        mesicni_pohyby[mesic]['CELKEM'] = {
            'prijem': celkovy_prijem,
            'vydej': celkovy_vydej,
            'hmotnost_krivych': celkova_hmotnost_krivych,
        }

    # Přidání celkových součtů dle zákazníků za celý rok
    rocni_pohyby = {}
    for mesic, zakaznici_pohyby in mesicni_pohyby.items():
        for zakaznik, pohyby in zakaznici_pohyby.items():
            if zakaznik not in rocni_pohyby:
                rocni_pohyby[zakaznik] = {'prijem': 0, 'vydej': 0, 'hmotnost_krivych': 0}
            rocni_pohyby[zakaznik]['prijem'] += pohyby['prijem']
            rocni_pohyby[zakaznik]['vydej'] += pohyby['vydej']
            rocni_pohyby[zakaznik]['hmotnost_krivych'] += pohyby['hmotnost_krivych']

    mesicni_pohyby['CELKEM'] = rocni_pohyby

    # Přidání rozdílu mezi příjmy a výdeji pro každý měsíc pro každého zákazníka
    for mesic, zakaznici_pohyby in mesicni_pohyby.items():
        for zakaznik, pohyby in zakaznici_pohyby.items():
            mesicni_pohyby[mesic][zakaznik]['rozdil'] = pohyby['prijem'] - pohyby['vydej']
            if pohyby['vydej']:
                mesicni_pohyby[mesic][zakaznik]['procento_krivych'] = (
                    Decimal(pohyby['hmotnost_krivych']) / Decimal(pohyby['vydej'])
                ) * Decimal('100')
            else:
                mesicni_pohyby[mesic][zakaznik]['procento_krivych'] = None

    # Přehled průměrného denního importu/exportu za posledních 14 dní
    end_date = timezone.localdate() - timedelta(days=1)
    start_date = end_date - timedelta(days=13)
    period_days = 14

    import_qs_14 = Kamion.objects.filter(
        prijem_vydej=KamionChoice.PRIJEM,
        datum__range=(start_date, end_date),
    )
    export_qs_14 = Kamion.objects.filter(
        prijem_vydej=KamionChoice.VYDEJ,
        datum__range=(start_date, end_date),
    )

    total_import_kg = (
        import_qs_14.aggregate(
            total=Sum(
                'zakazky_prijem__bedny__hmotnost',
                filter=Q(zakazky_prijem__bedny__fakturovat=True),
            )
        ).get('total')
        or Decimal('0')
    )
    total_export_kg = (
        export_qs_14.aggregate(
            total=Sum(
                'zakazky_vydej__bedny__hmotnost',
                filter=Q(zakazky_vydej__bedny__fakturovat=True),
            )
        ).get('total')
        or Decimal('0')
    )

    avg_import_t = Decimal(total_import_kg) / Decimal(period_days * 1000)
    avg_export_t = Decimal(total_export_kg) / Decimal(period_days * 1000)
    import_truck_count = (Decimal(total_import_kg) / Decimal(1000)) / Decimal('18')
    export_truck_count = (Decimal(total_export_kg) / Decimal(1000)) / Decimal('18')

    context = {
        'mesicni_pohyby': mesicni_pohyby,
        'rok': rok,
        'prumery_14_dni': {
            'start_date': start_date,
            'end_date': end_date,
            'import_t': avg_import_t,
            'export_t': avg_export_t,
            'import_kamiony': import_truck_count,
            'export_kamiony': export_truck_count,
        },
        'db_table': 'dashboard_kamiony',
        'current_time': timezone.now(),
    }
    
    if request.htmx:
        return render(request, "orders/partials/dashboard_kamiony_content.html", context)
    return render(request, 'orders/dashboard_kamiony.html', context)


@login_required
def dashboard_vyroba_view(request):
    """
    Přehled výroby (včerejší den + 14denní historie).
    """
    context = _build_vyroba_dashboard_context()
    if request.htmx:
        return render(request, "orders/partials/dashboard_vyroba_content.html", context)
    return render(request, 'orders/dashboard_vyroba.html', context)


@login_required
def dashboard_vyroba_historie_view(request):
    """
    Roční přehled historie výroby vrutů pro TQF XL1 / TQF XL2.
    """
    year_value = request.GET.get('rok')
    context = _build_vyroba_historie_context(year_value=year_value)
    if request.htmx:
        return render(request, "orders/partials/dashboard_vyroba_historie_content.html", context)
    return render(request, 'orders/dashboard_vyroba_historie.html', context)


@login_required
def dashboard_vyroba_zakaznici_vyuziti_view(request):
    """
    Roční přehled průměrného využití roštů v jednotlivých týdnech pro jednotlivé zákazníky.
    """
    year_value = request.GET.get('rok')
    context = _build_vyroba_zakaznici_vyuziti_context(year_value=year_value)
    if request.htmx:
        return render(request, "orders/partials/dashboard_vyroba_zakaznici_vyuziti_content.html", context)
    return render(request, 'orders/dashboard_vyroba_zakaznici_vyuziti.html', context)


@login_required
def dashboard_vyroba_historie_mesic_view(request):
    """
    Detail denní produkce za zvolený měsíc v roční historii výroby.
    """
    year_value = request.GET.get('rok')
    month_value = request.GET.get('mesic')
    if month_value is None or str(month_value).strip() == '':
        if year_value:
            return redirect(f"{reverse('dashboard_vyroba_historie')}?rok={year_value}")
        return redirect('dashboard_vyroba_historie')

    context = _build_vyroba_historie_context(year_value=year_value, month_value=month_value)
    if context['vyroba_historie'].get('month_detail') is None:
        if year_value:
            return redirect(f"{reverse('dashboard_vyroba_historie')}?rok={year_value}")
        return redirect('dashboard_vyroba_historie')

    if request.htmx:
        return render(request, "orders/partials/dashboard_vyroba_historie_mesic_content.html", context)
    return render(request, 'orders/dashboard_vyroba_historie_mesic.html', context)


def _get_bedny_k_navezeni_groups():
    """Sestaví seskupená data beden k navezení podle pozice a zakázky."""
    pozice_list = list(Pozice.objects.order_by('kod'))

    qs = (
        Bedna.objects
        .filter(stav_bedny=StavBednyChoice.K_NAVEZENI)
        .select_related('pozice', 'zakazka')
        .order_by('pozice__kod', 'zakazka', 'cislo_bedny')
    )
    bedny = list(qs)

    active_pairs = {
        (bedna.pozice_id, bedna.zakazka_id)
        for bedna in bedny
        if bedna.pozice_id is not None and bedna.zakazka_id is not None
    }
    orders_by_position = {}
    # Keep PoziceZakazkaOrder synced with current bedny state.
    with transaction.atomic():
        existing_orders = list(
            PoziceZakazkaOrder.objects.order_by('pozice_id', 'poradi', 'pk')
        )

        stale_ids = {
            order.pk for order in existing_orders
            if (order.pozice_id, order.zakazka_id) not in active_pairs
        }
        if stale_ids:
            PoziceZakazkaOrder.objects.filter(pk__in=stale_ids).delete()
            existing_orders = [order for order in existing_orders if order.pk not in stale_ids]

        for order in existing_orders:
            if order.pozice_id is None:
                continue
            orders_by_position.setdefault(order.pozice_id, []).append(order)

        for pozice_id, order_list in orders_by_position.items():
            for idx, order in enumerate(order_list, start=1):
                if order.poradi != idx:
                    PoziceZakazkaOrder.objects.filter(pk=order.pk).update(poradi=idx)
                    order.poradi = idx

        seen_pairs = set()
        for bedna in bedny:
            pozice_id = bedna.pozice_id
            zakazka_id = bedna.zakazka_id
            if pozice_id is None or zakazka_id is None:
                continue
            pair = (pozice_id, zakazka_id)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            order_list = orders_by_position.setdefault(pozice_id, [])
            if not any(order.zakazka_id == zakazka_id for order in order_list):
                poradi = len(order_list) + 1
                new_order = PoziceZakazkaOrder.objects.create(
                    pozice_id=pozice_id,
                    zakazka_id=zakazka_id,
                    poradi=poradi,
                    poznamka_k_navezeni=None,
                )
                order_list.append(new_order)

    order_map = {}
    note_map = {}
    nasledne_map = {}
    for order_list in orders_by_position.values():
        for order in order_list:
            order_map[(order.pozice_id, order.zakazka_id)] = order.poradi
            note_text = order.poznamka_k_navezeni
            if isinstance(note_text, str):
                note_text = note_text.strip()
            note_map[(order.pozice_id, order.zakazka_id)] = note_text or None
            nasledne_map[(order.pozice_id, order.zakazka_id)] = order.nasledne

    groups = []
    pozice_map = {}

    # V dashboardu zobrazujeme vždy všechny pozice, i když jsou prázdné.
    for pozice in pozice_list:
        poznamka_pozice = (pozice.poznamka_k_pozici or '').strip() or None
        pozice_group = {
            'pozice': pozice.kod,
            'pozice_id': pozice.id,
            'poznamka_k_pozici': poznamka_pozice,
            'zakazky_group': [],
        }
        groups.append(pozice_group)
        pozice_map[pozice.kod] = pozice_group

    for bedna in bedny:
        pozice_kod = bedna.pozice.kod if bedna.pozice else None
        pozice_id = bedna.pozice_id
        zakazka_id = bedna.zakazka.id if bedna.zakazka else None

        # Najde nebo vytvoří skupinu pro pozici (fallback pro nekonzistentní data).
        if pozice_kod not in pozice_map:
            pozice_group = {
                'pozice': pozice_kod,
                'pozice_id': pozice_id,
                'poznamka_k_pozici': None,
                'zakazky_group': [],
            }
            pozice_map[pozice_kod] = pozice_group
            groups.append(pozice_group)
        pozice_group = pozice_map[pozice_kod]

        # Najde nebo vytvoří podskupinu pro zakázku
        zakazka_group = next((z for z in pozice_group['zakazky_group'] if z['zakazka'].id == zakazka_id), None)
        if not zakazka_group:
            # Získání pořadí z mapy, případně default 0
            poradi = order_map.get((bedna.pozice_id, zakazka_id), 0)
            zakazka_group = {
                'zakazka': bedna.zakazka,
                'bedny': [],
                'poradi': poradi,
                'pozice_id': bedna.pozice_id,
                'poznamka_k_navezeni': note_map.get((bedna.pozice_id, zakazka_id)),
                'nasledne': nasledne_map.get((bedna.pozice_id, zakazka_id), False),
            }
            pozice_group['zakazky_group'].append(zakazka_group)

        # Přidá bednu do správné zakázky
        zakazka_group['bedny'].append(bedna)

    # Seřadí zakázky v rámci každé pozice dle pořadí
    for pozice_group in groups:
        pozice_group['zakazky_group'].sort(
            key=lambda z: (z.get('poradi', 0), z['zakazka'].id)
        )

    return groups


def _split_bedny_k_navezeni_groups_by_nasledne(groups):
    """
    Rozdělí skupiny beden k navezení na dvě části:
    - false_groups: zakázky, které nemají následné zakázky (nasledne=False)
    - true_groups: zakázky, které mají následné zakázky (nasledne=True)
    """
    false_groups = []
    true_groups = []

    for group in groups:
        false_items = [z for z in group['zakazky_group'] if not z.get('nasledne')]
        true_items = [z for z in group['zakazky_group'] if z.get('nasledne')]
        poznamka_k_pozici = group.get('poznamka_k_pozici')

        # Poznámka k pozici se tiskne pouze ve skupině "nyní".
        # Pokud je pozice bez beden, ale má poznámku, stále ji zařadíme do "nyní".
        if false_items or poznamka_k_pozici:
            false_groups.append({
                'pozice': group['pozice'],
                'pozice_id': group.get('pozice_id'),
                'poznamka_k_pozici': poznamka_k_pozici,
                'zakazky_group': false_items,
            })
        if true_items:
            true_groups.append({
                'pozice': group['pozice'],
                'pozice_id': group.get('pozice_id'),
                'poznamka_k_pozici': None,
                'zakazky_group': true_items,
            })

    return false_groups, true_groups


@login_required
def dashboard_bedny_k_navezeni_view(request):
    """
    Zobrazí všechny bedny se stavem K_NAVEZENI, seskupené podle pozice a zakázky.

    Sloupce: artikl, číslo bedny, rozměr (průměr x délka), popis, poznámka.
    Seskupeno podle pozice (kód pozice), setříděno podle pozice a čísla bedny.
    Umožňuje aktualizovat pořadí zakázek v rámci pozice pomocí HTMX POST požadavků.
    """
    # Získání všech kódů pozic a mapování předchozí a následující pozice do šablony
    pozice_kody = list(
        Pozice.objects.values_list('kod', flat=True).order_by('kod')
    )
    pozice_id_by_kod = dict(
        Pozice.objects.values_list('kod', 'id')
    )
    prev_map = {}
    next_map = {}
    for i, kod in enumerate(pozice_kody):
        if i > 0:
            prev_map[kod] = pozice_kody[i - 1]
        if i < len(pozice_kody) - 1:
            next_map[kod] = pozice_kody[i + 1]

    # Umožní aktualizaci pořadí pro konkrétní zakázku v pozici
    if request.method == 'POST':
        try:
            pozice_id = int(request.POST.get('pozice_id'))
            zakazka_id = int(request.POST.get('zakazka_id'))
        except (TypeError, ValueError):
            pozice_id = zakazka_id = None
        move = (request.POST.get('move') or '').lower()
        poradi = request.POST.get('poradi')
        try:
            poradi = int(poradi) if poradi is not None and poradi != '' else 0
        except ValueError:
            poradi = 0

        if pozice_id and zakazka_id:
            with transaction.atomic():
                # Zamkni pořadí pro aktuální pozici
                qs = list(
                    PoziceZakazkaOrder.objects
                    .select_for_update()
                    .filter(pozice_id=pozice_id)
                    .order_by('poradi', 'zakazka_id')
                )

                n = len(qs)
                cur_idx = next((i for i, p in enumerate(qs) if p.zakazka_id == zakazka_id), None)

                moved_between_positions = False
                target_pozice_id = None
                if move == 'up' and cur_idx == 0:
                    # přesun do předchozí pozice na konec
                    pozice_kod = next((k for k, v in pozice_id_by_kod.items() if v == pozice_id), None)
                    prev_kod = prev_map.get(pozice_kod)
                    target_pozice_id = pozice_id_by_kod.get(prev_kod)
                    if target_pozice_id:
                        moved_between_positions = True
                        source_note_by_zakazka = {o.zakazka_id: o.poznamka_k_navezeni for o in qs}
                        source_nasledne_by_zakazka = {o.zakazka_id: o.nasledne for o in qs}
                        moved_note = source_note_by_zakazka.get(zakazka_id)
                        moved_nasledne = source_nasledne_by_zakazka.get(zakazka_id, False)
                        # uzamkni cílovou pozici
                        dst_orders = list(
                            PoziceZakazkaOrder.objects
                            .select_for_update()
                            .filter(pozice_id=target_pozice_id)
                            .order_by('poradi', 'zakazka_id')
                        )
                        target_note_by_zakazka = {o.zakazka_id: o.poznamka_k_navezeni for o in dst_orders}
                        target_nasledne_by_zakazka = {o.zakazka_id: o.nasledne for o in dst_orders}
                        # přesun beden
                        Bedna.objects.filter(zakazka_id=zakazka_id, pozice_id=pozice_id).update(pozice_id=target_pozice_id)
                        # přepiš pořadí ve zdrojové pozici (bez této zakázky)
                        src_ids = [p.zakazka_id for p in qs if p.zakazka_id != zakazka_id]
                        PoziceZakazkaOrder.objects.filter(pozice_id=pozice_id).delete()
                        PoziceZakazkaOrder.objects.bulk_create([
                            PoziceZakazkaOrder(
                                pozice_id=pozice_id,
                                zakazka_id=zid,
                                poradi=idx,
                                poznamka_k_navezeni=source_note_by_zakazka.get(zid),
                                nasledne=source_nasledne_by_zakazka.get(zid, False),
                            )
                            for idx, zid in enumerate(src_ids, start=1)
                        ])
                        # vlož do cílové pozice na konec (bez duplicit, kdyby tam zakázka už byla)
                        dst_ids = [p.zakazka_id for p in dst_orders if p.zakazka_id != zakazka_id] + [zakazka_id]
                        PoziceZakazkaOrder.objects.filter(pozice_id=target_pozice_id).delete()
                        PoziceZakazkaOrder.objects.bulk_create([
                            PoziceZakazkaOrder(
                                pozice_id=target_pozice_id,
                                zakazka_id=zid,
                                poradi=idx,
                                poznamka_k_navezeni=(
                                    (target_note_by_zakazka.get(zid) or moved_note)
                                    if zid == zakazka_id and zakazka_id in target_note_by_zakazka
                                    else (moved_note if zid == zakazka_id else target_note_by_zakazka.get(zid))
                                ),
                                nasledne=(
                                    target_nasledne_by_zakazka.get(zid)
                                    if zid == zakazka_id and zakazka_id in target_nasledne_by_zakazka
                                    else (moved_nasledne if zid == zakazka_id else target_nasledne_by_zakazka.get(zid, False))
                                ),
                            )
                            for idx, zid in enumerate(dst_ids, start=1)
                        ])

                elif move == 'down' and cur_idx is not None and cur_idx == n - 1:
                    # přesun do následující pozice na začátek
                    pozice_kod = next((k for k, v in pozice_id_by_kod.items() if v == pozice_id), None)
                    next_kod = next_map.get(pozice_kod)
                    target_pozice_id = pozice_id_by_kod.get(next_kod)
                    if target_pozice_id:
                        moved_between_positions = True
                        source_note_by_zakazka = {o.zakazka_id: o.poznamka_k_navezeni for o in qs}
                        source_nasledne_by_zakazka = {o.zakazka_id: o.nasledne for o in qs}
                        moved_note = source_note_by_zakazka.get(zakazka_id)
                        moved_nasledne = source_nasledne_by_zakazka.get(zakazka_id, False)
                        dst_orders = list(
                            PoziceZakazkaOrder.objects
                            .select_for_update()
                            .filter(pozice_id=target_pozice_id)
                            .order_by('poradi', 'zakazka_id')
                        )
                        target_note_by_zakazka = {o.zakazka_id: o.poznamka_k_navezeni for o in dst_orders}
                        target_nasledne_by_zakazka = {o.zakazka_id: o.nasledne for o in dst_orders}
                        Bedna.objects.filter(zakazka_id=zakazka_id, pozice_id=pozice_id).update(pozice_id=target_pozice_id)
                        # zdrojová pozice bez této zakázky
                        src_ids = [p.zakazka_id for p in qs if p.zakazka_id != zakazka_id]
                        PoziceZakazkaOrder.objects.filter(pozice_id=pozice_id).delete()
                        PoziceZakazkaOrder.objects.bulk_create([
                            PoziceZakazkaOrder(
                                pozice_id=pozice_id,
                                zakazka_id=zid,
                                poradi=idx,
                                poznamka_k_navezeni=source_note_by_zakazka.get(zid),
                                nasledne=source_nasledne_by_zakazka.get(zid, False),
                            )
                            for idx, zid in enumerate(src_ids, start=1)
                        ])
                        # cílová pozice: vlož na začátek (bez duplicit)
                        dst_ids = [zakazka_id] + [p.zakazka_id for p in dst_orders if p.zakazka_id != zakazka_id]
                        PoziceZakazkaOrder.objects.filter(pozice_id=target_pozice_id).delete()
                        PoziceZakazkaOrder.objects.bulk_create([
                            PoziceZakazkaOrder(
                                pozice_id=target_pozice_id,
                                zakazka_id=zid,
                                poradi=idx,
                                poznamka_k_navezeni=(
                                    (target_note_by_zakazka.get(zid) or moved_note)
                                    if zid == zakazka_id and zakazka_id in target_note_by_zakazka
                                    else (moved_note if zid == zakazka_id else target_note_by_zakazka.get(zid))
                                ),
                                nasledne=(
                                    target_nasledne_by_zakazka.get(zid)
                                    if zid == zakazka_id and zakazka_id in target_nasledne_by_zakazka
                                    else (moved_nasledne if zid == zakazka_id else target_nasledne_by_zakazka.get(zid, False))
                                ),
                            )
                            for idx, zid in enumerate(dst_ids, start=1)
                        ])

                if not moved_between_positions:
                    # stávající logika přeuspořádání uvnitř pozice
                    if move in ('up', 'down'):
                        n = len(qs)
                        cur_idx = next((i for i, p in enumerate(qs) if p.zakazka_id == zakazka_id), None)
                        if cur_idx is None:
                            poradi = n + 1  # neexistuje -> vlož na konec
                        else:
                            if move == 'up' and cur_idx > 0:
                                poradi = cur_idx  # posun o 1 nahoru
                            elif move == 'down' and cur_idx < n - 1:
                                poradi = cur_idx + 2  # posun o 1 dolů
                            else:
                                poradi = cur_idx + 1  # bez změny (okraj)

                    PoziceZakazkaOrder.objects.filter(pozice_id=pozice_id).update(poradi=F('poradi') + 1000)

                    qs_others = [p for p in qs if p.zakazka_id != zakazka_id]
                    count = len(qs_others)
                    desired = poradi if poradi and poradi > 0 else (count + 1)
                    if desired > count + 1:
                        desired = count + 1
                    if desired < 1:
                        desired = 1

                    new_order = []
                    inserted = False
                    for idx, p in enumerate(qs_others, start=1):
                        if not inserted and idx == desired:
                            new_order.append(('CURRENT', zakazka_id))
                            inserted = True
                        new_order.append((p.pk, p.zakazka_id))
                    if not inserted:
                        new_order.append(('CURRENT', zakazka_id))

                    pos = 1
                    for pk, z_id in new_order:
                        if pk == 'CURRENT':
                            PoziceZakazkaOrder.objects.update_or_create(
                                pozice_id=pozice_id,
                                zakazka_id=zakazka_id,
                                defaults={'poradi': pos}
                            )
                        else:
                            PoziceZakazkaOrder.objects.filter(pk=pk).update(poradi=pos)
                        pos += 1

            messages.success(request, "Pořadí bylo upraveno.")
            logger.info(
                f"Uživatel {request.user} upravil pořadí zakázek v přehledu beden k navezení."
            )
            return redirect('dashboard_bedny_k_navezeni')

        # I při neplatném POSTu přesměruj zpět (PRG), ať se neodesílá formulář znovu po refreshi
        return redirect('dashboard_bedny_k_navezeni')
    
    context = {
        'groups': _get_bedny_k_navezeni_groups(),
        'db_table': 'bedny_k_navezeni',
        'current_time': timezone.now(),
        'pozice_kody': pozice_kody,
        'prev_map': prev_map,
        'next_map': next_map,
    }

    if request.htmx:
        return render(request, "orders/partials/dashboard_bedny_k_navezeni_content.html", context)
    return render(request, 'orders/dashboard_bedny_k_navezeni.html', context)


@login_required
def dashboard_bedny_k_navezeni_poznamka_view(request):
    """HTMX endpoint pro inline úpravu poznámky k navezení pro zakázku v pozici."""
    pozice_id_raw = request.GET.get('pozice_id') or request.POST.get('pozice_id')
    zakazka_id_raw = request.GET.get('zakazka_id') or request.POST.get('zakazka_id')
    mode = (request.GET.get('mode') or request.POST.get('mode') or '').lower()

    try:
        pozice_id = int(pozice_id_raw)
        zakazka_id = int(zakazka_id_raw)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Neplatné ID pozice nebo zakázky.")

    qs = Bedna.objects.filter(zakazka_id=zakazka_id, pozice_id=pozice_id)
    if not qs.exists():
        return HttpResponseBadRequest("Nebyla nalezena kombinace pozice a zakázky.")

    order_obj, _ = PoziceZakazkaOrder.objects.get_or_create(
        pozice_id=pozice_id,
        zakazka_id=zakazka_id,
        defaults={
            'poradi': (
                (PoziceZakazkaOrder.objects.filter(pozice_id=pozice_id).order_by('-poradi').values_list('poradi', flat=True).first() or 0)
                + 1
            ),
            'poznamka_k_navezeni': None,
        }
    )
    poznamka = (order_obj.poznamka_k_navezeni or '').strip()

    if request.method == 'POST':
        poznamka = (request.POST.get('poznamka') or '').strip()
        order_obj.poznamka_k_navezeni = (poznamka or None)
        order_obj.save(update_fields=['poznamka_k_navezeni'])
        mode = 'display'

    context = {
        'mode': 'form' if mode == 'form' and request.method == 'GET' else 'display',
        'pozice_id': pozice_id,
        'zakazka_id': zakazka_id,
        'poznamka': poznamka,
        'target_id': f"note-{pozice_id}-{zakazka_id}",
    }
    return render(request, "orders/partials/dashboard_bedny_k_navezeni_note.html", context)


@login_required
def dashboard_bedny_k_navezeni_poznamka_pozice_view(request):
    """HTMX endpoint pro inline úpravu poznámky na úrovni pozice."""
    pozice_id_raw = request.GET.get('pozice_id') or request.POST.get('pozice_id')
    mode = (request.GET.get('mode') or request.POST.get('mode') or '').lower()

    try:
        pozice_id = int(pozice_id_raw)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Neplatné ID pozice.")

    pozice = get_object_or_404(Pozice, pk=pozice_id)
    poznamka = (pozice.poznamka_k_pozici or '').strip()

    if request.method == 'POST':
        poznamka = (request.POST.get('poznamka') or '').strip()
        pozice.poznamka_k_pozici = (poznamka or None)
        pozice.save(update_fields=['poznamka_k_pozici'])
        mode = 'display'

    context = {
        'mode': 'form' if mode == 'form' and request.method == 'GET' else 'display',
        'pozice_id': pozice_id,
        'poznamka': poznamka,
        'target_id': f"position-note-{pozice_id}",
    }
    return render(request, "orders/partials/dashboard_bedny_k_navezeni_pozice_note.html", context)


@login_required
def dashboard_bedny_k_navezeni_nasledne_view(request):
    """HTMX endpoint pro inline přepnutí příznaku 'Následně?' pro zakázku v pozici."""
    pozice_id_raw = request.POST.get('pozice_id') or request.GET.get('pozice_id')
    zakazka_id_raw = request.POST.get('zakazka_id') or request.GET.get('zakazka_id')

    try:
        pozice_id = int(pozice_id_raw)
        zakazka_id = int(zakazka_id_raw)
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Neplatné ID pozice nebo zakázky.")

    qs = Bedna.objects.filter(zakazka_id=zakazka_id, pozice_id=pozice_id)
    if not qs.exists():
        return HttpResponseBadRequest("Nebyla nalezena kombinace pozice a zakázky.")

    order_obj, _ = PoziceZakazkaOrder.objects.get_or_create(
        pozice_id=pozice_id,
        zakazka_id=zakazka_id,
        defaults={
            'poradi': (
                (PoziceZakazkaOrder.objects.filter(pozice_id=pozice_id).order_by('-poradi').values_list('poradi', flat=True).first() or 0)
                + 1
            ),
            'poznamka_k_navezeni': None,
            'nasledne': False,
        }
    )

    if request.method == 'POST':
        nasledne = request.POST.get('nasledne') in ('1', 'true', 'on', 'yes')
        order_obj.nasledne = nasledne
        order_obj.save(update_fields=['nasledne'])

    context = {
        'pozice_id': pozice_id,
        'zakazka_id': zakazka_id,
        'nasledne': order_obj.nasledne,
        'target_id': f"nasledne-{pozice_id}-{zakazka_id}",
    }
    return render(request, "orders/partials/dashboard_bedny_k_navezeni_nasledne.html", context)


@login_required
def dashboard_bedny_k_navezeni_pdf_view(request):
    """PDF verze přehledu beden k navezení (WeasyPrint)."""
    groups = _get_bedny_k_navezeni_groups()
    groups_false, groups_true = _split_bedny_k_navezeni_groups_by_nasledne(groups)
    context = {
        'groups_false': groups_false,
        'groups_true': groups_true,
        'current_time': timezone.now(),
    }
    from django.template.loader import render_to_string
    from django.http import HttpResponse

    html_string = render_to_string('orders/print/bedny_k_navezeni_print.html', context)
    pdf_bytes = HTML(string=html_string).write_pdf()
    response = HttpResponse(pdf_bytes, content_type='application/pdf')
    response['Content-Disposition'] = 'inline; filename="bedny_k_navezeni.pdf"'
    return response


@login_required
def protokol_kamion_vydej_pdf_view(request, pk: int):
    """GET endpoint pro PDF protokol kamionu (výdej)."""
    kamion = get_object_or_404(Kamion, pk=pk, prijem_vydej=KamionChoice.VYDEJ)

    zakazky = kamion.zakazky_vydej.all().order_by('id')
    base_url = getattr(settings, 'WEASYPRINT_BASEURL', None)
    if not base_url:
        base_url = request.build_absolute_uri('/') if request else None

    static_url = settings.STATIC_URL
    if base_url and base_url.startswith('file:'):
        if not static_url.startswith('http://') and not static_url.startswith('https://'):
            static_url = base_url.rstrip('/') + '/'

    context = {
        "kamion": kamion,
        "zakazky": zakazky,
        "generated_at": timezone.now(),
        "issued_by": request.user.get_full_name() if request.user.is_authenticated else "",
        "pdf_static_url": static_url,
    }

    html_string = render_to_string(f"orders/protokol_kamion_vydej_{kamion.zakaznik.zkratka.lower()}.html", context)

    stylesheets = []
    css_path = finders.find('orders/css/pdf_shared.css')
    if css_path:
        stylesheets.append(CSS(filename=css_path))
    else:
        logger.warning("Nepodařilo se najít CSS 'orders/css/pdf_shared.css' pro tisk protokolu kamionu výdej.")

    pdf_bytes = HTML(string=html_string, base_url=base_url).write_pdf(stylesheets=stylesheets)

    cislo_dl_raw = kamion.cislo_dl or f"kamion_{kamion}"
    cislo_dl = slugify(cislo_dl_raw, allow_unicode=False) or "kamion"
    filename = f"protokol_{cislo_dl}.pdf"

    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response['Content-Disposition'] = (
        f"inline; filename=\"{filename}\"; filename*=UTF-8''{filename}"
    )
    response['Content-Length'] = str(len(pdf_bytes))
    return response


@login_required
def dodaci_list_kamion_vydej_pdf_view(request, pk: int):
    """GET endpoint pro dodací list kamionu výdej."""
    kamion = get_object_or_404(Kamion, pk=pk, prijem_vydej=KamionChoice.VYDEJ)
    zakaznik_zkratka = getattr(kamion.zakaznik, 'zkratka', None)
    if not zakaznik_zkratka:
        return HttpResponse("Kamion nemá zkratku zákazníka", status=400)

    html_path = f"orders/dodaci_list/dodaci_list_{zakaznik_zkratka.lower()}.html"
    cislo_dl_raw = kamion.cislo_dl or f"kamion_{kamion}"
    cislo_dl = slugify(cislo_dl_raw, allow_unicode=False) or "kamion"
    filename = f"dodaci_list_{cislo_dl}.pdf"

    response = utilita_tisk_dl_a_proforma_faktury(None, request, kamion, html_path, filename)
    return response


@login_required
def proforma_kamion_vydej_pdf_view(request, pk: int):
    """GET endpoint pro proforma fakturu kamionu výdej."""
    kamion = get_object_or_404(Kamion, pk=pk, prijem_vydej=KamionChoice.VYDEJ)
    zakaznik_zkratka = getattr(kamion.zakaznik, 'zkratka', None)
    if not zakaznik_zkratka:
        return HttpResponse("Kamion nemá zkratku zákazníka", status=400)

    if kamion.zakaznik.proforma_po_bednach:
        html_path = "orders/proforma_faktura_po_bednach.html"
    else:
        html_path = "orders/proforma_faktura_po_zakazkach.html"

    cislo_dl_raw = kamion.cislo_dl or f"kamion_{kamion}"
    cislo_dl = slugify(cislo_dl_raw, allow_unicode=False) or "kamion"
    filename = f"proforma_faktura_{cislo_dl}.pdf"

    response = utilita_tisk_dl_a_proforma_faktury(None, request, kamion, html_path, filename)
    return response


def _get_latest_bedna_change_marker():
    history_model = Bedna.history.model
    return history_model.objects.order_by('-history_date', '-history_id').first()


def _build_bedna_change_poll_payload(request):
    latest = _get_latest_bedna_change_marker()
    last_change = latest.history_date if latest else None
    last_history_id = latest.history_id if latest else None
    since_raw = request.GET.get('since')
    since_id_raw = request.GET.get('since_id')
    since_value = None
    since_id = None

    if since_raw:
        try:
            normalized = since_raw.replace(' ', '+')
            since_value = datetime.fromisoformat(normalized)
            if timezone.is_naive(since_value):
                since_value = timezone.make_aware(since_value, timezone.get_current_timezone())
        except ValueError:
            since_value = None

    if since_id_raw:
        try:
            since_id = int(since_id_raw)
        except (TypeError, ValueError):
            since_id = None

    changed = False
    if last_change:
        if since_id is not None and last_history_id is not None:
            changed = last_history_id > since_id
        elif since_value:
            changed = last_change > since_value

    return {
        'changed': changed,
        'timestamp': last_change.isoformat() if last_change else None,
        'history_id': last_history_id,
    }


@permission_required('orders.view_bedna', raise_exception=True)
def bedna_changes_poll_view(request):
    return JsonResponse(_build_bedna_change_poll_payload(request))


class BednyListView(LoginRequiredMixin, PermissionRequiredMixin, ListView):
    """
    Zobrazuje seznam beden.

    Template:
    - `bedny_list.html`

    Kontext:
    - Seznam beden a možnosti filtrování.
    """
    permission_required = 'orders.view_bedna'
    model = Bedna
    template_name = 'orders/bedny_list.html'
    ordering = ['id']

    def get_context_data(self, **kwargs):
        """
        Přidává další data do kontextu pro zobrazení v šabloně.

        Vrací:
        - Kontext obsahující filtry a řazení.
        """
        context = super().get_context_data(**kwargs)

        table_columns = [
            {"field": "cislo_bedny", "label": "Č. bedny"},
            {"field": "stav_bedny", "label": "Stav"},
            {"field": "zakazka__prumer", "label": "Ø"},
            {"field": "zakazka__delka", "label": "Délka"},
            {"field": "fake_skupina_TZ_ann", "label": "TZ"},
        ]
        table_rows = []
        previous_zakazka_id = None
        for row_index, bedna in enumerate(context['object_list']):
            current_zakazka_id = bedna.zakazka_id
            priorita_color = 'red' if bedna.zakazka and bedna.zakazka.priorita == 'P1' else 'orange' if bedna.zakazka and bedna.zakazka.priorita == 'P2' else 'black'
            table_rows.append({
                "cislo_bedny": format_cislo_bedny(bedna),
                "stav_bedny": bedna.get_stav_bedny_display(),
                "zakazka__prumer": bedna.zakazka.prumer if bedna.zakazka else "",
                "zakazka__delka": int(bedna.zakazka.delka) if bedna.zakazka and bedna.zakazka.delka else "",
                "fake_skupina_TZ_ann": format_skupina_TZ(getattr(bedna, 'fake_skupina_TZ_ann', bedna.fake_skupina_TZ)),
                "priorita_color": priorita_color,
                "starts_new_zakazka_group": row_index > 0 and current_zakazka_id != previous_zakazka_id,
            })
            previous_zakazka_id = current_zakazka_id

        stav_choices = [("SK", "SKLADEM")] + list(StavBednyChoice.choices) + [("RO", "Rozpracováno"), ("PE", "Po exspiraci")]
        zakaznik_choices = [("", "VŠE")] + [(zakaznik.zkratka, zakaznik.zkraceny_nazev) for zakaznik in Zakaznik.objects.all()]
        zakazka_priorita_choices = [("", "VŠE"), ("P1_P2", "P1 & P2")] + list(PrioritaChoice.choices)
        fake_skupina_TZ_choices = [("", "VŠE")] + [
            (str(skupina), str(skupina))
            for skupina in self._get_available_fake_skupiny_TZ()
        ]
        pozastaveno_choices = [("False", "Ne"), ("True", "Ano")]
        available_delky = self._get_available_delky()
        delka_choices = [("", "VŠE")] + [
            (str(delka), self._format_delka_choice_label(delka))
            for delka in available_delky
        ]
        delka_filter = self._get_effective_delka_filter()
        latest_bedna_change = _get_latest_bedna_change_marker()
        bedna_last_change = latest_bedna_change.history_date if latest_bedna_change else None
        bedna_last_change_id = latest_bedna_change.history_id if latest_bedna_change else None

        context.update({
            'db_table': 'bedny',
            'sort': self.request.GET.get('sort') or '',
            'order': self.request.GET.get('order') or '',
            'query': self.request.GET.get('query', ''),
            'stav_filter': self.request.GET.get('stav_filter', 'SK'),
            'stav_choices': stav_choices,
            'zakaznik_filter': self.request.GET.get('zakaznik_filter', ''),
            'zakaznik_choices': zakaznik_choices,
            'zakazka_priorita_filter': self.request.GET.get('zakazka_priorita_filter', ''),
            'zakazka_priorita_choices': zakazka_priorita_choices,
            'fake_skupina_TZ_filter': self.request.GET.get('fake_skupina_TZ_filter', ''),
            'fake_skupina_TZ_choices': fake_skupina_TZ_choices,
            'pozastaveno_filter': self.request.GET.get('pozastaveno_filter', 'False'),
            'pozastaveno_choices': pozastaveno_choices,
            'delka_filter': delka_filter,
            'delka_choices': delka_choices,
            'table_columns': table_columns,
            'table_rows': table_rows,
            'bedna_poll_url': reverse('bedny_changes_poll'),
            'bedna_last_change': bedna_last_change.isoformat() if bedna_last_change else '',
            'bedna_last_change_id': bedna_last_change_id if bedna_last_change_id else '',
            'bedna_poll_interval': 30000,
        })
        return context
    
    def _get_base_queryset(self):
        return Bedna.objects.select_related(
            'zakazka',
            'zakazka__kamion_prijem',
            'zakazka__kamion_prijem__zakaznik',
            'zakazka__predpis',
            'zakazka__typ_hlavy',
        ).annotate(fake_skupina_TZ_ann=build_fake_skupina_TZ_annotation())

    def _apply_filters(self, queryset, include_delka_filter=True, include_fake_skupina_TZ_filter=True):
        query = self.request.GET.get('query', '')
        stav_filter = self.request.GET.get('stav_filter','SK')      
        zakaznik_filter = self.request.GET.get('zakaznik_filter', '')
        zakazka_priorita_filter = self.request.GET.get('zakazka_priorita_filter', '')
        fake_skupina_TZ_filter = self.request.GET.get('fake_skupina_TZ_filter', '')
        pozastaveno_filter = self.request.GET.get('pozastaveno_filter', 'False')
        delka_filter = self._get_effective_delka_filter() if include_delka_filter else ''

        if stav_filter == 'SK' or not stav_filter:
            queryset = queryset.exclude(stav_bedny='EX')
        elif stav_filter == 'RO':
            queryset = queryset.filter(stav_bedny__in=STAV_BEDNY_ROZPRACOVANOST)
        elif stav_filter == 'PE':
            expiration_date = timezone.localdate() - timedelta(days=28)
            queryset = queryset.exclude(stav_bedny=StavBednyChoice.EXPEDOVANO).filter(zakazka__kamion_prijem__datum__lt=expiration_date)            
        else:
            queryset = queryset.filter(stav_bedny=stav_filter)

        if zakaznik_filter:
            queryset = queryset.filter(zakazka__kamion_prijem__zakaznik__zkratka=zakaznik_filter)

        if zakazka_priorita_filter == "P1_P2":
            queryset = queryset.filter(zakazka__priorita__in=[PrioritaChoice.VYSOKA, PrioritaChoice.STREDNI])
        elif zakazka_priorita_filter:
            queryset = queryset.filter(zakazka__priorita=zakazka_priorita_filter)

        if include_fake_skupina_TZ_filter and fake_skupina_TZ_filter:
            try:
                fake_skupina_TZ_filter = int(fake_skupina_TZ_filter)
            except (TypeError, ValueError):
                fake_skupina_TZ_filter = None
            if fake_skupina_TZ_filter is not None:
                queryset = queryset.filter(fake_skupina_TZ_ann=fake_skupina_TZ_filter)

        if pozastaveno_filter == 'True':
            queryset = queryset.filter(pozastaveno=True)
        else:
            queryset = queryset.filter(pozastaveno=False)

        if query:
            queryset = queryset.filter(cislo_bedny__icontains=query)

        if include_delka_filter and delka_filter:
            queryset = queryset.filter(zakazka__delka=delka_filter)

        return queryset

    def _get_available_delky(self):
        if not hasattr(self, '_available_delky_cache'):
            self._available_delky_cache = list(
                self._apply_filters(self._get_base_queryset(), include_delka_filter=False)
                .exclude(zakazka__delka__isnull=True)
                .order_by('zakazka__delka')
                .values_list('zakazka__delka', flat=True)
                .distinct()
            )
        return self._available_delky_cache

    def _get_effective_delka_filter(self):
        delka_filter = self.request.GET.get('delka_filter', '')
        if not delka_filter:
            return ''

        try:
            selected_delka = Decimal(str(delka_filter))
        except (InvalidOperation, TypeError, ValueError):
            return ''

        for available_delka in self._get_available_delky():
            if selected_delka == Decimal(str(available_delka)):
                return str(available_delka)
        return ''

    def _get_available_fake_skupiny_TZ(self):
        return (
            self._get_base_queryset()
            .exclude(stav_bedny=StavBednyChoice.EXPEDOVANO)
            .filter(pozastaveno=False)
            .exclude(fake_skupina_TZ_ann__isnull=True)
            .order_by('fake_skupina_TZ_ann')
            .values_list('fake_skupina_TZ_ann', flat=True)
            .distinct()
        )

    def _format_delka_choice_label(self, delka):
        if delka == delka.to_integral_value():
            return str(int(delka))
        return str(delka).rstrip('0').rstrip('.').replace('.', ',')

    def get_queryset(self):
        """
        Získává seznam beden na základě vyhledávání a filtrování.

        Vrací:
        - queryset: Filtrovaný a seřazený seznam beden.
        """
        queryset = self._apply_filters(self._get_base_queryset())
        sort = self.request.GET.get('sort') or 'id'
        order = self.request.GET.get('order') or 'up'

        if order == 'down':
            sort = f"-{sort}"
         
        queryset = queryset.order_by(sort, 'id')  # Přidání 'id' jako sekundárního řazení pro stabilitu

        return queryset
    
    def render_to_response(self, context, **response_kwargs):
        if self.request.headers.get('Hx-Request') == 'true':
            return render(self.request, "orders/partials/bedny_list_content.html", context)
        else:
            return super().render_to_response(context, **response_kwargs)
