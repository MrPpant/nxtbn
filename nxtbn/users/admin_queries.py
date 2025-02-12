import graphene

from nxtbn.users.admin_types import AdminUserType, PermissionType
from django.contrib.auth.models import Permission
from graphene_django.filter import DjangoFilterConnectionField

from nxtbn.users.models import User


class UserAdminQuery(graphene.ObjectType):
    users = DjangoFilterConnectionField(AdminUserType)
    user = graphene.Field(AdminUserType, id=graphene.Int(required=True))
    permissions = graphene.List(PermissionType, search=graphene.String(required=True), user_id=graphene.Int(required=True))

    def resolve_users(self, info, **kwargs):
        return User.objects.filter(is_staff=True)
    
    def resolve_user(self, info, id):
        try:
            user = User.objects.get(id=id)
        except User.DoesNotExist:
            raise Exception("User not found")
        
        return user

    def resolve_permissions(self, info, search, user_id):
        # Get the user by the provided user_id
        try:
            user = User.objects.prefetch_related('user_permissions').get(id=user_id)
        except User.DoesNotExist:
            return []  # If the user doesn't exist, return an empty list

        # Retrieve all permissions from the database
        permissions = Permission.objects.filter(name__icontains=search)

        # Create a set of user's permissions for quick lookup
        user_permissions = set(user.user_permissions.all())

        # Create a list of PermissionType objects with the user permission check
        permission_data = [
            PermissionType(
                codename=permission.codename,
                name=permission.name,
                has_assigned=permission in user_permissions  # Check if the user has the permission
            )
            for permission in permissions
        ]
        return permission_data
