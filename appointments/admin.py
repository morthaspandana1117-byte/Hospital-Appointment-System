# Register your models here.
from django.contrib import admin
from .models import Appointment, Doctor, MedicalReport, Message, Patient

admin.site.register(Patient)
admin.site.register(Doctor)
admin.site.register(Appointment)
admin.site.register(MedicalReport)
admin.site.register(Message)
