from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import send_mail
from .models import Patient, Doctor, Appointment
from django.conf import settings
from .models import Appointment, Doctor
from django.contrib import messages

# ---------------- REGISTER ----------------
def register_view(request):
    if request.method == "POST":
        username = request.POST.get('username')
        email = request.POST.get('email')
        phone = request.POST.get('phone')
        password = request.POST.get('password')
        role = request.POST.get('role')

        # Doctor fields
        specialization = request.POST.get('specialization')
        certificate = request.FILES.get('certificate')

        if User.objects.filter(username=username).exists():
            return render(request, "appointments/register.html", {
                "error": "Username already exists"
            })

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password
        )

        if role == "patient":
            Patient.objects.create(user=user, phone=phone)
            login(request, user)
            return redirect('patient-dashboard')

        elif role == "doctor":
            Doctor.objects.create(
                user=user,
                specialization=specialization,
                certificate=certificate,
                is_verified=False   # 🔥 important
            )

            # ❌ Do NOT login doctor immediately
            return render(request, "appointments/login.html", {
                "message": "Registration successful. Wait for admin verification."
            })

    return render(request, "appointments/register.html")

# ---------------- LOGIN ----------------
def login_view(request):
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']

        user = authenticate(request, username=username, password=password)

        if user is not None:

            # 🔥 Check doctor verification BEFORE login
            if hasattr(user, 'doctor'):
                if not user.doctor.is_verified:
                    messages.error(request, "Your account is not verified by admin yet.")
                    return redirect('login')

            login(request, user)

            if user.is_superuser:
                return redirect('admin-dashboard')

            elif hasattr(user, 'patient'):
                return redirect('patient-dashboard')

            elif hasattr(user, 'doctor'):
                return redirect('doctor-dashboard')

        else:
            return render(request, "appointments/login.html", {
                "error": "Invalid credentials"
            })

    return render(request, "appointments/login.html")


# ---------------- LOGOUT ----------------
def logout_view(request):
    logout(request)
    return redirect('login')


# ---------------- BOOKING ----------------
@login_required
def booking_view(request):

    if request.method == "POST":
        problem = request.POST.get('problem')
        date = request.POST.get('date')

        patient = request.user.patient

        Appointment.objects.create(
            patient=patient,
            problem=problem,
            date=date,
            status="Pending"
        )

        return redirect('patient-dashboard')

    return render(request, "appointments/booking.html")


# ---------------- PATIENT DASHBOARD ----------------
@login_required
def patient_dashboard(request):
    patient = request.user.patient
    appointments = Appointment.objects.filter(patient=patient)
    return render(request, "appointments/patient-dashboard.html", {"appointments": appointments})


# ---------------- DOCTOR DASHBOARD ----------------
@login_required
def doctor_dashboard(request):
    doctor = request.user.doctor

    appointments = Appointment.objects.filter(doctor=doctor)

    return render(request, "appointments/doctor-dashboard.html", {
        "appointments": appointments
    })


# ---------------- DOCTOR PROFILE ----------------
@login_required
def doctor_details(request):
    doctor = request.user.doctor

    if request.method == "POST":
        doctor.specialization = request.POST.get("specialization")
        doctor.working_hours = request.POST.get("working_hours")
        doctor.save()
        return redirect('doctor-dashboard')

    return render(request, "appointments/doctor-details.html", {"doctor": doctor})


# ---------------- ADMIN DASHBOARD ----------------
@login_required
def admin_dashboard(request):
    if not request.user.is_superuser:
        return redirect('login')

    appointments = Appointment.objects.all()
    doctors = Doctor.objects.all()

    return render(request, "appointments/admin-dashboard.html", {
        "appointments": appointments,
        "doctors": doctors
    })


# ---------------- ACCEPT ----------------
def accept(request, id):
    appointment = Appointment.objects.get(id=id)
    appointment.status = "Accepted"
    appointment.save()

    return redirect('doctor-dashboard')


# ---------------- REJECT ----------------
def reject(request, id):
    appointment = Appointment.objects.get(id=id)
    appointment.status = "Rejected"
    appointment.save()

    return redirect('doctor-dashboard')


# ---------------- CANCEL ----------------
@login_required
def cancel_appointment(request, appointment_id):
    appointment = get_object_or_404(Appointment, id=appointment_id, patient=request.user.patient)
    appointment.status = "Cancelled"
    appointment.save()
    return redirect('patient-dashboard')


# ---------------- EMAIL ----------------

def send_status_email(request, appointment_id):
    print("Sending email...")
    appointment = get_object_or_404(Appointment, id=appointment_id)

    patient_name = appointment.patient.user.username
    patient_email = appointment.patient.user.email

    doctor_name = appointment.doctor.user.username

    status = appointment.status
    date = appointment.time
    time = appointment.time

    subject = "Appointment Status Update"

    message = f"""
Hello {patient_name},

Your appointment with Dr. {doctor_name} has been updated.

Appointment Details:
Date: {date}
Time: {time}
Status: {status}

If you have any questions, please contact the hospital.

Thank you,
Hospital Appointment System
"""

    # Send email
    send_mail(
        subject,
        message,
        settings.EMAIL_HOST_USER,
        [patient_email],
        fail_silently=False,
    )

    return redirect('admin-dashboard')


# ---------------- PROFILE ----------------
@login_required
def edit_profile(request):
    user = request.user

    current_role = 'admin' if user.is_superuser else ('doctor' if hasattr(user, 'doctor') else ('patient' if hasattr(user, 'patient') else ''))
    if request.method == "POST":
        username = request.POST['username']
        email = request.POST['email']
        password = request.POST.get('password')
        user.username = username
        user.email = email
        if password:
            user.set_password(password)
        user.save()

        # Update doctor specialization if applicable
        if hasattr(user, 'doctor'):
            doctor = user.doctor
            doctor.specialization = request.POST.get('specialization', '')
            doctor.working_hours = request.POST.get('working_hours', '')
            doctor.save()

        new_role = request.POST.get('role')
        if new_role and new_role != current_role:
            if current_role == 'patient':
                user.patient.delete()
            elif current_role == 'doctor':
                user.doctor.delete()
            elif current_role == 'admin':
                user.is_superuser = False
                user.is_staff = False
                user.save()
            if new_role == 'patient':
                Patient.objects.create(user=user)
            elif new_role == 'doctor':
                Doctor.objects.create(user=user)
            elif new_role == 'admin':
                user.is_superuser = True
                user.is_staff = True
                user.save()

        if user.is_superuser:
            return redirect('admin-dashboard')
        elif hasattr(user, 'doctor'):
            return redirect('doctor-dashboard')
        else:
            return redirect('patient-dashboard')
    return render(request, 'appointments/profile.html', {'user': user, 'role': current_role})

def assign_doctor(request, id):
    appointment = Appointment.objects.get(id=id)

    if request.method == "POST":
        doctor_id = request.POST.get('doctor')
        time = request.POST.get('time')

        doctor = Doctor.objects.get(id=doctor_id)

        appointment.doctor = doctor
        appointment.time = time
        appointment.status = "Assigned"
        appointment.save()

    return redirect('admin-dashboard')

def cancel_appointment(request, id):
    appointment = Appointment.objects.get(id=id)
    appointment.status = "Cancelled"
    appointment.save()

    return redirect('admin-dashboard')

def verify_doctor(request, id):
    doctor = Doctor.objects.get(id=id)
    doctor.is_verified = True
    doctor.save()

    return redirect('admin-dashboard')

def manage_users(request):
    patients = Patient.objects.all()
    doctors = Doctor.objects.all()

    return render(request, "appointments/manage_users.html", {
        "patients": patients,
        "doctors": doctors
    })

def verify_doctor(request, id):
    doctor = Doctor.objects.get(id=id)
    doctor.is_verified = True
    doctor.save()

    return redirect('admin-dashboard')