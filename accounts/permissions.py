from rest_framework.permissions import BasePermission

class IsAdminUserRole(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and request.user.active_role == "ADMIN"
        )

class IsExhibitorWithProfile(BasePermission):
    """
    Permission class that checks:
    1. User is authenticated
    2. User's active_role is EXHIBITOR
    3. User has completed their exhibitor profile
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        
        if request.user.active_role != "EXHIBITOR":
            return False
        
        if not request.user.profile_completed:
            return False
        
        return True
    
    def handle_no_permission(self):
        from rest_framework.response import Response
        from rest_framework import status
        
        return Response(
            {"error": "Please complete your exhibitor profile first"},
            status=status.HTTP_403_FORBIDDEN
        )
