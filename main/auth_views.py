""" Copyright (C) 2021 Patrick Frontzek
This file is part of OpenAssetTracker-Server.

OpenAssetTracker-Server is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

OpenAssetTracker-Server is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with OpenAssetTracker-Server.  If not, see <http://www.gnu.org/licenses/>.
"""

__author__ = "Patrick Frontzek"
__copyright__ = "Copyright 2021, Patrick Frontzek"
__license__ = "GPLv3"

import django.contrib.auth.views as a_views
from django.contrib import messages
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic import FormView

from .forms import UserCreationFormWithoutPassword


@method_decorator(csrf_exempt, "dispatch")
class LoginView(a_views.LoginView):
    template_name = "main/auth/login.html"
    extra_context = {"auth": True}

    def form_valid(self, form):
        messages.success(self.request, f"Erfolgreich als {form.get_user()} angemeldet.")
        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Nutzername und/oder Passwort ungültig!")
        return super().form_invalid(form)


class LogoutView(a_views.LogoutView):
    def dispatch(self, request, *args, **kwargs):
        messages.info(request, "Du wurdest erfolgreich abgemeldet.")
        return super().dispatch(request, *args, **kwargs)


class UserCreationView(FormView):
    template_name = "main/usercreation.html"
    form_class = UserCreationFormWithoutPassword
    success_url = "/"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        from .models import Device

        context["tracker_all"] = Device.objects.all().order_by("sn")
        return context

    def form_valid(self, form):
        user = form.save()
        messages.success(
            self.request, f"Der Nutzer {user.username} wurde erfolgreich erstellt."
        )
        from django.contrib.auth.forms import PasswordResetForm

        pwf = PasswordResetForm({"email": user.email})
        pwf.is_valid()
        pwf.save(
            subject_template_name="main/auth/mail/account_creation_subject.txt",
            email_template_name="main/auth/mail/account_creation.html",
            request=self.request,
        )
        print(user.email)
        return super().form_valid(form)


class PasswordResetView(a_views.PasswordResetView):
    success_url = reverse_lazy("auth:login")
    extra_context = {"auth": True}

    def form_valid(self, form):
        messages.info(
            self.request,
            f"Bitte überprüfen Sie das Postfach von '{form.cleaned_data['email']}'",
        )
        return super().form_valid(form)

    def form_invalid(self, form):
        return self.form_valid(form)


class PasswordResetConfirmView(a_views.PasswordResetConfirmView):
    success_url = reverse_lazy("index")
    extra_context = {"auth": True}

    def form_valid(self, form):
        messages.success(self.request, "Ihr Passwort wurde erfolgreich geändert.")
        return super().form_valid(form)


class PasswordChangeView(a_views.PasswordChangeView):
    success_url = reverse_lazy("index")
    extra_context = {"auth": True}

    def form_valid(self, form):
        messages.success(self.request, "Ihr Passwort wurde erfolgreich geändert.")
        return super().form_valid(form)
