import graphene
from django.contrib.auth import authenticate
from django.contrib.auth.models import Permission

from django.conf import settings
from graphql import GraphQLError

from nxtbn.core.admin_permissions import gql_store_admin_required
from nxtbn.users.admin_types import PermissionType
from nxtbn.users.api.storefront.serializers import JwtBasicUserSerializer
from nxtbn.users.models import User
from nxtbn.users.utils.jwt_utils import JWTManager

class AdminTokenType(graphene.ObjectType):
    access = graphene.String()
    refresh = graphene.String()
    expiresIn = graphene.Int()
    refreshExpiresIn = graphene.Int()

class AdminLoginUserType(graphene.ObjectType):
    id = graphene.ID()
    email = graphene.String()
    username = graphene.String()
    firstName = graphene.String()
    lastName = graphene.String()
    full_name = graphene.String()
    role = graphene.String()

class AdminLoginResponse(graphene.ObjectType):
    user = graphene.Field(AdminLoginUserType)
    storeUrl = graphene.String()
    version = graphene.String()
    base_currency = graphene.String()
    token = graphene.Field(AdminTokenType)

class AdminLoginMutation(graphene.Mutation):
    class Arguments:
        email = graphene.String(required=True)
        password = graphene.String(required=True)

    login = graphene.Field(AdminLoginResponse)

    def mutate(self, info, email, password):
        jwt_manager = JWTManager()

        user = authenticate(email=email, password=password)
        if user:
            if not user.is_staff:
                raise Exception("Only staff members can log in.")
            
            if not user.is_active:
                raise Exception("User is not active.")

            access_token = jwt_manager.generate_access_token(user)
            refresh_token = jwt_manager.generate_refresh_token(user)

            user_data = JwtBasicUserSerializer(user).data

            response = AdminLoginResponse(
                user=AdminLoginUserType(**user_data),
                storeUrl=settings.STORE_URL,
                version=settings.VERSION,
                base_currency=settings.BASE_CURRENCY,
                token=AdminTokenType(
                    access=access_token,
                    refresh=refresh_token,
                    expiresIn=jwt_manager.access_token_expiration_seconds,
                    refreshExpiresIn=jwt_manager.refresh_token_expiration_seconds
                )
            )

            return AdminLoginMutation(login=response)
        else:
            raise Exception("Invalid credentials")
        



class AdminTokenRefreshMutation(graphene.Mutation):
    class Arguments:
        refresh_token = graphene.String(required=True)

    refresh = graphene.Field(AdminLoginResponse)

    def mutate(self, info, refresh_token):
        jwt_manager = JWTManager()

        # Verify refresh token
        user = jwt_manager.verify_jwt_token(refresh_token)

        if user:
            access_token = jwt_manager.generate_access_token(user)
            new_refresh_token = jwt_manager.generate_refresh_token(user)

            user_data = JwtBasicUserSerializer(user).data

            response = AdminLoginResponse(
                user=AdminLoginUserType(**user_data),
                storeUrl=settings.STORE_URL,
                version=settings.VERSION,
                base_currency=settings.BASE_CURRENCY,
                token=AdminTokenType(
                    access=access_token,
                    refresh=new_refresh_token,
                    expiresIn=jwt_manager.access_token_expiration_seconds,
                    refreshExpiresIn=jwt_manager.refresh_token_expiration_seconds
                )
            )

            return AdminTokenRefreshMutation(refresh=response)
        else:
            raise Exception("Invalid or expired refresh token")
        



class TogglePermissionMutation(graphene.Mutation):
    class Arguments:
        user_id = graphene.Int(required=True)
        permission_codename = graphene.String(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    @gql_store_admin_required
    def mutate(self, info, user_id, permission_codename):
        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            return TogglePermissionMutation(success=False, message="User not found")
        

        if user.is_superuser or user.is_store_admin:
            raise GraphQLError("Superusers and store administrators have all permissions by default and their permissions cannot be modified.")
        
        if not user.is_active or not user.is_staff:
            raise GraphQLError("User is not an active staff member.")

        try:
            permission = Permission.objects.get(codename=permission_codename)
        except Permission.DoesNotExist:
            return TogglePermissionMutation(success=False, message="Permission not found")

        if user.user_permissions.filter(id=permission.id).exists():
            # If the permission is already assigned, remove it
            user.user_permissions.remove(permission)
            return TogglePermissionMutation(success=True, message="Permission removed successfully")
        else:
            # Otherwise, add the permission
            user.user_permissions.add(permission)
            return TogglePermissionMutation(success=True, message="Permission assigned successfully")



class ChangeUserPasswordMutation(graphene.Mutation):
    class Arguments:
        user_id = graphene.ID(required=True)
        password = graphene.String(required=True)
        confirm_password = graphene.String(required=True)

    success = graphene.Boolean()
    message = graphene.String()

    def mutate(self, info, user_id, password, confirm_password):

        try:
            user = User.objects.get(id=user_id)
        except User.DoesNotExist:
            raise GraphQLError("User not found")

        if password != confirm_password:
            raise GraphQLError("Passwords do not match")

        user.set_password(password)
        user.save()
        
        return ChangeUserPasswordMutation(success=True, message="Password changed successfully")

class AdminUserMutation(graphene.ObjectType):
    login = AdminLoginMutation.Field()
    refresh_token = AdminTokenRefreshMutation.Field()
    toggle_permission = TogglePermissionMutation.Field()
    change_user_password = ChangeUserPasswordMutation.Field()

    
