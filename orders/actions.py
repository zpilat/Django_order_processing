from django.contrib import admin, messages
from django.shortcuts import redirect
from django.http import HttpResponse, HttpResponseRedirect
from django.template.loader import render_to_string
from django.shortcuts import render
from django.db import transaction, IntegrityError, DataError
from django.utils import timezone
from django.utils.text import slugify
from django import forms
from django.forms import formset_factory
from django.template.response import TemplateResponse
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError
from django.contrib.admin.widgets import AdminDateWidget
from django.conf import settings
from django.contrib.staticfiles import finders
from django.db.models import Count, Q

import csv
import datetime
from decimal import Decimal, ROUND_HALF_UP
from weasyprint import HTML
from weasyprint import CSS

from .models import Zakazka, Bedna, Kamion, Zakaznik, Pozice, PoziceZakazkaOrder, Rozpracovanost, Cena, Zarizeni, SarzeKrok, SarzeKrokBedna
from .utils import (
    utilita_tisk_dokumentace,
    utilita_tisk_dokumentace_sablony,
    utilita_expedice_zakazek,
    utilita_expedice_beden,
    utilita_kontrola_zakazek,
    utilita_tisk_dl_a_proforma_faktury,
    utilita_export_beden_zinkovani_csv,
    validate_bedny_pripraveny_k_expedici,
)
from .services.pdf_cards_service import resolve_customer_templates
from .services.expedice_service import (
    expedice_beden_do_noveho_kamionu,
    expedice_zakazek_do_noveho_kamionu,
)
from .services.exceptions import ServiceValidationError
from django.urls import reverse
from .forms import VyberKamionVydejForm, OdberatelForm, KNavezeniForm, NavezenoForm
from .choices import (
    KamionChoice,
    StavBednyChoice,
    RovnaniChoice,
    TryskaniChoice,
    ZinkovaniChoice,
    PrioritaChoice,
    STAV_BEDNY_SKLADEM,
    STAV_BEDNY_ROZPRACOVANOST,
)

import logging
logger = logging.getLogger('orders')


class SarzeKrokActionInitForm(forms.Form):
    datum = forms.DateField(
        required=True,
        label='Datum',
        input_formats=['%d.%m.%Y', '%Y-%m-%d'],
        widget=AdminDateWidget(),
    )
    zarizeni = forms.ModelChoiceField(
        queryset=Zarizeni.objects.order_by('kod_zarizeni', 'nazev_zarizeni'),
        required=True,
        label='Pracoviště',
    )
    zacatek = forms.TimeField(required=True, label='Začátek', input_formats=['%H:%M', '%H.%M'])
    konec = forms.TimeField(required=False, label='Konec', input_formats=['%H:%M', '%H.%M'])
    operator = forms.CharField(max_length=30, required=True, label='Operátor')
    program = forms.CharField(max_length=20, required=False, label='Program')
    alarm = forms.CharField(max_length=50, required=False, label='Alarm')
    poznamka = forms.CharField(max_length=100, required=False, label='Poznámka')

    def clean_operator(self):
        operator = (self.cleaned_data.get('operator') or '').strip()
        if not operator:
            raise ValidationError('Pole Operátor je povinné.')
        return operator


def _get_changelist_url(modeladmin):
    opts = modeladmin.model._meta
    return reverse(f'admin:{opts.app_label}_{opts.model_name}_changelist')


def _build_sarzekrokbedna_preview_rows(source_rows):
    preview_rows = []
    for row in source_rows:
        bedna_value = None
        if row.bedna:
            bedna_value = row.bedna.cislo_bedny if row.bedna.cislo_bedny is not None else row.bedna.pk
        if bedna_value is None:
            bedna_value = row.cislo_bedny_mimo_db or '--------'

        preview_rows.append(
            {
                'bedna': bedna_value,
                'patro': row.patro,
                'procent_z_patra': row.procent_z_patra,
                'popis': row.popis_mimo_db,
                'zakaznik': row.zakaznik_mimo_db,
                'zakazka': row.zakazka_mimo_db,
            }
        )
    return preview_rows


def _render_sarzekrok_action_init_form(modeladmin, request, queryset, form, action_name, source_krok, source_rows):
    source_row_preview = _build_sarzekrokbedna_preview_rows(source_rows)
    predicted_poradi = (source_krok.poradi or 0) + 1 if source_krok else None
    context = {
        **modeladmin.admin_site.each_context(request),
        'title': 'Založení nového kroku šarže',
        'opts': modeladmin.model._meta,
        'media': modeladmin.media + form.media,
        'form': form,
        'queryset': queryset,
        'source_krok': source_krok,
        'source_row_preview': source_row_preview,
        'source_row_count': len(source_row_preview),
        'predicted_poradi': predicted_poradi,
        'action_name': action_name,
        'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        'cancel_url': _get_changelist_url(modeladmin),
    }
    return TemplateResponse(request, 'admin/orders/sarzekrok/action_init_form.html', context)


def _create_sarzekrok_and_copy_rows(
    source_krok,
    source_rows,
    *,
    datum,
    zarizeni,
    zacatek,
    konec,
    operator,
    program,
    alarm,
    poznamka,
):
    with transaction.atomic():
        target_krok = SarzeKrok.objects.create(
            sarze=source_krok.sarze,
            datum=datum,
            zarizeni=zarizeni,
            zacatek=zacatek,
            konec=konec,
            operator=operator,
            program=program,
            alarm=alarm,
            poznamka=poznamka,
        )

        copied_count = 0
        skipped_conflict = 0
        for row in source_rows:
            exists = SarzeKrokBedna.objects.filter(
                krok=target_krok,
                bedna=row.bedna,
                patro=row.patro,
            ).exists()
            if exists:
                skipped_conflict += 1
                continue

            SarzeKrokBedna.objects.create(
                krok=target_krok,
                bedna=row.bedna,
                patro=row.patro,
                procent_z_patra=row.procent_z_patra,
                popis_mimo_db=row.popis_mimo_db,
                zakaznik_mimo_db=row.zakaznik_mimo_db,
                zakazka_mimo_db=row.zakazka_mimo_db,
                cislo_bedny_mimo_db=row.cislo_bedny_mimo_db,
            )
            copied_count += 1

    return target_krok, copied_count, skipped_conflict


def _safe_filename(label: str, fallback: str = "soubor") -> str:
    """Vytvoří bezpečný název souboru bez lomítek a speciálních znaků."""
    if not label:
        return fallback
    safe = slugify(label, allow_unicode=False)
    return safe or fallback


def _abort_if_paused_bedny(modeladmin, request, queryset, action_label):
    """Vrátí True, pokud výběr obsahuje pozastavené bedny a vypíše chybovou hlášku.

    Pozn.: queryset může být již oříznut (slice) a pak nelze volat .filter().
    V takovém případě spadne do Python fallbacku.
    """
    try:
        paused_count = queryset.filter(pozastaveno=True).count()
    except TypeError:
        paused_count = sum(1 for obj in queryset if getattr(obj, 'pozastaveno', False))
    if paused_count:
        logger.info(
            f"Uživatel {request.user} se pokusil provést akci '{action_label}', ale výběr obsahuje {paused_count} pozastavených beden."
        )
        message = _(
            f"Akci \"{action_label}\" nelze provést, protože výběr obsahuje {paused_count} pozastavených beden."
        )
        modeladmin.message_user(request, message, level=messages.ERROR)
        return True
    return False

def _abort_if_zakazky_maji_pozastavene_bedny(modeladmin, request, queryset, action_label):
    """Vrátí True, pokud vybrané zakázky obsahují pozastavené bedny."""
    paused_qs = Bedna.objects.filter(zakazka__in=queryset, pozastaveno=True)
    if paused_qs.exists():
        paused_count = paused_qs.count()
        zakazka_count = paused_qs.values("zakazka_id").distinct().count()
        logger.info(
            f"Uživatel {request.user} se pokusil provést akci '{action_label}', ale vybrané zakázky obsahují {paused_count} pozastavených beden ve {zakazka_count} zakázkách."
        )
        message = _(f"Akci \"{action_label}\" nelze provést, protože vybrané zakázky obsahují {paused_count} pozastavených beden (celkem {zakazka_count} zakázek).")
        modeladmin.message_user(request, message, level=messages.ERROR)
        return True
    return False

def _abort_if_kamiony_maji_pozastavene_bedny(modeladmin, request, queryset, action_label):
    """Vrátí True, pokud vybrané kamiony obsahují zakázky s pozastavenými bednami."""
    paused_qs = Bedna.objects.filter(zakazka__kamion_prijem__in=queryset, pozastaveno=True)
    if paused_qs.exists():
        paused_count = paused_qs.count()
        kamion_count = paused_qs.values("zakazka__kamion_prijem_id").distinct().count()
        logger.info(
            f"Uživatel {request.user} se pokusil provést akci '{action_label}', ale vybrané kamiony obsahují {paused_count} pozastavených beden ve {kamion_count} kamionech."
        )
        message = _(f"Akci \"{action_label}\" nelze provést, protože vybrané kamiony obsahují {paused_count} pozastavených beden (celkem {kamion_count} kamionů).")
        modeladmin.message_user(request, message, level=messages.ERROR)
        return True
    return False


def _validate_proforma_pricing(kamion):
    """Vrátí seznam chybových hlášek pro zakázky, které nemají požadované ceny pro tisk proformy."""
    errors = []
    zakazky = kamion.zakazky_vydej.select_related('kamion_prijem__zakaznik').all()
    for zakazka in zakazky:
        label = f"{zakazka.artikl or zakazka.pk}"
        kamion_prijem = getattr(zakazka, 'kamion_prijem', None)
        zakaznik_prijem = getattr(kamion_prijem, 'zakaznik', None) if kamion_prijem else None
        if not zakaznik_prijem:
            errors.append(f"Zakázka {label}: chybí kamion příjem se zákazníkem pro výpočet cen.")
            continue

        predpis = getattr(zakazka, 'predpis', None)
        delka = getattr(zakazka, 'delka', None)
        if not predpis or delka is None:
            errors.append(f"Zakázka {label}: chybí předpis nebo délka pro výpočet ceny.")
            continue

        try:
            cena_obj = Cena.objects.get(
                predpis=predpis,
                delka_min__lte=delka,
                delka_max__gt=delka,
                zakaznik=zakaznik_prijem
            )
        except Cena.DoesNotExist:
            errors.append(f"Zakázka {label}: nenalezena cena pro předpis {predpis} a délku {delka}.")
            continue
        except Cena.MultipleObjectsReturned:
            errors.append(f"Zakázka {label}: nalezeno více cen pro předpis {predpis} a délku {delka}. Opravte ceník.")
            continue

        cena_za_kg = cena_obj.cena_za_kg
        if cena_za_kg is None or cena_za_kg <= 0:
            errors.append(f"Zakázka {label}: cena za kg musí být větší než 0.")

        if zakaznik_prijem.fakturovat_rovnani:
            cena_rovnani = cena_obj.cena_rovnani_za_kg
            if cena_rovnani is None or cena_rovnani <= 0:
                errors.append(f"Zakázka {label}: cena rovnání za kg musí být větší než 0.")

        if zakaznik_prijem.fakturovat_tryskani:
            cena_tryskani = cena_obj.cena_tryskani_za_kg
            if cena_tryskani is None or cena_tryskani <= 0:
                errors.append(f"Zakázka {label}: cena tryskání za kg musí být větší než 0.")

    return errors

def _format_decimal(value):
    """Vrátí číslo s desetinnou čárkou; prázdný řetězec pro None."""
    if value is None:
        return ''
    try:
        decimal_value = Decimal(value)
    except Exception:
        logger.warning("Nepodařilo se převést hodnotu na Decimal ve _format_decimal.", exc_info=True)
        return str(value)
    text = format(decimal_value, 'f')
    if '.' in text:
        text = text.rstrip('0').rstrip('.')
    return text.replace('.', ',')

def _resolve_user_name(user):
    if not user or not getattr(user, 'is_authenticated', False):
        return ''
    full_name = user.get_full_name()
    if full_name:
        return full_name
    if user.last_name:
        return user.last_name
    return user.get_username()

def _format_rozmer(zakazka):
    prumer = _format_decimal(getattr(zakazka, 'prumer', None))
    delka = _format_decimal(getattr(zakazka, 'delka', None))
    if prumer and delka:
        return f"{prumer} x {delka}"
    return prumer or delka or ''

def _abort_if_bedna_has_not_hmotnost_zakazka_predpis(modeladmin, request, queryset, action_label):
    """Vrátí True, pokud výběr obsahuje bednu bez hmotnosti, zakázky, předpisu nebo název předpisu má hodnotu 'Neznámý předpis'."""
    missing_qs = queryset.filter(
        Q(hmotnost__isnull=True) | Q(hmotnost__lte=0) | Q(zakazka__isnull=True) | Q(zakazka__predpis__isnull=True) | Q(zakazka__predpis__nazev='Neznámý předpis')
        )
    if missing_qs.exists():
        count = missing_qs.count()

        detail_items = []
        max_detail_items = 20
        for bedna in missing_qs.select_related('zakazka__predpis')[:max_detail_items]:
            reasons = []
            if bedna.hmotnost is None or bedna.hmotnost <= 0:
                reasons.append('neplatná hmotnost')

            zakazka = getattr(bedna, 'zakazka', None)
            if zakazka is None:
                reasons.append('chybí zakázka')
            else:
                predpis = getattr(zakazka, 'predpis', None)
                if predpis is None:
                    reasons.append('chybí předpis')
                elif getattr(predpis, 'nazev', None) == 'Neznámý předpis':
                    reasons.append('neplatný předpis (Neznámý předpis)')

            if reasons:
                detail_items.append(f"{bedna.cislo_bedny}: {', '.join(reasons)}")

        detail_text = '; '.join(detail_items)
        remaining = count - len(detail_items)
        if remaining > 0:
            detail_text = f"{detail_text}; ... a dalších {remaining} beden" if detail_text else f"... a dalších {remaining} beden"

        logger.info(
            f"Uživatel {request.user} se pokusil provést akci '{action_label}', ale výběr obsahuje {count} nevalidních beden. Detaily: {detail_text}"
        )
        message = _(
            f"Akci \"{action_label}\" nelze provést, protože výběr obsahuje {count} beden bez zadané hmotnosti, zakázky nebo předpisu. "
            f"Detaily: {detail_text}."
        )
        modeladmin.message_user(request, message, level=messages.ERROR)
        return True
    return False


@admin.action(description='Přesunout šarži do dalšího kroku z vybraných beden')
def vytvorit_dalsi_krok_sarze_action(modeladmin, request, queryset):
    source_rows = list(queryset.select_related('krok', 'krok__sarze', 'bedna'))
    if not source_rows:
        modeladmin.message_user(request, 'Nebyl vybrán žádný záznam.', level=messages.WARNING)
        return None

    source_krok_ids = {row.krok_id for row in source_rows if row.krok_id}
    if len(source_krok_ids) != 1:
        modeladmin.message_user(
            request,
            'Vyberte záznamy pouze z jednoho kroku šarže.',
            level=messages.ERROR,
        )
        return None

    source_krok = source_rows[0].krok
    if not source_krok or not source_krok.sarze_id:
        modeladmin.message_user(request, 'Zdrojový krok šarže není validní.', level=messages.ERROR)
        return None
    if not source_krok.konec:
        modeladmin.message_user(
            request,
            'Původní krok šarže nemá vyplněný konec, nezapomeňte jej vyplnit.',
            level=messages.WARNING,
        )

    if 'apply' not in request.POST:
        initial = {'datum': timezone.localdate()}
        form = SarzeKrokActionInitForm(initial=initial)
        return _render_sarzekrok_action_init_form(
            modeladmin,
            request,
            queryset,
            form,
            'vytvorit_dalsi_krok_sarze_action',
            source_krok,
            source_rows,
        )

    form = SarzeKrokActionInitForm(request.POST)
    if not form.is_valid():
        return _render_sarzekrok_action_init_form(
            modeladmin,
            request,
            queryset,
            form,
            'vytvorit_dalsi_krok_sarze_action',
            source_krok,
            source_rows,
        )

    target_krok, copied_count, skipped_conflict = _create_sarzekrok_and_copy_rows(
        source_krok,
        source_rows,
        datum=form.cleaned_data['datum'],
        zarizeni=form.cleaned_data['zarizeni'],
        zacatek=form.cleaned_data['zacatek'],
        konec=form.cleaned_data['konec'],
        operator=form.cleaned_data['operator'],
        program=form.cleaned_data['program'],
        alarm=form.cleaned_data['alarm'],
        poznamka=form.cleaned_data['poznamka'],
    )

    modeladmin.message_user(
        request,
        f'Vytvořen nový krok šarže {target_krok} a zkopírováno {copied_count} řádků deníku.',
        level=messages.SUCCESS,
    )
    if skipped_conflict:
        modeladmin.message_user(
            request,
            f'Přeskočeno {skipped_conflict} řádků kvůli duplicitě (bedna + patro).',
            level=messages.WARNING,
        )
    return HttpResponseRedirect(_get_changelist_url(modeladmin))


@admin.action(description='Přesunout šarži do dalšího kroku')
def vytvorit_novy_krok_z_kroku_sarze_action(modeladmin, request, queryset):
    source_kroky = list(queryset.select_related('sarze', 'zarizeni'))
    if len(source_kroky) != 1:
        modeladmin.message_user(
            request,
            'Vyberte právě jeden krok šarže.',
            level=messages.ERROR,
        )
        return None

    source_krok = source_kroky[0]
    if not source_krok.konec:
        modeladmin.message_user(
            request,
            'Původní krok šarže nemá vyplněný konec, nezapomeňte jej vyplnit.',
            level=messages.WARNING,
        )

    source_rows = list(
        SarzeKrokBedna.objects.filter(krok=source_krok).select_related('bedna').order_by('pk')
    )

    if 'apply' not in request.POST:
        initial = {'datum': timezone.localdate()}
        form = SarzeKrokActionInitForm(initial=initial)
        return _render_sarzekrok_action_init_form(
            modeladmin,
            request,
            queryset,
            form,
            'vytvorit_novy_krok_z_kroku_sarze_action',
            source_krok,
            source_rows,
        )

    form = SarzeKrokActionInitForm(request.POST)
    if not form.is_valid():
        return _render_sarzekrok_action_init_form(
            modeladmin,
            request,
            queryset,
            form,
            'vytvorit_novy_krok_z_kroku_sarze_action',
            source_krok,
            source_rows,
        )

    target_krok, copied_count, skipped_conflict = _create_sarzekrok_and_copy_rows(
        source_krok,
        source_rows,
        datum=form.cleaned_data['datum'],
        zarizeni=form.cleaned_data['zarizeni'],
        zacatek=form.cleaned_data['zacatek'],
        konec=form.cleaned_data['konec'],
        operator=form.cleaned_data['operator'],
        program=form.cleaned_data['program'],
        alarm=form.cleaned_data['alarm'],
        poznamka=form.cleaned_data['poznamka'],
    )

    modeladmin.message_user(
        request,
        f'Vytvořen nový krok šarže {target_krok} a zkopírováno {copied_count} řádků deníku.',
        level=messages.SUCCESS,
    )
    if skipped_conflict:
        modeladmin.message_user(
            request,
            f'Přeskočeno {skipped_conflict} řádků kvůli duplicitě (bedna + patro).',
            level=messages.WARNING,
        )
    return HttpResponseRedirect(_get_changelist_url(modeladmin))

# Akce pro bedny:

@admin.action(description="Export vybraných beden do CSV pro původní rozpracovanost")
def export_bedny_to_csv_action(modeladmin, request, queryset):
    """Exportuje aktuálně vyfiltrované bedny do CSV (celý queryset, ne jen stránku)."""
    select_across = request.POST.get('select_across') == '1'
    selected_ids = request.POST.getlist(admin.helpers.ACTION_CHECKBOX_NAME)

    try:
        initial_count = queryset.count()
    except Exception:
        logger.warning("Nepodařilo se získat queryset.count() v export_bedny_to_csv_action, používá se fallback.", exc_info=True)
        initial_count = len(list(queryset))

    queryset = queryset.select_related(
        'zakazka',
        'zakazka__kamion_prijem',
        'zakazka__kamion_prijem__zakaznik',
        'zakazka__typ_hlavy',
        'zakazka__predpis',
    )

    zakazka_ids = list(queryset.values_list('zakazka_id', flat=True).distinct())
    all_ke_map = {}
    if zakazka_ids:
        aggregation = (
            Bedna.objects.filter(zakazka_id__in=zakazka_ids)
            .values('zakazka_id')
            .annotate(
                total=Count('id'),
                ke_total=Count('id', filter=Q(stav_bedny=StavBednyChoice.K_EXPEDICI)),
            )
        )
        all_ke_map = {row['zakazka_id']: row['total'] == row['ke_total'] and row['total'] > 0 for row in aggregation}

    rows = list(queryset.order_by('pk'))

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f"bedny_export_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')  # BOM pro korektní otevření v Excelu
    writer = csv.writer(response, delimiter=';', quoting=csv.QUOTE_MINIMAL)

    header = [
        'Zákazník',
        'Datum',
        'Zakázka',
        'Číslo bedny',
        'Navezené',
        'Rozměr',
        'Do zprac.',
        'Zakal.',
        'Kontrol.',
        'Křivost',
        'Čistota',
        'K expedici',
        'Hmotnost',
        'Poznámka',
        'Hlava + závit',
        'Název',
        'Skupina',
    ]
    writer.writerow(header)

    stav_pro_navezene_x = {
        StavBednyChoice.K_NAVEZENI: 'o',
        StavBednyChoice.NAVEZENO: 'x',
    }
    do_zpracovani_states = {
        StavBednyChoice.DO_ZPRACOVANI,
        StavBednyChoice.ZAKALENO,
        StavBednyChoice.ZKONTROLOVANO,
        StavBednyChoice.K_EXPEDICI,
    }
    zakaleno_states = {
        StavBednyChoice.ZAKALENO,
        StavBednyChoice.ZKONTROLOVANO,
        StavBednyChoice.K_EXPEDICI,
    }
    zkontrolovano_states = {
        StavBednyChoice.ZKONTROLOVANO,
        StavBednyChoice.K_EXPEDICI,
    }
    rovnat_map = {
        RovnaniChoice.ROVNA: 'x',
        RovnaniChoice.KRIVA: 'křivá',
        RovnaniChoice.KOULENI: 'koulení',
        RovnaniChoice.ROVNA_SE: 'rovná se',
        RovnaniChoice.VYROVNANA: 'vyrovnaná',
    }
    tryskat_map = {
        TryskaniChoice.CISTA: 'x',
        TryskaniChoice.SPINAVA: 'špinavá',
        TryskaniChoice.OTRYSKANA: 'otryskaná',
    }

    for bedna in rows:
        zakazka = getattr(bedna, 'zakazka', None)
        kamion_prijem = getattr(zakazka, 'kamion_prijem', None) if zakazka else None
        zakaznik = getattr(kamion_prijem, 'zakaznik', None) if kamion_prijem else None

        prumer = _format_decimal(getattr(zakazka, 'prumer', None)) if zakazka else ''
        delka = _format_decimal(getattr(zakazka, 'delka', None)) if zakazka else ''
        if prumer and delka:
            rozmer = f'{prumer} x {delka}'
        elif prumer:
            rozmer = prumer
        elif delka:
            rozmer = delka
        else:
            rozmer = ''

        stav = bedna.stav_bedny
        navezene = stav_pro_navezene_x.get(stav, '')
        do_zpracovani = 'x' if stav in do_zpracovani_states else ''
        zakaleno = 'x' if stav in zakaleno_states else ''
        zkontrolovano = 'x' if stav in zkontrolovano_states else ''

        rovnat_value = rovnat_map.get(bedna.rovnat, '')
        tryskat_value = tryskat_map.get(bedna.tryskat, '')

        all_ke = all_ke_map.get(getattr(zakazka, 'id', None), False)
        if stav == StavBednyChoice.K_EXPEDICI:
            k_expedici = 'x' if all_ke else '0'
        else:
            k_expedici = ''

        typ_hlavy = ''
        if zakazka and zakazka.typ_hlavy:
            typ_hlavy = str(zakazka.typ_hlavy)
        if zakazka and zakazka.celozavit:
            typ_hlavy = f"{typ_hlavy} + VG" if typ_hlavy else 'VG'

        datum = ''
        if zakazka and zakazka.kamion_prijem and zakazka.kamion_prijem.datum:
            datum = zakazka.kamion_prijem.datum.strftime('%d.%m.%Y')

        writer.writerow([
            str(zakaznik) if zakaznik else '',
            datum,
            getattr(zakazka, 'artikl', '') if zakazka else '',
            bedna.cislo_bedny,
            navezene,
            rozmer,
            do_zpracovani,
            zakaleno,
            zkontrolovano,
            rovnat_value,
            tryskat_value,
            k_expedici,
            _format_decimal(bedna.hmotnost),
            bedna.poznamka or '',
            typ_hlavy,
            getattr(zakazka, 'zkraceny_popis', '') if zakazka else '',
            getattr(getattr(zakazka, 'predpis', None), 'skupina', '') if zakazka else '',
        ])

    logger.info(
        f"Uživatel {getattr(request, 'user', None)} exportoval {len(rows)} beden do CSV.",
    )
    return response

@admin.action(description="Export vybraných beden do CSV pro zákazníka")
def export_bedny_to_csv_customer_action(modeladmin, request, queryset):
    """
    Exportuje aktuálně vyfiltrované bedny do CSV pro informování zákazníka.
    Rozlišuje se, zda se jedná o seznam beden, které se rovnají - filtr rovnani=="k_vyrovnani"
    nebo pro schválení beden před exportem - filtr stav_bedny==StavBednyChoice.K_EXPEDICI.

    Podmínky:
    - Všechny bedny musí patřit jednomu zákazníkovi (podle zakazka__kamion_prijem__zakaznik).
    - Pro schválení před expedicí exportuje tyto sloupce: Artikel-Nr., Behälter-Nr., Abmessung (prumer x delka),
      Kopf (typ_hlavy), Bezeichnung (zkraceny popis) a # (číslo bedny), 
    - Pro rovnání exportuje stejné sloupce a navíc Stand (rovnat), Priorität (priorita) 
      a Datum (datum změny rovnat na ROVNA_SE + 7 dní).
    - Pro zákazníka ROT jsou přeloženy názvy sloupců do italštiny.
    """
    if not queryset.exists():
        return None

    zakaznik_count = queryset.values('zakazka__kamion_prijem__zakaznik').distinct().count()
    if zakaznik_count != 1:
        logger.info(
            f"Uživatel {request.user} se pokusil exportovat bedny pro schválení, ale výběr obsahuje bedny od {zakaznik_count} zákazníků."
        )
        modeladmin.message_user(request, "Pro export musí být vybrány bedny pouze od jednoho zákazníka.", level=messages.ERROR)
        return None
    
    zakaznik_zkratka = queryset.values_list('zakazka__kamion_prijem__zakaznik__zkratka', flat=True).first()

    queryset = queryset.select_related(
        'zakazka',
        'zakazka__kamion_prijem',
    ).order_by('cislo_bedny')

    is_rovnani_export = request.GET.get('rovnani', '') == 'k_vyrovnani'
    filename_suffix = 'rovnani' if is_rovnani_export else 'expedice'

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f"bedny_zakaznik_{zakaznik_zkratka}_{filename_suffix}_{timezone.now().strftime('%Y%m%d')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')
    writer = csv.writer(response, delimiter=';', quoting=csv.QUOTE_MINIMAL)

    if is_rovnani_export:
        if zakaznik_zkratka == 'ROT':
            writer.writerow([
                'Batch', 'Nr. Cass', 'Dimensione', '', 'Descrizione', 'Stato', 'Priorità', 'Data di completamento', 'HPM-Nr.', 'kg'
            ])
        else:
            writer.writerow([
                'Artikel-Nr.', 'Behälter-Nr.', 'Abmessung', 'Kopf', 'Bezeichnung', 'Stand', 'Priorität', 'Fertigstellungsdatum', 'HPM-Nr.', 'kg'
                ])
    else:
        if zakaznik_zkratka == 'ROT':
            writer.writerow(['Batch', 'Nr. Cass', 'Dimensione', '', 'Descrizione', 'HPM-Nr.', 'kg'])
        else:
            writer.writerow(['Artikel-Nr.', 'Behälter-Nr.', 'Abmessung', 'Kopf', 'Bezeichnung', 'HPM-Nr.', 'kg'])

    stav_rovnani_map = {
        RovnaniChoice.KRIVA: 'Krumm',
        RovnaniChoice.KOULENI: 'Geplant fürs Richten',
        RovnaniChoice.ROVNA_SE: 'Richten',
    }
    doba_vyrovnani_bedny_dni = 7

    for bedna in queryset:
        zakazka = getattr(bedna, 'zakazka', None)
        behalter_nr = getattr(bedna, 'behalter_nr', '') if bedna else ''
        artikl = getattr(zakazka, 'artikl', '') if zakazka else ''
        prumer = _format_decimal(getattr(zakazka, 'prumer', None)) if zakazka else ''
        delka = _format_decimal(getattr(zakazka, 'delka', None)) if zakazka else ''
        abm = f"{prumer} x {delka}" if prumer and delka else ''
        typ_hlavy = getattr(zakazka, 'typ_hlavy', '') if zakazka else ''
        zkraceny_popis = getattr(zakazka, 'zkraceny_popis', '') if zakazka else ''
        cislo_bedny = getattr(bedna, 'cislo_bedny', '') if bedna else ''
        hmotnost = _format_decimal(getattr(bedna, 'hmotnost', None)) if bedna else ''

        if is_rovnani_export:
            stav_rovnani = stav_rovnani_map.get(bedna.rovnat, '')
            priorita = bedna.zakazka.priorita if bedna.zakazka.priorita in [PrioritaChoice.VYSOKA, PrioritaChoice.STREDNI] else ''
            datum_vyrovnani = ''
            if bedna.rovnat == RovnaniChoice.ROVNA_SE:
                hqs = (
                    bedna.history.order_by('-history_date', '-history_id')
                )
                for h in hqs:
                    if h.rovnat == RovnaniChoice.ROVNA_SE:
                        prev = h.prev_record
                        if prev and prev.rovnat != RovnaniChoice.ROVNA_SE:
                            datum_zmeny_na_rovna_se = h.history_date
                            datum_vyrovnani_date = (datum_zmeny_na_rovna_se + datetime.timedelta(days=doba_vyrovnani_bedny_dni)).date()
                            if datum_vyrovnani_date <= timezone.now().date():
                                datum_vyrovnani_date = timezone.now().date() + datetime.timedelta(days=1)
                            datum_vyrovnani = datum_vyrovnani_date.strftime('%d.%m.%Y')
                            break

        row = [artikl, behalter_nr, abm, typ_hlavy, zkraceny_popis]
        if is_rovnani_export:
            row.extend([stav_rovnani, priorita, datum_vyrovnani])
        row.extend([cislo_bedny, hmotnost])

        writer.writerow(row)

    logger.info(
        f"Uživatel {getattr(request, 'user', None)} vyexportoval {queryset.count()} beden pro schválení zákazníkem do CSV.",
    )
    return response


@admin.action(description="Export vybraných beden do CSV pro vložení do DL")
def export_bedny_dl_action(modeladmin, request, queryset):
    """
    Export pro DL na export Eurotec nebo pro DL na zinkování: validuje stav K_EXPEDICI / EXPEDOVANO a jednoho zákazníka.
    Sloupce: Vorgang+, Artikel-Nr., Materialcharge, ∑, Gewicht, Abmess., Kopf, Bezeichnung,
    Oberfläche, Beschicht., Behälter-Nr., Sonder Zusatzinfo, Lief., Fertigungsauftrags Nr., Reinheit, 
    pro stav K_EXPEDICI navíc HPM-Nr.
    """
    if not queryset.exists():
        return None

    zakaznici = queryset.values('zakazka__kamion_prijem__zakaznik__zkratka').distinct()
    if zakaznici.count() != 1:
        modeladmin.message_user(request, "Export je možný pouze pro bedny jednoho zákazníka.", level=messages.ERROR)
        return None
    zakaznik_zkratka = zakaznici.first().get('zakazka__kamion_prijem__zakaznik__zkratka')

    if queryset.exclude(stav_bedny__in=[StavBednyChoice.K_EXPEDICI, StavBednyChoice.EXPEDOVANO]).exists():
        modeladmin.message_user(request, "Všechny vybrané bedny musí být ve stavu K_EXPEDICI nebo EXPEDOVANO.", level=messages.ERROR)
        return None

    queryset = queryset.select_related(
        'zakazka',
        'zakazka__typ_hlavy',
        'zakazka__kamion_prijem__zakaznik',
    ).order_by('zakazka_id', 'id')

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f"bedny_{zakaznik_zkratka}_dl_{timezone.now().strftime('%Y%m%d_%H%M%S')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')
    writer = csv.writer(response, delimiter=';', quoting=csv.QUOTE_MINIMAL)

    row = [
        'Vorgang+', 'Artikel-Nr.', 'Materialcharge', '∑', 'Gewicht', 'Abmess.', 'Kopf', 'Bezeichnung',
        'Oberfläche', 'Beschicht.', 'Behälter-Nr.', 'Sonder Zusatzinfo', 'Lief.', 'Fertigungsauftrags Nr.', 'Reinheit'
    ]
    if request.GET.get('stav_bedny', '') == StavBednyChoice.K_EXPEDICI:
        row.append('HPM-Nr.')
    writer.writerow(row)
    for bedna in queryset:
        zak = getattr(bedna, 'zakazka', None)
        prumer = _format_decimal(getattr(zak, 'prumer', None)) if zak else ''
        delka = _format_decimal(getattr(zak, 'delka', None)) if zak else ''
        if prumer and delka:
            abm = f"{prumer} x {delka}"
        elif prumer:
            abm = prumer
        elif delka:
            abm = delka
        else:
            abm = ''

        row = [
            getattr(zak, 'prubeh', '') if zak else '',
            getattr(zak, 'artikl', '') if zak else '',
            getattr(bedna, 'sarze', '') or '',
            '',
            _format_decimal(getattr(bedna, 'hmotnost', None)),
            abm,
            str(getattr(zak, 'typ_hlavy', '') or ''),
            getattr(zak, 'popis', '') if zak else '',
            getattr(zak, 'povrch', '') if zak else '',
            getattr(zak, 'vrstva', '') if zak else '',
            getattr(bedna, 'behalter_nr', '') or '',
            getattr(bedna, 'dodatecne_info', '') or '',
            getattr(bedna, 'dodavatel_materialu', '') or '',
            getattr(bedna, 'vyrobni_zakazka', '') or '',
            'sandgestrahlt' if getattr(bedna, 'tryskat', None) == TryskaniChoice.OTRYSKANA else '--',
        ]
        if request.GET.get('stav_bedny', '') == StavBednyChoice.K_EXPEDICI:
            row.append(getattr(bedna, 'cislo_bedny', '') or '')
        writer.writerow(row)

    logger.info(
        f"Uživatel {getattr(request, 'user', None)} exportoval {queryset.count()} beden {zakaznik_zkratka} do CSV pro DL.",
    )
    return response

@admin.action(description="Vytisknout karty bedny")
def tisk_karet_beden_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartou bedny pro označené bedny.
    Bedny musí být od jednoho zákazníka.
    Bedny musí mít zadanou hmotnost, zakázku a předpis.
    """
    if queryset.values('zakazka__kamion_prijem__zakaznik').distinct().count() != 1:
        logger.error(f"Uživatel {request.user} se pokusil tisknout karty beden, ale vybral bedny od více zákazníků.")
        modeladmin.message_user(request, "Pro tisk karet beden musí být vybrány bedny od jednoho zákazníka.", level=messages.ERROR)
        return None
    
    if _abort_if_bedna_has_not_hmotnost_zakazka_predpis(modeladmin, request, queryset, "tisk karet beden"):
        return None

    zakaznik_zkratka = queryset.first().zakazka.kamion_prijem.zakaznik.zkratka
    if zakaznik_zkratka:
        try:
            template_paths, filename = resolve_customer_templates(
                zakaznik_zkratka=zakaznik_zkratka,
                mode="bedna",
            )
            html_path = template_paths[0]
        except ServiceValidationError as exc:
            modeladmin.message_user(request, str(exc), level=messages.ERROR)
            return None
        response = utilita_tisk_dokumentace(modeladmin, request, queryset, html_path, filename)
        logger.info(f"Uživatel {request.user} tiskne karty beden pro {queryset.count()} vybraných beden.")
        return response
    else:
        logger.error(f"Bedna {queryset.first()} nemá přiřazeného zákazníka nebo zákazník nemá zkratku.")
        modeladmin.message_user(request, "Bedna nemá přiřazeného zákazníka nebo zákazník nemá zkratku.", level=messages.ERROR)
        return None

@admin.action(description="Vytisknout KKK")
def tisk_karet_kontroly_kvality_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartou kontroly kvality pro označené bedny.
    Bedny musít být od jednoho zákazníka.
    Bedny musí mít zadanou hmotnost, zakázku a předpis.
    """
    if queryset.values('zakazka__kamion_prijem__zakaznik').distinct().count() != 1:
        logger.error(f"Uživatel {request.user} se pokusil tisknout karty beden, ale vybral bedny od více zákazníků.")
        modeladmin.message_user(request, "Pro tisk karet beden musí být vybrány bedny od jednoho zákazníka.", level=messages.ERROR)
        return None
    
    if _abort_if_bedna_has_not_hmotnost_zakazka_predpis(modeladmin, request, queryset, "tisk karet kontroly kvality"):
        return None

    zakaznik_zkratka = queryset.first().zakazka.kamion_prijem.zakaznik.zkratka
    if zakaznik_zkratka:
        try:
            template_paths, filename = resolve_customer_templates(
                zakaznik_zkratka=zakaznik_zkratka,
                mode="kkk",
            )
            html_path = template_paths[0]
        except ServiceValidationError as exc:
            modeladmin.message_user(request, str(exc), level=messages.ERROR)
            return None
        response = utilita_tisk_dokumentace(modeladmin, request, queryset, html_path, filename)
        logger.info(f"Uživatel {request.user} tiskne karty kontroly kvality pro {queryset.count()} vybraných beden.")
        return response        
    else:
        logger.error(f"Bedna {queryset.first()} nemá přiřazeného zákazníka nebo zákazník nemá zkratku.")
        modeladmin.message_user(request, "Bedna nemá přiřazeného zákazníka nebo zákazník nemá zkratku.", level=messages.ERROR)
        return None


@admin.action(description="Vytisknout karty bedny + KKK")
def tisk_karet_bedny_a_kontroly_action(modeladmin, request, queryset):
    """
    Vytvoří PDF, kde má každá bedna svoji kartu a navazující kartu kontroly kvality.
    Bedny musít být od jednoho zákazníka.
    Bedny musí mít zadanou hmotnost, zakázku a předpis.
    """
    if queryset.values('zakazka__kamion_prijem__zakaznik').distinct().count() != 1:
        logger.error(
            f"Uživatel {getattr(request, 'user', None)} se pokusil tisknout kombinované karty beden, ale vybral bedny od více zákazníků."
        )
        modeladmin.message_user(
            request,
            "Pro tisk kombinovaných karet musí být vybrány bedny od jednoho zákazníka.",
            level=messages.ERROR,
        )
        return None
    
    if _abort_if_bedna_has_not_hmotnost_zakazka_predpis(modeladmin, request, queryset, "tisk kombinovaných karet"):
        return None

    first_bedna = queryset.first()
    if not first_bedna or not first_bedna.zakazka or not first_bedna.zakazka.kamion_prijem:
        logger.error("Tisk kombinovaných karet selhal: chybí zakázka nebo kamion příjem u vybrané bedny.")
        modeladmin.message_user(request, "Bedna nemá kompletní vazby pro tisk.", level=messages.ERROR)
        return None

    zakaznik = first_bedna.zakazka.kamion_prijem.zakaznik
    zakaznik_zkratka = getattr(zakaznik, 'zkratka', None)
    if zakaznik_zkratka:
        try:
            html_paths, filename = resolve_customer_templates(
                zakaznik_zkratka=zakaznik_zkratka,
                mode="kombi",
            )
        except ServiceValidationError as exc:
            modeladmin.message_user(request, str(exc), level=messages.ERROR)
            return None
        response = utilita_tisk_dokumentace_sablony(modeladmin, request, queryset, html_paths, filename)
        if response:
            logger.info(
                f"Uživatel {getattr(request, 'user', None)} tiskne kombinované karty bedny+KKK pro {queryset.count()} vybraných beden."
            )
        return response

    logger.error(f"Bedna {first_bedna} nemá přiřazeného zákazníka nebo zákazník nemá zkratku.")
    modeladmin.message_user(
        request,
        "Bedna nemá přiřazeného zákazníka nebo zákazník nemá zkratku.",
        level=messages.ERROR,
    )
    return None

@admin.action(description="Přijmout vybrané bedny na sklad", permissions=('change',))
def prijmout_bedny_action(modeladmin, request, queryset):
    """
    Přijme vybrané bedny (NEPRIJATO -> PRIJATO) v režimu ČÁSTEČNÉHO ÚSPĚCHU.

    - Každá bedna je validována a ukládána samostatně.
    - Chybné bedny se přeskočí a zobrazí se pro ně chybové zprávy.
    - Úspěšné se přepnou do stavu PRIJATO ihned (bez globálního rollbacku).
    - Bedny, které nejsou ve stavu NEPRIJATO, jsou hlášeny jako chyba a ponechány beze změny.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Přijmout vybrané bedny na sklad"):
        return None

    success = 0
    failures = 0

    # Pro deterministiku pořadí (stabilita logů) seřadíme podle PK
    for bedna in queryset.order_by('pk'):
        if bedna.stav_bedny != StavBednyChoice.NEPRIJATO:
            modeladmin.message_user(
                request,
                f"Bedna {bedna} není ve stavu NEPRIJATO.",
                level=messages.ERROR,
            )
            failures += 1
            continue

        original_state = bedna.stav_bedny
        bedna.stav_bedny = StavBednyChoice.PRIJATO
        try:
            bedna.full_clean()
            bedna.save()
            success += 1
        except ValidationError as e:
            bedna.stav_bedny = original_state
            for msg in e.messages:
                modeladmin.message_user(
                    request,
                    f"Bedna {bedna}: {msg}",
                    level=messages.ERROR,
                )
            failures += 1
        except (IntegrityError, DataError) as e:
            bedna.stav_bedny = original_state
            modeladmin.message_user(
                request,
                f"Bedna {bedna}: {e}",
                level=messages.ERROR,
            )
            failures += 1
        except Exception as e:  # Neočekávané
            bedna.stav_bedny = original_state
            logger.exception(f"Neočekávaná chyba při přijímání bedny {bedna}")
            modeladmin.message_user(
                request,
                f"Bedna {bedna}: Neočekávaná chyba: {e}",
                level=messages.ERROR,
            )
            failures += 1

    if success:
        modeladmin.message_user(
            request,
            f"Přijato na sklad: {success} beden.",
            level=messages.SUCCESS,
        )

    if failures and success:
        modeladmin.message_user(
            request,
            f"Nepřijato: {failures} beden – viz chybové zprávy výše.",
            level=messages.WARNING,
        )
        logger.info(f"Uživatel {request.user} přijal na sklad {success} beden (částečný režim), {failures} mělo chybu.")
    elif failures and not success:
        modeladmin.message_user(
            request,
            "Žádná bedna nebyla přijata (všechny měly chybu).",
            level=messages.ERROR,
        )
        logger.info(f"Uživatel {request.user} se pokusil přijmout bedny na sklad, ale žádná nebyla přijata (všechny měly chybu).")

    return None

def _render_oznacit_k_navezeni(modeladmin, request, queryset, formset):
    """
    Interní funkce vykreslení mezikroku akce (formset s volbou pozic).
    """
    action = request.POST.get("action") or request.GET.get("action") or "oznacit_k_navezeni_action"
    pozice = Pozice.objects.all().order_by('kod')
    context = {
        **modeladmin.admin_site.each_context(request),
        "title": "Zvol pozice pro vybrané bedny",
        "queryset": queryset,
        "formset": formset,
        "vsechny_pozice": pozice,
        "opts": modeladmin.model._meta,
        "action_name": action,
        "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
    }
    return TemplateResponse(request, "admin/bedna/oznacit_k_navezeni.html", context)    

def _render_oznacit_prijato_navezeno(modeladmin, request, queryset, formset):
    """Zobrazení potvrzovací obrazovky pro navezení beden."""
    action = request.POST.get("action") or request.GET.get("action") or "oznacit_prijato_navezeno_action"
    pozice = Pozice.objects.all().order_by('kod')
    context = {
        **modeladmin.admin_site.each_context(request),
        "title": "Potvrďte navezení vybraných beden",
        "queryset": queryset,
        "formset": formset,
        "vsechny_pozice": pozice,
        "opts": modeladmin.model._meta,
        "action_name": action,
        "action_checkbox_name": admin.helpers.ACTION_CHECKBOX_NAME,
    }
    return TemplateResponse(request, "admin/bedna/oznacit_navezeno.html", context)

@admin.action(description="Změna stavu bedny na K_NAVEZENI", permissions=('change',))
def oznacit_k_navezeni_action(modeladmin, request, queryset):
    """
    Změní stav vybraných beden na K_NAVEZENI a přidá k bedně zvolenou pozici.
    Zkontroluje zda nejsou v querysetu pozastavené bedny a zda jsou všechny ve stavu PRIJATO.
    Pokud nejsou podmínky splněny, akce se přeruší s chybovou hláškou.
    1) GET: zobrazí formset s výběrem pozice pro každou vybranou bednu.
    2) POST (apply): validace kapacit + uložení (stav PRIJATO -> K_NAVEZENI a přiřazení pozice).
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu bedny na K_NAVEZENÍ"):
        return None


    bedny_errors = [bedna for bedna in queryset if bedna.stav_bedny != StavBednyChoice.PRIJATO]
    if bedny_errors:
        logger.info(
            f"Uživatel {request.user} se pokusil změnit stav na K_NAVEZENÍ, ale následující bedny nejsou v PRIJATO: {', '.join(str(b) for b in bedny_errors)}"
        )
        for bedna in bedny_errors:
            modeladmin.message_user(
                request,
                f"Bedna {bedna} není ve stavu PRIJATO, nelze změnit na K NAVEZENÍ.",
                level=messages.ERROR,
            )
        return None

    KNavezeniFormSet = formset_factory(KNavezeniForm, extra=0)

    if request.method == "POST" and ("apply" in request.POST or "apply_open_dashboard" in request.POST):
        redirect_requested = "apply_open_dashboard" in request.POST
        select_ids = request.POST.getlist(admin.helpers.ACTION_CHECKBOX_NAME)
        qs = Bedna.objects.filter(pk__in=select_ids)            
        if _abort_if_paused_bedny(modeladmin, request, qs, "Změna stavu bedny na K_NAVEZENÍ"):
            return None

        note_map = {
            (order.pozice_id, order.zakazka_id): order.poznamka_k_navezeni
            for order in PoziceZakazkaOrder.objects.filter(
                pozice_id__in=qs.values_list('pozice_id', flat=True),
                zakazka_id__in=qs.values_list('zakazka_id', flat=True),
            )
        }
        initial = [
            {
                "bedna_id": bedna.pk,
                "cislo": bedna.cislo_bedny,
                "prumer": bedna.zakazka.prumer,
                "delka": bedna.zakazka.delka,
                "hmotnost": bedna.hmotnost,
                "zakazka_id": bedna.zakazka.pk,
                "artikl": bedna.zakazka.artikl,
                "typ_hlavy": bedna.zakazka.typ_hlavy,
                "popis": bedna.zakazka.popis,
                "poznamka_k_navezeni": note_map.get((bedna.pozice_id, bedna.zakazka_id)),
                "pozice": bedna.pozice
            } for bedna in qs
        ]
        formset = KNavezeniFormSet(data=request.POST, initial=initial, prefix="ozn")

        # Pokud formset není validní, znovu se vykreslí s hodnotami
        if not formset.is_valid():           
            messages.error(request, "Formulář není validní.")
            return _render_oznacit_k_navezeni(modeladmin, request, qs, formset)
        
        # Pokud není uvedena pozice u první bedny, znovu se vykreslí s hodnotami a chybou
        aktualni_pozice = formset.forms[0].cleaned_data.get("pozice")
        if not aktualni_pozice:
            messages.error(request, "Je potřeba vybrat alespoň první pozici.")
            return _render_oznacit_k_navezeni(modeladmin, request, qs, formset)

        # Předpočítáme aktuální obsazenost/kapacity pro varování
        kapacita = {}
        obsazenost = {}
        for p in Pozice.objects.all():
            kapacita[p.pk] = p.kapacita
            obsazenost[p.pk] = p.bedny.count()

        uspesne = 0
        prekrocena_kapacita = 0

        with transaction.atomic():
            vybrane_ids = [f.cleaned_data["bedna_id"] for f in formset.forms]
            bedny_map = {
                b.pk: b for b in Bedna.objects.select_for_update().filter(pk__in=vybrane_ids)
            }
            pair_note_map = {}

            for form in formset.forms:
                bedna_id = form.cleaned_data["bedna_id"]
                poznamka_k_navezeni = form.cleaned_data["poznamka_k_navezeni"]
                pozice = form.cleaned_data["pozice"] #co zadal uživatel na tomto řádku

                # pokud uživatel zadal na řádku pozici, stane se aktuální pozicí, jinak se použije poslední zadaná pozice
                if pozice:
                    aktualni_pozice = pozice
                else:
                    pozice = aktualni_pozice               

                bedna = bedny_map.get(bedna_id)
                if not bedna:
                    messages.warning(request, f"Bedna s ID {bedna_id} nebyla nalezena, přeskočena.")
                    continue

                pid = pozice.pk
                # Pokud by přiřazení přesáhlo kapacitu, jen poznačíme pro warning
                if obsazenost[pid] + 1 > kapacita[pid]:
                    prekrocena_kapacita += 1

                # Přesun + změna stavu (bez ohledu na kapacitu)
                bedna.pozice = pozice
                bedna.stav_bedny = StavBednyChoice.K_NAVEZENI
                bedna.save()
                pair_key = (pozice.pk, bedna.zakazka_id)
                note_value = (poznamka_k_navezeni or None)
                if pair_key not in pair_note_map:
                    pair_note_map[pair_key] = note_value
                elif note_value is not None:
                    pair_note_map[pair_key] = note_value

                obsazenost[pid] += 1
                uspesne += 1

            for (pozice_id, zakazka_id), note in pair_note_map.items():
                existing = (
                    PoziceZakazkaOrder.objects
                    .select_for_update()
                    .filter(pozice_id=pozice_id, zakazka_id=zakazka_id)
                    .first()
                )
                if existing:
                    if existing.poznamka_k_navezeni != note:
                        existing.poznamka_k_navezeni = note
                        existing.save(update_fields=['poznamka_k_navezeni'])
                    continue

                # Soubeh: dve transakce mohou soucasne chtit zalozit stejny zaznam
                # nebo stejne poradi v pozici. Pri kolizi proto retry.
                max_attempts = 5
                for attempt in range(max_attempts):
                    last_poradi = (
                        PoziceZakazkaOrder.objects
                        .select_for_update()
                        .filter(pozice_id=pozice_id)
                        .order_by('-poradi')
                        .values_list('poradi', flat=True)
                        .first()
                        or 0
                    )
                    try:
                        PoziceZakazkaOrder.objects.create(
                            pozice_id=pozice_id,
                            zakazka_id=zakazka_id,
                            poradi=last_poradi + 1,
                            poznamka_k_navezeni=note,
                        )
                        break
                    except IntegrityError:
                        existing_retry = (
                            PoziceZakazkaOrder.objects
                            .select_for_update()
                            .filter(pozice_id=pozice_id, zakazka_id=zakazka_id)
                            .first()
                        )
                        if existing_retry:
                            if existing_retry.poznamka_k_navezeni != note:
                                existing_retry.poznamka_k_navezeni = note
                                existing_retry.save(update_fields=['poznamka_k_navezeni'])
                            break
                        if attempt == max_attempts - 1:
                            raise

        if uspesne:
            messages.success(request, f"Připraveno k navezení: {uspesne} beden.")
        if prekrocena_kapacita:
            messages.warning(
                request,
                f"U {prekrocena_kapacita} beden byla překročena kapacita cílové pozice, přesto byly přiřazeny."
            )

        if redirect_requested:
            return redirect("dashboard_bedny_k_navezeni")
        return None

    # GET – předvyplň formset
    note_map = {
        (order.pozice_id, order.zakazka_id): order.poznamka_k_navezeni
        for order in PoziceZakazkaOrder.objects.filter(
            pozice_id__in=queryset.values_list('pozice_id', flat=True),
            zakazka_id__in=queryset.values_list('zakazka_id', flat=True),
        )
    }
    initial = [
        {
            "bedna_id": bedna.pk,
            "cislo": bedna.cislo_bedny,
            "prumer": bedna.zakazka.prumer,
            "delka": bedna.zakazka.delka,
            "hmotnost": bedna.hmotnost,
            "artikl": bedna.zakazka.artikl,
            "zakazka_id": bedna.zakazka.pk,
            "typ_hlavy": bedna.zakazka.typ_hlavy,
            "popis": bedna.zakazka.popis,
            "poznamka_k_navezeni": note_map.get((bedna.pozice_id, bedna.zakazka_id)),
            "pozice": bedna.pozice
        } for bedna in queryset
    ]
    formset = KNavezeniFormSet(initial=initial, prefix="ozn")
    return _render_oznacit_k_navezeni(modeladmin, request, queryset, formset)       

@admin.action(description="Změna stavu bedny na NAVEZENO", permissions=('change',))
def oznacit_navezeno_action(modeladmin, request, queryset):
    """
    Změní stav vybraných beden z K_NAVEZENI na NAVEZENO.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu bedny na NAVEZENO"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu K_NAVEZENI
    if queryset.exclude(stav_bedny=StavBednyChoice.K_NAVEZENI).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na NAVEZENO, ale některé bedny nejsou ve stavu K NAVEZENÍ.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu K NAVEZENÍ.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.stav_bedny == StavBednyChoice.K_NAVEZENI:
                bedna.stav_bedny = StavBednyChoice.NAVEZENO
                bedna.save()

    modeladmin.message_user(request, f"Navezeno: {queryset.count()} beden.", level=messages.SUCCESS)
    logger.info(f"Uživatel {request.user} změnil stav na NAVEZENO u {queryset.count()} beden.")
    return None

@admin.action(description="Navezení beden (PŘIJATO, K_NAVEZENÍ -> NAVEZENO)")
def oznacit_prijato_navezeno_action(modeladmin, request, queryset):
    """
    Potvrdí navezení beden a přepne stav PŘIJATO/K_NAVEZENÍ na NAVEZENO.

    Akce vyžaduje oprávnění `mark_bedna_navezeno` (nebo obecné `change_bedna`).
    Nejprve ověří, že žádná bedna není pozastavená a že všechny mají povolený vstupní stav.
    V potvrzovacím formuláři se pořadí beden drží podle uživatelského výběru:
    první řádek musí mít ručně zadanou pozici, tu pak akce doplní do dalších
    prázdných řádků. Celý přechod probíhá v transakci a jednotlivé bedny jsou
    uzamčeny pomocí `select_for_update`.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Navezení beden (PŘIJATO, K_NAVEZENÍ -> NAVEZENO)"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu PŘIJATO nebo K_NAVEZENI
    if queryset.exclude(stav_bedny__in=[StavBednyChoice.PRIJATO, StavBednyChoice.K_NAVEZENI]).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na NAVEZENO, ale některé bedny nejsou ve stavu PŘIJATO nebo K_NAVEZENÍ.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu PŘIJATO nebo K_NAVEZENÍ.", level=messages.ERROR)
        return None
    
    NavezenoFormSet = formset_factory(NavezenoForm, extra=0)

    if request.method == "POST" and "apply" in request.POST:
        select_ids = request.POST.getlist(admin.helpers.ACTION_CHECKBOX_NAME)
        qs = Bedna.objects.filter(pk__in=select_ids)
        if _abort_if_paused_bedny(modeladmin, request, qs, "Navezení beden (PŘIJATO, K_NAVEZENÍ -> NAVEZENO)"):
            return None
        
        initial = [
            {
                "bedna_id": bedna.pk,
                "cislo": bedna.cislo_bedny,
                "pozice": bedna.pozice
            } for bedna in qs
        ]
        formset = NavezenoFormSet(data=request.POST, initial=initial, prefix="ozn")

        # Pokud formset není validní, znovu se vykreslí s hodnotami
        if not formset.is_valid():
            messages.error(request, "Formulář není validní.")
            return _render_oznacit_prijato_navezeno(modeladmin, request, qs, formset)

        # Pokud není uvedena pozice u první bedny, znovu se vykreslí s hodnotami a chybou
        aktualni_pozice = formset.forms[0].cleaned_data.get("pozice")
        if not aktualni_pozice:
            messages.error(request, "Je potřeba vybrat alespoň první pozici.")
            return _render_oznacit_prijato_navezeno(modeladmin, request, qs, formset)

        vybrane_ids = [f.cleaned_data["bedna_id"] for f in formset.forms]
        formularova_data = []
        for form in formset.forms:
            bedna_id = form.cleaned_data["bedna_id"]
            pozice = form.cleaned_data.get("pozice")
            if pozice:
                aktualni_pozice = pozice
            else:
                pozice = aktualni_pozice

            formularova_data.append((bedna_id, pozice))

        uspesne = 0

        with transaction.atomic():
            locked_qs = Bedna.objects.select_for_update().filter(pk__in=vybrane_ids)
            if _abort_if_paused_bedny(modeladmin, request, locked_qs, "Navezení beden (PŘIJATO, K_NAVEZENÍ -> NAVEZENO)"):
                return None

            if locked_qs.exclude(stav_bedny__in=[StavBednyChoice.PRIJATO, StavBednyChoice.K_NAVEZENI]).exists():
                logger.info(
                    f"Uživatel {request.user} se pokusil změnit stav na NAVEZENO, ale některé bedny už nejsou ve stavu PŘIJATO nebo K_NAVEZENÍ."
                )
                modeladmin.message_user(
                    request,
                    "Některé vybrané bedny už nejsou ve stavu PŘIJATO nebo K_NAVEZENÍ.",
                    level=messages.ERROR,
                )
                return None

            bedny_map = {b.pk: b for b in locked_qs}

            for bedna_id, pozice in formularova_data:
                bedna = bedny_map.get(bedna_id)
                if not bedna:
                    messages.warning(request, f"Bedna s ID {bedna_id} nebyla nalezena, přeskočena.")
                    continue

                bedna.stav_bedny = StavBednyChoice.NAVEZENO
                bedna.pozice = pozice
                bedna.save()
                uspesne += 1

        if uspesne:
            modeladmin.message_user(request, f"Navezeno: {uspesne} beden.", level=messages.SUCCESS)
            logger.info(f"Uživatel {request.user} změnil stav na NAVEZENO u {uspesne} beden.")

        return None
    
    # GET – předvyplň formset
    initial = [
        {
            "bedna_id": bedna.pk,
            "cislo": bedna.cislo_bedny,
            "pozice": bedna.pozice
        } for bedna in queryset
    ]
    formset = NavezenoFormSet(initial=initial, prefix="ozn")
    return _render_oznacit_prijato_navezeno(modeladmin, request, queryset, formset)

@admin.action(description="Změnit stav bedny z PŘIJATO rovnou do ZAKALENO (při reklamaci)", permissions=('mark_bedna_zakaleno',))
def oznacit_prijato_do_zakaleno_action(modeladmin, request, queryset):
    """
    
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změnit stav bedny z PŘIJATO rovnou do ZAKALENO (při reklamaci)"):
        return None

    # kontrola, zda jsou všechny zakázky v querysetu ve stavu PRIJATO
    if queryset.exclude(stav_bedny=StavBednyChoice.PRIJATO).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav z PŘIJATO do ZAKALENO, ale některé bedny nejsou ve stavu PŘIJATO.")
        messages.error(request, "Některé vybrané bedny nejsou ve stavu PŘIJATO.")
        return None

    selected_ids = list(queryset.values_list('pk', flat=True))
    with transaction.atomic():
        locked_qs = Bedna.objects.select_for_update().filter(pk__in=selected_ids)

        if _abort_if_paused_bedny(modeladmin, request, locked_qs, "Změnit stav bedny z PŘIJATO rovnou do ZAKALENO (při reklamaci)"):
            return None

        if locked_qs.exclude(stav_bedny=StavBednyChoice.PRIJATO).exists():
            logger.info(
                f"Uživatel {request.user} se pokusil změnit stav z PŘIJATO do ZAKALENO, ale některé bedny už nejsou ve stavu PŘIJATO."
            )
            messages.error(request, "Některé vybrané bedny už nejsou ve stavu PŘIJATO.")
            return None

        zmeneno = locked_qs.update(stav_bedny=StavBednyChoice.ZAKALENO)

    logger.info(f"Uživatel {request.user} změnil stav z PŘIJATO do ZAKALENO u {zmeneno} beden.")
    messages.success(request, f"Změněno z PŘIJATO do ZAKALENO: {zmeneno} beden.")
    return None      

@admin.action(description="Vrátit bedny ze stavu K NAVEZENÍ do stavu PŘIJATO", permissions=('change',))
def vratit_bedny_ze_stavu_k_navezeni_do_stavu_prijato_action(modeladmin, request, queryset):
    """
    Vrátí vybrané bedny ze stavu K NAVEZENÍ do PŘIJATO.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Vrátit bedny ze stavu K NAVEZENÍ do stavu PŘIJATO"):
        return None

    # kontrola, zda jsou všechny zakázky v querysetu ve stavu K_NAVEZENI
    if queryset.exclude(stav_bedny=StavBednyChoice.K_NAVEZENI).exists():
        logger.info(f"Uživatel {request.user} se pokusil vrátit bedny do stavu PŘIJATO, ale některé nejsou ve stavu K NAVEZENÍ.")
        messages.error(request, "Některé vybrané bedny nejsou ve stavu K NAVEZENÍ.")
        return None

    selected_ids = list(queryset.values_list('pk', flat=True))
    with transaction.atomic():
        locked_qs = Bedna.objects.select_for_update().filter(pk__in=selected_ids)

        if _abort_if_paused_bedny(modeladmin, request, locked_qs, "Vrátit bedny ze stavu K NAVEZENÍ do stavu PŘIJATO"):
            return None

        if locked_qs.exclude(stav_bedny=StavBednyChoice.K_NAVEZENI).exists():
            logger.info(
                f"Uživatel {request.user} se pokusil vrátit bedny do stavu PŘIJATO, ale některé už nejsou ve stavu K NAVEZENÍ."
            )
            messages.error(request, "Některé vybrané bedny už nejsou ve stavu K NAVEZENÍ.")
            return None

        vraceno = locked_qs.update(stav_bedny=StavBednyChoice.PRIJATO)

    logger.info(f"Uživatel {request.user} vrátil do stavu PŘIJATO {vraceno} beden.")
    messages.success(request, f"Vráceno do stavu PŘIJATO: {vraceno} beden.")
    return None

@admin.action(description="Vrátit bedny ze stavu NAVEZENO do stavu PŘIJATO", permissions=('mark_bedna_navezeno',))
def vratit_bedny_ze_stavu_navezeno_do_stavu_prijato_action(modeladmin, request, queryset):
    """
    Vrátí vybrané bedny ze stavu NAVEZENO do PŘIJATO.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Vrátit bedny ze stavu NAVEZENO do stavu PŘIJATO"):
        return None

    # kontrola, zda jsou všechny zakázky v querysetu ve stavu NAVEZENO
    if queryset.exclude(stav_bedny=StavBednyChoice.NAVEZENO).exists():
        logger.info(f"Uživatel {request.user} se pokusil vrátit bedny do stavu PŘIJATO, ale některé nejsou ve stavu NAVEZENO.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu NAVEZENO.", level=messages.ERROR)
        return None

    selected_ids = list(queryset.values_list('pk', flat=True))
    with transaction.atomic():
        locked_qs = Bedna.objects.select_for_update().filter(pk__in=selected_ids)

        if _abort_if_paused_bedny(modeladmin, request, locked_qs, "Vrátit bedny ze stavu NAVEZENO do stavu PŘIJATO"):
            return None

        if locked_qs.exclude(stav_bedny=StavBednyChoice.NAVEZENO).exists():
            logger.info(
                f"Uživatel {request.user} se pokusil vrátit bedny do stavu PŘIJATO, ale některé už nejsou ve stavu NAVEZENO."
            )
            modeladmin.message_user(request, "Některé vybrané bedny už nejsou ve stavu NAVEZENO.", level=messages.ERROR)
            return None

        vraceno = locked_qs.update(stav_bedny=StavBednyChoice.PRIJATO)

    logger.info(f"Uživatel {request.user} vrátil do stavu PŘIJATO {vraceno} beden.")
    modeladmin.message_user(request, f"Vráceno do stavu PŘIJATO: {vraceno} beden.", level=messages.SUCCESS)
    return None    

@admin.action(description="Vrátit bedny z rozpracovanosti do stavu PŘIJATO", permissions=('change',))
def vratit_bedny_z_rozpracovanosti_do_stavu_prijato_action(modeladmin, request, queryset):
    """
    Vrátí vybrané bedny z rozpracovanosti do stavu PŘIJATO.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Vrátit bedny z rozpracovanosti do stavu PŘIJATO"):
        return None

    # kontrola, zda jsou všechny zakázky v querysetu v rozpracovanosti
    if queryset.exclude(stav_bedny__in=STAV_BEDNY_ROZPRACOVANOST).exists():
        logger.info(f"Uživatel {request.user} se pokusil vrátit bedny do stavu PŘIJATO, ale některé nejsou v rozpracovanosti.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou v rozpracovanosti.", level=messages.ERROR)
        return None

    selected_ids = list(queryset.values_list('pk', flat=True))
    with transaction.atomic():
        locked_qs = Bedna.objects.select_for_update().filter(pk__in=selected_ids)

        if _abort_if_paused_bedny(modeladmin, request, locked_qs, "Vrátit bedny z rozpracovanosti do stavu PŘIJATO"):
            return None

        if locked_qs.exclude(stav_bedny__in=STAV_BEDNY_ROZPRACOVANOST).exists():
            logger.info(
                f"Uživatel {request.user} se pokusil vrátit bedny do stavu PŘIJATO, ale některé už nejsou v rozpracovanosti."
            )
            modeladmin.message_user(request, "Některé vybrané bedny už nejsou v rozpracovanosti.", level=messages.ERROR)
            return None

        vraceno = locked_qs.update(stav_bedny=StavBednyChoice.PRIJATO)

    logger.info(f"Uživatel {request.user} vrátil do stavu PŘIJATO {vraceno} beden.")
    modeladmin.message_user(request, f"Vráceno do stavu PŘIJATO: {vraceno} beden.", level=messages.SUCCESS)
    return None    

@admin.action(description="Změna stavu bedny na DO ZPRACOVÁNÍ", permissions=('change',))
def oznacit_do_zpracovani_action(modeladmin, request, queryset):
    """
    Změní stav vybraných beden ze stavu ROZPRACOVANOST (NAVEZENO, DO_ZPRACOVANI, ZAKALENO, ZKONTROLOVANO) na DO_ZPRACOVANI.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu bedny na DO ZPRACOVÁNÍ"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu ROZPRACOVANOST (NAVEZENO, DO_ZPRACOVANI, ZAKALENO, ZKONTROLOVANO)
    if queryset.exclude(stav_bedny__in=STAV_BEDNY_ROZPRACOVANOST).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na DO ZPRACOVÁNÍ, ale některé bedny nejsou ve stavu ROZPRACOVANOST.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu ROZPRACOVANOST.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.stav_bedny in STAV_BEDNY_ROZPRACOVANOST:
                bedna.stav_bedny = StavBednyChoice.DO_ZPRACOVANI
                bedna.save()

    modeladmin.message_user(request, f"Do zpracování: {queryset.count()} beden.", level=messages.SUCCESS)
    logger.info(f"Uživatel {request.user} změnil stav na DO ZPRACOVÁNÍ u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu bedny na ZAKALENO", permissions=('change',))
def oznacit_zakaleno_action(modeladmin, request, queryset):
    """
    Změní stav vybraných beden ze stavu ROZPRACOVANOST (NAVEZENO, DO_ZPRACOVANI, ZAKALENO, ZKONTROLOVANO) na ZAKALENO.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu bedny na ZAKALENO"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu ROZPRACOVANOST
    if queryset.exclude(stav_bedny__in=STAV_BEDNY_ROZPRACOVANOST).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na ZAKALENO, ale některé bedny nejsou ve stavu ROZPRACOVANOST.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu ROZPRACOVANOST.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.stav_bedny in STAV_BEDNY_ROZPRACOVANOST:
                bedna.stav_bedny = StavBednyChoice.ZAKALENO
                bedna.save()

    modeladmin.message_user(request, f"Zakaleno: {queryset.count()} beden.", level=messages.SUCCESS)
    logger.info(f"Uživatel {request.user} změnil stav na ZAKALENO u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu bedny na ZKONTROLOVÁNO", permissions=('change',))
def oznacit_zkontrolovano_action(modeladmin, request, queryset):
    """
    Změní stav vybraných beden na ZKONTROLOVANO.
    Může měnit všechny bedny ve stavu ROZPRACOVANOST (NAVEZENO, DO_ZPRACOVANI, ZAKALENO, ZKONTROLOVANO) na ZKONTROLOVANO.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu bedny na ZKONTROLOVÁNO"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu ROZPRACOVANOST
    if queryset.exclude(stav_bedny__in=STAV_BEDNY_ROZPRACOVANOST).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na ZKONTROLOVANO, ale některé bedny nejsou ve stavu ROZPRACOVANOST.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu ROZPRACOVANOST.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.stav_bedny in STAV_BEDNY_ROZPRACOVANOST:
                bedna.stav_bedny = StavBednyChoice.ZKONTROLOVANO
                bedna.save()

    modeladmin.message_user(request, f"Zkontrolováno: {queryset.count()} beden.", level=messages.SUCCESS)
    logger.info(f"Uživatel {request.user} změnil stav na ZKONTROLOVANO u {queryset.count()} beden.")
    return None

@admin.action(description="Uvolnění pozastavených beden", permissions=('change_pozastavena_bedna',))
def uvolnit_pozastavene_bedny_action(modeladmin, request, queryset):
    """
    Uvolní pozastavené bedny (parametr bedna.pozastaveno z True na False).
    """    
    # kontrola, zda nejsou žádné bedny expedované (stav EXPEDOVANO)
    if queryset.filter(stav_bedny=StavBednyChoice.EXPEDOVANO).exists():
        logger.info(f"Uživatel {request.user} se pokusil uvolnit pozastavené bedny, ale některé jsou ve stavu EXPEDOVANO.")
        modeladmin.message_user(request, "Některé vybrané bedny jsou ve stavu EXPEDOVANO a nelze je uvolnit.", level=messages.ERROR)
        return None

    # kontrola, zda jsou všechny bedny v querysetu pozastavené
    if queryset.exclude(pozastaveno=True).exists():
        logger.info(f"Uživatel {request.user} se pokusil uvolnit pozastavené bedny, ale některé nejsou pozastavené.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou pozastavené.", level=messages.ERROR)
        return None
    
    with transaction.atomic():
        for bedna in queryset:
            if bedna.pozastaveno and bedna.stav_bedny != StavBednyChoice.EXPEDOVANO:
                bedna.pozastaveno = False
                bedna.save()

    modeladmin.message_user(request, f"Uvolněno: {queryset.count()} beden.", level=messages.SUCCESS)
    logger.info(f"Uživatel {request.user} uvolnil {queryset.count()} beden.")
    return None


@admin.action(description="Označení nefakturovat", permissions=('change',))
def oznacit_nefakturovat_action(modeladmin, request, queryset):
    """
    Nastaví příznak fakturovat=False u vybraných beden.
    """
    # kontrola, zda nejsou žádné bedny expedované (stav EXPEDOVANO)
    if queryset.filter(stav_bedny=StavBednyChoice.EXPEDOVANO).exists():
        logger.info(f"Uživatel {request.user} se pokusil označit bedny jako nefakturovat, ale některé jsou ve stavu EXPEDOVANO.")
        modeladmin.message_user(request, "Některé vybrané bedny jsou ve stavu EXPEDOVANO a nelze je označit jako nefakturovat.", level=messages.ERROR)
        return None

    # kontrola, zda jsou všechny bedny v querysetu aktuálně fakturovat=True
    if queryset.exclude(fakturovat=True).exists():
        logger.info(f"Uživatel {request.user} se pokusil označit bedny jako nefakturovat, ale některé už mají příznak nefakturovat.")
        modeladmin.message_user(request, "Některé vybrané bedny už jsou označené jako nefakturovat.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.stav_bedny != StavBednyChoice.EXPEDOVANO and bedna.fakturovat:
                bedna.fakturovat = False
                bedna.save(update_fields=['fakturovat'])

    modeladmin.message_user(request, f"Označeno nefakturovat: {queryset.count()} beden.", level=messages.SUCCESS)
    logger.info(f"Uživatel {request.user} označil jako nefakturovat {queryset.count()} beden.")
    return None


@admin.action(description="Změna stavu bedny na K_EXPEDICI", permissions=('change',))
def oznacit_k_expedici_action(modeladmin, request, queryset):
    """
    Změní stav vybraných beden ze stavu ROZPRACOVANOST (NAVEZENO, DO_ZPRACOVANI, ZAKALENO nebo ZKONTROLOVANO) na K_EXPEDICI.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu bedny na K EXPEDICI"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu ROZPRACOVANOST (NAVEZENO, DO_ZPRACOVANI, ZAKALENO, ZKONTROLOVANO)
    if queryset.exclude(stav_bedny__in=STAV_BEDNY_ROZPRACOVANOST).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na K_EXPEDICI, ale některé bedny nejsou ve stavu ROZPRACOVANOST.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu ROZPRACOVANOST.", level=messages.ERROR)
        return None
    
    # kontrola, zda všechny bedny splňují podmínky pro přechod do stavu K_EXPEDICI:

    # rovnání musí být buď Rovná nebo Vyrovnaná
    if queryset.exclude(rovnat__in=[RovnaniChoice.ROVNA, RovnaniChoice.VYROVNANA]).exists():
        logger.warning(f'Uživatel {request.user} se pokusil změnit stav na K_EXPEDICI s neplatným stavem rovnání.')
        modeladmin.message_user(request, _("Pro změnu stavu bedny na 'K expedici' musí být rovnání buď Rovná nebo Vyrovnaná " \
        "a tryskání buď Čistá nebo Otryskaná."), level=messages.ERROR)
        return None
        
    # tryskat musí být buď Čistá nebo Otryskaná
    if queryset.exclude(tryskat__in=[TryskaniChoice.CISTA, TryskaniChoice.OTRYSKANA]).exists():
        logger.warning(f'Uživatel {request.user} se pokusil změnit stav na K_EXPEDICI s neplatným stavem tryskání.')
        modeladmin.message_user(request, _("Pro změnu stavu bedny na 'K expedici' musí být rovnání buď Rovná nebo Vyrovnaná " \
        "a tryskání buď Čistá nebo Otryskaná."), level=messages.ERROR)
        return None

    # zinkovat musí být buď Nezinkovat nebo Uvolněno
    if queryset.exclude(zinkovat__in=[ZinkovaniChoice.NEZINKOVAT, ZinkovaniChoice.UVOLNENO]).exists():
        logger.warning(f'Uživatel {request.user} se pokusil změnit stav na K_EXPEDICI s neplatným stavem zinkování.')
        modeladmin.message_user(
            request,
            _("Pro změnu stavu bedny na 'K expedici' musí být zinkování buď Nezinkovat nebo Uvolněno."),
            level=messages.ERROR,
        )
        return None

    selected_ids = list(queryset.values_list('pk', flat=True))
    with transaction.atomic():
        locked_qs = Bedna.objects.select_for_update().filter(pk__in=selected_ids)

        if _abort_if_paused_bedny(modeladmin, request, locked_qs, "Změna stavu bedny na K EXPEDICI"):
            return None

        if locked_qs.exclude(stav_bedny__in=STAV_BEDNY_ROZPRACOVANOST).exists():
            logger.info(
                f"Uživatel {request.user} se pokusil změnit stav na K_EXPEDICI, ale některé bedny už nejsou ve stavu ROZPRACOVANOST."
            )
            modeladmin.message_user(request, "Některé vybrané bedny už nejsou ve stavu ROZPRACOVANOST.", level=messages.ERROR)
            return None

        if locked_qs.exclude(rovnat__in=[RovnaniChoice.ROVNA, RovnaniChoice.VYROVNANA]).exists():
            logger.warning(f'Uživatel {request.user} se pokusil změnit stav na K_EXPEDICI s neplatným stavem rovnání.')
            modeladmin.message_user(request, _("Pro změnu stavu bedny na 'K expedici' musí být rovnání buď Rovná nebo Vyrovnaná " \
            "a tryskání buď Čistá nebo Otryskaná."), level=messages.ERROR)
            return None

        if locked_qs.exclude(tryskat__in=[TryskaniChoice.CISTA, TryskaniChoice.OTRYSKANA]).exists():
            logger.warning(f'Uživatel {request.user} se pokusil změnit stav na K_EXPEDICI s neplatným stavem tryskání.')
            modeladmin.message_user(request, _("Pro změnu stavu bedny na 'K expedici' musí být rovnání buď Rovná nebo Vyrovnaná " \
            "a tryskání buď Čistá nebo Otryskaná."), level=messages.ERROR)
            return None

        if locked_qs.exclude(zinkovat__in=[ZinkovaniChoice.NEZINKOVAT, ZinkovaniChoice.UVOLNENO]).exists():
            logger.warning(f'Uživatel {request.user} se pokusil změnit stav na K_EXPEDICI s neplatným stavem zinkování.')
            modeladmin.message_user(
                request,
                _("Pro změnu stavu bedny na 'K expedici' musí být zinkování buď Nezinkovat nebo Uvolněno."),
                level=messages.ERROR,
            )
            return None

        zmeneno = locked_qs.update(stav_bedny=StavBednyChoice.K_EXPEDICI)

    modeladmin.message_user(request, f"Změněno na K EXPEDICI: {zmeneno} beden.", level=messages.SUCCESS)
    logger.info(f"Uživatel {request.user} změnil stav na K_EXPEDICI u {zmeneno} beden.")
    return None


@admin.action(description="Expedice vybraných beden", permissions=('change',))
def expedice_beden_action(modeladmin, request, queryset):
    """
    Expeduje vybrané bedny (mohou být z více zakázek i zákazníků) do nových kamionů výdej.

    Průběh:
    1. Kontrola querysetu a beden.
    2. Získání všech zákazníků, kteří mají kamiony spojené s vybranými bednami.
    3. Vytvoří se formulář pro výběr odběratele.
    4. Pro každého zákazníka v querysetu:
        - Vytvoří se nový objekt `Kamion`:
            - `prijem_vydej=KamionChoice.VYDEJ`
            - `datum` dnešní datum
            - `zakaznik` nastavený na aktuálního zákazníka
            - `odberatel` zvolený odběratel z formuláře
    5. Pro každou bednu daného zákazníka:
        - Zkontroluje se, zda má stav `K_EXPEDICI`.
        - Pokud ano, vyexpeduje bednu.
    6. Po úspěšném průběhu odešle `messages.success`. V případě nesplnění podmínek vrátí chybu pomocí `messages.error` a akce se přeruší.
    """
    if not queryset.exists():
        return None

    if 'apply' in request.POST:
        form = OdberatelForm(request.POST)
        if form.is_valid():
            odberatel = form.cleaned_data['odberatel']
            try:
                selected_ids = list(queryset.values_list('pk', flat=True))
                with transaction.atomic():
                    zakazky_ids = list(
                        {
                            pk
                            for pk in Zakazka.objects.filter(bedny__pk__in=selected_ids).values_list('pk', flat=True)
                            if pk is not None
                        }
                    )
                    locked_zakazky_qs = (
                        Zakazka.objects
                        .select_for_update()
                        .filter(pk__in=zakazky_ids)
                        .order_by('pk')
                    )
                    locked_qs = (
                        Bedna.objects
                        .select_for_update()
                        .filter(pk__in=selected_ids)
                        .order_by('pk')
                    )

                    if not locked_qs.exists():
                        modeladmin.message_user(request, "Nebyla vybrána žádná bedna.", level=messages.ERROR)
                        return None

                    if _abort_if_paused_bedny(modeladmin, request, locked_qs, "Expedice beden"):
                        return None

                    if locked_qs.exclude(stav_bedny=StavBednyChoice.K_EXPEDICI).exists():
                        modeladmin.message_user(
                            request,
                            "Všechny vybrané bedny musí být ve stavu K_EXPEDICI.",
                            level=messages.ERROR,
                        )
                        return None

                    locked_zakaznici_ids = list(
                        {pk for pk in locked_qs.values_list('zakazka__kamion_prijem__zakaznik', flat=True) if pk is not None}
                    )
                    locked_zakaznici = Zakaznik.objects.filter(id__in=locked_zakaznici_ids)
                    locked_zakaznici_pouze_komplet = [z for z in locked_zakaznici if z.pouze_komplet]

                    for zakaznik in locked_zakaznici_pouze_komplet:
                        zakazky_ids = list(
                            {
                                pk
                                for pk in locked_qs.filter(zakazka__kamion_prijem__zakaznik=zakaznik)
                                .values_list('zakazka_id', flat=True)
                                if pk is not None
                            }
                        )
                        zakazky_dotcene = Zakazka.objects.filter(id__in=zakazky_ids).select_related('kamion_prijem')
                        for zakazka in zakazky_dotcene:
                            if not zakazka.kamion_prijem:
                                modeladmin.message_user(
                                    request,
                                    f"Zakázka {zakazka} nemá kamion příjem – nelze ověřit příznak 'Pouze kompletní zakázky'.",
                                    level=messages.ERROR,
                                )
                                return None

                            vsechny_bedny = zakazka.bedny.all()
                            vse_k_expedici = vsechny_bedny.filter(stav_bedny=StavBednyChoice.K_EXPEDICI)
                            vybrane_count = locked_qs.filter(zakazka=zakazka).count()

                            if not vse_k_expedici.exists() or vse_k_expedici.count() != vsechny_bedny.count():
                                modeladmin.message_user(
                                    request,
                                    f"Zakázka {zakazka} pro zákazníka s příznakem 'Pouze kompletní zakázky' musí mít všechny bedny ve stavu K_EXPEDICI.",
                                    level=messages.ERROR,
                                )
                                return None

                            if vybrane_count != vse_k_expedici.count():
                                modeladmin.message_user(
                                    request,
                                    f"Zakázka {zakazka} pro zákazníka s příznakem 'Pouze kompletní zakázky' musí být expedována celá (vyberte všechny bedny ze zakázky).",
                                    level=messages.ERROR,
                                )
                                return None

                    if not validate_bedny_pripraveny_k_expedici(modeladmin, request, locked_qs):
                        return None

                    result = expedice_beden_do_noveho_kamionu(
                        bedny_qs=locked_qs,
                        zakaznici=locked_zakaznici,
                        odberatel=odberatel,
                        actor=request.user,
                        today=datetime.date.today(),
                    )
            except ServiceValidationError as exc:
                modeladmin.message_user(request, str(exc), level=messages.ERROR)
                return None
            except Exception as e:
                logger.error(f"Nastala chyba {e} při vytváření kamionu pro expedici beden.")
                modeladmin.message_user(request, f"Nastala chyba {e} při vytváření kamionu pro expedici beden.", level=messages.ERROR)
                return None

            logger.info(
                f"Uživatel {request.user} úspěšně expedoval bedny do nových kamionů: {', '.join(result.created_kamiony)}."
            )
            modeladmin.message_user(
                request,
                f"Bedny byly úspěšně expedovány, vytvořené kamiony výdeje {', '.join(result.created_kamiony)}.",
                level=messages.SUCCESS,
            )
            return None
    else:
        logger.info(f"Uživatel {request.user} expeduje bedny do nového kamionu.")
        form = OdberatelForm()

    return render(request, 'admin/expedice_kamionu_form.html', {
        'bedny': queryset,
        'form': form,
        'title': "Expedice beden do nového kamionu",
        'action': "expedice_beden_action",
    })

@admin.action(description="Expedice vybraných beden do existujícího kamiónu", permissions=('change',))
def expedice_beden_kamion_action(modeladmin, request, queryset):
    """
    Expeduje vybrané bedny do existujícího kamionu zákazníka.

    Průběh:
    1. Kontrola querysetu a beden.
    2. Získá se zákazník, ke kterému patří všechny vybrané bedny. Pokud bedny patří více zákazníkům, akce se přeruší s chybou.
    3. Vytvoří se formulář pro výběr kamionu daného zákazníka.
    4. Po odeslání formuláře:
        - Získá se zvolený kamion.
        - Pro každou bednu daného zákazníka:
            - Zkontroluje se, zda má stav `K_EXPEDICI`.
            - Pokud ano, vyexpeduje bednu.
    5. Po úspěšném průběhu odešle `messages.success`. V případě nesplnění podmínek vrátí chybu pomocí `messages.error` a akce se přeruší.
    """
    if not queryset.exists():
        return None

    zakaznici_ids = list({pk for pk in queryset.values_list('zakazka__kamion_prijem__zakaznik', flat=True) if pk is not None})
    if len(zakaznici_ids) != 1:
        modeladmin.message_user(request, f"Vybrané bedny musí patřit jednomu zákazníkovi.", level=messages.ERROR)
        return None

    zakaznik_id = zakaznici_ids[0]

    if 'apply' in request.POST:
        form = VyberKamionVydejForm(request.POST, zakaznik=zakaznik_id)
        if form.is_valid():
            kamion = form.cleaned_data['kamion']
            selected_ids = list(queryset.values_list('pk', flat=True))
            with transaction.atomic():
                zakazky_ids = list(
                    {
                        pk
                        for pk in Zakazka.objects.filter(bedny__pk__in=selected_ids).values_list('pk', flat=True)
                        if pk is not None
                    }
                )
                locked_zakazky_qs = (
                    Zakazka.objects
                    .select_for_update()
                    .filter(pk__in=zakazky_ids)
                    .order_by('pk')
                )
                locked_qs = (
                    Bedna.objects
                    .select_for_update()
                    .filter(pk__in=selected_ids)
                    .order_by('pk')
                )

                if not locked_qs.exists():
                    modeladmin.message_user(request, "Nebyla vybrána žádná bedna.", level=messages.ERROR)
                    return None

                if _abort_if_paused_bedny(modeladmin, request, locked_qs, "Expedice beden do existujícího kamionu"):
                    return None

                if locked_qs.exclude(stav_bedny=StavBednyChoice.K_EXPEDICI).exists():
                    modeladmin.message_user(request, "Všechny vybrané bedny musí být ve stavu K_EXPEDICI.", level=messages.ERROR)
                    return None

                locked_zakaznici_ids = list(
                    {pk for pk in locked_qs.values_list('zakazka__kamion_prijem__zakaznik', flat=True) if pk is not None}
                )
                if len(locked_zakaznici_ids) != 1:
                    modeladmin.message_user(request, "Vybrané bedny musí patřit jednomu zákazníkovi.", level=messages.ERROR)
                    return None

                locked_zakaznik = Zakaznik.objects.get(id=locked_zakaznici_ids[0])
                if locked_zakaznik.pouze_komplet:
                    zakazky_ids = list(
                        {
                            pk
                            for pk in locked_qs.filter(zakazka__kamion_prijem__zakaznik=locked_zakaznik)
                            .values_list('zakazka_id', flat=True)
                            if pk is not None
                        }
                    )
                    zakazky_dotcene = Zakazka.objects.filter(id__in=zakazky_ids).select_related('kamion_prijem')
                    for zakazka in zakazky_dotcene:
                        if not zakazka.kamion_prijem:
                            modeladmin.message_user(
                                request,
                                f"Zakázka {zakazka} nemá kamion příjem – nelze ověřit příznak 'Pouze kompletní zakázky'.",
                                level=messages.ERROR,
                            )
                            return None

                        vsechny_bedny = zakazka.bedny.all()
                        vse_k_expedici = vsechny_bedny.filter(stav_bedny=StavBednyChoice.K_EXPEDICI)
                        vybrane_count = locked_qs.filter(zakazka=zakazka).count()

                        if not vse_k_expedici.exists() or vse_k_expedici.count() != vsechny_bedny.count():
                            modeladmin.message_user(
                                request,
                                f"Zakázka {zakazka} pro zákazníka s příznakem 'Pouze kompletní zakázky' musí mít všechny bedny ve stavu K_EXPEDICI.",
                                level=messages.ERROR,
                            )
                            return None

                        if vybrane_count != vse_k_expedici.count():
                            modeladmin.message_user(
                                request,
                                f"Zakázka {zakazka} pro zákazníka s příznakem 'Pouze kompletní zakázky' musí být expedována celá (vyberte všechny bedny ze zakázky).",
                                level=messages.ERROR,
                            )
                            return None

                if not validate_bedny_pripraveny_k_expedici(modeladmin, request, locked_qs):
                    return None

                if not utilita_expedice_beden(modeladmin, request, queryset, kamion):
                    return None
            logger.info(
                f"Uživatel {request.user} úspěšně expedoval bedny do kamionu {kamion.cislo_dl} zákazníka {kamion.zakaznik.nazev}."
            )
            modeladmin.message_user(
                request,
                f"Bedny byly úspěšně expedovány do kamionu {kamion} zákazníka {kamion.zakaznik.nazev}.",
                level=messages.SUCCESS,
            )
            return None
    else:
        logger.info(
            f"Uživatel {request.user} expeduje bedny do existujícího kamionu zákazníka {Zakaznik.objects.get(id=zakaznik_id).nazev}."
        )
        form = VyberKamionVydejForm(zakaznik=zakaznik_id)

    return render(request, 'admin/expedice_zakazek_beden_form.html', {
        'bedny': queryset,
        'form': form,
        'title': "Expedice beden do existujícího kamionu",
        'action': "expedice_beden_kamion_action",
    })

@admin.action(description="Změna stavu rovnání na ROVNÁ", permissions=('change',))
def oznacit_rovna_action(modeladmin, request, queryset):
    """
    Změní stav rovnání vybraných beden z NEZADANO na ROVNA.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu rovnání na ROVNÁ"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu NEZADANO
    if queryset.exclude(rovnat=RovnaniChoice.NEZADANO).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na ROVNA, ale některé bedny nejsou ve stavu NEZADANO.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu NEZADANO.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.rovnat == RovnaniChoice.NEZADANO:
                bedna.rovnat = RovnaniChoice.ROVNA
                bedna.save()

    modeladmin.message_user(request, f"Změněno: {queryset.count()} beden.", level=messages.SUCCESS)
    logger.info(f"Uživatel {request.user} změnil stav rovnání na ROVNA u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu rovnání na KŘIVÁ", permissions=('change',))
def oznacit_kriva_action(modeladmin, request, queryset):
    """
    Změní stav rovnání vybraných beden z NEZADANO na KRIVA.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu rovnání na KŘIVÁ"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu NEZADANO
    if queryset.exclude(rovnat=RovnaniChoice.NEZADANO).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na KRIVA, ale některé bedny nejsou ve stavu NEZADANO.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu NEZADANO.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.rovnat == RovnaniChoice.NEZADANO:
                bedna.rovnat = RovnaniChoice.KRIVA
                bedna.save()

    modeladmin.message_user(request, f"Změněno: {queryset.count()} beden.", level=messages.SUCCESS)
    logger.info(f"Uživatel {request.user} změnil stav rovnání na KRIVA u {queryset.count()} beden.")
    return None

@admin.action(description="Přesun beden na rovnání (ROVNÁ SE)", permissions=('change',))
def oznacit_rovna_se_action(modeladmin, request, queryset):
    """
    Změní stav rovnání vybraných beden z KRIVA a KOULENI na ROVNA_SE.
    Vytiskne seznam beden k rovnání.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu rovnání na ROVNÁ SE"):
        return None

    bedny = list(queryset.select_related("zakazka__kamion_prijem__zakaznik"))
    if not bedny:
        messages.error(request, "Nebyla vybrána žádná bedna.")
        logger.warning("Akce 'oznacit_rovna_se' byla spuštěna bez vybraných beden.")
        return None

    if any(bedna.rovnat not in [RovnaniChoice.KRIVA, RovnaniChoice.KOULENI] for bedna in bedny):
        logger.info(
            f"Uživatel {request.user} se pokusil změnit stav na ROVNA SE, ale alespoň jedna bedna není ve stavu KRIVA nebo KOULENI."
        )
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu KRIVA nebo KOULENI.", level=messages.ERROR)
        return None

    try:
        with transaction.atomic():
            for bedna in bedny:
                bedna.rovnat = RovnaniChoice.ROVNA_SE
                bedna.save()
        logger.info(
            f"Uživatel {request.user} změnil stav rovnání na ROVNA SE u {len(bedny)} beden."
        )
        modeladmin.message_user(request, f"Změněno: {len(bedny)} beden.", level=messages.SUCCESS)

    except Exception as e:
        logger.error(f"Chyba při změně stavu rovnání na ROVNA SE: {e}")
        modeladmin.message_user(request, "Došlo k chybě při změně stavu rovnání.", level=messages.ERROR)
        return None

    generated_at = timezone.now()
    user_last_name = ""
    if request.user.is_authenticated:
        user_last_name = (
            request.user.last_name
            or request.user.get_full_name()
            or request.user.get_username()
        )

    total_weight = sum(
        (bedna.hmotnost if bedna.hmotnost is not None else Decimal("0"))
        for bedna in bedny
    )
    total_count = len(bedny)

    context = {
        "bedny": bedny,
        "generated_at": generated_at,
        "user_last_name": user_last_name,
        "total_weight": total_weight,
        "total_count": total_count,
    }

    html_path = "orders/seznam_beden_k_rovnani.html"
    html_string = render_to_string(html_path, context)

    stylesheets = []
    css_path = finders.find('orders/css/pdf_shared.css')
    if css_path:
        stylesheets.append(CSS(filename=css_path))
    else:
        logger.warning("Nepodařilo se najít CSS 'orders/css/pdf_shared.css' pro tisk seznamu beden k rovnání.")

    base_url = request.build_absolute_uri('/')
    pdf_file = HTML(string=html_string, base_url=base_url).write_pdf(stylesheets=stylesheets)

    filename = "seznam_beden_k_rovnani.pdf"
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response['Content-Disposition'] = f'inline; filename={filename}'
    logger.info(
        f"Uživatel {request.user} tiskne seznam beden k rovnání ({total_count} ks)."
    )
    return response


@admin.action(description="Přesun beden na KOULENÍ", permissions=('change',))
def oznacit_kouleni_action(modeladmin, request, queryset):
    """
    Změní stav rovnání vybraných beden z KRIVA na KOULENI.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Přesun beden na KOULENÍ"):
        return None

    if queryset.exclude(rovnat=RovnaniChoice.KRIVA).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na KOULENI, ale některé bedny nejsou ve stavu KRIVA.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu KRIVA.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.rovnat == RovnaniChoice.KRIVA:
                bedna.rovnat = RovnaniChoice.KOULENI
                bedna.save()

    modeladmin.message_user(request, f"Změněno: {queryset.count()} beden.", level=messages.SUCCESS)
    logger.info(f"Uživatel {request.user} změnil stav rovnání na KOULENI u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu rovnání na VYROVNANÁ", permissions=('change',))
def oznacit_vyrovnana_action(modeladmin, request, queryset):
    """
    Změní stav rovnání vybraných beden z KRIVA, KOULENI a ROVNA_SE na VYROVNANA.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu rovnání na VYROVNANÁ"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu KRIVA, KOULENI nebo ROVNA_SE
    if queryset.exclude(rovnat__in=[RovnaniChoice.KRIVA, RovnaniChoice.KOULENI, RovnaniChoice.ROVNA_SE]).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav na VYROVNANA, ale některé bedny nejsou ve stavu KRIVA, KOULENI nebo ROVNA_SE.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu KRIVA, KOULENI nebo ROVNÁ SE.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.rovnat in [RovnaniChoice.KRIVA, RovnaniChoice.KOULENI, RovnaniChoice.ROVNA_SE]:
                bedna.rovnat = RovnaniChoice.VYROVNANA
                bedna.save()

    modeladmin.message_user(request, f"Změněno: {queryset.count()} beden.", level=messages.SUCCESS)
    logger.info(f"Uživatel {request.user} změnil stav rovnání na VYROVNANÁ u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu tryskání na ČISTÁ", permissions=('change',))
def oznacit_cista_action(modeladmin, request, queryset):
    """
    Změní stav tryskání vybraných beden z NEZADANO na CISTA.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu tryskání na ČISTÁ"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu NEZADANO
    if queryset.exclude(tryskat=TryskaniChoice.NEZADANO).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav tryskání na CISTA, ale některé bedny nejsou ve stavu NEZADANO.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu NEZADANO.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.tryskat == TryskaniChoice.NEZADANO:
                bedna.tryskat = TryskaniChoice.CISTA
                bedna.save()

    modeladmin.message_user(request, f"Změněno: {queryset.count()} beden.", level=messages.SUCCESS)
    logger.info(f"Uživatel {request.user} změnil stav tryskání na CISTA u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu tryskání na ŠPINAVÁ", permissions=('change',))
def oznacit_spinava_action(modeladmin, request, queryset):
    """
    Změní stav tryskání vybraných beden z NEZADANO na SPINAVA.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu tryskání na ŠPINAVÁ"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu NEZADANO
    if queryset.exclude(tryskat=TryskaniChoice.NEZADANO).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav tryskání na SPINAVA, ale některé bedny nejsou ve stavu NEZADANO.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu NEZADANO.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.tryskat == TryskaniChoice.NEZADANO:
                bedna.tryskat = TryskaniChoice.SPINAVA
                bedna.save()

    modeladmin.message_user(request, f"Změněno: {queryset.count()} beden.", level=messages.SUCCESS)
    logger.info(f"Uživatel {request.user} změnil stav tryskání na SPINAVA u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu tryskání na OTRYSKANÁ", permissions=('change',))
def oznacit_otryskana_action(modeladmin, request, queryset):
    """
    Změní stav tryskání vybraných beden ze SPINAVA na OTRYSKANA.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu tryskání na OTRYSKANÁ"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu SPINAVA
    if queryset.exclude(tryskat=TryskaniChoice.SPINAVA).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav tryskání na OTRYSKANÁ, ale některé bedny nejsou ve stavu SPINAVA.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu SPINAVA.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.tryskat == TryskaniChoice.SPINAVA:
                bedna.tryskat = TryskaniChoice.OTRYSKANA
                bedna.save()

    modeladmin.message_user(request, f"Změněno: {queryset.count()} beden.", level=messages.SUCCESS)
    logger.info(f"Uživatel {request.user} změnil stav tryskání na OTRYSKANA u {queryset.count()} beden.")
    return None


@admin.action(description="Označit V ZINKOVNĚ a vyexportovat DL", permissions=('change',))
def odeslat_na_zinkovani_action(modeladmin, request, queryset):
    """
    Pro bedny ve stavu ZKONTROLOVANO a se zinkováním ZINKOVAT:
    - přepne zinkovat na V ZINKOVNĚ
    - vrátí dočasný CSV export pro externí zinkovnu
    """
    if not queryset.exists():
        return None

    if _abort_if_paused_bedny(modeladmin, request, queryset, "Označit V ZINKOVNĚ a vyexportovat DL"):
        return None

    if queryset.exclude(stav_bedny=StavBednyChoice.ZKONTROLOVANO).exists():
        modeladmin.message_user(request, "Všechny vybrané bedny musí být ve stavu ZKONTROLOVANO.", level=messages.ERROR)
        return None

    if queryset.exclude(zinkovat=ZinkovaniChoice.ZINKOVAT).exists():
        modeladmin.message_user(request, "Všechny vybrané bedny musí mít zinkování ZINKOVAT.", level=messages.ERROR)
        return None

    export_ids = list(queryset.values_list('pk', flat=True))
    with transaction.atomic():
        queryset.update(zinkovat=ZinkovaniChoice.V_ZINKOVNE)

    # Použijeme čerstvý queryset podle primárních klíčů, aby se neztratil výběr,
    # pokud původní queryset měl filtr na zinkovat=ZINKOVAT a po update by byl prázdný.
    export_qs = Bedna.objects.filter(pk__in=export_ids).select_related('zakazka')

    logger.info(
        f"Uživatel {getattr(request, 'user', None)} označil {export_qs.count()} beden na zinkování a vyexportoval DL do CSV.",
    )
    return utilita_export_beden_zinkovani_csv(export_qs, filename_prefix="bedny_na_zinkovani", sort_like_dl=True)


@admin.action(description="Export beden se stavem V ZINKOVNĚ do DL", permissions=('change',))
def export_na_zinkovani_action(modeladmin, request, queryset):
    """
    Exportuje bedny ve stavu ZKONTROLOVANO a se zinkováním V ZINKOVNĚ pro externí zinkovnu.
    """
    if not queryset.exists():
        return None

    if _abort_if_paused_bedny(modeladmin, request, queryset, "Export beden se stavem V ZINKOVNĚ do DL"):
        return None

    if queryset.exclude(stav_bedny=StavBednyChoice.ZKONTROLOVANO).exists():
        modeladmin.message_user(request, "Všechny vybrané bedny musí být ve stavu ZKONTROLOVANO.", level=messages.ERROR)
        return None

    if queryset.exclude(zinkovat=ZinkovaniChoice.V_ZINKOVNE).exists():
        modeladmin.message_user(request, "Všechny vybrané bedny musí mít zinkování V ZINKOVNĚ.", level=messages.ERROR)
        return None

    logger.info(
        f"Uživatel {getattr(request, 'user', None)} vyexportoval {queryset.count()} beden se zinkováním V ZINKOVNĚ do DL.",
    )
    return utilita_export_beden_zinkovani_csv(
        queryset,
        filename_prefix="bedny_na_zinkovani",
        sort_like_dl=True,
    )

@admin.action(description="Změna stavu zinkování na ZINKOVAT", permissions=('change',))
def oznacit_k_zinkovani_action(modeladmin, request, queryset):
    """
    Změní stav zinkování vybraných beden z NEZADANO nebo z NEZINKOVAT na ZINKOVAT.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu zinkování na ZINKOVAT"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu NEZADANO nebo NEZINKOVAT
    if queryset.exclude(zinkovat__in=[ZinkovaniChoice.NEZADANO, ZinkovaniChoice.NEZINKOVAT]).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav zinkování na ZINKOVAT, ale některé bedny nejsou ve stavu NEZADANO nebo NEZINKOVAT.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu NEZADANO nebo NEZINKOVAT.", level=messages.ERROR)
        return None

    # kontrola, zda jsou všechny bedny mimo stav_bedny K_EXPEDICI a EXPEDOVANO
    if queryset.filter(stav_bedny__in=[StavBednyChoice.K_EXPEDICI, StavBednyChoice.EXPEDOVANO]).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav zinkování na ZINKOVAT, ale některé bedny jsou ve stavu K_EXPEDICI nebo EXPEDOVANO.")
        modeladmin.message_user(request, "Některé vybrané bedny jsou ve stavu K_EXPEDICI nebo EXPEDOVANO.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.zinkovat in [ZinkovaniChoice.NEZADANO, ZinkovaniChoice.NEZINKOVAT]:
                bedna.zinkovat = ZinkovaniChoice.ZINKOVAT
                bedna.save()

    modeladmin.message_user(request, f"Změněno: {queryset.count()} beden.", level=messages.SUCCESS)
    logger.info(f"Uživatel {request.user} změnil stav zinkování na ZINKOVAT u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu zinkování na POZINKOVÁNO", permissions=('change',))
def oznacit_po_zinkovani_action(modeladmin, request, queryset):
    """
    Změní stav zinkování vybraných beden z V ZINKOVNĚ na POZINKOVANO.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu zinkování na POZINKOVÁNO"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu V ZINKOVNĚ
    if queryset.exclude(zinkovat=ZinkovaniChoice.V_ZINKOVNE).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav zinkování na POZINKOVANO, ale některé bedny nejsou ve stavu V ZINKOVNĚ.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu V ZINKOVNĚ.", level=messages.ERROR)
        return None
    
    # kontrola, zda jsou všechny bedny mimo stav_bedny K_EXPEDICI a EXPEDOVANO
    if queryset.filter(stav_bedny__in=[StavBednyChoice.K_EXPEDICI, StavBednyChoice.EXPEDOVANO]).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav zinkování na POZINKOVANO, ale některé bedny jsou ve stavu K_EXPEDICI nebo EXPEDOVANO.")
        modeladmin.message_user(request, "Některé vybrané bedny jsou ve stavu K_EXPEDICI nebo EXPEDOVANO.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.zinkovat == ZinkovaniChoice.V_ZINKOVNE:
                bedna.zinkovat = ZinkovaniChoice.POZINKOVANO
                bedna.save()

    modeladmin.message_user(request, f"Změněno: {queryset.count()} beden.", level=messages.SUCCESS)
    logger.info(f"Uživatel {request.user} změnil stav zinkování na POZINKOVANO u {queryset.count()} beden.")
    return None

@admin.action(description="Změna stavu zinkování na UVOLNĚNO", permissions=('change',))
def oznacit_uvolneno_action(modeladmin, request, queryset):
    """
    Změní stav zinkování vybraných beden z V ZINKOVNĚ a POZINKOVANO na UVOLNENO.
    """
    if _abort_if_paused_bedny(modeladmin, request, queryset, "Změna stavu zinkování na UVOLNĚNO"):
        return None

    # kontrola, zda jsou všechny bedny v querysetu ve stavu V ZINKOVNĚ a POZINKOVANO
    if queryset.exclude(zinkovat__in=[ZinkovaniChoice.V_ZINKOVNE, ZinkovaniChoice.POZINKOVANO]).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav zinkování na UVOLNĚNO, ale některé bedny nejsou ve stavu V ZINKOVNĚ nebo POZINKOVANO.")
        modeladmin.message_user(request, "Některé vybrané bedny nejsou ve stavu V ZINKOVNĚ nebo POZINKOVANO.", level=messages.ERROR)
        return None

    # kontrola, zda jsou všechny bedny mimo stav_bedny K_EXPEDICI a EXPEDOVANO
    if queryset.filter(stav_bedny__in=[StavBednyChoice.K_EXPEDICI, StavBednyChoice.EXPEDOVANO]).exists():
        logger.info(f"Uživatel {request.user} se pokusil změnit stav zinkování na UVOLNĚNO, ale některé bedny jsou ve stavu K_EXPEDICI nebo EXPEDOVANO.")
        modeladmin.message_user(request, "Některé vybrané bedny jsou ve stavu K_EXPEDICI nebo EXPEDOVANO.", level=messages.ERROR)
        return None

    with transaction.atomic():
        for bedna in queryset:
            if bedna.zinkovat in [ZinkovaniChoice.V_ZINKOVNE, ZinkovaniChoice.POZINKOVANO]:
                bedna.zinkovat = ZinkovaniChoice.UVOLNENO
                bedna.save()

    modeladmin.message_user(request, f"Změněno: {queryset.count()} beden.", level=messages.SUCCESS)
    logger.info(f"Uživatel {request.user} změnil stav zinkování na UVOLNĚNO u {queryset.count()} beden.")
    return None


# Akce pro zakázky:

@admin.action(description="Přijmout vybrané zakázky na sklad", permissions=('change',))
def prijmout_zakazku_action(modeladmin, request, queryset):
    """
    Přijme vybrané zakázky na sklad.

    Pro každou zakázku provede:
    - Kontrolu, že obsahuje alespoň jednu bednu ve stavu NEPRIJATO.
    - V jedné transakci a pod řádkovým zámkem (select_for_update) předvaliduje přechod všech beden
      ze stavu NEPRIJATO do stavu PRIJATO pomocí full_clean.
    - Pokud validace projde, uloží změnu stavu všech těchto beden na PRIJATO.

    Jednotlivé zakázky se zpracují nezávisle; pokud u některé validace selže, přeskočí se a pokračuje se další.
    """
    if not queryset.exists():
        return None

    if _abort_if_zakazky_maji_pozastavene_bedny(modeladmin, request, queryset, "Přijmout vybrané zakázky na sklad"):
        return None
    
    prijato_count = 0
    preskoceno_count = 0

    for zakazka in queryset:
        # Kontrola: v zakázce musí být alespoň jedna bedna ve stavu NEPRIJATO
        if not Bedna.objects.filter(zakazka=zakazka, stav_bedny=StavBednyChoice.NEPRIJATO).exists():
            logger.info(
                f"Uživatel {request.user} se pokusil přijmout zakázku {zakazka}, ale nemá žádnou bednu ve stavu NEPRIJATO."
            )
            modeladmin.message_user(
                request,
                f"Zakázka {zakazka} neobsahuje žádné bedny ve stavu NEPRIJATO.",
                level=messages.ERROR,
            )
            preskoceno_count += 1
            continue

        try:
            with transaction.atomic():
                bedny_qs = Bedna.objects.select_for_update().filter(
                    zakazka=zakazka,
                    stav_bedny=StavBednyChoice.NEPRIJATO,
                )
                bedny = list(bedny_qs)

                # Předvalidace všech beden
                errors = []
                for bedna in bedny:
                    original_state = bedna.stav_bedny
                    bedna.stav_bedny = StavBednyChoice.PRIJATO
                    try:
                        bedna.full_clean()
                    except ValidationError as e:
                        errors.append((bedna, e))
                    finally:
                        bedna.stav_bedny = original_state

                if errors:
                    for bedna, e in errors:
                        # Použije se e.messages (seznam chybových zpráv), aby odpadl slovník s __all__a podobně
                        logger.info(
                            f"Uživatel {request.user} se pokusil přijmout zakázku {zakazka}, ale bedna {bedna} neprošla validací: {e.messages}."
                        )
                        modeladmin.message_user(
                            request,
                            f"Nelze přijmout zakázku {zakazka}, bedna {bedna} neprošla validací: {e.messages}",
                            level=messages.ERROR,
                        )
                    preskoceno_count += 1
                    continue

                # Uložení přechodu stavů
                for bedna in bedny:
                    bedna.stav_bedny = StavBednyChoice.PRIJATO
                    bedna.save()

            prijato_count += 1

        except Exception as e:
            logger.error(
                f"Nastala chyba {e} při přijímání zakázky {zakazka}, zakázka nebyla přijata."
            )
            modeladmin.message_user(
                request,
                f"Nastala chyba {e} při přijímání zakázky {zakazka}.",
                level=messages.ERROR,
            )

    if prijato_count:
        modeladmin.message_user(
            request,
            f"Přijato na sklad: {prijato_count} zakázek.",
            level=messages.SUCCESS,
        )
        
    if preskoceno_count:
        modeladmin.message_user(
            request,
            f"Přeskočeno: {preskoceno_count} zakázek.",
            level=messages.WARNING,
        )

    return None

@admin.action(description="Expedice vybraných zakázek", permissions=('change',))
def expedice_zakazek_action(modeladmin, request, queryset):
    """
    Expeduje vybrané zakázky a jejich bedny.

    Průběh:
    1. Kontrola querysetu a zakázek.     
    2. Získání všech zákazníků, kteří mají kamiony spojené s vybranými zakázkami.
    3. Vytvoří se formulář pro výběr odběratele.  
    4. Pro každého zákazníka v querysetu:
        - Vytvoří se nový objekt `Kamion`:
            - `prijem_vydej=KamionChoice.VYDEJ`
            - `datum` dnešní datum
            - `zakaznik` nastavený na aktuálního zákazníka
            - `odberatel` zvolený odběratel z formuláře
    5. Pro každou zakázku daného zákazníka:
        - Zkontroluje se, zda všechny bedny v zakázce mají stav `K_EXPEDICI`.
        - Pokud ano, vyexpeduje celou zakázku.
        - Pro zákazníka s příznakem pouze_komplet mohou být expedovány pouze kompletní zakázky, které mají všechny bedny ve stavu `K_EXPEDICI` - kontrola v utilitě.
        - Pokud ne, vyexpeduje bedny K_EXPEDICI a vytvoří novou zakázku se stejnými daty jako původní a převede do ní bedny, které nejsou ve stavu `K_EXPEDICI`.      
        - Pokud nemá žádné bedny ve stavu `K_EXPEDICI`, zakázka se přeskočí.      
    6. Po úspěšném průběhu odešle `modeladmin.message_user` s úrovní `messages.SUCCESS`. V případě nesplnění podmínek vrátí chybu pomocí `modeladmin.message_user` s úrovní `messages.ERROR` a akce se přeruší.
    """        
    if not queryset.exists():
        return None

    if _abort_if_zakazky_maji_pozastavene_bedny(modeladmin, request, queryset, "Expedice zakázek do nového kamionu"):
        return None

    if 'apply' in request.POST:
        form = OdberatelForm(request.POST)
        if form.is_valid():
            odberatel = form.cleaned_data['odberatel']

            try:
                selected_ids = list(queryset.values_list('pk', flat=True))
                with transaction.atomic():
                    locked_zakazky_qs = Zakazka.objects.select_for_update().filter(pk__in=selected_ids)

                    if not locked_zakazky_qs.exists():
                        modeladmin.message_user(request, "Nebyla vybrána žádná zakázka.", level=messages.ERROR)
                        return None

                    if _abort_if_zakazky_maji_pozastavene_bedny(
                        modeladmin, request, locked_zakazky_qs, "Expedice zakázek do nového kamionu"
                    ):
                        return None

                    if not utilita_kontrola_zakazek(modeladmin, request, locked_zakazky_qs):
                        return None

                    locked_bedny_ke_kontrole = Bedna.objects.filter(
                        zakazka__in=locked_zakazky_qs,
                        stav_bedny=StavBednyChoice.K_EXPEDICI,
                    )
                    if not validate_bedny_pripraveny_k_expedici(modeladmin, request, locked_bedny_ke_kontrole):
                        return None

                    locked_zakaznici_ids = list(
                        {
                            pk
                            for pk in locked_zakazky_qs.values_list('kamion_prijem__zakaznik', flat=True)
                            if pk is not None
                        }
                    )
                    locked_zakaznici = Zakaznik.objects.filter(id__in=locked_zakaznici_ids)

                    result = expedice_zakazek_do_noveho_kamionu(
                        zakazky_qs=locked_zakazky_qs,
                        zakaznici=locked_zakaznici,
                        odberatel=odberatel,
                        actor=request.user,
                        today=datetime.date.today(),
                    )
            except ServiceValidationError as exc:
                modeladmin.message_user(request, str(exc), level=messages.ERROR)
                return
            except Exception as e:
                logger.error(f"Nastala chyba {e} při vytváření kamionu pro zákazníka.")
                modeladmin.message_user(request, f"Nastala chyba {e} při vytváření kamionu pro zákazníka", level=messages.ERROR)
                return

            logger.info(f"Uživatel {request.user} úspěšně expedoval zakázky do nových kamionů: {', '.join(result.created_kamiony)}.")
            modeladmin.message_user(request, f"Zakázky byly úspěšně expedovány, vytvořené kamiony výdeje {', '.join(result.created_kamiony)}.", level=messages.SUCCESS)
            return
    else:
        logger.info(f"Uživatel {request.user} expeduje zakázky do nového kamionu.")
        form = OdberatelForm()

    return render(request, 'admin/expedice_kamionu_form.html', {
        'zakazky': queryset,
        'form': form,
        'title': "Expedice zakázek nového kamionu",
        'action': "expedice_zakazek_action",
    })

@admin.action(description="Expedice vybraných zakázek do existujícího kamiónu", permissions=('change',))
def expedice_zakazek_kamion_action(modeladmin, request, queryset):
    """
    Expeduje vybrané zakázky do existujícího kamionu zákazníka.
    Průběh:
    1. Kontrola querysetu a zakázek.     
    2. Získá se zákazník, ke kterému patří všechny vybrané zakázky. Pokud zakázky patří více zákazníkům, akce se přeruší s chybou.
    3. Vytvoří se formulář pro výběr kamionu daného zákazníka.  
    4. Po odeslání formuláře:
        - Získá se zvolený kamion.
        - Pro každou zakázku daného zákazníka:
            - Zkontroluje se, zda všechny bedny v zakázce mají stav `K_EXPEDICI`.
            - Pokud ano, vyexpeduje celou zakázku.
            - Pro zákazníka s příznakem pouze_komplet mohou být expedovány pouze kompletní zakázky, které mají všechny bedny ve stavu `K_EXPEDICI` - kontrola v utilitě.
            - Pokud ne, vyexpeduje bedny K_EXPEDICI a vytvoří novou zakázku se stejnými daty jako původní a převede do ní bedny, které nejsou ve stavu `K_EXPEDICI`.      
            - Pokud nemá žádné bedny ve stavu `K_EXPEDICI`, zakázka se přeskočí.      
    5. Po úspěšném průběhu odešle `modeladmin.message_user` s úrovní `messages.SUCCESS`. V případě nesplnění podmínek vrátí chybu pomocí `modeladmin.message_user` s úrovní `messages.ERROR` a akce se přeruší.
    """
    zakaznici = queryset.values_list('kamion_prijem__zakaznik', flat=True).distinct()
    if zakaznici.count() != 1:
        logger.error(f"Uživatel {request.user} se pokusil expedovat zakázky do existujícího kamionu, ale vybrané zakázky nepatří jednomu zákazníkovi.")
        modeladmin.message_user(request, "Všechny vybrané zakázky musí patřit jednomu zákazníkovi.", level=messages.ERROR)
        return

    if _abort_if_zakazky_maji_pozastavene_bedny(modeladmin, request, queryset, "Expedice zakázek do existujícího kamionu"):
        return None

    zakaznik_id = zakaznici[0]

    if 'apply' in request.POST:
        form = VyberKamionVydejForm(request.POST, zakaznik=zakaznik_id)
        if form.is_valid():
            kamion = form.cleaned_data['kamion']
            selected_ids = list(queryset.values_list('pk', flat=True))
            with transaction.atomic():
                locked_zakazky_qs = Zakazka.objects.select_for_update().filter(pk__in=selected_ids)

                if not locked_zakazky_qs.exists():
                    modeladmin.message_user(request, "Nebyla vybrána žádná zakázka.", level=messages.ERROR)
                    return None

                locked_zakaznici = {
                    pk for pk in locked_zakazky_qs.values_list('kamion_prijem__zakaznik', flat=True) if pk is not None
                }
                if len(locked_zakaznici) != 1:
                    modeladmin.message_user(request, "Všechny vybrané zakázky musí patřit jednomu zákazníkovi.", level=messages.ERROR)
                    return None

                if _abort_if_zakazky_maji_pozastavene_bedny(
                    modeladmin, request, locked_zakazky_qs, "Expedice zakázek do existujícího kamionu"
                ):
                    return None

                if not utilita_kontrola_zakazek(modeladmin, request, locked_zakazky_qs):
                    return None

                locked_bedny_ke_kontrole = Bedna.objects.filter(
                    zakazka__in=locked_zakazky_qs,
                    stav_bedny=StavBednyChoice.K_EXPEDICI,
                )
                if not validate_bedny_pripraveny_k_expedici(modeladmin, request, locked_bedny_ke_kontrole):
                    return None

                if not utilita_expedice_zakazek(modeladmin, request, queryset, kamion):
                    return None
            logger.info(f"Uživatel {request.user} úspěšně expedoval zakázky do kamionu {kamion.cislo_dl} zákazníka {kamion.zakaznik.nazev}.")
            modeladmin.message_user(request, f"Zakázky byly úspěšně expedovány do kamionu {kamion} zákazníka {kamion.zakaznik.nazev}.", level=messages.SUCCESS)
            return
    else:
        logger.info(f"Uživatel {request.user} expeduje zakázky do existujícího kamionu zákazníka {Zakaznik.objects.get(id=zakaznik_id).nazev}.")
        form = VyberKamionVydejForm(zakaznik=zakaznik_id)

    return render(request, 'admin/expedice_zakazek_beden_form.html', {
        'zakazky': queryset,
        'form': form,
        'title': "Expedice do existujícího kamionu",
        'action': "expedice_zakazek_kamion_action",
    })

@admin.action(description="Vytisknout karty beden z vybraných zakázek")
def tisk_karet_beden_zakazek_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartami beden ze zvolených zakázkách. Zakázky mohou být pouze od jednoho zákazníka.
    Zakázky musí obsahovat alespoň jednu bednu.
    Bedny musí mít zadanou hmotnost, zakázku a předpis.
    """
    if queryset.values_list('kamion_prijem__zakaznik', flat=True).distinct().count() != 1:
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty beden z více zákazníků.")
        modeladmin.message_user(request, "Zakázky musí být od jednoho zákazníka.", level=messages.ERROR)
        return None
    
    bedny = Bedna.objects.filter(zakazka__in=queryset)

    if not bedny.exists():
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty beden, ale v označených zakázkách nejsou žádné bedny.")
        modeladmin.message_user(request, "V označených zakázkách nejsou žádné bedny.", level=messages.ERROR)
        return None
    
    if _abort_if_bedna_has_not_hmotnost_zakazka_predpis(modeladmin, request, bedny, "Tisk karet beden z vybraných zakázek"):
        return None

    zakaznik_zkratka = queryset.first().kamion_prijem.zakaznik.zkratka
    if zakaznik_zkratka:
        try:
            template_paths, filename = resolve_customer_templates(
                zakaznik_zkratka=zakaznik_zkratka,
                mode="bedna",
            )
            html_path = template_paths[0]
        except ServiceValidationError as exc:
            modeladmin.message_user(request, str(exc), level=messages.ERROR)
            return None
        response = utilita_tisk_dokumentace(modeladmin, request, bedny, html_path, filename)
        logger.info(f"Uživatel {request.user} tiskne karty beden pro {bedny.count()} vybraných beden.")
        return response
    else:
        logger.error(f"Zakázka {queryset.first()} nemá přiřazeného zákazníka nebo zákazník nemá zkratku.")
        modeladmin.message_user(request, "Zakázka nemá přiřazeného zákazníka nebo zákazník nemá zkratku.", level=messages.ERROR)
        return None

@admin.action(description="Vytisknout KKK z vybraných zakázek")
def tisk_karet_kontroly_kvality_zakazek_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartami kontroly kvality ze zvolených zakázkách. Zakázky musí být od jednoho zákazníka.
    Vybrané zakázky musí obsahovat alespoň jednu bednu.
    Bedny musí mít zadanou hmotnost, zakázku a předpis.
    """
    if queryset.values_list('kamion_prijem__zakaznik', flat=True).distinct().count() != 1:
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty beden z více zákazníků.")
        modeladmin.message_user(request, "Zakázky musí být od jednoho zákazníka.", level=messages.ERROR)
        return None
    
    bedny = Bedna.objects.filter(zakazka__in=queryset)

    if not bedny.exists():
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty kontroly kvality, ale v označených zakázkách nejsou žádné bedny.")
        modeladmin.message_user(request, "V označených zakázkách nejsou žádné bedny.", level=messages.ERROR)
        return None

    if _abort_if_bedna_has_not_hmotnost_zakazka_predpis(modeladmin, request, bedny, "Tisk karet kontroly kvality z vybraných zakázek"):
        return None
    
    zakaznik_zkratka = queryset.first().kamion_prijem.zakaznik.zkratka
    if zakaznik_zkratka:
        try:
            template_paths, filename = resolve_customer_templates(
                zakaznik_zkratka=zakaznik_zkratka,
                mode="kkk",
            )
            html_path = template_paths[0]
        except ServiceValidationError as exc:
            modeladmin.message_user(request, str(exc), level=messages.ERROR)
            return None
        response = utilita_tisk_dokumentace(modeladmin, request, bedny, html_path, filename)
        logger.info(f"Uživatel {request.user} tiskne karty kontroly kvality pro {bedny.count()} vybraných beden.")
        return response
    else:
        logger.error(f"Zakázka {queryset.first()} nemá přiřazeného zákazníka nebo zákazník nemá zkratku.")
        modeladmin.message_user(request, "Zakázka nemá přiřazeného zákazníka nebo zákazník nemá zkratku.", level=messages.ERROR)
        return None

@admin.action(description="Vrácení vybraných zakázek z expedice", permissions=('change',))
def vratit_zakazky_z_expedice_action(modeladmin, request, queryset):
    """
    Vrátí vybrané zakázky z expedice a pokud jsou z oddělené zakázky a původní zakázka není ještě expedována, tak bedny
    z této zakázky vrátí zpět do původní zakázky.
    
    Průběh:
    1. Pro každou zakázku v querysetu se zkontroluje, zda je expedovana (expedovano=True) a zda jsou všechny bedny ve stavu EXPEDOVANO.
        pokud ne, zakázka se přeskočí a zobrazí se chybová zpráva pomocí `messages.error`.
    2. Zjistí se, zda má zakázka původní zakázku (fk puvodni_zakazka) - tedy zda byla zakázka oddělena od kořenové zakázky při expedici.
        a) Pokud nemá anebo pokud má, ale tato kořenová zakázka už byla expedována (puvodni_zakazka.expedovano=True),
        zakázka se obnoví do původního stavu před expedicí:
            - Nastaví se expedovano=False a kamion_vydej=None.
            - Všechny bedny v zakázce se převedou na stav K_EXPEDICI.
        b) Pokud má a tato kořenová zakázka ještě nebyla expedována (puvodni_zakazka.expedovano=False),
        bedny se zakázky vrátí zpět do původní zakázky a aktuální zakázka se smaže:
            - Všechny bedny v aktuální zakázce se převedou na stav K_EXPEDICI a přesunou se do původní zakázky.
            - Zkontroluje se, zda má aktuální zakázka nějaké bedny, pokud ne, pokračuje se dalším krokem.
            - Pokud má, zobrazí se chybová zpráva pomocí `messages.error`, že nelze smazat zakázku, protože obsahuje bedny.
            - Jinak se aktuální zakázka smaže.
    3. Po úspěšném průběhu odešle `messages.success`.
    """
    uspely = 0

    for zakazka in queryset:
        try:
            with transaction.atomic():
                locked_zakazka = (
                    Zakazka.objects
                    .select_for_update()
                    .get(pk=zakazka.pk)
                )

                if not locked_zakazka.expedovano:
                    logger.info(
                        f"Uživatel {request.user} se pokusil vrátit zakázku {locked_zakazka}, ale ta není vyexpedována."
                    )
                    modeladmin.message_user(
                        request,
                        f"Zakázka {locked_zakazka} není vyexpedována.",
                        level=messages.ERROR,
                    )
                    continue

                locked_bedny_qs = Bedna.objects.select_for_update().filter(zakazka=locked_zakazka)
                if locked_bedny_qs.exclude(stav_bedny=StavBednyChoice.EXPEDOVANO).exists():
                    logger.error(
                        f"Uživatel {request.user} se pokusil vrátit zakázku {locked_zakazka}, ale ne všechny bedny jsou ve stavu EXPEDOVANO."
                    )
                    modeladmin.message_user(
                        request,
                        f"Zakázku {locked_zakazka} nelze vrátit: některé bedny nejsou ve stavu EXPEDOVANO.",
                        level=messages.ERROR,
                    )
                    continue

                puvodni_zakazka = None
                if locked_zakazka.puvodni_zakazka_id:
                    puvodni_zakazka = (
                        Zakazka.objects
                        .select_for_update()
                        .filter(pk=locked_zakazka.puvodni_zakazka_id)
                        .first()
                    )

                # Varianta A: žádná původní zakázka, nebo byla už expedována – obnovíme aktuální zakázku
                if puvodni_zakazka is None or puvodni_zakazka.expedovano:
                    locked_zakazka.expedovano = False
                    locked_zakazka.kamion_vydej = None
                    locked_zakazka.save(update_fields=["expedovano", "kamion_vydej"])
                    locked_bedny_qs.update(stav_bedny=StavBednyChoice.K_EXPEDICI)
                    uspely += 1
                    logger.info(
                        f"Uživatel {request.user} úspěšně vrátil zakázku {locked_zakazka} z expedice do původního stavu."
                    )
                    continue

                # Varianta B: existuje původní zakázka, která ještě není expedována – přesuneme bedny zpět
                bedny = list(locked_bedny_qs)
                for bedna in bedny:
                    bedna.stav_bedny = StavBednyChoice.K_EXPEDICI
                    bedna.zakazka = puvodni_zakazka
                Bedna.objects.bulk_update(bedny, ["stav_bedny", "zakazka"])

                if Bedna.objects.filter(zakazka=locked_zakazka).exists():
                    logger.error(
                        f"Uživatel {request.user} nemůže smazat zakázku {locked_zakazka}, protože v ní stále jsou bedny."
                    )
                    modeladmin.message_user(
                        request,
                        f"Nelze smazat zakázku {locked_zakazka}, protože stále obsahuje bedny.",
                        level=messages.ERROR,
                    )
                    continue

                locked_zakazka.delete()
                uspely += 1
                logger.info(
                    f"Uživatel {request.user} vrátil bedny ze zakázky {locked_zakazka} do původní zakázky {puvodni_zakazka} a zakázku smazal."
                )
        except Exception as e:
            logger.error(
                f"Nastala chyba {e} při vracení zakázky {getattr(zakazka, 'pk', '?')} z expedice."
            )
            modeladmin.message_user(
                request,
                f"Zakázku {zakazka} se nepodařilo vrátit z expedice kvůli neočekávané chybě.",
                level=messages.ERROR,
            )
            continue

    if uspely:
        modeladmin.message_user(
            request,
            f"Úspěšně vráceno z expedice: {uspely} zakázek.",
            level=messages.SUCCESS,
        )

# Akce pro kamiony:

@admin.action(description="Importovat dodací list pro vybraný kamion příjem bez zakázek", permissions=('change',))
def import_kamionu_action(modeladmin, request, queryset):
    """
    Importuje dodací list pro vybraný kamion.
    Předpokládá, že je vybrán pouze jeden kamion a to kamion s příznakem příjem.
    Pokud je vybráno více kamionů, zobrazí se chybová zpráva.
    V tuto chvíli je import pouze pro zákazníka EUR a SPX.
    """
    # Pokud je vybráno více kamionů, zobrazí se chybová zpráva
    if queryset.count() != 1:
        logger.info(f"Uživatel {request.user} se pokusil importovat kamion, ale vybral více než jeden kamion.")
        modeladmin.message_user(request, "Vyber pouze jeden kamion.", level=messages.ERROR)
        return
    kamion = queryset.first()
    # Zkontroluje, zda je kamion s příznakem příjem
    if kamion.prijem_vydej != KamionChoice.PRIJEM:
        logger.info(f"Uživatel {request.user} se pokusil importovat kamion {kamion.cislo_dl}, ale není to kamion s příznakem příjem.")
        modeladmin.message_user(request, "Import je možný pouze pro kamiony příjem.", level=messages.ERROR)
        return
    # Zkontroluje, zda ke kamionu ještě nejsou přiřazeny žádné zakázky
    if kamion.zakazky_prijem.exists():
        logger.info(f"Uživatel {request.user} se pokusil importovat kamion {kamion.cislo_dl}, ale kamion již obsahuje zakázky.")
        modeladmin.message_user(request, "Kamion již obsahuje zakázky, nelze provést import.", level=messages.ERROR)
        return
    # Import pro zákazníky EUR a SPX, pro ostatní zákazníky zatím není import umožněn
    if kamion.zakaznik.zkratka in ["EUR", "SPX"]:
        logger.info(f"Uživatel {request.user} importuje kamion {kamion.cislo_dl} pro zákazníka {kamion.zakaznik.zkratka}.")
        return redirect(f'./import-zakazek/?kamion={kamion.pk}')
    else:
        # Pokud není pro zákazníka zatím import umožněn, zobrazí se chybová zpráva
        logger.info(f"Uživatel {request.user} se pokusil importovat kamion {kamion.cislo_dl}, ale pro zákazníka {kamion.zakaznik.zkratka} zatím není import umožněn.")
        modeladmin.message_user(request, f"Import není zatím umožněn pro zákazníka {kamion.zakaznik.zkratka}.", level=messages.ERROR)
        return
    
@admin.action(description="Přijmout kamion na sklad", permissions=('change',))
def prijmout_kamion_action(modeladmin, request, queryset):
    """
    Přijme vybraný kamion na sklad.
    Předpokládá, že je vybrán pouze jeden kamion a to kamion s příznakem příjem, který obsahuje aspoň 
    jednu bednu ve stavu bedny NEPRIJATO. Převede všechny bedny ze stavu NEPRIJATO do stavu PRIJATO.
    Pokud je vybráno více kamionů, zobrazí se chybová zpráva.
    """
    # Pokud je vybráno více kamionů, zobrazí se chybová zpráva
    if queryset.count() != 1:
        logger.info(f"Uživatel {request.user} se pokusil přijmout kamion, ale vybral více než jeden kamion.")
        modeladmin.message_user(request, "Vyber pouze jeden kamion.", level=messages.ERROR)
        return
    kamion = queryset.first()
    # Zkontroluje, zda je kamion s příznakem příjem
    if kamion.prijem_vydej != KamionChoice.PRIJEM:
        logger.info(f"Uživatel {request.user} se pokusil přijmout kamion {kamion.cislo_dl}, ale není to kamion s příznakem příjem.")
        modeladmin.message_user(request, "Přijmout kamion je možné pouze u kamionů příjem.", level=messages.ERROR)
        return

    if _abort_if_kamiony_maji_pozastavene_bedny(modeladmin, request, queryset, "Přijmout kamion na sklad"):
        return
    # Zkontroluje, zda kamion obsahuje aspoň jednu bednu ve stavu NEPRIJATO
    if not Bedna.objects.filter(zakazka__kamion_prijem=kamion, stav_bedny=StavBednyChoice.NEPRIJATO).exists():
        logger.info(f"Uživatel {request.user} se pokusil přijmout kamion {kamion.cislo_dl}, ale neobsahuje žádné bedny ve stavu NEPRIJATO.")
        modeladmin.message_user(request, "Kamion neobsahuje žádné bedny ve stavu NEPRIJATO.", level=messages.ERROR)
        return
    # Předvalidace a uložení v jedné transakci pod řádkovým zámkem
    with transaction.atomic():
        bedny_qs = Bedna.objects.select_for_update().filter(
            zakazka__kamion_prijem=kamion,
            stav_bedny=StavBednyChoice.NEPRIJATO,
        )
        bedny = list(bedny_qs)

        # Nejprve všechny zvalidovat pro přechod do PRIJATO
        errors = []
        for bedna in bedny:
            original_state = bedna.stav_bedny
            bedna.stav_bedny = StavBednyChoice.PRIJATO
            try:
                bedna.full_clean()
            except ValidationError as e:
                errors.append((bedna, e))
            finally:
                bedna.stav_bedny = original_state

        if errors:
            # Použije se e.messages (seznam chybových zpráv), aby odpadl slovník s __all__a podobně
            for bedna, e in errors:
                logger.info(
                    f"Uživatel {request.user} se pokusil přijmout kamion {kamion.cislo_dl}, ale bedna {bedna} neprošla validací: {e.messages}."
                )
                modeladmin.message_user(
                    request,
                    f"Nelze přijmout kamion, bedna {bedna} neprošla validací: {e.messages}",
                    level=messages.ERROR,
                )
            return

        # Vše OK – proveď přechod stavu a ulož všechny
        for bedna in bedny:
            try:
                bedna.stav_bedny = StavBednyChoice.PRIJATO
                bedna.save()
            except Exception as e:
                logger.error(
                    f"Nastala chyba {e} při přijímání bedny {bedna} z kamionu {kamion.cislo_dl}, kamion nebyl přijat."
                )
                modeladmin.message_user(
                    request,
                    f"Nastala chyba {e} při přijímání bedny {bedna} z kamionu {kamion.cislo_dl}.",
                    level=messages.ERROR,
                )
                return
            
    logger.info(f"Uživatel {request.user} přijal kamion {kamion} na sklad.")
    modeladmin.message_user(request, f"Kamion {kamion} byl přijat na sklad.", level=messages.SUCCESS)
    return

@admin.action(description="Vytisknout dodací list vybraného kamionu výdej")
def tisk_dodaciho_listu_kamionu_action(modeladmin, request, queryset):
    """
    Vytiskne dodací list pro vybraný kamion do PDF.
    Předpokládá, že je vybrán pouze jeden kamion a to kamion s příznakem výdej.
    Pokud je vybráno více kamionů, zobrazí se chybová zpráva.
    """
    # Pokud je vybráno více kamionů, zobrazí se chybová zpráva
    if queryset.count() != 1:
        logger.info(f"Uživatel {request.user} se pokusil tisknout dodací list, ale vybral více než jeden kamion.")
        modeladmin.message_user(request, "Vyberte pouze jeden kamion.", level=messages.ERROR)
        return
    kamion = queryset.first()
    # Zkontroluje, zda je kamion s příznakem výdej
    if kamion.prijem_vydej != KamionChoice.VYDEJ:
        logger.info(f"Uživatel {request.user} se pokusil tisknout dodací list kamionu {kamion.cislo_dl}, ale není to kamion s příznakem výdej.")
        modeladmin.message_user(request, "Tisk DL je možný pouze pro kamiony výdej.", level=messages.ERROR)
        return

    zakaznik_zkratka = kamion.zakaznik.zkratka
    if zakaznik_zkratka:
        logger.info(f"Uživatel {request.user} tiskne dodací list kamionu {kamion.cislo_dl} pro zákazníka {zakaznik_zkratka}.")
        return HttpResponseRedirect(reverse('dodaci_list_kamion_vydej_pdf', args=[kamion.pk]))
    logger.error(f"Kamion {kamion} nemá přiřazeného zákazníka nebo zákazník nemá zkratku.")
    modeladmin.message_user(request, "Kamion nemá přiřazeného zákazníka nebo zákazník nemá zkratku.", level=messages.ERROR)
    return None


@admin.action(description="Vytisknout certifikát 3.1 kamionu výdej")
def tisk_protokolu_kamionu_vydej_action(modeladmin, request, queryset):
    """
    Vytvoří jednoduchý PDF protokol pro kamion výdej s přehledem naměřených hodnot na zakázkách.
    """
    if queryset.count() != 1:
        logger.info(
            f"Uživatel {getattr(request, 'user', None)} se pokusil tisknout protokol kamionu výdej, ale vybral více než jednu položku."
        )
        modeladmin.message_user(request, "Vyberte pouze jeden kamion.", level=messages.ERROR)
        return None

    kamion = queryset.first()
    if kamion.prijem_vydej != KamionChoice.VYDEJ:
        logger.info(
            f"Uživatel {getattr(request, 'user', None)} se pokusil tisknout protokol pro kamion {kamion}, ale kamion není typu výdej.",
        )
        modeladmin.message_user(request, "Tisk protokolu je možný pouze pro kamiony výdej.", level=messages.ERROR)
        return None

    # Přesměrujeme na GET endpoint, aby stažení z vieweru fungovalo (admin akce je POST).
    url = reverse('protokol_kamion_vydej_pdf', args=[kamion.pk])
    return HttpResponseRedirect(url)

@admin.action(description="Vytisknout proforma fakturu vybraného kamionu výdej")
def tisk_proforma_faktury_kamionu_action(modeladmin, request, queryset):
    """
    Vytiskne proforma fakturu pro vybraný kamion do PDF.
    Předpokládá, že je vybrán pouze jeden kamion a to kamion s příznakem výdej.
    Pokud je vybráno více kamionů, zobrazí se chybová zpráva.
    Pokud kamion nemá přiřazeného zákazníka nebo zákazník nemá zkratku, zobrazí se chybová zpráva.
    Validuje ceny na zakázkách kamionu před tiskem. Pokud jsou neplatné ceny, zobrazí se chybová zpráva.
    Podle příznaku zákazníka proforma_po_bednach se vybere šablona pro tisk po bednách nebo po zakázkách.
    """
    # Pokud je vybráno více kamionů, zobrazí se chybová zpráva
    if queryset.count() != 1:
        logger.info(f"Uživatel {request.user} se pokusil tisknout proforma fakturu, ale vybral více než jeden kamion.")
        modeladmin.message_user(request, "Vyberte pouze jeden kamion.", level=messages.ERROR)
        return
    kamion = queryset.first()
    # Zkontroluje, zda je kamion s příznakem výdej
    if kamion.prijem_vydej != KamionChoice.VYDEJ:
        logger.info(f"Uživatel {request.user} se pokusil tisknout proforma fakturu kamionu {kamion.cislo_dl}, ale není to kamion s příznakem výdej.")
        modeladmin.message_user(request, "Tisk proforma faktury je možný pouze pro kamiony výdej.", level=messages.ERROR)
        return

    zakaznik_zkratka = kamion.zakaznik.zkratka
    if zakaznik_zkratka:
        validation_errors = _validate_proforma_pricing(kamion)
        if validation_errors:
            joined = '; '.join(validation_errors)
            logger.warning(
                f"Proforma faktura pro kamion {kamion.cislo_dl or kamion} nelze vytisknout kvůli neplatným cenám: {joined}",
            )
            modeladmin.message_user(
                request,
                f"Nelze tisknout proforma fakturu: {joined}",
                level=messages.ERROR,
            )
            return None
        logger.info(f"Uživatel {request.user} tiskne proforma fakturu kamionu {kamion.cislo_dl} pro zákazníka {zakaznik_zkratka}.")
        return HttpResponseRedirect(reverse('proforma_kamion_vydej_pdf', args=[kamion.pk]))


@admin.action(description="Vytisknout karty beden z vybraného kamionu příjem se zakázkami")
def tisk_karet_beden_kamionu_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartami beden z vybraného kamionu.
    Musí být vybrán pouze jeden kamion, jinak se zobrazí chybová zpráva.
    Musí se jednat o kamion s příznakem příjem, jinak se zobrazí chybová zpráva.
    Tisknou se pouze karty beden, které nejsou již expedovány.
    Bedny musí mít zadanou hmotnost, zakázku a předpis.
    """
    if queryset.count() != 1:
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty beden, ale vybral více než jeden kamion.")
        modeladmin.message_user(request, "Vyberte pouze jeden kamion.", level=messages.ERROR)
        return None
    if queryset.first().prijem_vydej != KamionChoice.PRIJEM:
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty beden kamionu {queryset.first().cislo_dl}, ale není to kamion s příznakem příjem.")
        modeladmin.message_user(request, "Tisk karet beden je možný pouze pro kamiony příjem.", level=messages.ERROR)
        return None
    bedny = Bedna.objects.filter(zakazka__kamion_prijem__in=queryset).exclude(stav_bedny=StavBednyChoice.EXPEDOVANO)

    if not bedny.exists():
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty beden, ale v označeném kamionu nejsou žádné bedny skladem.")
        modeladmin.message_user(request, "V označeném kamionu nejsou žádné bedny skladem.", level=messages.ERROR)
        return None
    
    if _abort_if_bedna_has_not_hmotnost_zakazka_predpis(modeladmin, request, bedny, "Tisk karet beden z vybraného kamionu příjem se zakázkami"):
        return None

    zakaznik_zkratka = queryset.first().zakaznik.zkratka
    if zakaznik_zkratka:
        try:
            template_paths, filename = resolve_customer_templates(
                zakaznik_zkratka=zakaznik_zkratka,
                mode="bedna",
            )
            html_path = template_paths[0]
        except ServiceValidationError as exc:
            modeladmin.message_user(request, str(exc), level=messages.ERROR)
            return None
        response = utilita_tisk_dokumentace(modeladmin, request, bedny, html_path, filename)
        logger.info(f"Uživatel {request.user} tiskne karty beden pro {bedny.count()} vybraných beden.")
        return response
    else:
        logger.error(f"Kamion {queryset.first()} nemá přiřazeného zákazníka nebo zákazník nemá zkratku.")
        modeladmin.message_user(request, "Kamion nemá přiřazeného zákazníka nebo zákazník nemá zkratku.", level=messages.ERROR)
        return None

@admin.action(description="Vytisknout KKK z vybraného kamionu příjem se zakázkami")
def tisk_karet_kontroly_kvality_kamionu_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s kartami kontroly kvality z vybraného kamionu.
    Musí být vybrán pouze jeden kamion, jinak se zobrazí chybová zpráva.
    Musí se jednat o kamion s příznakem příjem, jinak se zobrazí chybová zpráva.
    Tisknou se pouze karty beden, které nejsou již expedovány.
    Bedny musí mít zadanou hmotnost, zakázku a předpis.
    """
    if queryset.count() != 1:
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty kontroly kvality, ale vybral více než jeden kamion.")
        modeladmin.message_user(request, "Vyberte pouze jeden kamion.", level=messages.ERROR)
        return None
    
    if queryset.first().prijem_vydej != KamionChoice.PRIJEM:
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty kontroly kvality kamionu {queryset.first().cislo_dl}, ale není to kamion s příznakem příjem.")
        modeladmin.message_user(request, "Tisk karet beden je možný pouze pro kamiony příjem.", level=messages.ERROR)
        return None
    
    bedny = Bedna.objects.filter(zakazka__kamion_prijem__in=queryset).exclude(stav_bedny=StavBednyChoice.EXPEDOVANO)
    
    if not bedny.exists():
        logger.info(f"Uživatel {request.user} se pokusil tisknout karty kontroly kvality, ale v označeném kamionu nejsou žádné bedny.")
        modeladmin.message_user(request, "V označeném kamionu nejsou žádné bedny.", level=messages.ERROR)
        return None
    
    if _abort_if_bedna_has_not_hmotnost_zakazka_predpis(modeladmin, request, bedny, "Tisk karet kontroly kvality z vybraného kamionu příjem se zakázkami"):
        return None
    
    zakaznik_zkratka = queryset.first().zakaznik.zkratka
    if zakaznik_zkratka:
        try:
            template_paths, filename = resolve_customer_templates(
                zakaznik_zkratka=zakaznik_zkratka,
                mode="kkk",
            )
            html_path = template_paths[0]
        except ServiceValidationError as exc:
            modeladmin.message_user(request, str(exc), level=messages.ERROR)
            return None
        response = utilita_tisk_dokumentace(modeladmin, request, bedny, html_path, filename)
        logger.info(f"Uživatel {request.user} tiskne karty kontroly kvality pro {bedny.count()} vybraných beden.")
        return response
    else:
        logger.error(f"Kamion {queryset.first()} nemá přiřazeného zákazníka nebo zákazník nemá zkratku.")
        modeladmin.message_user(request, "Kamion nemá přiřazeného zákazníka nebo zákazník nemá zkratku.", level=messages.ERROR)
        return None

@admin.action(description="Tisk přehledu zakázek z vybraného kamionu příjem se zakázkami")
def tisk_prehledu_zakazek_kamionu_action(modeladmin, request, queryset):
    """
    Vytvoří PDF s přehledem zakázek z vybraného kamionu pro potřeby kontroly kvality.
    Musí být vybrán pouze jeden kamion, jinak se zobrazí chybová zpráva.
    Musí se jednat o kamion s příznakem příjem, jinak se zobrazí chybová zpráva.     
    Tiskne se vždy přehled všech zakázek v kamionu, i těch, které jsou již expedovány.
    Pokud jsou v kamionu bedny nepřijaté, zobrazí se chybová zpráva a tisk se přeruší.
    """
    if queryset.count() != 1:
        logger.info(f"Uživatel {request.user} se pokusil tisknout přehled zakázek, ale vybral více než jeden kamion.")
        modeladmin.message_user(request, "Vyberte pouze jeden kamion.", level=messages.ERROR)
        return None
    
    kamion = queryset.first()
    if kamion.prijem_vydej != KamionChoice.PRIJEM:
        logger.info(f"Uživatel {request.user} se pokusil tisknout přehled zakázek kamionu {kamion.cislo_dl}, ale není to kamion s příznakem příjem.")
        modeladmin.message_user(request, "Tisk přehledu zakázek je možný pouze pro kamiony příjem.", level=messages.ERROR)
        return None

    zakaznik_zkratka = kamion.zakaznik.zkratka
    if not zakaznik_zkratka:
        logger.error(f"Kamion {kamion} nemá přiřazeného zákazníka nebo zákazník nemá zkratku.")
        modeladmin.message_user(request, f"Kamion {kamion} nemá přiřazeného zákazníka nebo zákazník nemá zkratku.", level=messages.ERROR)
        return None

    bedny = Bedna.objects.filter(zakazka__kamion_prijem=kamion)
    if not bedny.exists():
        logger.info(f"Uživatel {request.user} se pokusil tisknout přehled zakázek, ale v označeném kamionu nejsou žádné bedny.")
        modeladmin.message_user(request, "V označeném kamionu nejsou žádné bedny.", level=messages.ERROR)
        return None
    
    if bedny.filter(stav_bedny=StavBednyChoice.NEPRIJATO).exists():
        logger.info(f"Uživatel {request.user} se pokusil tisknout přehled zakázek kamionu {kamion}, ale některé bedny nejsou přijaty.")
        modeladmin.message_user(request, "Některé bedny v označeném kamionu nejsou přijaty, lze tisknout pouze komplet přijatý kamion.", level=messages.ERROR)
        return None    

    filename = f"prehled_zakazek_{kamion.cislo_dl}_{zakaznik_zkratka}.pdf"
    html_path = "orders/prehled_zakazek.html"
    response = utilita_tisk_dl_a_proforma_faktury(modeladmin, request, kamion, html_path, filename)
    logger.info(f"Uživatel {request.user} tiskne přehled zakázek pro kamion {kamion.cislo_dl} obsahující {kamion.zakazky_prijem.count()} zakázek.")
    return response
    
# Akce pro rozpracovanost

@admin.action(description="Vytisknout rozpracovanost (PDF)")
def tisk_rozpracovanost_action(modeladmin, request, queryset):
    if queryset.count() != 1:
        modeladmin.message_user(request, "Vyberte prosím právě jeden záznam rozpracovanosti.", level=messages.ERROR)
        return None

    snapshot = queryset.first()
    if not isinstance(snapshot, Rozpracovanost):
        modeladmin.message_user(request, "Neplatný výběr pro tisk rozpracovanosti.", level=messages.ERROR)
        return None

    bedny_qs = snapshot.bedny.filter(fakturovat=True).select_related(
        'zakazka',
        'zakazka__predpis',
        'zakazka__kamion_prijem',
        'zakazka__kamion_prijem__zakaznik',
        'zakazka__typ_hlavy',
    ).order_by(
        'zakazka__kamion_prijem__zakaznik__nazev',
        'zakazka__artikl',
        'cislo_bedny',
    )

    bedny = list(bedny_qs)
    if not bedny:
        modeladmin.message_user(request, "Vybraný záznam rozpracovanosti neobsahuje žádné bedny.", level=messages.WARNING)
        return None

    customer_map: dict[int, dict] = {}
    skipped = 0
    weight_quant = Decimal('0.1')
    money_quant = Decimal('0.01')
    pricing_warnings = []
    warned_zakazky = set()

    def _to_decimal_or_none(value):
        if value is None:
            return None
        if isinstance(value, Decimal):
            return value
        try:
            return Decimal(value)
        except Exception:
            logger.warning("Nepodařilo se převést cenu zakázky na Decimal při tisku rozpracovanosti.", exc_info=True)
            return None

    for bedna in bedny:
        zakazka = getattr(bedna, 'zakazka', None)
        kamion_prijem = getattr(zakazka, 'kamion_prijem', None) if zakazka else None
        zakaznik = getattr(kamion_prijem, 'zakaznik', None) if kamion_prijem else None

        if not zakazka or not zakaznik:
            skipped += 1
            continue

        if zakazka.pk not in warned_zakazky:
            warning_reasons = []
            predpis = getattr(zakazka, 'predpis', None)
            if not predpis or getattr(predpis, 'nazev', None) == 'Neznámý předpis':
                warning_reasons.append('chybí předpis')

            cena_za_kg = _to_decimal_or_none(getattr(zakazka, 'cena_za_kg', None))
            if cena_za_kg is None or cena_za_kg <= 0:
                warning_reasons.append('cena kalení <= 0')

            if zakaznik.fakturovat_rovnani:
                cena_rovnani = _to_decimal_or_none(getattr(zakazka, 'cena_rovnani_za_kg', None))
                if cena_rovnani is None or cena_rovnani <= 0:
                    warning_reasons.append('cena rovnání <= 0')

            if zakaznik.fakturovat_tryskani:
                cena_tryskani = _to_decimal_or_none(getattr(zakazka, 'cena_tryskani_za_kg', None))
                if cena_tryskani is None or cena_tryskani <= 0:
                    warning_reasons.append('cena tryskání <= 0')

            if warning_reasons:
                pricing_warnings.append(
                    f"{zakaznik.zkraceny_nazev} / {zakazka.artikl or zakazka.pk}: {', '.join(warning_reasons)}"
                )
            warned_zakazky.add(zakazka.pk)

        customer_entry = customer_map.setdefault(
            zakaznik.pk,
            {
                'zakaznik': zakaznik,
                'zakazky': {},
                'sum_hmotnost': Decimal('0.0'),
                'sum_beden': 0,
                'sum_cena_netto': Decimal('0.0'),
                'sum_tryskani_hmotnost': Decimal('0.0'),
                'sum_tryskani_beden': 0,
                'sum_tryskani_cena_netto': Decimal('0.0'),
                'sum_rovnani_hmotnost': Decimal('0.0'),
                'sum_rovnani_beden': 0,
                'sum_rovnani_cena_netto': Decimal('0.0'),
            },
        )

        zakazka_entry = customer_entry['zakazky'].setdefault(
            zakazka.pk,
            {
                'artikl': zakazka.artikl,
                'datum': kamion_prijem.datum if kamion_prijem else None,
                'rozmer': _format_rozmer(zakazka),
                'typ': zakazka.zkraceny_popis,
                'hlava': str(zakazka.typ_hlavy) if zakazka.typ_hlavy else '',
                'cena_kg': Decimal(zakazka.cena_za_kg or 0),
                'cena_tryskani_za_kg': Decimal(zakazka.cena_tryskani_za_kg or 0) if zakaznik.fakturovat_tryskani else Decimal('0.00'),
                'cena_rovnani_za_kg': Decimal(zakazka.cena_rovnani_za_kg or 0) if zakaznik.fakturovat_rovnani else Decimal('0.00'),
                'hmotnost': Decimal('0.0'),
                'tryskani_hmotnost': Decimal('0.0'),
                'rovnani_hmotnost': Decimal('0.0'),
                'pocet_beden': 0,
                'tryskani_pocet_beden': 0,
                'rovnani_pocet_beden': 0,
            },
        )

        hmotnost = bedna.hmotnost or Decimal('0')
        if not isinstance(hmotnost, Decimal):
            try:
                hmotnost = Decimal(hmotnost)
            except Exception:
                logger.warning("Nepodařilo se převést hmotnost bedny na Decimal při exportu zákazníka, používá se 0.", exc_info=True)
                hmotnost = Decimal('0')

        zakazka_entry['hmotnost'] += hmotnost
        zakazka_entry['pocet_beden'] += 1

        if zakaznik.fakturovat_tryskani and bedna.tryskat == TryskaniChoice.OTRYSKANA:
            zakazka_entry['tryskani_hmotnost'] += hmotnost
            zakazka_entry['tryskani_pocet_beden'] += 1
            customer_entry['sum_tryskani_hmotnost'] += hmotnost
            customer_entry['sum_tryskani_beden'] += 1

        if zakaznik.fakturovat_rovnani and bedna.rovnat == RovnaniChoice.VYROVNANA:
            zakazka_entry['rovnani_hmotnost'] += hmotnost
            zakazka_entry['rovnani_pocet_beden'] += 1
            customer_entry['sum_rovnani_hmotnost'] += hmotnost
            customer_entry['sum_rovnani_beden'] += 1

        customer_entry['sum_hmotnost'] += hmotnost
        customer_entry['sum_beden'] += 1

    if not customer_map:
        modeladmin.message_user(
            request,
            "Pro vybraný záznam rozpracovanosti nebyla nalezena kompletní data.",
            level=messages.ERROR,
        )
        if skipped:
            logger.warning(
                f"Rozpracovanost PDF: přeskočeno {skipped} beden bez vazby na zakázku/zákazníka.",
            )
        return None

    if pricing_warnings:
        preview_items = pricing_warnings[:8]
        remaining = len(pricing_warnings) - len(preview_items)
        detail_text = '; '.join(preview_items)
        if remaining > 0:
            detail_text = f"{detail_text}; ... a dalších {remaining} zakázek"
        logger.warning(
            "Rozpracovanost PDF: nalezeny zakázky s nekompletním ceníkem/předpisem. "
            f"Počet: {len(pricing_warnings)}. Detaily: {detail_text}"
        )

    sections = []
    for customer_entry in sorted(customer_map.values(), key=lambda item: item['zakaznik'].nazev):
        zakazky_rows = []
        for zakazka_entry in sorted(customer_entry['zakazky'].values(), key=lambda item: item['artikl']):
            hm_total = zakazka_entry['hmotnost'].quantize(weight_quant, rounding=ROUND_HALF_UP)
            cena_kg = zakazka_entry['cena_kg'].quantize(money_quant, rounding=ROUND_HALF_UP) if zakazka_entry['cena_kg'] else Decimal('0.00')
            cena_netto = (zakazka_entry['hmotnost'] * zakazka_entry['cena_kg']).quantize(money_quant, rounding=ROUND_HALF_UP)
            tryskani_hmotnost = zakazka_entry['tryskani_hmotnost'].quantize(weight_quant, rounding=ROUND_HALF_UP)
            rovnani_hmotnost = zakazka_entry['rovnani_hmotnost'].quantize(weight_quant, rounding=ROUND_HALF_UP)
            cena_tryskani_kg = zakazka_entry['cena_tryskani_za_kg'].quantize(money_quant, rounding=ROUND_HALF_UP) if zakazka_entry['cena_tryskani_za_kg'] else Decimal('0.00')
            cena_rovnani_kg = zakazka_entry['cena_rovnani_za_kg'].quantize(money_quant, rounding=ROUND_HALF_UP) if zakazka_entry['cena_rovnani_za_kg'] else Decimal('0.00')
            cena_tryskani_netto = (zakazka_entry['tryskani_hmotnost'] * zakazka_entry['cena_tryskani_za_kg']).quantize(money_quant, rounding=ROUND_HALF_UP)
            cena_rovnani_netto = (zakazka_entry['rovnani_hmotnost'] * zakazka_entry['cena_rovnani_za_kg']).quantize(money_quant, rounding=ROUND_HALF_UP)
            customer_entry['sum_cena_netto'] += cena_netto
            customer_entry['sum_tryskani_cena_netto'] += cena_tryskani_netto
            customer_entry['sum_rovnani_cena_netto'] += cena_rovnani_netto
            zakazky_rows.append({
                'artikl': zakazka_entry['artikl'],
                'datum': zakazka_entry['datum'],
                'hmotnost': hm_total,
                'rozmer': zakazka_entry['rozmer'],
                'typ': zakazka_entry['typ'],
                'hlava': zakazka_entry['hlava'],
                'cena_kg': cena_kg,
                'cena_netto': cena_netto,
                'pocet_beden': zakazka_entry['pocet_beden'],
                'tryskani_pocet_beden': zakazka_entry['tryskani_pocet_beden'],
                'tryskani_hmotnost': tryskani_hmotnost,
                'tryskani_cena_kg': cena_tryskani_kg,
                'tryskani_cena_netto': cena_tryskani_netto,
                'rovnani_pocet_beden': zakazka_entry['rovnani_pocet_beden'],
                'rovnani_hmotnost': rovnani_hmotnost,
                'rovnani_cena_kg': cena_rovnani_kg,
                'rovnani_cena_netto': cena_rovnani_netto,
            })

        sum_tryskani_hmotnost = customer_entry['sum_tryskani_hmotnost']
        sum_rovnani_hmotnost = customer_entry['sum_rovnani_hmotnost']
        sum_tryskani_cena_netto = customer_entry['sum_tryskani_cena_netto']
        sum_rovnani_cena_netto = customer_entry['sum_rovnani_cena_netto']
        sum_tryskani_cena_kg = (
            (sum_tryskani_cena_netto / sum_tryskani_hmotnost).quantize(money_quant, rounding=ROUND_HALF_UP)
            if sum_tryskani_hmotnost else Decimal('0.00')
        )
        sum_rovnani_cena_kg = (
            (sum_rovnani_cena_netto / sum_rovnani_hmotnost).quantize(money_quant, rounding=ROUND_HALF_UP)
            if sum_rovnani_hmotnost else Decimal('0.00')
        )

        sections.append({
            'zakaznik': customer_entry['zakaznik'],
            'zakazky': zakazky_rows,
            'sum_hmotnost': customer_entry['sum_hmotnost'].quantize(weight_quant, rounding=ROUND_HALF_UP),
            'sum_beden': customer_entry['sum_beden'],
            'sum_cena_netto': customer_entry['sum_cena_netto'].quantize(money_quant, rounding=ROUND_HALF_UP),
            'sum_tryskani_hmotnost': sum_tryskani_hmotnost.quantize(weight_quant, rounding=ROUND_HALF_UP),
            'sum_tryskani_beden': customer_entry['sum_tryskani_beden'],
            'sum_tryskani_cena_netto': sum_tryskani_cena_netto.quantize(money_quant, rounding=ROUND_HALF_UP),
            'sum_tryskani_cena_kg': sum_tryskani_cena_kg,
            'sum_rovnani_hmotnost': sum_rovnani_hmotnost.quantize(weight_quant, rounding=ROUND_HALF_UP),
            'sum_rovnani_beden': customer_entry['sum_rovnani_beden'],
            'sum_rovnani_cena_netto': sum_rovnani_cena_netto.quantize(money_quant, rounding=ROUND_HALF_UP),
            'sum_rovnani_cena_kg': sum_rovnani_cena_kg,
        })

    context = {
        'snapshot': snapshot,
        'sections': sections,
        'pricing_warnings': pricing_warnings,
        'generated_at': timezone.now(),
        'prepared_by': _resolve_user_name(getattr(request, 'user', None)),
    }

    html = render_to_string('orders/rozpracovanost_report.html', context)
    stylesheets = []
    css_path = finders.find('orders/css/pdf_shared.css')
    if css_path:
        stylesheets.append(CSS(filename=css_path))
    else:
        logger.warning("PDF rozpracovanost: CSS 'orders/css/pdf_shared.css' nebylo nalezeno.")

    base_url = request.build_absolute_uri('/') if request else None
    pdf_content = HTML(string=html, base_url=base_url).write_pdf(stylesheets=stylesheets)

    filename = f"rozpracovanost_{snapshot.cas_zaznamu:%Y%m%d_%H%M%S}.pdf"
    response = HttpResponse(pdf_content, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="{filename}"'

    logger.info(
        f"Uživatel {getattr(request, 'user', None)} vygeneroval PDF rozpracovanosti ID {snapshot.pk} (beden: {sum(section['sum_beden'] for section in sections)}, přeskočeno: {skipped})."
    )

    return response