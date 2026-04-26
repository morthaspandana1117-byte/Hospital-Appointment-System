from django.urls import path

from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('logout/', views.logout_view, name='logout'),
    path('forgot-password/', views.forgot_password, name='forgot-password'),

    path('patient-dashboard/', views.patient_dashboard, name='patient-dashboard'),
    path('doctor-dashboard/', views.doctor_dashboard, name='doctor-dashboard'),
    path('mediator-dashboard/', views.mediator_dashboard, name='mediator-dashboard'),
    path('admin-dashboard/', views.admin_dashboard, name='admin-dashboard'),

    path('booking/', views.booking_view, name='booking'),
    path('cancel/<int:appointment_id>/', views.cancel_appointment, name='cancel-appointment'),
    path('doctor-details/', views.doctor_details, name='doctor-details'),
    path('profile/', views.edit_profile, name='profile'),
    path('notifications/', views.notifications, name='notifications'),
    path('download-token/<int:id>/', views.download_token, name='download-token'),
    path('appointments/<int:appointment_id>/reports/upload/', views.upload_medical_report, name='upload-medical-report'),
    path('patient-reports/', views.patient_reports, name='patient-reports'),
    path('doctor-reports/', views.doctor_reports, name='doctor-reports'),
    path('appointments/<int:appointment_id>/chat/', views.chat_view, name='chat'),
    path('appointments/<int:appointment_id>/chat/messages/', views.chat_messages_api, name='chat-messages-api'),
    path('appointments/<int:appointment_id>/chat/send/', views.send_message, name='send-message'),
    path('reports/<int:report_id>/preview/', views.preview_medical_report, name='preview-medical-report'),
    path('reports/<int:report_id>/file/', views.serve_medical_report, name='serve-medical-report'),
    path('reports/<int:report_id>/download/', views.download_medical_report, name='download-medical-report'),
    path('reports/<int:report_id>/delete/', views.delete_medical_report, name='delete-medical-report'),

    path('mediator/accept/<int:id>/', views.accept, name='accept'),
    path('mediator/reject/<int:id>/', views.reject, name='reject'),

    path('mediator/assign-doctor/<int:id>/', views.assign_doctor, name='assign-doctor'),
    path('admin/cancel/<int:id>/', views.admin_cancel_appointment, name='admin-cancel-appointment'),
    path('verify-doctor/<int:id>/', views.verify_doctor, name='verify-doctor'),
    path('manage-users/', views.manage_users, name='manage-users'),
    path('delete-user/<int:user_id>/', views.delete_user, name='delete-user'),
    path('confirm-token/<int:id>/', views.confirm_token, name='confirm-token'),
]
