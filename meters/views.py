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
from rest_framework.decorators import api_view
from drf_spectacular.utils import extend_schema, OpenApiResponse

from .models import ReadingPosition, Request, User, WaterMeter
from .serializers import (
    LoginSerializer, RegisterSerializer, PositionAddSerializer,
    PositionUpdateSerializer, RequestUpdateSerializer, MeterAddSerializer
)


# получение текущего пользователя (для заявок, потом понадобится)
def get_current_user(request=None):
    if request and hasattr(request, 'session'):
        user_id = request.session.get('user_id')
        print(f"get_current_user: user_id={user_id}")
        if user_id:
            try:
                return User.objects.get(id=user_id)
            except User.DoesNotExist:
                return None
    return None


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


def meter_list(request):
    search_query = request.GET.get("search", "")
    meters = WaterMeter.objects.filter(is_active=True)
    if search_query:
        meters = meters.filter(address__icontains=search_query)

    current_user = get_current_user(request)
    if current_user.is_admin:
        meters = WaterMeter.objects.filter(is_active=True)
    else:
        meters = WaterMeter.objects.filter(is_active=True, user=current_user)

    draft_request = Request.objects.filter(status="draft", user=current_user).first()
    if draft_request:
        draft_request.positions_count = ReadingPosition.objects.filter(request=draft_request).count()

    context = {
        "meters": meters,
        "draft_request": draft_request,
        "search_query": search_query,
    }
    return render(request, "meters/meter_list.html", context)


def meter_detail(request, meter_id):
    meter = get_object_or_404(WaterMeter, id=meter_id, is_active=True)
    return render(request, "meters/meter_detail.html", {"meter": meter})


def request_list(request):
    current_user = get_current_user(request)
    requests_list = Request.objects.filter(user=current_user).exclude(status="deleted").order_by("-created_at")
    for req in requests_list:
        req.positions_count = ReadingPosition.objects.filter(request=req).count()
    return render(request, "meters/request_list.html", {"requests": requests_list})


def request_detail(request, request_id):
    current_user = get_current_user(request)
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
    if request.method == "OPTIONS":
        return api_response_success(message="OK")
    try:
        data = json.loads(request.body)
        meter_id = data.get("meter_id")
        current_reading = data.get("current_reading")
        current_user = get_current_user(request)
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
    current_user = get_current_user(request)
    request_obj = get_object_or_404(Request, id=request_id, user=current_user)
    if request_obj.status == "draft":
        request_obj.status = "submitted"
        request_obj.submitted_at = timezone.now()
        request_obj.save()
    return redirect("request_detail", request_id=request_id)


def delete_request(request, request_id):
    if request.method == "POST":
        current_user = get_current_user(request)
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE requests SET status = 'deleted' WHERE id = %s AND user_id = %s",
                [request_id, current_user.id],
            )
        return redirect("request_list")
    return redirect("request_list")


@extend_schema(
    responses={200: OpenApiResponse(description='Успешный ответ')},
    operation_id='meters_list'
)
@api_view(['GET'])
def api_meters(request):

    try:
        current_user = get_current_user(request)
        if current_user and current_user.is_admin:
            meters = WaterMeter.objects.filter(is_active=True)
        else:
            meters = WaterMeter.objects.filter(is_active=True, user=current_user) if current_user else WaterMeter.objects.filter(is_active=True)
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


@api_view(['GET'])
def api_meter_detail(request, meter_id):

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


@extend_schema(request=MeterAddSerializer)
@api_view(['POST'])
@csrf_exempt
@require_http_methods(["POST"])
def api_meter_add(request):

    try:
        address = request.POST.get('address')
        serial_number = request.POST.get('serial_number')
        meter_type = request.POST.get('meter_type')
        meter_model = request.POST.get('meter_model')
        installation_date = request.POST.get('installation_date')
        initial_reading = request.POST.get('initial_reading', 0)
        last_verified_reading = request.POST.get('last_verified_reading', 0)

        
        photo = request.FILES.get('photo')
        photo_url = None
        if photo:
            ext = os.path.splitext(photo.name)[1]
            filename = f"imagers/meter_{uuid.uuid4().hex}{ext}"
            path = default_storage.save(filename, ContentFile(photo.read()))
            photo_url = f"http://localhost:9002/{settings.MINIO_BUCKET}/{path}"

        
        video = request.FILES.get('video')
        video_url = None
        if video:
            ext = os.path.splitext(video.name)[1]
            filename = f"video/meter_{uuid.uuid4().hex}{ext}"
            path = default_storage.save(filename, ContentFile(video.read()))
            video_url = f"http://localhost:9002/{settings.MINIO_BUCKET}/{path}"
        
        current_user = get_current_user(request)
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


@api_view(['GET'])
def api_cart(request):
    current_user = get_current_user(request)
    draft = Request.objects.filter(status='draft', user=current_user).first()
    if not draft:
        return api_response_success(data={"request_id": None, "items_count": 0})
    
    items_count = ReadingPosition.objects.filter(request=draft).count()
    return api_response_success(data={"request_id": draft.id, "items_count": items_count})


@api_view(['GET'])
def api_requests(request):
    
    try:
        current_user = get_current_user(request)
        
        # Проверка: если пользователь не авторизован — возвращаем 403
        if not current_user:
            return api_response_error("Не авторизован", status=403)
        
        if current_user and current_user.is_admin:
            queryset = Request.objects.exclude(status='deleted')
        else:
            queryset = Request.objects.filter(user=current_user).exclude(status='deleted')
        
        status = request.GET.get('status')
        if status:
            queryset = queryset.filter(status=status)
        
        date_from = request.GET.get('date_from')
        date_to = request.GET.get('date_to')
        if date_from:
            queryset = queryset.filter(submitted_at__gte=date_from)
        if date_to:
            queryset = queryset.filter(submitted_at__lte=date_to)
        
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


@api_view(['GET'])
def api_request_detail(request, request_id):

    try:
        current_user = get_current_user(request)
        if current_user and current_user.is_admin:
            request_obj = get_object_or_404(Request, id=request_id)
        else:
            request_obj = get_object_or_404(Request, id=request_id, user=current_user)
        

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


@extend_schema(request=RequestUpdateSerializer)
@api_view(['PUT'])
@csrf_exempt
@require_http_methods(["PUT"])
def api_request_update(request, request_id):
    try:
        data = json.loads(request.body)
        current_user = get_current_user(request)
        req = get_object_or_404(Request, id=request_id, user=current_user, status='draft')
        if 'comment' in data:
            req.comment = data['comment']
        req.save()
        return api_response_success(message="Заявка обновлена")
    except Exception as e:
        return api_response_error(str(e), status=400)


@api_view(['PUT'])
@csrf_exempt
@require_http_methods(["PUT"])
def api_submit_request(request, request_id):
    current_user = get_current_user(request)
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


@api_view(['PUT'])
@csrf_exempt
@require_http_methods(["PUT"])
def api_complete_request(request, request_id):
    try:
        current_user = get_current_user(request)
        if not current_user or not current_user.is_admin:
            return api_response_error("Доступ только для модератора", status=403)
        req = get_object_or_404(Request, id=request_id, status='submitted')
        req.status = 'completed'
        req.completed_at = timezone.now()
        req.save()
        return api_response_success(data={"request_id": req.id, "status": req.status}, message="Заявка завершена")
    except Exception as e:
        return api_response_error(str(e), status=400)


@api_view(['PUT'])
@csrf_exempt
@require_http_methods(["PUT"])
def api_reject_request(request, request_id):
    try:
        current_user = get_current_user(request)
        if not current_user or not current_user.is_admin:
            return api_response_error("Доступ только для модератора", status=403)
        req = get_object_or_404(Request, id=request_id, status='submitted')
        req.status = 'rejected'
        req.completed_at = timezone.now()
        req.save()
        return api_response_success(data={"request_id": req.id, "status": req.status}, message="Заявка отклонена")
    except Exception as e:
        return api_response_error(str(e), status=400)


@api_view(['DELETE'])
@csrf_exempt
@require_http_methods(["DELETE"])
def api_delete_request(request, request_id):
    try:
        current_user = get_current_user(request)
        
        # Если админ — может удалить любую заявку
        if current_user.is_admin:
            req = get_object_or_404(Request, id=request_id)
        else:
            req = get_object_or_404(Request, id=request_id, user=current_user)
        
        # Черновик можно удалить всегда
        if req.status == 'draft':
            ReadingPosition.objects.filter(request=req).delete()
            req.status = 'deleted'
            req.save()
            return api_response_success(message="Черновик удалён")
        
        # Отправленную заявку можно удалить только в течение часа
        if req.status == 'submitted' and req.submitted_at:
            time_diff = timezone.now() - req.submitted_at
            if time_diff.total_seconds() <= 3600:
                ReadingPosition.objects.filter(request=req).delete()
                req.status = 'deleted'
                req.save()
                return api_response_success(message="Заявка удалена")
            else:
                return api_response_error("Нельзя удалить: прошло больше часа", status=400)
        
        return api_response_error("Нельзя удалить заявку в статусе " + req.status, status=400)
    except Exception as e:
        return api_response_error(str(e), status=400)


@extend_schema(request=PositionAddSerializer)
@api_view(['POST'])
@csrf_exempt
@require_http_methods(["POST"])
def api_position_add(request):
    try:
        data = json.loads(request.body)
        meter_id = data.get('meter_id')
        current_reading = data.get('current_reading')
        request_id = data.get('request_id')
        
        current_user = get_current_user(request)
        meter = get_object_or_404(WaterMeter, id=meter_id)
        
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


@extend_schema(request=PositionUpdateSerializer)
@api_view(['PUT'])
@csrf_exempt
@require_http_methods(["PUT"])
def api_position_update(request, position_id):
    try:
        data = json.loads(request.body)
        current_reading = data.get('current_reading')
        
        position = get_object_or_404(ReadingPosition, id=position_id)
        request_obj = position.request
        
        if position.request.status != 'draft':
            return api_response_error("Нельзя изменить: заявка не в черновике", status=400)
        
        if request_obj.status == 'submitted' and request_obj.submitted_at:
            if timezone.is_naive(request_obj.submitted_at):
                submitted_at_aware = timezone.make_aware(request_obj.submitted_at)
            else:
                submitted_at_aware = request_obj.submitted_at
            time_diff_submitted = timezone.now() - submitted_at_aware
            can_edit = time_diff_submitted.total_seconds() <= 3600
        else:
            can_edit = (request_obj.status == 'draft')
        
        if not can_edit:
            return api_response_error("Нельзя изменить: заявка не редактируема", status=400)
        
        consumption = int(current_reading) - position.water_meter.last_verified_reading
        if consumption < 0:
            return api_response_error("Текущие показания не могут быть меньше предыдущих", status=400)
        
        position.current_reading = current_reading
        position.consumption = consumption
        position.save()
        return api_response_success(message="Позиция обновлена")
    except Exception as e:
        return api_response_error(str(e), status=400)


@api_view(['DELETE'])
@csrf_exempt
@require_http_methods(["DELETE"])
def api_position_delete(request, position_id):
    try:
        position = get_object_or_404(ReadingPosition, id=position_id)
        if position.request.status != 'draft':
            return api_response_error("Нельзя удалить: заявка не в черновике", status=400)
        position.delete()
        return api_response_success(message="Позиция удалена")
    except Exception as e:
        return api_response_error(str(e), status=400)


@extend_schema(request=RegisterSerializer)
@api_view(['POST'])
@csrf_exempt
@require_http_methods(["POST"])
def api_register(request):
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


import hashlib


@extend_schema(request=LoginSerializer)
@api_view(['POST'])
@csrf_exempt
@require_http_methods(["POST"])
def api_login(request):
    try:
        data = json.loads(request.body)
        username = data.get('username')
        password = data.get('password')
        
        # Хешируем введённый пароль MD5
        hashed_password = hashlib.md5(password.encode()).hexdigest()
        
        try:
            user = User.objects.get(username=username)
            if user.password != hashed_password:
                return api_response_error("Неверный пароль", status=401)
        except User.DoesNotExist:
            return api_response_error("Пользователь не найден", status=401)
        
        request.session['user_id'] = user.id
        request.session['is_admin'] = user.is_admin
        
        return api_response_success(data={
            "user_id": user.id,
            "username": user.username,
            "is_admin": user.is_admin
        }, message="Успешный вход")
    except Exception as e:
        return api_response_error(str(e), status=400)


@api_view(['POST'])
@csrf_exempt
@require_http_methods(["POST"])
def api_logout(request):
    request.session.flush()
    return api_response_success(message="Выход выполнен")


def get_current_user_from_session(request):
    user_id = request.session.get('user_id')
    if user_id:
        try:
            return User.objects.get(id=user_id)
        except User.DoesNotExist:
            return None
    return None