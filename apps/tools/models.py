from django.db import models
from django.contrib.auth.models import User


class ToolUsageLog(models.Model):
    TOOL_CHOICES = [
        ('TEST_CASE', 'Test Case Generator'),
        ('QUALITY_CHECK', 'Code Quality Check'),
        ('PERF_TEST', 'Performance Simulator'),
    ]
    # 在 models.py 中添加
    preview_image = models.ImageField(upload_to='tool_previews/', null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    tool_type = models.CharField(max_length=20, choices=TOOL_CHOICES)
    input_data = models.TextField()
    output_file = models.FileField(upload_to='tool_outputs/')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']