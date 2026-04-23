from rest_framework import permissions

class IsOwnerOrReadOnly(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in permissions.SAFE_METHODS:
            return True
        # Получаем пользователя из сессии
        user_id = request.session.get('user_id')
        if not user_id:
            return False
        return obj.user_id == user_id

class IsModerator(permissions.BasePermission):
    def has_permission(self, request, view):
        user_id = request.session.get('user_id')
        if not user_id:
            return False
        from .models import User
        try:
            user = User.objects.get(id=user_id)
            return user.is_admin
        except User.DoesNotExist:
            return False

class IsAuthenticatedAndOwner(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        user_id = request.session.get('user_id')
        if not user_id:
            return False
        return obj.user_id == user_id