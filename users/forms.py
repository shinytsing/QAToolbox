# forms.py
from captcha.fields import CaptchaField
from django import forms
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['username', 'email']  # 根据需要设置字段



class LoginForm(forms.Form):
    username = forms.CharField(max_length=150)
    password = forms.CharField(widget=forms.PasswordInput)
    captcha = forms.CharField(max_length=6)  # 添加长度限制，以适应验证码要求