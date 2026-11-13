from django.db import migrations
from django.db.models import F, OuterRef, Subquery


OPERATIONS = ('kaleni', 'rovnani', 'tryskani', 'zinkovani')


def forwards(apps, schema_editor):
    alias = schema_editor.connection.alias
    Crate = apps.get_model('orders', 'Bedna')
    History = apps.get_model('orders', 'HistoricalBedna')
    Order = apps.get_model('orders', 'Zakazka')
    # History retains the original meaning; only invert the renamed flags.
    History.objects.using(alias).update(**{'fakturovat_' + op: ~F('fakturovat_' + op) for op in OPERATIONS})
    orders = Order.objects.using(alias).filter(pk=OuterRef('zakazka_id'))
    Crate.objects.using(alias).filter(atypicky_prubeh=False).update(
        fakturovat_kaleni=True,
        fakturovat_rovnani=Subquery(orders.values('kamion_prijem__zakaznik__fakturovat_rovnani')[:1]),
        fakturovat_tryskani=Subquery(orders.values('kamion_prijem__zakaznik__fakturovat_tryskani')[:1]),
        fakturovat_zinkovani=False,
    )
    Crate.objects.using(alias).filter(atypicky_prubeh=True).update(
        **{'fakturovat_' + op: False for op in OPERATIONS}
    )


def backwards(apps, schema_editor):
    # Preserve current choices when reverting to the negative field names.
    for name in ('Bedna', 'HistoricalBedna'):
        apps.get_model('orders', name).objects.using(schema_editor.connection.alias).update(
            **{'fakturovat_' + op: ~F('fakturovat_' + op) for op in OPERATIONS}
        )


class Migration(migrations.Migration):
    dependencies = [('orders', '0249_kladna_fakturace_schema')]
    operations = [migrations.RunPython(forwards, backwards)]
