from django.urls import path
from . import views

urlpatterns = [
    path('test-case-generator/', views.test_case_generator, name='test_case_generator'),
    path('api/generate-testcases/', views.GenerateTestCasesAPI.as_view()),
    path('download/<path:filename>/', views.download_file, name='download_file'),
]