from django.urls import path
from .views import article_list, article_detail, article_create, article_edit, article_delete,add_comment

urlpatterns = [
    path('', article_list, name='article_list'),  # 文章列表
    path('<int:pk>/', article_detail, name='article_detail'),  # 查看单个文章
    path('create/', article_create, name='article_create'),  # 创建文章
    path('edit/<int:pk>/', article_edit, name='article_edit'),  # 编辑文章
    path('delete/<int:pk>/', article_delete, name='article_delete'),  # 删除文章
    path('articles/<int:article_id>/comment/', add_comment, name='add_comment'),

]
