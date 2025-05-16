from django.urls import path
from .views import BednyListView

urlpatterns = [
    path('bedny/', BednyListView.as_view(), name='bedny_list'),
]
