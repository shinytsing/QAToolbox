"""
URL configuration for QAToolBox project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.urls import include, path
from apps.QAToolBox.views import home_view, tool_view
from django.http import HttpResponse
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', home_view, name='home'),
    path('admin/', admin.site.urls),
    # 工具主页面路由
    path('tool/', tool_view, name='tool'),
    # 工具子路由（包含测试用例生成器等）
    path('tool/', include('apps.tools.urls')),
    path('users/', include('apps.users.urls')),
    path('content/', include('apps.content.urls')),
    path('about/', lambda request: HttpResponse('关于页面'), name='about'),
    path('contact/', lambda request: HttpResponse('联系页面'), name='contact'),
]

# 开发环境下提供媒体文件访问
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)