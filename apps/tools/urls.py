# QAToolbox/apps/tools/urls.py
from django.urls import path
from . import views
from .api import GenerateTestCasesAPI  # 从api.py导入正确的类

urlpatterns = [
    path('test-case-generator/', views.test_case_generator, name='test_case_generator'),
    path('api/generate-testcases/', GenerateTestCasesAPI.as_view()),  # 使用导入的类
    path('download/<path:filename>/', views.download_file, name='download_file'),
]