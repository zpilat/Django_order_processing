"""Denní počty dokončených kontrol a vyřešení neshod z auditní historie."""

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import timezone

from orders.choices import StavBednyChoice, UvolneniKontrolyChoice
from orders.models import Bedna, KontrolaBedny
from orders.services.history_service import history_transitions_to_qs


DOKONCENI_KONTROLY_REASON = 'Dokončení kontroly bedny tlačítkem.'
RUCNI_ZKONTROLOVANO_REASON = 'Ruční nastavení Zkontrolováno v administraci.'
REPORT_TIMEZONE = ZoneInfo('Europe/Prague')


def build_kontrolori_prehled(*, today=None):
    today = today or timezone.localdate(timezone=REPORT_TIMEZONE)
    start = today - timedelta(days=29)
    start_dt = datetime.combine(start, time.min, tzinfo=REPORT_TIMEZONE)
    end_dt = datetime.combine(today + timedelta(days=1), time.min, tzinfo=REPORT_TIMEZONE)

    completions = history_transitions_to_qs(
        model=Bedna, field_name='stav_bedny', target_value=StavBednyChoice.ZKONTROLOVANO,
    ).filter(previous_field_value=StavBednyChoice.ZAKALENO)
    # Starší historie nerozlišuje tlačítko a ruční přechod v administraci.
    completions = completions.filter(
        Q(history_change_reason=DOKONCENI_KONTROLY_REASON)
        | Q(history_change_reason__isnull=True)
        | Q(history_change_reason='')
    )
    resolutions = history_transitions_to_qs(
        model=KontrolaBedny, field_name='uvolneni',
        target_value=(UvolneniKontrolyChoice.UVOLNENO, UvolneniKontrolyChoice.UVOLNENO_S_ODCHYLKOU),
    ).filter(previous_field_value=UvolneniKontrolyChoice.NESHODA)

    daily_counts = {}
    totals = {}
    for field, events in (('completed', completions), ('resolved', resolutions)):
        counts = (
            events.filter(history_date__gte=start_dt, history_date__lt=end_dt)
            .order_by()
            .annotate(day=TruncDate('history_date', tzinfo=REPORT_TIMEZONE))
            .values('day', 'history_user_id')
            .annotate(count=Count('history_id'))
        )
        for row in counts:
            user_id = row['history_user_id']
            daily_counts.setdefault((row['day'], user_id), {'completed': 0, 'resolved': 0})[field] += row['count']
            totals.setdefault(user_id, {'completed': 0, 'resolved': 0})[field] += row['count']

    users = get_user_model().objects.in_bulk(user_id for user_id in totals if user_id is not None)
    names = {
        user_id: (user.get_full_name().strip() or user.get_username())
        for user_id, user in users.items()
    }
    names[None] = 'Neznámý uživatel'
    user_ids = sorted(totals, key=lambda user_id: (user_id is None, names[user_id].casefold(), user_id or 0))
    summary = [{'user_id': user_id, 'name': names[user_id], **totals[user_id]} for user_id in user_ids]
    days = []
    for offset in range(30):
        day = today - timedelta(days=offset)
        rows = [
            {'user_id': user_id, 'name': names[user_id],
             **daily_counts.get((day, user_id), {'completed': 0, 'resolved': 0})}
            for user_id in user_ids
        ]
        days.append({
            'date': day, 'rows': rows,
            'completed': sum(row['completed'] for row in rows),
            'resolved': sum(row['resolved'] for row in rows),
        })
    return {
        'start_date': start, 'end_date': today, 'summary': summary, 'days': days,
        'completed': sum(row['completed'] for row in summary),
        'resolved': sum(row['resolved'] for row in summary),
    }
