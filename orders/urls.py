from django.urls import path
from .views import home_view, BednyListView, ZakazkyListView, dashboard_bedny_view, dashboard_kamiony_view

urlpatterns = [
    path('', home_view, name='home'),
    path('dashboard/bedny/', dashboard_bedny_view, name='dashboard_bedny'),
    path('bedny/', BednyListView.as_view(), name='bedny_list'),
    path('zakazky/', ZakazkyListView.as_view(), name='zakazky_list'),
    path('dashboard/kamiony/', dashboard_kamiony_view, name='dashboard_kamiony'),
]
