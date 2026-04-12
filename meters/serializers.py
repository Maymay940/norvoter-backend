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