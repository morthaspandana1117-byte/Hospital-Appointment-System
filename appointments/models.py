from django.db import models
from django.contrib.auth.models import User

import uuid

class Patient(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    phone = models.CharField(max_length=15)

    def __str__(self):
        return self.user.username


class Doctor(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    specialization = models.CharField(max_length=100, blank=True)
    working_hours = models.CharField(max_length=100, blank=True)

    def __str__(self):
        return self.user.username
    

    certificate = models.FileField(upload_to='certificates/', null=True, blank=True)
    is_verified = models.BooleanField(default=False)


class Appointment(models.Model):
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Accepted', 'Accepted'),
        ('Rejected', 'Rejected'),
        ('Cancelled', 'Cancelled'),
        ('Confirmed', 'Confirmed'),   # ✅ NEW
    ]

    patient = models.ForeignKey(Patient, on_delete=models.CASCADE)
    problem = models.TextField()

    doctor = models.ForeignKey(Doctor, on_delete=models.SET_NULL, null=True, blank=True)
    time = models.TimeField(null=True, blank=True)
    date = models.DateField(null=True, blank=True)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="Pending")

    # ✅ TOKEN SYSTEM FIELDS
    token_number = models.CharField(max_length=20, unique=True, blank=True, null=True)
    is_token_generated = models.BooleanField(default=False)
    is_token_confirmed = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # Generate token only once
        if self.is_token_generated and not self.token_number:
            self.token_number = "TKN-" + str(uuid.uuid4())[:8].upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.patient} - {self.doctor}"

class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.message[:20]}"
