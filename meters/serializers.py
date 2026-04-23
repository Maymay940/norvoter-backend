from rest_framework import serializers
from .models import User, WaterMeter, Request, ReadingPosition

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name', 'phone', 'is_active']

class WaterMeterSerializer(serializers.ModelSerializer):
    class Meta:
        model = WaterMeter
        fields = '__all__'

class ReadingPositionSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReadingPosition
        fields = '__all__'

class RequestSerializer(serializers.ModelSerializer):
    positions = ReadingPositionSerializer(many=True, read_only=True)
    total_cost = serializers.SerializerMethodField()
    
    class Meta:
        model = Request
        fields = '__all__'
    
    def get_total_cost(self, obj):
        if obj.total_consumption:
            return float(obj.total_consumption) * 50
        return None
    
class LoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=100)
    password = serializers.CharField(max_length=255, write_only=True)

class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=100)
    email = serializers.EmailField()
    first_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    last_name = serializers.CharField(max_length=100, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=20, required=False, allow_blank=True)

class PositionAddSerializer(serializers.Serializer):
    meter_id = serializers.IntegerField()
    current_reading = serializers.IntegerField()
    request_id = serializers.IntegerField(required=False, allow_null=True)

class PositionUpdateSerializer(serializers.Serializer):
    current_reading = serializers.IntegerField()

class RequestUpdateSerializer(serializers.Serializer):
    comment = serializers.CharField(required=False, allow_blank=True)

class MeterAddSerializer(serializers.Serializer):
    address = serializers.CharField(max_length=255)
    serial_number = serializers.CharField(max_length=50)
    meter_type = serializers.ChoiceField(choices=['HOT', 'COLD'])
    meter_model = serializers.CharField(max_length=100)
    installation_date = serializers.DateField()
    initial_reading = serializers.IntegerField(default=0)
    last_verified_reading = serializers.IntegerField(default=0)