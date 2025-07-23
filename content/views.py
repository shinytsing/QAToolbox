from django.http import HttpResponseForbidden
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Article
from .forms import ArticleForm
from .models import Comment

# 文章列表视图（所有用户可见）
def article_list(request):
    articles = Article.objects.all()
    return render(request, 'content/templates/content/article_list.html', {'articles': articles})

# 查看单个文章的视图（所有用户可见）
def article_detail(request, pk):
    article = get_object_or_404(Article, pk=pk)
    return render(request, 'content/templates/content/article_detail.html', {'article': article})

# 创建文章的视图（只允许登录用户）
@login_required
def article_create(request):
    if request.method == 'POST':
        form = ArticleForm(request.POST)
        if form.is_valid():
            article = form.save(commit=False)
            article.author = request.user
            article.save()
            messages.success(request, '文章已成功创建！')
            return redirect('article_list')
    else:
        form = ArticleForm()

    return render(request, 'content/templates/content/article_form.html', {'form': form})

# 编辑文章的视图（只允许管理员或有相应权限的用户）
@login_required
@permission_required('app_name.can_edit_article', raise_exception=False)
def article_edit(request, pk):
    article = get_object_or_404(Article, pk=pk)

    # 检查权限并返回提示信息
    if not request.user.has_perm('app_name.can_edit_article'):

        messages.error(request, "您没有权限编辑这篇文章。")
        print("+++++"+redirect('article_detail', pk=article.pk))
        return redirect('article_detail', pk=article.pk)  # 重定向到文章详情

    if request.method == 'POST':
        form = ArticleForm(request.POST, instance=article)
        if form.is_valid():
            form.save()
            messages.success(request, '文章已成功更新！')
            return redirect('article_detail', pk=article.pk)
    else:
        form = ArticleForm(instance=article)

    return render(request, 'content/templates/content/article_form.html', {'form': form, 'article': article})

# 删除文章的视图（只允许管理员删除）
@login_required
@permission_required('app_name.can_delete_article', raise_exception=False)
def article_delete(request, pk):
    article = get_object_or_404(Article, pk=pk)

    # 检查权限并返回提示信息
    if not request.user.is_staff:
        messages.error(request, "您没有权限删除这篇文章。")
        return redirect('article_detail', pk=article.pk)  # 重定向到文章详情

    if request.method == 'POST':
        article.delete()
        messages.success(request, f'文章 "{article.title}" 已成功删除！')
        return redirect('article_list')

    return render(request, 'content/templates/content/article_confirm_delete.html', {'article': article})

# 添加评论的视图
@login_required
def add_comment(request, article_id):
    article = get_object_or_404(Article, pk=article_id)
    if request.method == 'POST':
        content = request.POST.get('content')
        if content:
            Comment.objects.create(article=article, user=request.user, content=content)
            messages.success(request, '评论已成功添加！')
        else:
            messages.error(request, '评论内容不能为空。')
        return redirect('article_detail', pk=article_id)
