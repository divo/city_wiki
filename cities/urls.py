from django.urls import path
from . import views

urlpatterns = [
    path('', views.city_list, name='city_list'),
    path('cities.json', views.city_list_json, name='city_list_json'),
    path('generate/', views.generate_text_view, name='generate_text_view'),
    path('city/<str:city_name>/', views.city_detail, name='city_detail'),
    path('city/<str:city_name>/map/', views.city_map, name='city_map'),
    path('city/<str:city_name>/delete/', views.delete_city, name='delete_city'),
    path('city/<str:city_name>/dump/', views.dump_city, name='dump_city'),
    path('city/<str:city_name>/generate/', views.generate_text, name='generate_text'),
    path('city/<str:city_name>/generate-list/', views.generate_list, name='generate_list'),
    path('import-city/', views.import_city, name='import_city'),
    path('import-status/<str:task_id>/', views.check_import_status, name='check_import_status'),
    path('city/<str:city_name>/poi/<int:poi_id>/history/', views.poi_history, name='poi_history'),
    path('city/<str:city_name>/poi/<int:poi_id>/revert/<int:revision_id>/', views.poi_revert, name='poi_revert'),
    path('city/<str:city_name>/poi/<int:poi_id>/edit/', views.poi_edit, name='poi_edit'),
    path('city/<str:city_name>/poi/<int:poi_id>/', views.poi_detail, name='poi_detail'),
    path('city/<str:city_name>/poi/merge/', views.poi_merge, name='poi_merge'),
    path('city/<str:city_name>/lists/', views.poi_lists, name='poi_lists'),
]
