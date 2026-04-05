from django.urls import path

from . import views

urlpatterns = [
    path("", views.meter_list, name="meter_list"),  # главная
    path("meters/<int:meter_id>/", views.meter_detail, name="meter_detail"),  # счетчики
    path("requests/", views.request_list, name="request_list"),  # заявки
    path("requests/<int:request_id>/", views.request_detail, name="request_detail"),  # заявки(переход внутрь)
    path("add-reading/", views.add_reading, name="add_reading"),  # добавить показания в БД
    path("submit-request/<int:request_id>/", views.submit_request, name="submit_request"),  # статус отправлено
    path("delete-request/<int:request_id>/", views.delete_request, name="delete_request"),  # статус удалено
    path("api/meters/", views.api_meters, name="api_meters"),
    path("api/meters/<int:meter_id>/", views.api_meter_detail, name="api_meter_detail"),
    path("api/requests/", views.api_requests, name="api_requests"),
    path(
        "api/requests/<int:request_id>/",
        views.api_request_detail,
        name="api_request_detail",
    ),
    path("api/add-reading/", views.api_add_reading, name="api_add_reading"),
    path(
        "api/submit-request/<int:request_id>/",
        views.api_submit_request,
        name="api_submit_request",
    ),
    path(
        "api/delete-request/<int:request_id>/",
        views.api_delete_request,
        name="api_delete_request",
    ),
]
