from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from .models import User


class LoginSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        data["role"] = self.user.role
        return data


class MeSerializer(serializers.ModelSerializer):
    store = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ["id", "username", "role", "store"]

    def get_store(self, obj):
        return {"id": obj.store_id, "name": obj.store.name, "code": obj.store.code} if obj.store_id else None
