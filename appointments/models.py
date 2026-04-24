import os
import uuid
from datetime import date

from django.conf import settings
from django.contrib.auth.models import User
from django.core.validators import FileExtensionValidator
from django.core.exceptions import ValidationError
from django.db import models


class Patient(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=15)

    def __str__(self):
        return self.user.username


class Doctor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    specialization = models.CharField(max_length=100, blank=True)
    working_hours = models.CharField(max_length=100, blank=True)
    certificate = models.FileField(upload_to="certificates/", null=True, blank=True)
    is_verified = models.BooleanField(default=False)

    def __str__(self):
        return self.user.username


class Mediator(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=15, blank=True)

    def __str__(self):
        return self.user.username


class Appointment(models.Model):
    STATUS_CHOICES = [
        ("Pending", "Pending"),
        ("Accepted", "Accepted"),
        ("Rejected", "Rejected"),
        ("Cancelled", "Cancelled"),
        ("Confirmed", "Confirmed"),
    ]
    PRIORITY_CHOICES = [
        ("Normal", "Normal"),
        ("Emergency", "Emergency"),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    problem = models.TextField()
    doctor = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True)
    time = models.TimeField(null=True, blank=True)
    date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="Normal")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Pending")
    token_number = models.CharField(max_length=20, unique=True, blank=True, null=True)
    is_token_generated = models.BooleanField(default=False)
    is_token_confirmed = models.BooleanField(default=False)

    def clean(self):
        if self.date and self.date < date.today():
            raise ValidationError({
                "date": "Cannot book appointment for past dates"
            })

        if self.doctor and self.date and self.time:
            conflicting_appointment = Appointment.objects.filter(
                doctor=self.doctor,
                date=self.date,
                time=self.time,
            ).exclude(
                id=self.id
            ).exclude(
                status__in=["Cancelled", "Rejected"]
            )
            if conflicting_appointment.exists():
                raise ValidationError({
                    "time": "This time slot is already booked"
                })

    def save(self, *args, **kwargs):
        if self.is_token_generated and not self.token_number:
            self.token_number = "TKN-" + str(uuid.uuid4())[:8].upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.patient} - {self.doctor}"


def report_upload_path(instance, filename):
    extension = os.path.splitext(filename)[1]
    unique_name = f"{uuid.uuid4().hex}{extension.lower()}"
    return f"reports/patient_{instance.patient_id}/{unique_name}"


def validate_report_file_size(value):
    max_size = getattr(settings, "MEDICAL_REPORT_MAX_UPLOAD_SIZE", 5 * 1024 * 1024)
    if value.size > max_size:
        raise ValidationError("Report file size must be 5 MB or less.")


class MedicalReport(models.Model):
    REPORT_TYPE_CHOICES = [
        ("Prescription", "Prescription"),
        ("Lab Report", "Lab Report"),
        ("Scan", "Scan"),
        ("Other", "Other"),
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE, related_name="medical_reports")
    doctor = models.ForeignKey(
        Doctor,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="medical_reports",
    )
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="medical_reports",
    )
    report_file = models.FileField(
        upload_to=report_upload_path,
        validators=[
            FileExtensionValidator(allowed_extensions=["pdf", "jpg", "jpeg", "png"]),
            validate_report_file_size,
        ],
    )
    original_file_name = models.CharField(max_length=255, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    description = models.TextField(blank=True)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES, default="Other")

    class Meta:
        ordering = ["-uploaded_at"]

    def clean(self):
        if self.appointment_id and self.patient_id != self.appointment.patient_id:
            raise ValidationError({
                "appointment": "This report must belong to one of the patient's appointments."
            })

        if self.appointment_id and self.appointment.doctor_id is None:
            raise ValidationError({
                "appointment": "You can upload reports only after doctor assignment."
            })

        if self.doctor_id and self.appointment.doctor_id != self.doctor_id:
            raise ValidationError({
                "doctor": "The selected doctor must match the appointment doctor."
            })

    def __str__(self):
        return f"Report for appointment #{self.appointment_id}"

    @property
    def file_name(self):
        return self.original_file_name or os.path.basename(self.report_file.name)

    @property
    def is_pdf(self):
        return self.report_file.name.lower().endswith(".pdf")

    @property
    def is_image(self):
        return self.report_file.name.lower().endswith((".jpg", ".jpeg", ".png"))

    def save(self, *args, **kwargs):
        if self.report_file and not self.original_file_name:
            self.original_file_name = self.report_file.name
        super().save(*args, **kwargs)


class Message(models.Model):
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_messages")
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name="received_messages")
    appointment = models.ForeignKey(
        Appointment,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    message_text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["timestamp"]

    def clean(self):
        if self.appointment_id:
            if self.appointment.status not in ["Accepted", "Confirmed"]:
                raise ValidationError("Chat is only available for accepted or confirmed appointments.")

            participants = {
                self.appointment.patient.user_id,
                self.appointment.doctor.user_id if self.appointment.doctor_id else None,
            }
            if self.sender_id not in participants or self.receiver_id not in participants:
                raise ValidationError("Messages can only be exchanged between the assigned doctor and patient.")

    def __str__(self):
        return f"Message for appointment #{self.appointment_id}"


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.message[:20]}"
