from datetime import date
import mimetypes

from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.http import FileResponse, HttpResponse, HttpResponseForbidden
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from .forms import MedicalReportForm
from .models import Appointment, Doctor, MedicalReport, Mediator, Message, Notification, Patient


def create_notification(user, message):
    Notification.objects.create(user=user, message=message)


def is_patient(user):
    return hasattr(user, "patient")


def is_doctor(user):
    return hasattr(user, "doctor")


def is_mediator(user):
    return hasattr(user, "mediator")


def get_dashboard_name(user):
    if user.is_superuser:
        return "admin-dashboard"
    if is_mediator(user):
        return "mediator-dashboard"
    if is_doctor(user):
        return "doctor-dashboard"
    return "patient-dashboard"


def mediator_only(request):
    if request.user.is_superuser:
        return False
    if not is_mediator(request.user):
        return HttpResponseForbidden("Only mediators can perform this action.")
    return None


def admin_only(request):
    if not request.user.is_superuser:
        return HttpResponseForbidden("Only admins can perform this action.")
    return None


def user_can_access_report(user, report):
    is_report_owner = is_patient(user) and report.patient_id == user.patient.id
    is_assigned_doctor = (
        is_doctor(user)
        and report.doctor_id is not None
        and report.doctor_id == user.doctor.id
    )
    return is_report_owner or is_assigned_doctor


def get_chat_appointment_for_user(user, appointment_id):
    appointment = get_object_or_404(
        Appointment.objects.select_related("patient__user", "doctor__user"),
        id=appointment_id,
    )

    if appointment.status not in ["Accepted", "Confirmed"]:
        return None, HttpResponseForbidden("Chat is only available for accepted or confirmed appointments.")

    is_chat_patient = is_patient(user) and appointment.patient_id == user.patient.id
    is_chat_doctor = (
        is_doctor(user)
        and appointment.doctor_id is not None
        and appointment.doctor_id == user.doctor.id
    )

    if not (is_chat_patient or is_chat_doctor):
        return None, HttpResponseForbidden("You are not authorized to access this chat.")

    if appointment.doctor_id is None:
        return None, HttpResponseForbidden("Chat is not available until a doctor is assigned.")

    return appointment, None


def apply_report_filters(queryset, request):
    search_query = request.GET.get("q", "").strip()
    report_type = request.GET.get("report_type", "").strip()

    if search_query:
        queryset = queryset.filter(
            Q(original_file_name__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(report_type__icontains=search_query)
            | Q(appointment__problem__icontains=search_query)
            | Q(patient__user__username__icontains=search_query)
            | Q(doctor__user__username__icontains=search_query)
        )

    if report_type:
        queryset = queryset.filter(report_type=report_type)

    return queryset, search_query, report_type


# ---------------- REGISTER ----------------
def register_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        email = request.POST.get("email")
        phone = request.POST.get("phone")
        password = request.POST.get("password")
        role = request.POST.get("role")
        specialization = request.POST.get("specialization")
        certificate = request.FILES.get("certificate")

        if User.objects.filter(username=username).exists():
            return render(request, "appointments/register.html", {
                "error": "Username already exists"
            })

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
        )

        if role == "patient":
            Patient.objects.create(user=user, phone=phone)
            login(request, user)
            return redirect("patient-dashboard")

        if role == "doctor":
            Doctor.objects.create(
                user=user,
                specialization=specialization,
                certificate=certificate,
                is_verified=False,
            )
            return render(request, "appointments/login.html", {
                "message": "Registration successful. Wait for admin verification."
            })

        if role == "mediator":
            Mediator.objects.create(user=user, phone=phone)
            login(request, user)
            return redirect("mediator-dashboard")

        user.delete()
        return render(request, "appointments/register.html", {
            "error": "Please select a valid role"
        })

    return render(request, "appointments/register.html")


# ---------------- LOGIN ----------------
def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(request, username=username, password=password)

        if user is None:
            return render(request, "appointments/login.html", {
                "error": "Invalid credentials"
            })

        if is_doctor(user) and not user.doctor.is_verified:
            messages.error(request, "Your account is not verified by admin yet.")
            return redirect("login")

        login(request, user)
        return redirect(get_dashboard_name(user))

    return render(request, "appointments/login.html")


# ---------------- LOGOUT ----------------
def logout_view(request):
    logout(request)
    return redirect("login")


# ---------------- BOOKING ----------------
@login_required
def booking_view(request):
    if not is_patient(request.user):
        return HttpResponseForbidden("Only patients can create appointment requests.")

    if request.method == "POST":
        problem = request.POST.get("problem")
        appointment_date = parse_date(request.POST.get("date"))
        priority = request.POST.get("priority", "Normal")
        patient = request.user.patient

        if priority not in dict(Appointment.PRIORITY_CHOICES):
            priority = "Normal"

        if not appointment_date:
            return render(request, "appointments/booking.html", {
                "error": "Please select a valid appointment date.",
                "today": date.today().isoformat(),
                "form_data": request.POST,
            })

        if appointment_date < date.today():
            return render(request, "appointments/booking.html", {
                "error": "Cannot book appointment for past dates",
                "today": date.today().isoformat(),
                "form_data": request.POST,
            })

        appointment = Appointment(
            patient=patient,
            problem=problem,
            date=appointment_date,
            priority=priority,
            status="Pending",
        )

        try:
            appointment.full_clean()
        except ValidationError as exc:
            error_message = exc.message_dict.get("date", exc.messages)
            if isinstance(error_message, list):
                error_message = error_message[0]
            return render(request, "appointments/booking.html", {
                "error": error_message,
                "today": date.today().isoformat(),
                "form_data": request.POST,
            })

        appointment.save()

        for admin in User.objects.filter(is_superuser=True):
            create_notification(admin, f"New appointment booked by {request.user.username}")

        for mediator in Mediator.objects.select_related("user"):
            create_notification(mediator.user, f"New pending appointment from {request.user.username}")

        return redirect("patient-dashboard")

    return render(request, "appointments/booking.html", {
        "today": date.today().isoformat(),
    })


# ---------------- PATIENT DASHBOARD ----------------
@login_required
def patient_dashboard(request):
    if not is_patient(request.user):
        return redirect(get_dashboard_name(request.user))

    appointments = Appointment.objects.filter(patient=request.user.patient).select_related(
        "doctor__user", "patient__user"
    ).prefetch_related("medical_reports")
    analytics = {
        "total_appointments": appointments.count(),
        "total_reports": MedicalReport.objects.filter(patient=request.user.patient).count(),
    }
    return render(request, "appointments/patient-dashboard.html", {
        "appointments": appointments,
        "analytics": analytics,
    })


# ---------------- DOCTOR DASHBOARD ----------------
@login_required
def doctor_dashboard(request):
    if not is_doctor(request.user):
        return redirect(get_dashboard_name(request.user))

    appointments = Appointment.objects.filter(doctor=request.user.doctor).select_related(
        "patient__user", "doctor__user"
    ).prefetch_related("medical_reports").order_by("-date", "-time")
    analytics = {
        "total_appointments": appointments.count(),
        "total_patients": appointments.exclude(patient=None).values("patient").distinct().count(),
        "total_reports": MedicalReport.objects.filter(doctor=request.user.doctor).count(),
    }

    return render(request, "appointments/doctor-dashboard.html", {
        "appointments": appointments,
        "analytics": analytics,
    })


# ---------------- MEDIATOR DASHBOARD ----------------
@login_required
def mediator_dashboard(request):
    denied_response = mediator_only(request)
    if denied_response:
        return denied_response

    appointments = Appointment.objects.select_related(
        "patient__user", "doctor__user"
    ).annotate(
        priority_rank=Case(
            When(priority="Emergency", then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    ).order_by("priority_rank", "date", "time")
    doctors = Doctor.objects.filter(is_verified=True).select_related("user")
    analytics = {
        "total_pending": appointments.filter(status="Pending").count(),
        "total_assigned": appointments.exclude(doctor=None).count(),
        "total_accepted": appointments.filter(status="Accepted").count(),
        "total_rejected": appointments.filter(status="Rejected").count(),
    }

    return render(request, "appointments/mediator-dashboard.html", {
        "appointments": appointments,
        "doctors": doctors,
        "analytics": analytics,
    })


# ---------------- DOCTOR PROFILE ----------------
@login_required
def doctor_details(request):
    if not is_doctor(request.user):
        return redirect(get_dashboard_name(request.user))

    doctor = request.user.doctor

    if request.method == "POST":
        doctor.specialization = request.POST.get("specialization", "")
        doctor.working_hours = request.POST.get("working_hours", "")
        doctor.save()
        return redirect("doctor-dashboard")

    return render(request, "appointments/doctor-details.html", {"doctor": doctor})


# ---------------- ADMIN DASHBOARD ----------------
@login_required
def admin_dashboard(request):
    denied_response = admin_only(request)
    if denied_response:
        return denied_response

    appointments = Appointment.objects.all().select_related("patient__user", "doctor__user")
    doctors = Doctor.objects.all().select_related("user")
    appointment_status_counts = {
        item["status"]: item["count"]
        for item in Appointment.objects.values("status").annotate(count=Count("id"))
    }
    analytics = {
        "total_patients": Patient.objects.count(),
        "total_doctors": Doctor.objects.count(),
        "total_appointments": appointments.count(),
        "pending_count": appointment_status_counts.get("Pending", 0),
        "accepted_count": appointment_status_counts.get("Accepted", 0),
        "rejected_count": appointment_status_counts.get("Rejected", 0),
        "confirmed_count": appointment_status_counts.get("Confirmed", 0),
        "cancelled_count": appointment_status_counts.get("Cancelled", 0),
    }

    return render(request, "appointments/admin-dashboard.html", {
        "appointments": appointments,
        "doctors": doctors,
        "analytics": analytics,
    })


# ---------------- MEDIATOR ACCEPT ----------------
@login_required
@require_POST
def accept(request, id):
    denied_response = mediator_only(request)
    if denied_response:
        return denied_response

    appointment = get_object_or_404(Appointment, id=id)
    appointment.status = "Accepted"
    appointment.save()

    create_notification(appointment.patient.user, "Your appointment request has been accepted.")

    if appointment.doctor:
        create_notification(
            appointment.doctor.user,
            f"Appointment for {appointment.patient.user.username} was accepted by mediator."
        )

    return redirect("mediator-dashboard")


# ---------------- MEDIATOR REJECT ----------------
@login_required
@require_POST
def reject(request, id):
    denied_response = mediator_only(request)
    if denied_response:
        return denied_response

    appointment = get_object_or_404(Appointment, id=id)
    appointment.status = "Rejected"
    appointment.save()

    create_notification(appointment.patient.user, "Your appointment request has been rejected.")

    if appointment.doctor:
        create_notification(
            appointment.doctor.user,
            f"Appointment for {appointment.patient.user.username} was rejected by mediator."
        )

    return redirect("mediator-dashboard")


# ---------------- PATIENT CANCEL ----------------
@login_required
def cancel_appointment(request, appointment_id):
    if not is_patient(request.user):
        return HttpResponseForbidden("Only patients can cancel their appointments from this page.")

    appointment = get_object_or_404(
        Appointment,
        id=appointment_id,
        patient=request.user.patient,
    )
    appointment.status = "Cancelled"
    appointment.save()

    for admin in User.objects.filter(is_superuser=True):
        create_notification(admin, f"{request.user.username} cancelled an appointment")

    for mediator in Mediator.objects.select_related("user"):
        create_notification(mediator.user, f"{request.user.username} cancelled an appointment")

    return redirect("patient-dashboard")


# ---------------- PROFILE ----------------
@login_required
def edit_profile(request):
    user = request.user

    if user.is_superuser:
        current_role = "admin"
    elif is_mediator(user):
        current_role = "mediator"
    elif is_doctor(user):
        current_role = "doctor"
    else:
        current_role = "patient"

    if request.method == "POST":
        user.username = request.POST.get("username")
        user.email = request.POST.get("email")
        password = request.POST.get("password")

        if password:
            user.set_password(password)

        user.save()

        if is_doctor(user):
            doctor = user.doctor
            doctor.specialization = request.POST.get("specialization", "")
            doctor.working_hours = request.POST.get("working_hours", "")
            doctor.save()

        if is_patient(user):
            user.patient.phone = request.POST.get("phone", user.patient.phone)
            user.patient.save()

        if is_mediator(user):
            user.mediator.phone = request.POST.get("phone", user.mediator.phone)
            user.mediator.save()

        if password:
            return redirect("login")

        return redirect(get_dashboard_name(user))

    return render(request, "appointments/profile.html", {
        "user": user,
        "role": current_role,
    })


# ---------------- ASSIGN DOCTOR ----------------
@login_required
@require_POST
def assign_doctor(request, id):
    denied_response = mediator_only(request)
    if denied_response:
        return denied_response

    appointment = get_object_or_404(Appointment, id=id)
    if appointment.doctor:
        return HttpResponseForbidden("A doctor is already assigned to this appointment.")

    doctor = get_object_or_404(Doctor, id=request.POST.get("doctor"))
    if not doctor.is_verified:
        return HttpResponseForbidden("Only verified doctors can be assigned.")

    appointment.doctor = doctor
    appointment.time = request.POST.get("time")
    appointment.is_token_generated = True
    try:
        appointment.full_clean()
    except ValidationError as exc:
        error_message = exc.message_dict.get("time", exc.messages)
        if isinstance(error_message, list):
            error_message = error_message[0]
        messages.error(request, error_message)
        return redirect("mediator-dashboard")

    appointment.save()

    create_notification(
        doctor.user,
        f"You have been assigned an appointment for {appointment.patient.user.username}."
    )

    create_notification(
        appointment.patient.user,
        f"Dr. {doctor.user.username} has been assigned to your appointment."
    )

    return redirect("mediator-dashboard")


# ---------------- ADMIN CANCEL ----------------
@login_required
def admin_cancel_appointment(request, id):
    denied_response = admin_only(request)
    if denied_response:
        return denied_response

    appointment = get_object_or_404(Appointment, id=id)
    appointment.status = "Cancelled"
    appointment.save()

    create_notification(appointment.patient.user, "Your appointment has been cancelled by admin.")
    return redirect("admin-dashboard")


# ---------------- VERIFY DOCTOR ----------------
@login_required
def verify_doctor(request, id):
    denied_response = admin_only(request)
    if denied_response:
        return denied_response

    doctor = get_object_or_404(Doctor, id=id)
    doctor.is_verified = True
    doctor.save()

    return redirect("admin-dashboard")


# ---------------- MANAGE USERS ----------------
@login_required
def manage_users(request):
    denied_response = admin_only(request)
    if denied_response:
        return denied_response

    patients = Patient.objects.all().select_related("user")
    doctors = Doctor.objects.all().select_related("user")

    patient_data = []
    for patient in patients:
        patient_data.append({
            "patient": patient,
            "appointments": Appointment.objects.filter(patient=patient).count(),
        })

    return render(request, "appointments/manage-users.html", {
        "patients": patient_data,
        "doctors": doctors,
    })


@login_required
@require_POST
def delete_user(request, user_id):
    denied_response = admin_only(request)
    if denied_response:
        return denied_response

    user = get_object_or_404(User, id=user_id)
    user.delete()
    return redirect("manage-users")


# ---------------- FORGOT PASSWORD ----------------
def forgot_password(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password1 = request.POST.get("password1")
        password2 = request.POST.get("password2")

        if password1 != password2:
            messages.error(request, "Passwords do not match")
            return redirect("forgot-password")

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            messages.error(request, "User not found")
            return redirect("forgot-password")

        user.set_password(password1)
        user.save()
        messages.success(request, "Password reset successful. Please login.")
        return redirect("login")

    return render(request, "appointments/forgot_password.html")


# ---------------- CONFIRM TOKEN ----------------
@login_required
def confirm_token(request, id):
    denied_response = admin_only(request)
    if denied_response:
        return denied_response

    appointment = get_object_or_404(Appointment, id=id)
    appointment.is_token_confirmed = True
    appointment.status = "Confirmed"
    appointment.save()

    create_notification(appointment.patient.user, "Your appointment has been confirmed by admin.")
    return redirect("admin-dashboard")


# ---------------- DOWNLOAD TOKEN ----------------
@login_required
def download_token(request, id):
    appointment = get_object_or_404(Appointment, id=id)

    if not is_patient(request.user) or appointment.patient != request.user.patient:
        return HttpResponseForbidden("You cannot download this token.")

    if not appointment.is_token_confirmed:
        return HttpResponse("Token not confirmed yet")

    response = HttpResponse(content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename=token_{appointment.id}.pdf'

    doc = SimpleDocTemplate(response)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph("<b>HOSPITAL APPOINTMENT TOKEN</b>", styles["Title"]))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(f"<b>Patient Name:</b> {appointment.patient.user.username}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Doctor Name:</b> {appointment.doctor.user.username}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Date:</b> {appointment.date}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Time:</b> {appointment.time}", styles["Normal"]))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph(f"<b>Token Number:</b> {appointment.token_number}", styles["Heading2"]))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("<b>Status:</b> Confirmed", styles["Normal"]))
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Please bring this token during your visit.", styles["Italic"]))

    doc.build(elements)
    return response


# ---------------- MEDICAL REPORTS ----------------
@login_required
def upload_medical_report(request, appointment_id):
    if not is_patient(request.user):
        return HttpResponseForbidden("Only patients can upload medical reports.")

    appointment = get_object_or_404(
        Appointment.objects.select_related("doctor__user", "patient__user"),
        id=appointment_id,
        patient=request.user.patient,
    )

    if appointment.doctor_id is None:
        messages.error(request, "You can upload reports only after doctor assignment.")
        return redirect("patient-dashboard")

    if request.method == "POST":
        form = MedicalReportForm(request.POST, request.FILES)
        if form.is_valid():
            report = form.save(commit=False)
            report.patient = request.user.patient
            report.doctor = appointment.doctor
            report.appointment = appointment
            try:
                report.full_clean()
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                report.save()

                create_notification(
                    appointment.doctor.user,
                    f"{request.user.username} uploaded a medical report for appointment #{appointment.id}."
                )

                messages.success(request, "Medical report uploaded successfully.")
                return redirect("patient-reports")
    else:
        form = MedicalReportForm()

    return render(request, "appointments/upload-report.html", {
        "form": form,
        "appointment": appointment,
    })


@login_required
def patient_reports(request):
    if not is_patient(request.user):
        return redirect(get_dashboard_name(request.user))

    reports = MedicalReport.objects.filter(patient=request.user.patient).select_related(
        "appointment",
        "doctor__user",
        "patient__user",
    )
    reports, search_query, report_type = apply_report_filters(reports, request)
    appointments = Appointment.objects.filter(patient=request.user.patient).select_related(
        "doctor__user"
    ).prefetch_related("medical_reports")

    return render(request, "appointments/patient-reports.html", {
        "reports": reports,
        "appointments": appointments,
        "search_query": search_query,
        "selected_report_type": report_type,
        "report_type_choices": MedicalReport.REPORT_TYPE_CHOICES,
    })


@login_required
def doctor_reports(request):
    if not is_doctor(request.user):
        return redirect(get_dashboard_name(request.user))

    reports = MedicalReport.objects.filter(doctor=request.user.doctor).select_related(
        "appointment",
        "patient__user",
        "doctor__user",
    )
    reports, search_query, report_type = apply_report_filters(reports, request)

    return render(request, "appointments/doctor-reports.html", {
        "reports": reports,
        "search_query": search_query,
        "selected_report_type": report_type,
        "report_type_choices": MedicalReport.REPORT_TYPE_CHOICES,
    })


@login_required
def preview_medical_report(request, report_id):
    report = get_object_or_404(
        MedicalReport.objects.select_related("patient__user", "doctor__user", "appointment"),
        id=report_id,
    )

    if not user_can_access_report(request.user, report):
        return HttpResponseForbidden("You are not authorized to access this report.")

    return render(request, "appointments/report-preview.html", {
        "report": report,
        "dashboard_url": get_dashboard_name(request.user),
    })


@login_required
@xframe_options_sameorigin
def serve_medical_report(request, report_id):
    report = get_object_or_404(
        MedicalReport.objects.select_related("patient__user", "doctor__user", "appointment"),
        id=report_id,
    )

    if not user_can_access_report(request.user, report):
        return HttpResponseForbidden("You are not authorized to access this report.")

    content_type, _ = mimetypes.guess_type(report.report_file.name)

    return FileResponse(
        report.report_file.open("rb"),
        as_attachment=False,
        content_type=content_type or "application/octet-stream",
    )


@login_required
def download_medical_report(request, report_id):
    report = get_object_or_404(
        MedicalReport.objects.select_related("patient__user", "doctor__user", "appointment"),
        id=report_id,
    )

    if not user_can_access_report(request.user, report):
        return HttpResponseForbidden("You are not authorized to access this report.")

    return FileResponse(
        report.report_file.open("rb"),
        as_attachment=True,
        filename=report.file_name,
    )


@login_required
@require_POST
def delete_medical_report(request, report_id):
    if not is_patient(request.user):
        return HttpResponseForbidden("Only patients can delete medical reports.")

    report = get_object_or_404(
        MedicalReport.objects.select_related("doctor__user", "appointment"),
        id=report_id,
        patient=request.user.patient,
    )

    if report.report_file:
        report.report_file.delete(save=False)
    report.delete()

    messages.success(request, "Medical report deleted successfully.")
    return redirect("patient-reports")


# ---------------- CHAT ----------------
@login_required
def chat_view(request, appointment_id):
    appointment, denied_response = get_chat_appointment_for_user(request.user, appointment_id)
    if denied_response:
        return denied_response

    chat_messages = appointment.messages.select_related("sender", "receiver")
    other_user = (
        appointment.doctor.user
        if is_patient(request.user)
        else appointment.patient.user
    )

    return render(request, "appointments/chat.html", {
        "appointment": appointment,
        "chat_messages": chat_messages,
        "other_user": other_user,
        "dashboard_url": get_dashboard_name(request.user),
    })


@login_required
@require_POST
def send_message(request, appointment_id):
    appointment, denied_response = get_chat_appointment_for_user(request.user, appointment_id)
    if denied_response:
        return denied_response

    message_text = request.POST.get("message_text", "").strip()
    if not message_text:
        messages.error(request, "Message cannot be empty.")
        return redirect("chat", appointment_id=appointment.id)

    receiver = appointment.doctor.user if is_patient(request.user) else appointment.patient.user
    chat_message = Message(
        sender=request.user,
        receiver=receiver,
        appointment=appointment,
        message_text=message_text,
    )

    try:
        chat_message.full_clean()
    except ValidationError as exc:
        error_message = exc.messages[0] if exc.messages else "Unable to send message."
        messages.error(request, error_message)
    else:
        chat_message.save()

    return redirect("chat", appointment_id=appointment.id)


# ---------------- NOTIFICATIONS ----------------
@login_required
def notifications(request):
    notes = Notification.objects.filter(user=request.user).order_by("-created_at")
    return render(request, "appointments/notifications.html", {
        "notes": notes,
        "dashboard_url": get_dashboard_name(request.user),
    })
