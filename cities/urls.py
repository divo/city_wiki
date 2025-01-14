from django.urls import path
from . import views

urlpatterns = [
    path('', views.city_list, name='city_list'),
    path('city/<str:city_name>/', views.city_detail, name='city_detail'),
    path('city/<str:city_name>/map/', views.city_map, name='city_map'),
    path('city/<str:city_name>/delete/', views.delete_city, name='delete_city'),
    path('city/<str:city_name>/dump/', views.dump_city, name='dump_city'),
    path('import-city/', views.import_city, name='import_city'),
    path('import-status/<str:task_id>/', views.check_import_status, name='check_import_status'),
]
