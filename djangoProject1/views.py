from django.shortcuts import redirect, render
from django.contrib.auth.decorators import login_required

@login_required  # 仅允许登录用户访问
def tool_view(request):
    return render(request, 'tool.html')  # 确保这里指向你的工具模板
# 添加一个根视图函数
def home_view(request):
    if request.user.is_authenticated:
        return render(request, 'tool.html')  # 如果用户已登录，重定向到小工具界面
    return render(request, 'home.html')  # 否则显示首页