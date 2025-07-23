from django.urls import path

from .views import login_view,register_view,profile_view,profile_edit,logout_view
from .views import generate_captcha  # 导入生成验证码的视图
urlpatterns = [
    path('register/', register_view, name='register'),
    path('login/', login_view, name='login'),
    path('captcha/', generate_captcha, name='generate_captcha'),
    path('logout/', logout_view, name='logout'),
    path('profile/', profile_view, name='profile_view'),
    path('profile/edit/', profile_edit, name='profile_edit'),
]
