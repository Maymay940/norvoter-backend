from django.urls import path

from . import views

urlpatterns = [
    # основные html страницы (фронтенд)
    path("", views.meter_list, name="meter_list"),  # главная
    path("meters/<int:meter_id>/", views.meter_detail, name="meter_detail"),  # счетчики
    path("requests/", views.request_list, name="request_list"),  # заявки
    path("requests/<int:request_id>/", views.request_detail, name="request_detail"),  # заявки(переход внутрь)
    path("add-reading/", views.add_reading, name="add_reading"),  # добавить показания в БД
    path("submit-request/<int:request_id>/", views.submit_request, name="submit_request"),  # статус отправлено
    path("delete-request/<int:request_id>/", views.delete_request, name="delete_request"),  # статус удалено

    # API эндпоинты 
    # услуги (счетчики воды)
    path("api/meters/", views.api_meters, name="api_meters"),  # get список с фильтрацией
    path("api/meters/<int:meter_id>/", views.api_meter_detail, name="api_meter_detail"),  # get одна запись
    path("api/meters/add/", views.api_meter_add, name="api_meter_add"),  # post добавление услуги + фото/видео

    # корзина (черновик заявки)
    path("api/cart/", views.api_cart, name="api_cart"),  # get иконка корзины (id черновика + количество услуг)

    # заявки
    path("api/requests/", views.api_requests, name="api_requests"),  # get список (с фильтрацией по дате и статусу)
    path("api/requests/<int:request_id>/", views.api_request_detail, name="api_request_detail"),  # get одна запись (с услугами)
    path("api/requests/<int:request_id>/update/", views.api_request_update, name="api_request_update"),  # put изменение полей заявки
    path("api/requests/<int:request_id>/submit/", views.api_submit_request, name="api_submit_request"),  # put сформировать создателем (дата формирования)
    path("api/requests/<int:request_id>/complete/", views.api_complete_request, name="api_complete_request"),  # put завершить модератором
    path("api/requests/<int:request_id>/reject/", views.api_reject_request, name="api_reject_request"),  # put отклонить модератором
    path("api/requests/<int:request_id>/delete/", views.api_delete_request, name="api_delete_request"),  # delete удаление (черновик)

    # позиции 
    path("api/positions/add/", views.api_position_add, name="api_position_add"),  # post добавление услуги в черновик
    path("api/positions/<int:position_id>/update/", views.api_position_update, name="api_position_update"),  # put изменение поля м-м
    path("api/positions/<int:position_id>/delete/", views.api_position_delete, name="api_position_delete"),  # delete удаление из заявки (без pk м-м)

    # пользователи 
    path("api/users/register/", views.api_register, name="api_register"),  # post регистрация
    path("api/users/login/", views.api_login, name="api_login"),  # post аутентификация (заглушка)
    path("api/users/logout/", views.api_logout, name="api_logout"),  # post деавторизация (заглушка)
]