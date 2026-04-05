import json

from django.db import connection
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import ReadingPosition, Request, User, WaterMeter


# получение текущего пользователя (для заявок, потом понадобится)
def get_current_user():
    # возвращает первого пользователя из БД (пока что пусть так будет)
    return User.objects.first()


def api_response_success(data=None, message=None):
    """Формирует успешный JSON-ответ"""
    response = {"success": True}
    if data is not None:
        response["data"] = data
    if message is not None:
        response["message"] = message
    return JsonResponse(response)


def api_response_error(error, status=400):
    """Формирует JSON-ответ с ошибкой"""
    return JsonResponse({"success": False, "error": error}, status=status)


def meter_list(request):  # get список всех счетчиков
    search_query = request.GET.get("search", "")  # поисковый запрос из URL

    # все счетчики на глав странице (получаем)
    meters = WaterMeter.objects.filter(is_active=True)

    if search_query:
        meters = meters.filter(address__icontains=search_query)  # фильтр по адресу если есть

    # для заявок используем пользователя (потом, когда сделаю)
    current_user = get_current_user()
    draft_request = Request.objects.filter(status="draft", user=current_user).first()
    if draft_request:
        draft_request.positions_count = ReadingPosition.objects.filter(request=draft_request).count()

    context = {
        "meters": meters,  # счетчики
        "draft_request": draft_request,
        "search_query": search_query,
    }
    return render(request, "meters/meter_list.html", context)


def meter_detail(request, meter_id):  # get /meters/<id>/ детальная страница счетчика
    # детали любого счетчика (получение счетчика по id)
    meter = get_object_or_404(WaterMeter, id=meter_id, is_active=True)
    return render(request, "meters/meter_detail.html", {"meter": meter})


def request_list(request):
    current_user = get_current_user()

    requests_list = Request.objects.filter(user=current_user).exclude(status="deleted").order_by("-created_at")

    for req in requests_list:
        req.positions_count = ReadingPosition.objects.filter(request=req).count()

    return render(request, "meters/request_list.html", {"requests": requests_list})


def request_detail(request, request_id):
    # внутренняя страница заявки
    current_user = get_current_user()
    request_obj = get_object_or_404(Request, id=request_id, user=current_user)

    if request_obj.status == "deleted":
        return redirect("request_list")

    positions = ReadingPosition.objects.filter(request=request_obj).select_related("water_meter")

    total_consumption = sum(p.consumption for p in positions)
    amount_to_pay = total_consumption * 50

    context = {
        "request_obj": request_obj,
        "positions": positions,
        "total_consumption": total_consumption,
        "amount_to_pay": amount_to_pay,
    }
    return render(request, "meters/request_detail.html", context)


def add_reading(request):  # post /add-reading/ добавление показаний
    # добавление показаний в черновик
    if request.method == "POST":
        current_user = get_current_user()
        meter_id = request.POST.get("meter_id")
        current_reading = request.POST.get("current_reading")

        # получение счетчик (без проверки пользователя)
        meter = get_object_or_404(WaterMeter, id=meter_id)

        draft_request = Request.objects.filter(status="draft", user=current_user).first()
        if not draft_request:
            draft_request = Request.objects.create(status="draft", user=current_user)

        existing_position = ReadingPosition.objects.filter(request=draft_request, water_meter=meter).first()

        consumption = int(current_reading) - meter.last_verified_reading

        if existing_position:
            existing_position.current_reading = current_reading
            existing_position.consumption = consumption
            existing_position.save()
        else:
            ReadingPosition.objects.create(
                request=draft_request,
                water_meter=meter,
                current_reading=current_reading,
                consumption=consumption,
            )

        return redirect("request_detail", request_id=draft_request.id)

    return redirect("meter_list")


def submit_request(request, request_id):
    # отправка заявки на проверку
    current_user = get_current_user()
    request_obj = get_object_or_404(Request, id=request_id, user=current_user)

    if request_obj.status == "draft":
        request_obj.status = "submitted"
        request_obj.submitted_at = timezone.now()
        request_obj.save()

    return redirect("request_detail", request_id=request_id)


def delete_request(request, request_id):
    # удаление заявки через SQL UPDATE
    if request.method == "POST":
        current_user = get_current_user()
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE requests SET status = 'deleted' WHERE id = %s AND user_id = %s",
                [request_id, current_user.id],
            )
        return redirect("request_list")
    return redirect("request_list")


def api_meters(request):
    """Возвращает список всех счетчиков в JSON"""
    try:
        meters = WaterMeter.objects.filter(is_active=True).values(
            "id",
            "address",
            "serial_number",
            "meter_type",
            "meter_model",
            "installation_date",
            "last_verified_reading",
            "photo_url",
            "setup_video_url",
        )
        return api_response_success(data=list(meters))
    except Exception as e:
        return api_response_error(f"Ошибка получения счетчиков: {str(e)}", status=500)


def api_meter_detail(request, meter_id):
    """Возвращает детали одного счетчика в JSON"""
    try:
        meter = WaterMeter.objects.get(id=meter_id, is_active=True)
        data = {
            "id": meter.id,
            "address": meter.address,
            "serial_number": meter.serial_number,
            "meter_type": meter.meter_type,
            "meter_model": meter.meter_model,
            "installation_date": meter.installation_date.strftime("%d.%m.%Y"),
            "last_verified_reading": meter.last_verified_reading,
            "photo_url": meter.photo_url,
            "setup_video_url": meter.setup_video_url,
        }
        return api_response_success(data=data)
    except WaterMeter.DoesNotExist:
        return api_response_error("Счетчик не найден", status=404)
    except Exception as e:
        return api_response_error(f"Ошибка получения счетчика: {str(e)}", status=500)


def api_requests(request):
    """Возвращает список всех заявок (кроме удаленных) в JSON"""
    try:
        current_user = User.objects.first()
        requests_list = Request.objects.filter(user=current_user).exclude(status="deleted").order_by("-created_at")

        result = []
        for req in requests_list:
            positions_count = ReadingPosition.objects.filter(request=req).count()
            result.append(
                {
                    "id": req.id,
                    "status": req.status,
                    "created_at": req.created_at.strftime("%d.%m.%Y %H:%M"),
                    "positions_count": positions_count,
                    "total_consumption": (float(req.total_consumption) if req.total_consumption else None),
                    "amount_to_pay": (float(req.amount_to_pay) if req.amount_to_pay else None),
                }
            )

        return api_response_success(data={"requests": result})
    except Exception as e:
        return api_response_error(f"Ошибка получения заявок: {str(e)}", status=500)


def api_request_detail(request, request_id):
    """Возвращает детали одной заявки в JSON"""
    try:
        current_user = User.objects.first()
        request_obj = Request.objects.get(id=request_id, user=current_user)

        # Получаем позиции
        positions = ReadingPosition.objects.filter(request=request_obj).select_related("water_meter")

        positions_data = []
        for pos in positions:
            positions_data.append(
                {
                    "water_meter__address": pos.water_meter.address,
                    "water_meter__meter_type": pos.water_meter.meter_type,
                    "water_meter__last_verified_reading": pos.water_meter.last_verified_reading,
                    "current_reading": pos.current_reading,
                    "consumption": pos.consumption,
                }
            )

        data = {
            "id": request_obj.id,
            "status": request_obj.status,
            "created_at": request_obj.created_at.strftime("%d.%m.%Y %H:%M"),
            "completed_at": (request_obj.completed_at.strftime("%d.%m.%Y %H:%M") if request_obj.completed_at else None),
            "positions": positions_data,
            "total_consumption": (float(request_obj.total_consumption) if request_obj.total_consumption else None),
            "amount_to_pay": (float(request_obj.amount_to_pay) if request_obj.amount_to_pay else None),
        }
        return api_response_success(data=data)
    except Request.DoesNotExist:
        return api_response_error("Заявка не найдена", status=404)
    except Exception as e:
        return api_response_error(f"Ошибка получения заявки: {str(e)}", status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_add_reading(request):
    """Добавление показаний (JSON API)"""
    try:
        data = json.loads(request.body)
        meter_id = data.get("meter_id")
        current_reading = data.get("current_reading")

        if not meter_id or not current_reading:
            return api_response_error("Не указаны meter_id или current_reading", status=400)

        current_user = User.objects.first()
        meter = get_object_or_404(WaterMeter, id=meter_id)

        # Находим или создаем черновик
        draft_request = Request.objects.filter(status="draft", user=current_user).first()
        if not draft_request:
            draft_request = Request.objects.create(status="draft", user=current_user)

        consumption = int(current_reading) - meter.last_verified_reading

        if consumption < 0:
            return api_response_error("Текущие показания не могут быть меньше предыдущих", status=400)

        # Проверяем существующую позицию
        existing = ReadingPosition.objects.filter(request=draft_request, water_meter=meter).first()

        if existing:
            existing.current_reading = current_reading
            existing.consumption = consumption
            existing.save()
        else:
            ReadingPosition.objects.create(
                request=draft_request,
                water_meter=meter,
                current_reading=current_reading,
                consumption=consumption,
            )

        return api_response_success(data={"request_id": draft_request.id}, message="Показания успешно добавлены")
    except json.JSONDecodeError:
        return api_response_error("Неверный формат JSON", status=400)
    except Exception as e:
        return api_response_error(str(e), status=400)


@csrf_exempt
@require_http_methods(["POST"])
def api_submit_request(request, request_id):
    """Отправка заявки (JSON API)"""
    try:
        current_user = User.objects.first()
        request_obj = Request.objects.get(id=request_id, user=current_user)
        if request_obj.status == "draft":
            request_obj.status = "submitted"
            request_obj.submitted_at = timezone.now()
            request_obj.save()
            return api_response_success(message="Заявка успешно отправлена")
        else:
            return api_response_error(f"Невозможно отправить заявку в статусе {request_obj.status}", status=400)
    except Request.DoesNotExist:
        return api_response_error("Заявка не найдена", status=404)
    except Exception as e:
        return api_response_error(str(e), status=500)


@csrf_exempt
@require_http_methods(["POST"])
def api_delete_request(request, request_id):
    """Удаление заявки через SQL UPDATE (JSON API)"""
    try:
        current_user = User.objects.first()
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE requests SET status = 'deleted' WHERE id = %s AND user_id = %s",
                [request_id, current_user.id],
            )
        return api_response_success(message="Заявка успешно удалена")
    except Exception as e:
        return api_response_error(str(e), status=500)
