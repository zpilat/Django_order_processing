from django.urls import path
from .views import home_view, BednyListView, ZakazkyListView

urlpatterns = [
    path('', home_view, name='home'),
    path('bedny/', BednyListView.as_view(), name='bedny_list'),
    path('zakazky/', ZakazkyListView.as_view(), name='zakazky_list'),
]
