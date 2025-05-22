from django.apps import AppConfig
from django.forms.fields import CharField, ChoiceField, BooleanField, DateField, IntegerField, FloatField
import logging
logger = logging.getLogger('orders')

class OrdersConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'orders'
    def ready(self):
        logger.debug("OrdersConfig.ready() volá override field templates")
        CharField.template_name = 'forms/text_field.html'
        ChoiceField.template_name = 'forms/select_field.html'
        BooleanField.template_name = 'forms/checkbox_field.html'
        DateField.template_name = 'forms/date_field.html'
        IntegerField.template_name = 'forms/number_field.html'
        FloatField.template_name = 'forms/number_field.html'