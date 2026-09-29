from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0232_uvolneni_s_odchylkou_a_neshoda'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RenameField(
            model_name='kontrolabedny', old_name='uvolnil', new_name='uvolneni_zmenil',
        ),
        migrations.RenameField(
            model_name='kontrolabedny', old_name='uvolneno_at', new_name='uvolneni_zmeneno_at',
        ),
        migrations.RenameField(
            model_name='historicalkontrolabedny', old_name='uvolnil', new_name='uvolneni_zmenil',
        ),
        migrations.RenameField(
            model_name='historicalkontrolabedny', old_name='uvolneno_at', new_name='uvolneni_zmeneno_at',
        ),
        migrations.AlterField(
            model_name='kontrolabedny', name='uvolneni_zmenil',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                related_name='zmenene_kontroly_beden', to=settings.AUTH_USER_MODEL,
                verbose_name='Stav uvolnění změnil',
            ),
        ),
        migrations.AlterField(
            model_name='historicalkontrolabedny', name='uvolneni_zmenil',
            field=models.ForeignKey(
                blank=True, db_constraint=False, null=True,
                on_delete=django.db.models.deletion.DO_NOTHING,
                related_name='+', to=settings.AUTH_USER_MODEL,
                verbose_name='Stav uvolnění změnil',
            ),
        ),
        migrations.AlterField(
            model_name='kontrolabedny', name='uvolneni_zmeneno_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Datum změny uvolnění'),
        ),
        migrations.AlterField(
            model_name='historicalkontrolabedny', name='uvolneni_zmeneno_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Datum změny uvolnění'),
        ),
    ]
