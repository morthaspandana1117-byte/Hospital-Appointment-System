"""
Role-Based Access Control Decorators for Hospital Appointment System

This module provides decorators for enforcing role-based access control:
- Patient, Doctor, Mediator, Admin

Each decorator ensures that only authorized users can access specific views.
"""

from functools import wraps
from django.http import HttpResponseForbidden, HttpResponseRedirect
from django.contrib import messages
from django.shortcuts import reverse


def is_patient(user):
    """Check if user is a patient"""
    return hasattr(user, 'patient') and user.patient is not None


def is_doctor(user):
    """Check if user is a doctor"""
    return hasattr(user, 'doctor') and user.doctor is not None


def is_mediator(user):
    """Check if user is a mediator"""
    return hasattr(user, 'mediator') and user.mediator is not None


def is_admin(user):
    """Check if user is an admin (superuser)"""
    return user.is_superuser


def get_user_role(user):
    """Get the role name for a user"""
    if is_admin(user):
        return 'admin'
    if is_mediator(user):
        return 'mediator'
    if is_doctor(user):
        return 'doctor'
    if is_patient(user):
        return 'patient'
    return 'unknown'


def get_dashboard_url(user):
    """Get the appropriate dashboard URL for a user"""
    if is_admin(user):
        return 'admin-dashboard'
    if is_mediator(user):
        return 'mediator-dashboard'
    if is_doctor(user):
        return 'doctor-dashboard'
    if is_patient(user):
        return 'patient-dashboard'
    return 'login'


def patient_required(view_func):
    """
    Decorator to ensure only patients can access the view.
    Redirects to appropriate dashboard if user is not a patient.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseRedirect(f"{reverse('login')}?next={request.path}")
        
        if not is_patient(request.user):
            messages.error(request, "This page is only accessible to patients.")
            return HttpResponseRedirect(reverse(get_dashboard_url(request.user)))
        
        return view_func(request, *args, **kwargs)
    return wrapper


def doctor_required(view_func):
    """
    Decorator to ensure only verified doctors can access the view.
    Redirects to appropriate dashboard if user is not a doctor.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseRedirect(f"{reverse('login')}?next={request.path}")
        
        if not is_doctor(request.user):
            messages.error(request, "This page is only accessible to doctors.")
            return HttpResponseRedirect(reverse(get_dashboard_url(request.user)))
        
        # Check if doctor is verified
        if not request.user.doctor.is_verified:
            messages.warning(request, "Your account is not verified yet. Please wait for admin approval.")
            return HttpResponseRedirect(reverse(get_dashboard_url(request.user)))
        
        return view_func(request, *args, **kwargs)
    return wrapper


def mediator_required(view_func):
    """
    Decorator to ensure only mediators can access the view.
    Admins can also access mediator pages.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseRedirect(f"{reverse('login')}?next={request.path}")
        
        if not is_mediator(request.user) and not is_admin(request.user):
            messages.error(request, "This page is only accessible to mediators.")
            return HttpResponseRedirect(reverse(get_dashboard_url(request.user)))
        
        return view_func(request, *args, **kwargs)
    return wrapper


def admin_required(view_func):
    """
    Decorator to ensure only admins can access the view.
    """
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return HttpResponseRedirect(f"{reverse('login')}?next={request.path}")
        
        if not is_admin(request.user):
            messages.error(request, "This page is only accessible to administrators.")
            return HttpResponseRedirect(reverse(get_dashboard_url(request.user)))
        
        return view_func(request, *args, **kwargs)
    return wrapper


def role_required(*allowed_roles):
    """
    Decorator to restrict access to specific roles.
    
    Usage:
        @role_required('patient')
        @role_required('doctor', 'mediator')
        @role_required('admin', 'mediator', 'doctor')
    """
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return HttpResponseRedirect(f"{reverse('login')}?next={request.path}")
            
            user_role = get_user_role(request.user)
            
            if user_role not in allowed_roles:
                messages.error(request, f"Access denied. This page requires: {', '.join(allowed_roles)}")
                return HttpResponseRedirect(reverse(get_dashboard_url(request.user)))
            
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


def can_access_appointment(user, appointment, require_owner=False):
    """
    Check if user can access a specific appointment.
    
    Args:
        user: The user to check
        appointment: The appointment object
        require_owner: If True, only the owner (patient) can access
    
    Returns:
        tuple: (can_access, error_message)
    """
    if not appointment:
        return False, "Appointment not found"
    
    # Admin has full access
    if is_admin(user):
        return True, None
    
    # Mediator has access to all appointments
    if is_mediator(user):
        return True, None
    
    # Check patient access
    if is_patient(user):
        if require_owner and appointment.patient.user_id != user.id:
            return False, "You can only access your own appointments"
        return True, None
    
    # Check doctor access
    if is_doctor(user):
        if appointment.doctor_id != user.doctor.id:
            return False, "You can only access your assigned appointments"
        return True, None
    
    return False, "You don't have permission to access this appointment"


def can_modify_appointment(user, appointment):
    """
    Check if user can modify (change status of) a specific appointment.
    
    Args:
        user: The user to check
        appointment: The appointment object
    
    Returns:
        tuple: (can_modify, error_message)
    """
    if not appointment:
        return False, "Appointment not found"
    
    # Admin can modify any appointment
    if is_admin(user):
        return True, None
    
    # Mediator can modify any appointment
    if is_mediator(user):
        return True, None
    
    # Patient can only cancel their own pending appointments
    if is_patient(user):
        if appointment.patient.user_id != user.id:
            return False, "You can only modify your own appointments"
        if appointment.status not in ['Requested', 'Assigned']:
            return False, f"Cannot modify appointment in {appointment.status} status"
        return True, None
    
    # Doctor can only modify their assigned appointments
    if is_doctor(user):
        if appointment.doctor_id != user.doctor.id:
            return False, "You can only modify your assigned appointments"
        if appointment.status not in ['Assigned', 'Accepted']:
            return False, f"Cannot modify appointment in {appointment.status} status"
        return True, None
    
    return False, "You don't have permission to modify this appointment"