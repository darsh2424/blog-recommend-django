from django.contrib import admin
from .models import Category,Post,Comment,CommentReply,PostReport
# Register your models here.
admin.site.register(Category)
admin.site.register(Post)
admin.site.register(Comment)
admin.site.register(CommentReply)
admin.site.register(PostReport)

