import json
import os
import uuid

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
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
    return User.objects.get(id=6)


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

    if current_user.is_admin:
        meters = WaterMeter.objects.filter(is_active=True)
    else:
        meters = WaterMeter.objects.filter(is_active=True, user=current_user)

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

@csrf_exempt
@require_http_methods(["POST", "OPTIONS"])
def add_reading(request):
    """Добавление показаний в черновик (JSON API)"""
    if request.method == "OPTIONS":
        return api_response_success(message="OK")
    
    try:
        data = json.loads(request.body)
        meter_id = data.get("meter_id")
        current_reading = data.get("current_reading")
        
        current_user = get_current_user()
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
        
        return api_response_success(data={"request_id": draft_request.id}, message="Показания добавлены")
    except Exception as e:
        return api_response_error(str(e), status=400)


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
    """GET список всех счетчиков с фильтрацией"""
    try:
        current_user = get_current_user()
        
        # Админ видит все счётчики, пользователь — только свои
        if current_user.is_admin:
            meters = WaterMeter.objects.filter(is_active=True)
        else:
            meters = WaterMeter.objects.filter(is_active=True, user=current_user)
        
        # фильтрация по адресу
        address = request.GET.get('address', '')
        if address:
            meters = meters.filter(address__icontains=address)
        
        data = list(meters.values(
            "id", "address", "serial_number", "meter_type",
            "meter_model", "installation_date", "last_verified_reading",
            "photo_url", "setup_video_url"
        ))
        return api_response_success(data=data)
    except Exception as e:
        return api_response_error(f"Ошибка получения счетчиков: {str(e)}", status=500)


def api_meter_detail(request, meter_id):
    """GET одна запись счетчика"""
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


@csrf_exempt
@require_http_methods(["POST"])
def api_meter_add(request):
    """POST добавление новой услуги (счетчика) с фото и видео"""
    try:
        address = request.POST.get('address')
        serial_number = request.POST.get('serial_number')
        meter_type = request.POST.get('meter_type')
        meter_model = request.POST.get('meter_model')
        installation_date = request.POST.get('installation_date')
        initial_reading = request.POST.get('initial_reading', 0)
        last_verified_reading = request.POST.get('last_verified_reading', 0)
        
        # загрузка фото
        photo = request.FILES.get('photo')
        photo_url = None
        if photo:
            ext = os.path.splitext(photo.name)[1]
            filename = f"imagers/meter_{uuid.uuid4().hex}{ext}"
            path = default_storage.save(filename, ContentFile(photo.read()))
            photo_url = f"http://localhost:9002/{settings.MINIO_BUCKET}/{path}"
        
        # загрузка видео
        video = request.FILES.get('video')
        video_url = None
        if video:
            ext = os.path.splitext(video.name)[1]
            filename = f"video/meter_{uuid.uuid4().hex}{ext}"
            path = default_storage.save(filename, ContentFile(video.read()))
            video_url = f"http://localhost:9002/{settings.MINIO_BUCKET}/{path}"
        
        current_user = get_current_user()
        
        meter = WaterMeter.objects.create(
            user=current_user,
            address=address,
            serial_number=serial_number,
            meter_type=meter_type,
            meter_model=meter_model,
            installation_date=installation_date,
            initial_reading=initial_reading,
            last_verified_reading=last_verified_reading,
            photo_url=photo_url,
            setup_video_url=video_url
        )
        
        return api_response_success(data={"id": meter.id}, message="Счётчик добавлен")
    except Exception as e:
        return api_response_error(str(e), status=400)


def api_cart(request):
    """GET иконка корзины: id черновика и количество услуг в нём"""
    current_user = get_current_user()
    draft = Request.objects.filter(status='draft', user=current_user).first()
    if not draft:
        return api_response_success(data={"request_id": None, "items_count": 0})
    
    items_count = ReadingPosition.objects.filter(request=draft).count()
    return api_response_success(data={"request_id": draft.id, "items_count": items_count})


def api_requests(request):
    """GET список заявок с фильтрацией по статусу и диапазону даты формирования"""
    try:
        current_user = get_current_user()
        
        # Админ видит все заявки, пользователь — только свои
        if current_user.is_admin:
            queryset = Request.objects.exclude(status='deleted')
        else:
            queryset = Request.objects.filter(user=current_user).exclude(status='deleted').exclude(status='draft')
        
        # фильтр по статусу
        status = request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        # фильтр по диапазону даты формирования (submitted_at)
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        if date_from:
            queryset = queryset.filter(submitted_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(submitted_at__lte=date_to)
        
        # формируем результат
        result = []
        for req in queryset:
            positions_count = ReadingPosition.objects.filter(request=req).count()
            result.append({
                "id": req.id,
                "status": req.status,
                "created_at": req.created_at.strftime("%d.%m.%Y %H:%M"),
                "submitted_at": req.submitted_at.strftime("%d.%m.%Y %H:%M") if req.submitted_at else None,
                "completed_at": req.completed_at.strftime("%d.%m.%Y %H:%M") if req.completed_at else None,
                "positions_count": positions_count,
                "total_consumption": float(req.total_consumption) if req.total_consumption else None,
                "amount_to_pay": float(req.amount_to_pay) if req.amount_to_pay else None,
                "comment": req.comment,
            })
        
        return api_response_success(data={"requests": result})
    except Exception as e:
        return api_response_error(f"Ошибка получения заявок: {str(e)}", status=500)


def api_request_detail(request, request_id):
    """GET одна запись заявки (поля заявки + её услуги с картинками)"""
    try:
        current_user = get_current_user()
        
        # Админ видит любую заявку, пользователь — только свою
        if current_user.is_admin:
            request_obj = get_object_or_404(Request, id=request_id)
        else:
            request_obj = get_object_or_404(Request, id=request_id, user=current_user)
        
        # получаем позиции с данными счетчиков
        positions = ReadingPosition.objects.filter(request=request_obj).select_related("water_meter")
        
        positions_data = []
        for pos in positions:
            positions_data.append({
                "id": pos.id,
                "water_meter__address": pos.water_meter.address,
                "water_meter__meter_type": pos.water_meter.meter_type,
                "water_meter__last_verified_reading": pos.water_meter.last_verified_reading,
                "water_meter__photo_url": pos.water_meter.photo_url,
                "current_reading": pos.current_reading,
                "consumption": pos.consumption,
        })
        
        data = {
            "id": request_obj.id,
            "status": request_obj.status,
            "created_at": request_obj.created_at.strftime("%d.%m.%Y %H:%M"),
            "submitted_at": request_obj.submitted_at.strftime("%d.%m.%Y %H:%M") if request_obj.submitted_at else None,
            "completed_at": request_obj.completed_at.strftime("%d.%m.%Y %H:%M") if request_obj.completed_at else None,
            "positions": positions_data,
            "total_consumption": float(request_obj.total_consumption) if request_obj.total_consumption else None,
            "amount_to_pay": float(request_obj.amount_to_pay) if request_obj.amount_to_pay else None,
            "comment": request_obj.comment,
        }
        return api_response_success(data=data)
    except Request.DoesNotExist:
        return api_response_error("Заявка не найдена", status=404)
    except Exception as e:
        return api_response_error(f"Ошибка получения заявки: {str(e)}", status=500)


@csrf_exempt
@require_http_methods(["PUT"])
def api_request_update(request, request_id):
    """PUT изменение полей заявки (только для черновика)"""
    try:
        data = json.loads(request.body)
        current_user = get_current_user()
        req = get_object_or_404(Request, id=request_id, user=current_user, status='draft')
        
        # разрешённые для изменения поля
        if 'comment' in data:
            req.comment = data['comment']
        
        req.save()
        return api_response_success(message="Заявка обновлена")
    except Exception as e:
        return api_response_error(str(e), status=400)


@csrf_exempt
@require_http_methods(["PUT"])
def api_submit_request(request, request_id):
    current_user = get_current_user()
    req = get_object_or_404(Request, id=request_id, user=current_user, status='draft')
    
    positions = ReadingPosition.objects.filter(request=req)
    if not positions.exists():
        return api_response_error("Нельзя сформировать пустую заявку", status=400)
    
    total_consumption = sum(p.consumption for p in positions)
    total_cost = total_consumption * 50
    
    req.status = 'submitted'
    req.submitted_at = timezone.now()
    req.total_consumption = total_consumption
    req.amount_to_pay = total_cost
    req.save()
    
    return api_response_success(message="Заявка сформирована", data={"request_id": req.id})

@csrf_exempt
@require_http_methods(["PUT"])
def api_complete_request(request, request_id):
    """PUT завершить заявку (только для модератора)"""
    try:
        current_user = get_current_user()
        
        # Проверка: только модератор
        if not current_user.is_admin:
            return api_response_error("Доступ только для модератора", status=403)
        
        req = get_object_or_404(Request, id=request_id, status='submitted')
        req.status = 'completed'
        req.completed_at = timezone.now()
        req.save()
        
        return api_response_success(data={"request_id": req.id, "status": req.status}, message="Заявка завершена")
    except Exception as e:
        return api_response_error(str(e), status=400)


@csrf_exempt
@require_http_methods(["PUT"])
def api_reject_request(request, request_id):
    """PUT отклонить заявку (только для модератора)"""
    try:
        current_user = get_current_user()
        
        # Проверка: только модератор
        if not current_user.is_admin:
            return api_response_error("Доступ только для модератора", status=403)
        
        req = get_object_or_404(Request, id=request_id, status='submitted')
        req.status = 'rejected'
        req.completed_at = timezone.now()
        req.save()
        
        return api_response_success(data={"request_id": req.id, "status": req.status}, message="Заявка отклонена")
    except Exception as e:
        return api_response_error(str(e), status=400)


@csrf_exempt
@require_http_methods(["DELETE"])
def api_delete_request(request, request_id):
    try:
        current_user = get_current_user()
        req = get_object_or_404(Request, id=request_id, user=current_user)
        
        time_diff = timezone.now() - req.submitted_at if req.submitted_at else None
        can_edit = (
            req.status == 'draft' or 
            (req.status == 'submitted' and time_diff and time_diff.total_seconds() <= 3600)
        )
        
        print(f"DEBUG DELETE: status={req.status}, submitted_at={req.submitted_at}, time_diff={time_diff}, can_edit={can_edit}")
        
        if not can_edit:
            return api_response_error("Нельзя удалить: заявка не редактируема", status=400)
        
        ReadingPosition.objects.filter(request=req).delete()
        req.status = 'deleted'
        req.save()
        return api_response_success(message="Заявка удалена")
    except Exception as e:
        return api_response_error(str(e), status=400)


@csrf_exempt
@require_http_methods(["POST"])
def api_position_add(request):
    try:
        data = json.loads(request.body)
        meter_id = data.get('meter_id')
        current_reading = data.get('current_reading')
        request_id = data.get('request_id')  # может быть None
        
        current_user = get_current_user()
        meter = get_object_or_404(WaterMeter, id=meter_id)
        
        # Если передан request_id — используем его, иначе ищем черновик
        if request_id:
            draft = get_object_or_404(Request, id=request_id, user=current_user, status='draft')
        else:
            draft = Request.objects.filter(status='draft', user=current_user).first()
            if not draft:
                draft = Request.objects.create(status='draft', user=current_user)
        
        consumption = int(current_reading) - meter.last_verified_reading
        if consumption < 0:
            return api_response_error("Текущие показания не могут быть меньше предыдущих", status=400)
        
        existing = ReadingPosition.objects.filter(request=draft, water_meter=meter).first()
        if existing:
            return api_response_error("Услуга уже добавлена в заявку", status=400)
        
        position = ReadingPosition.objects.create(
            request=draft,
            water_meter=meter,
            current_reading=current_reading,
            consumption=consumption
        )
        
        return api_response_success(data={"position_id": position.id, "request_id": draft.id}, message="Услуга добавлена")
    except Exception as e:
        return api_response_error(str(e), status=400)


@csrf_exempt
@require_http_methods(["PUT"])
def api_position_update(request, position_id):
    """PUT изменение поля м-м (текущие показания) с проверкой времени"""
    try:
        data = json.loads(request.body)
        current_reading = data.get('current_reading')
        
        position = get_object_or_404(ReadingPosition, id=position_id)
        request_obj = position.request
        
        # Проверка: можно редактировать только в течение часа после создания ИЛИ если черновик
        time_diff_created = timezone.now() - position.created_at
        time_diff_submitted = timezone.now() - request_obj.submitted_at if request_obj.submitted_at else None
        
        can_edit = (
            request_obj.status == 'draft' or 
            (request_obj.status == 'submitted' and time_diff_submitted and time_diff_submitted.total_seconds() <= 3600)
        )
        
        # Дополнительная проверка: в течение часа после создания позиции
        if time_diff_created.total_seconds() > 3600:
            return api_response_error("Редактирование показаний доступно только в течение часа после создания", status=403)
        
        if not can_edit:
            return api_response_error("Нельзя изменить: заявка не редактируема", status=400)
        
        if position.request.status != 'draft' and position.request.status != 'submitted':
            return api_response_error("Нельзя изменить позицию в не черновике и не отправленной заявке", status=400)
        
        consumption = int(current_reading) - position.water_meter.last_verified_reading
        if consumption < 0:
            return api_response_error("Текущие показания не могут быть меньше предыдущих", status=400)
        
        position.current_reading = current_reading
        position.consumption = consumption
        position.save()
        
        return api_response_success(message="Позиция обновлена")
    except Exception as e:
        return api_response_error(str(e), status=400)


@csrf_exempt
@require_http_methods(["DELETE"])
def api_position_delete(request, position_id):
    try:
        position = get_object_or_404(ReadingPosition, id=position_id)
        request_obj = position.request
        time_diff = timezone.now() - request_obj.submitted_at if request_obj.submitted_at else None
        
        can_edit = (
            request_obj.status == 'draft' or 
            (request_obj.status == 'submitted' and time_diff and time_diff.total_seconds() <= 3600)
        )
        
        print(f"DEBUG DELETE POS: status={request_obj.status}, submitted_at={request_obj.submitted_at}, time_diff={time_diff}, can_edit={can_edit}")
        
        if not can_edit:
            return api_response_error("Нельзя удалить: заявка не редактируема", status=400)
        
        position.delete()
        return api_response_success(message="Позиция удалена")
    except Exception as e:
        return api_response_error(str(e), status=400)

@csrf_exempt
@require_http_methods(["POST"])
def api_register(request):
    """POST регистрация нового пользователя"""
    try:
        data = json.loads(request.body)
        username = data.get('username')
        email = data.get('email')
        first_name = data.get('first_name', '')
        last_name = data.get('last_name', '')
        phone = data.get('phone', '')
        
        if User.objects.filter(username=username).exists():
            return api_response_error("Пользователь с таким именем уже существует", status=400)
        
        user = User.objects.create(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            is_active=True
        )
        return api_response_success(data={"id": user.id, "username": user.username}, message="Пользователь зарегистрирован")
    except Exception as e:
        return api_response_error(str(e), status=400)
    
def check_moderator(user):
    if not user.is_admin:
        return api_response_error("Доступ только для модератора", status=403)
    return None


@csrf_exempt
@require_http_methods(["POST"])
def api_login(request):
    """POST аутентификация (заглушка для 4 лабы)"""
    return api_response_success(message="Аутентификация будет в 4 лабе", data={"token": "fake-token"})


@csrf_exempt
@require_http_methods(["POST"])
def api_logout(request):
    """POST деавторизация (заглушка для 4 лабы)"""
    return api_response_success(message="Деавторизация будет в 4 лабе")