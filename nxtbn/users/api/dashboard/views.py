from django.conf import settings
from rest_framework import generics, status
from rest_framework.decorators import action
from rest_framework import viewsets
from rest_framework.response import Response
from django.utils.translation import gettext_lazy as _
from rest_framework.permissions import AllowAny
from django.contrib.auth import authenticate
from nxtbn.core.admin_permissions import CommonPermissions, GranularPermission, IsStoreStaff
from nxtbn.core.enum_perms import PermissionsEnum
from nxtbn.core.paginator import NxtbnPagination
from nxtbn.users import UserRole
from nxtbn.users.models import User
from nxtbn.users.api.dashboard.serializers import CustomerSerializer, DashboardLoginSerializer, MeSerializer, UserMututionalSerializer, UserSerializer, CustomerWithAddressSerializer, CustomerUpdateSerializer
from nxtbn.users.api.dashboard.serializers import DashboardLoginSerializer, PasswordChangeSerializer
from nxtbn.users.api.storefront.serializers import JwtBasicUserSerializer
from nxtbn.users.api.storefront.views import LogoutView
from nxtbn.users.utils.jwt_utils import JWTManager
from nxtbn.users.models import User
from nxtbn.order.models import Address
from nxtbn.users.api.dashboard.serializers import AddressMutationalSerializer

from rest_framework import filters as drf_filters
import django_filters
from django_filters import rest_framework as filters


class LoginView(generics.GenericAPIView):
    permission_classes = (AllowAny,)
    serializer_class = DashboardLoginSerializer
    authentication_classes = []

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.jwt_manager = JWTManager()

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        email = request.data.get("email")
        password = request.data.get("password")

        user = authenticate(email=email, password=password)
        if user:
            if not user.is_staff:
                return Response({"detail": _("Only staff members can log in.")}, status=status.HTTP_403_FORBIDDEN)
                
            access_token = self.jwt_manager.generate_access_token(user)
            refresh_token = self.jwt_manager.generate_refresh_token(user)

            user_data = JwtBasicUserSerializer(user).data

            response =  Response(
                {
                    "user": user_data,
                    'store_url': settings.STORE_URL,
                    'VERSION': settings.VERSION,
                    "token": {
                        "access": access_token,
                        "refresh": refresh_token,
                        "expires_in": self.jwt_manager.access_token_expiration_seconds,
                        "refresh_expires_in": self.jwt_manager.refresh_token_expiration_seconds,
                    },
                },
                status=status.HTTP_200_OK,
            )

            response.set_cookie(
                key=self.jwt_manager.access_token_cookie_name,
                value=access_token,
                httponly=True,  # Make in-accessible via JavaScript (recommended)
                secure=True,
                samesite="None",  # Options: 'Strict', 'Lax', 'None'
                max_age=self.jwt_manager.access_token_expiration,
            )
            response.set_cookie(
                key=self.jwt_manager.refresh_token_cookie_name,
                value=refresh_token,
                httponly=True,  # Make in-accessible via JavaScript (recommended)
                secure=True,
                samesite="None",  # Options: 'Strict', 'Lax', 'None'
                max_age=self.jwt_manager.refresh_token_expiration,
            )

            return response

        return Response({"detail": _("Invalid credentials")}, status=status.HTTP_400_BAD_REQUEST)



class DashboardLogoutView(LogoutView):
    pass

#=========================================
# Authentication related views end here
#=========================================



class CustomerFilter(filters.FilterSet):
    username = filters.CharFilter(field_name='username', lookup_expr='icontains')
    date_joined = filters.DateFromToRangeFilter(field_name='date_joined')

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'date_joined',
        ]


class CustomerFilterMixin:
    filter_backends = [
        django_filters.rest_framework.DjangoFilterBackend,
        drf_filters.SearchFilter,
        drf_filters.OrderingFilter
    ] 
    search_fields = [
        'id',
        'first_name',
        'last_name',
        'username',
        'email',
    ]
    ordering_fields = [
        'username',
        'date_joined',
    ]
    filterset_class = CustomerFilter

    def get_queryset(self):
        return User.objects.filter(role=UserRole.CUSTOMER)
    

class CustomerListAPIView(CustomerFilterMixin, generics.ListAPIView):
    permission_classes = (GranularPermission,)
    model = User
    required_perm = PermissionsEnum.CAN_READ_CUSTOMER
    """
    API view to retrieve the list of customers (users with role 'CUSTOMER').
    """
    filter_backends = [
        django_filters.rest_framework.DjangoFilterBackend,
        drf_filters.SearchFilter,
        drf_filters.OrderingFilter
    ] 
    serializer_class = CustomerSerializer
    pagination_class = NxtbnPagination
    search_fields = ['id', 'username', 'email']


class CustomerRetrieveUpdateAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = (GranularPermission,)
    model = User
    required_perm = PermissionsEnum.CAN_UPDATE_CUSTOMER
    serializer_class = CustomerUpdateSerializer
    lookup_field = 'id'

    def get_queryset(self):
        return User.objects.filter(role=UserRole.CUSTOMER)
    

    

class CustomerWithAddressView(generics.RetrieveAPIView):
    permission_classes = (CommonPermissions,)
    model = User
    serializer_class = CustomerWithAddressSerializer
    lookup_field = 'id'

    def get_queryset(self):
        return User.objects.filter(role=UserRole.CUSTOMER)


    

class PasswordChangeView(generics.UpdateAPIView):
    permission_classes = (IsStoreStaff,)
    serializer_class = PasswordChangeSerializer
    model = User

    def get_object(self, queryset=None):
        return self.request.user

    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        serializer = self.get_serializer(data=request.data)

        if serializer.is_valid():
            # Set the new password
            serializer.save()
            return Response('Password changed successfully', status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ==========================
# User related views end here
# ==========================



class UserFilter(filters.FilterSet):
    username = filters.CharFilter(field_name='username', lookup_expr='icontains')
    date_joined = filters.DateFromToRangeFilter(field_name='date_joined')

    class Meta:
        model = User
        fields = [
            'id',
            'username',
            'date_joined',
            'role',
            'is_active',
            'is_staff',
            'is_superuser',
        ]


class UserFilterMixin:
    filter_backends = [
        django_filters.rest_framework.DjangoFilterBackend,
        drf_filters.SearchFilter,
        drf_filters.OrderingFilter
    ] 
    search_fields = [
        'id',
        'first_name',
        'last_name',
        'username',
        'email',
        'role',
    ]
    ordering_fields = [
        'username',
        'date_joined',
    ]
    filterset_class = UserFilter

    def get_queryset(self):
        return User.objects.all()
    
class UserViewSet(UserFilterMixin, viewsets.ModelViewSet):
    permission_classes = (CommonPermissions,)
    model = User
    serializer_class = UserMututionalSerializer
    pagination_class = NxtbnPagination
    
    def perform_destroy(self, instance):
        instance.is_active = False
        instance.save()

    def get_serializer_class(self):
        if self.action == 'list':
            return UserSerializer
        return UserMututionalSerializer
    
    def get_queryset(self):
        return User.objects.filter(
            is_staff=True,
        )
    
    @action(detail=True, methods=['put'])
    def deactivate(self, request, pk=None):
        """
        Deactivates a user by setting is_active to False.
        """
        user = self.get_object()
        user.is_active = False
        user.save()
        return Response({'status': 'user deactivated'}, status=status.HTTP_200_OK)
    



class AddressCreateAPIView(generics.CreateAPIView):
    permission_classes = (CommonPermissions,)
    model = User
    serializer_class = AddressMutationalSerializer
    queryset = Address.objects.all()

    

class AddressRetriveUpdateDestroyAPIView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = (CommonPermissions,)
    model = User
    serializer_class = AddressMutationalSerializer
    queryset = Address.objects.all()
    lookup_field = 'id'


class MeDetailsAPIView(generics.RetrieveUpdateAPIView):
    permission_classes = (IsStoreStaff,)
    serializer_class = MeSerializer

    def get_object(self):
        return self.request.user