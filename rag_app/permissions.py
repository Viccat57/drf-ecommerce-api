from django.conf import settings
from rest_framework.exceptions import APIException
from rest_framework.permissions import BasePermission, SAFE_METHODS


class AIDisabled(APIException):
    status_code = 503
    default_detail = "El asistente de IA está desactivado."
    default_code = "ai_disabled"


class AIEnabled(BasePermission):
    def has_permission(self, request, view):
        if not settings.AI_ENABLED:
            raise AIDisabled()
        return True

class IsReviewAuthorOrStaff(BasePermission):
    def has_object_permission(self, request, view, obj):
        if request.method in SAFE_METHODS:
            return True
        return obj.user_id == request.user.id or request.user.is_staff