from django.contrib import admin
from django.urls import path, include

from django.conf import settings
from django.conf.urls.static import static

from django.contrib.auth import views as auth_views

urlpatterns = [
    path('admin/', admin.site.urls),

    # 👉 This connects your app URLs
    path('', include('appointments.urls')),

    path('forgot-password/', auth_views.PasswordResetView.as_view(
        template_name='appointments/forgot_password.html'
    ), name='forgot-password'),

    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='appointments/reset_password.html'
    ), name='password_reset_confirm'),
]

# 👉 For media files (certificate upload)
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)