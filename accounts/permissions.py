from rest_framework.permissions import SAFE_METHODS, BasePermission


class HasStore(BasePermission):
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.store_id)


class IsAdminRole(BasePermission):
    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and u.store_id and u.role == "ADMIN")


class IsAdminOrReadOnlyForCashier(BasePermission):
    """Admin: full access. Cashier: read-only."""

    def has_permission(self, request, view):
        u = request.user
        if not (u and u.is_authenticated and u.store_id):
            return False
        return request.method in SAFE_METHODS or u.role == "ADMIN"
