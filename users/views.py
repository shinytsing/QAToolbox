
import matplotlib
matplotlib.use('Agg')  # 设置后端为Agg
import random
import string
import re
import matplotlib.pyplot as plt
from django.http import HttpResponse
import numpy as np
from django.contrib import messages
from django.contrib.auth import authenticate, login,logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from .forms import UserEditForm
from .forms import LoginForm


def has_repeated_characters(password):
    """检查密码中是否有连续重复的字符"""
    for i in range(len(password) - 1):
        if password[i] == password[i + 1]:
            return True
    return False

def has_consecutive_characters(password):
    """检查密码中是否有完全连续的字符"""
    # 检查字符是否是连续的，例如 "12345678" 或 "abcdefg"
    for i in range(len(password) - 1):
        if ord(password[i]) + 1 == ord(password[i + 1]):
            return True
    return False

def has_two_different_character_types(password):
    """检查密码中是否包含至少两种不同的字符类型"""
    types = {
        'lower': re.search(r'[a-z]', password),
        'upper': re.search(r'[A-Z]', password),
        'digit': re.search(r'\d', password),
        'special': re.search(r'[@$!%*?&]', password)  # 可以自定义特殊字符
    }
    return sum(bool(t) for t in types.values()) >= 2

def register_view(request):
    if request.method == 'POST':
        username = request.POST['username']
        password = request.POST['password']
        password_confirm = request.POST['password_confirm']
        email = request.POST.get('email', None)  # 邮箱为可选字段

        if password == password_confirm:
            if User.objects.filter(username=username).exists():
                messages.error(request, '用户名已存在，请选择其他用户名。', extra_tags='username')  # 对应标签
            else:
                if len(password) < 8:
                    messages.error(request, '密码必须大于8位。', extra_tags='password')
                elif has_repeated_characters(password):
                    messages.error(request, '密码不能包含连续重复的字符。', extra_tags='password')
                elif has_consecutive_characters(password):
                    messages.error(request, '密码不能是完全连续的字符。', extra_tags='password')
                elif not has_two_different_character_types(password):
                    messages.error(request, '密码必须包含至少两种不同的字符类型（如字母和数字）。', extra_tags='password')
                else:
                    try:
                        user = User.objects.create_user(username=username, password=password, email=email)
                        user.save()
                        messages.success(request, f'{username} 的账户已创建！')
                        return redirect('login')
                    except Exception as e:
                        messages.error(request, f'错误: {str(e)}')
        else:
            messages.error(request, '密码输入不一致，请重新确认。', extra_tags='password_confirm')  # 对应标签

    return render(request, 'users/register.html')

def login_view(request):
    form = LoginForm(request.POST or None)  # 如果是GET请求，表单将为None

    if request.method == 'POST':
        captcha_response = request.POST.get('captcha')  # 获取用户输入的验证码

        # 验证验证码
        if captcha_response != request.session.get('captcha'):
            messages.error(request, '验证码不正确，请重新输入。', extra_tags='captcha')
        elif form.is_valid():
            username = form.cleaned_data.get('username')
            password = form.cleaned_data.get('password')
            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user)
                return redirect('home')  # 登录成功后重定向到主页
            else:
                messages.error(request, "用户名或密码不正确。")
        else:
            messages.error(request, "请检查输入的内容。")

    return render(request, 'users/login.html', {'form': form})

def logout_view(request):
    if request.user.is_authenticated:
        logout(request)  # 退出用户
        messages.info(request, "你已成功登出。")  # 添加登出成功的消息
    else:
        messages.warning(request, "请先登录。")  # 添加没有登录时的提示
    return redirect('home')  # 重定向到首页或其他指定页面

# 在这里定义生成验证码的视图
def generate_captcha(request):
    # 生成随机验证码
    captcha_text = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

    # 创建验证码图像
    fig = plt.figure(figsize=(3, 1), dpi=100)
    plt.text(0.5, 0.5, captcha_text, fontsize=40, ha='center', va='center', color='black', fontweight='bold')

    # 添加干扰线
    for _ in range(5):  # 添加5条干扰线
        x_values = np.random.rand(2)
        y_values = np.random.rand(2)
        plt.plot(x_values, y_values, color='red', linewidth=1, alpha=0.5)

    # 设置背景颜色为淡色
    fig.patch.set_facecolor('#f0f0f0')

    # 隐藏坐标轴
    plt.axis('off')

    # 将验证码文本存储在会话中
    request.session['captcha'] = captcha_text

    # 保存验证码图像到内存
    response = HttpResponse(content_type='image/png')
    plt.savefig(response, format='png')  # 保存图像到响应
    plt.close(fig)  # 关闭图像以释放内存
    return response

@login_required
def profile_view(request):
    return render(request, 'users/profile.html', {'user': request.user})



@login_required
def profile_edit(request):
    if request.method == 'POST':
        form = UserEditForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()  # 保存修改的信息到数据库
            messages.success(request, "资料已成功更新！")
            return redirect('profile_view')  # 重定向到用户资料视图
    else:
        form = UserEditForm(instance=request.user)

    return render(request, 'users/profile_edit.html', {'form': form})