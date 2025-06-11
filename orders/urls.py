from django.urls import path
from .views import home_view, BednyListView, ZakazkyListView, dashboard_view, karta_bedny_view

urlpatterns = [
    path('', home_view, name='home'),
    path('dashboard/', dashboard_view, name='dashboard'),
    path('bedny/', BednyListView.as_view(), name='bedny_list'),
    path('bedna/<int:pk>/karta/', karta_bedny_view, name='karta_bedny'),
    path('zakazky/', ZakazkyListView.as_view(), name='zakazky_list'),
]
