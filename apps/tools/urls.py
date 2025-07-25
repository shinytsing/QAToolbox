# QAToolbox/apps/tool/urls.py
from django.urls import path
from .views import test_case_generator, download_file
from .api import GenerateTestCasesAPI

urlpatterns = [
    # 测试用例生成页面
    path('test-case-generator/', test_case_generator, name='test_case_generator'),
    # 文件下载路由
    path('download/<str:filename>/', download_file, name='download_file'),
    # API 路由
    path('api/generate-testcases/', GenerateTestCasesAPI.as_view(), name='generate_testcases_api'),
]