from rest_framework import serializers
from .models import ToolUsageLog

class ToolUsageLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ToolUsageLog
        fields = ['id', 'tool_type', 'created_at', 'input_data']
        read_only_fields = ['created_at']