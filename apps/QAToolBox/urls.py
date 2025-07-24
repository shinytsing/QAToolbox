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



urlpatterns = [
    path('',home_view, name='home'),
    path('admin/', admin.site.urls),
    path('tools/', tool_view, name='tools'),  # 允许访问 /tools.html

    path('users/', include('apps.users.urls')),  # 确保这里包含了 QAToolBox 的 URL
    path('content/', include('apps.content.urls')),  # 假设你的内容管理路由是这样设置的
    path('about/', lambda request: HttpResponse('关于页面'), name='about'),  # 临时占位符
    path('contact/', lambda request: HttpResponse('联系页面'), name='contact'),  # 临时占位符
]



