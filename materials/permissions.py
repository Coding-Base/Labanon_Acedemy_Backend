# backend/materials/permissions.py

from rest_framework import permissions


class IsAdminForMaterials(permissions.BasePermission):
    """
    Only Master Admin can create, edit, or delete materials.
    Anyone can view published materials.
    """
    
    def has_permission(self, request, view):
        # GET/HEAD/OPTIONS - anyone can view published materials
        if request.method in permissions.SAFE_METHODS:
            return True
        
        # POST/PATCH/DELETE - admin only
        return (
            request.user 
            and request.user.is_authenticated 
            and request.user.is_staff 
            and request.user.is_superuser
        )
    
    def has_object_permission(self, request, view, obj):
        # GET - anyone can view published
        if request.method in permissions.SAFE_METHODS:
            return obj.is_published
        
        # PUT/PATCH/DELETE - admin only
        return (
            request.user 
            and request.user.is_authenticated 
            and request.user.is_staff 
            and request.user.is_superuser
        )


class CanAccessMaterial(permissions.BasePermission):
    """
    User can download material only if:
    1. Material is free (price = 0)
    2. User has purchased the material (MaterialPurchase exists)
    """
    
    def has_object_permission(self, request, view, obj):
        # Check if user is authenticated
        if not request.user or not request.user.is_authenticated:
            return False
        
        # Free materials - all authenticated users can access
        if obj.is_free:
            return True
        
        # Paid materials - check if user has purchase
        return obj.purchases.filter(user=request.user).exists()
