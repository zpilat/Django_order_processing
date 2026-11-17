"""Dodatečná rekonstrukce chybějící historie migrace 0250, bez změn živých dat."""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from django.db import connection, transaction
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Min
from django.utils import timezone

from orders.models import Bedna, Kamion, Zakazka, Zakaznik
from orders.services.exceptions import ServiceValidationError


SCHEMA_MIGRATION = '0249_kladna_fakturace_schema'
DATA_MIGRATION = '0250_vychozi_fakturace_beden'
FLAGS = tuple(f'fakturovat_{operation}' for operation in ('kaleni', 'rovnani', 'tryskani', 'zinkovani'))
REPAIR_REASON = 'Doplnění historie migrace 0250.'
ATYPICAL_REASON = 'Převod na atypický průběh.'


@dataclass
class BillingHistoryRepairPlan:
    migration_at: datetime
    records: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    issues: list = field(default_factory=list)
    already_recorded: int = 0
    unchanged: int = 0
    first_saved: int = 0
    not_saved: int = 0


def _latest_before(model, at):
    return {
        record.id: record
        for record in model.history.filter(history_date__lt=at)
        .order_by('id', '-history_date', '-history_id').distinct('id')
    }


def _flag_values(record):
    return tuple(getattr(record, name) for name in FLAGS)


def build_billing_history_repair_plan():
    """Pouze čte data a sestaví historické snímky podle skutečného běhu migrace.

    Datum je čas dokončení 0250 z django_migrations. Ostatní pole snímku pocházejí
    z poslední historie před 0249. Hodnoty zákazníka se dohledávají historicky,
    přes tehdejší zakázku a kamion. Pozdější ruční změny se nepřepisují.
    """
    if connection.vendor != 'postgresql':
        raise ServiceValidationError('Rekonstrukce historie vyžaduje PostgreSQL.')
    try:
        start = MigrationRecorder.Migration.objects.get(app='orders', name=SCHEMA_MIGRATION).applied
        end = MigrationRecorder.Migration.objects.get(app='orders', name=DATA_MIGRATION).applied
    except MigrationRecorder.Migration.DoesNotExist as error:
        raise ServiceValidationError('Chybí záznam o provedení migrací 0249 a 0250.') from error
    if start >= end:
        raise ServiceValidationError('Časy migrací 0249 a 0250 nemají očekávané pořadí.')

    plan = BillingHistoryRepairPlan(migration_at=end)
    history_model = Bedna.history.model
    tracked_names = [item.attname for item in history_model.tracked_fields]
    previous = _latest_before(Bedna, start)
    first_after = {
        record.id: record
        for record in Bedna.history.filter(history_date__gt=end)
        .order_by('id', 'history_date', 'history_id').distinct('id')
    }
    current = Bedna.objects.in_bulk()
    markers = defaultdict(list)
    for record in Bedna.history.filter(history_change_reason__startswith=REPAIR_REASON):
        markers[record.id].append(record)
    boundary = set(
        Bedna.history.filter(history_date__gte=start, history_date__lte=end)
        .exclude(history_date=end, history_change_reason__startswith=REPAIR_REASON)
        .values_list('id', flat=True)
    )
    snapshots = {
        at: {model: _latest_before(model, at) for model in (Zakazka, Kamion, Zakaznik)}
        for at in (start, end)
    }

    def migration_flags(record, at):
        if record.atypicky_prubeh:
            return (False, False, False, False), 'ATYP'
        old_order = snapshots[at][Zakazka].get(record.zakazka_id)
        old_truck = snapshots[at][Kamion].get(old_order.kamion_prijem_id) if old_order else None
        customer = snapshots[at][Zakaznik].get(old_truck.zakaznik_id) if old_truck else None
        if (
            old_order is None or old_order.history_type == '-'
            or old_truck is None or old_truck.history_type == '-'
            or customer is None or customer.history_type == '-'
        ):
            raise ServiceValidationError('Chybí tehdejší historie zakázky, kamionu nebo zákazníka.')
        # Přesná pravidla 0250: kalení Ano, R/T ze zákazníka, zinkování Ne.
        return (True, customer.fakturovat_rovnani, customer.fakturovat_tryskani, False), customer.zkratka

    reason = f'{REPAIR_REASON} Rekonstrukce zapsaná {timezone.localtime().isoformat(timespec="seconds")}.'
    for pk, old in previous.items():
        if old.history_type == '-':
            continue
        prefix = f'Bedna {old.cislo_bedny} (ID {pk})'
        try:
            if pk in boundary:
                raise ServiceValidationError('Má historii přímo v časovém okně migrace.')
            expected, customer_code = migration_flags(old, start)
            if migration_flags(old, end)[0] != expected:
                raise ServiceValidationError('Během migrace se změnilo související nastavení zákazníka.')
            if _flag_values(old) == expected:
                if markers.get(pk):
                    raise ServiceValidationError('Má záznam opravy, přestože migrace neměnila jeho volby.')
                plan.unchanged += 1
                continue

            data = {name: getattr(old, name) for name in tracked_names}
            data.update(zip(FLAGS, expected))
            marker = history_model(
                **data, history_date=end, history_type='~',
                history_user=None, history_change_reason=reason,
            )
            existing = markers.get(pk, [])
            if existing:
                if len(existing) != 1:
                    raise ServiceValidationError('Má více záznamů stejné opravy.')
                saved = existing[0]
                if (
                    saved.history_date != end or saved.history_type != '~' or saved.history_user_id is not None
                    or any(getattr(saved, name) != getattr(marker, name) for name in tracked_names)
                ):
                    raise ServiceValidationError('Existující záznam opravy neodpovídá rekonstrukci.')
                plan.already_recorded += 1
                continue

            first = first_after.get(pk)
            if first is not None:
                conversion = (
                    not old.atypicky_prubeh and first.atypicky_prubeh
                    and first.history_change_reason == ATYPICAL_REASON
                    and _flag_values(first) == (False, False, False, False)
                )
                if first.history_type == '+' or (_flag_values(first) != expected and not conversion):
                    raise ServiceValidationError('První pozdější snímek má nejednoznačné fakturační volby.')
                plan.first_saved += 1
            else:
                live = current.get(pk)
                if live is None or _flag_values(live) != expected:
                    raise ServiceValidationError('Chybí pozdější historie a současný stav nelze potvrdit.')
                plan.not_saved += 1
            plan.records.append(marker)
            plan.rows.append({
                'id': pk, 'cislo_bedny': old.cislo_bedny, 'zakaznik': customer_code,
                'puvodni_historie_id': old.history_id,
                'prvni_pozdejsi_historie_id': first.history_id if first else None,
                'datum_migrace': end.isoformat(),
                **{f'{name}_pred': getattr(old, name) for name in FLAGS},
                **{f'{name}_po': getattr(marker, name) for name in FLAGS},
            })
        except ServiceValidationError as error:
            plan.issues.append(f'{prefix}: {error}')

    for pk in markers:
        if pk not in previous or previous[pk].history_type == '-':
            plan.issues.append(f'ID {pk}: záznam opravy nepatří bedně existující před migrací.')
    for pk in boundary - previous.keys():
        plan.issues.append(f'ID {pk}: vzniklo v časovém okně migrace; vyžaduje ruční posouzení.')
    for pk in current.keys() - previous.keys() - first_after.keys() - boundary:
        plan.issues.append(f'ID {pk}: chybí historie vzniku bedny.')
    return plan


def repair_billing_history(*, apply=False, rollback=False):
    """Náhled, atomický zápis nebo úplná zkouška zakončená rollbackem.

    Současné bedny ani existující historické záznamy se nikdy neukládají.
    Zápisy příkazu se serializují transakčním advisory lockem. Zkušební režim
    používá dočasná záporná ID, takže neposune ani sekvenci historie.
    """
    if apply and rollback:
        raise ServiceValidationError('Zvolte pouze --apply nebo --rollback.')
    with transaction.atomic():
        if apply or rollback:
            if connection.vendor != 'postgresql':
                raise ServiceValidationError('Rekonstrukce historie vyžaduje PostgreSQL.')
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(%s, %s)', [0x4F524452, 250])
        plan = build_billing_history_repair_plan()
        if apply or rollback:
            if plan.issues:
                raise ServiceValidationError('Rekonstrukce nebyla zapsána: ' + ' '.join(plan.issues))
            if rollback:
                smallest = Bedna.history.aggregate(value=Min('history_id'))['value'] or 0
                for index, record in enumerate(plan.records, start=1):
                    record.history_id = min(smallest, 0) - index
            Bedna.history.model.objects.bulk_create(plan.records, batch_size=500)
            verification = build_billing_history_repair_plan()
            if verification.issues or verification.records:
                raise ServiceValidationError('Kontrola po zápisu selhala; celá operace se vrací zpět.')
            if rollback:
                transaction.set_rollback(True)
        return plan
