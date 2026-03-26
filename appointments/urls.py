from django.urls import path
from . import views

urlpatterns = [

    path('', views.login_view, name='login'),

    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),

    path('patient-dashboard/', views.patient_dashboard, name='patient-dashboard'),
    path('doctor-dashboard/', views.doctor_dashboard, name='doctor-dashboard'),
    path('admin-dashboard/', views.admin_dashboard, name='admin-dashboard'),

    path('booking/', views.booking_view, name='booking'),
    path('cancel/<int:appointment_id>/', views.cancel_appointment, name='cancel-appointment'),

    path('doctor-details/', views.doctor_details, name='doctor-details'),

    path('accept/<int:appointment_id>/', views.accept_appointment, name='accept'),
    path('reject/<int:appointment_id>/', views.reject_appointment, name='reject'),

    path('send-email/<int:appointment_id>/', views.send_status_email, name='send-email'),

    path('profile/', views.edit_profile, name='profile'),
]
