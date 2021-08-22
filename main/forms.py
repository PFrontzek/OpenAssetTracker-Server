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

import json
from django.contrib.auth.models import User
from django.forms import CharField
from django.forms import EmailField
from django.forms import HiddenInput
from django.forms import ModelForm

from .models import Device


class UserCreationFormWithoutPassword(ModelForm):
    username = EmailField(label="Email")
    tracker = CharField(widget=HiddenInput())

    class Meta:
        model = User
        fields = ("username",)

    def save(self, commit=True) -> User:
        import string
        from random import SystemRandom

        user: User = super(ModelForm, self).save(commit=False)
        user.email = user.username
        user.set_password(
            "".join(SystemRandom().choices(string.ascii_letters + string.digits, k=128))
        )  # Zufälliges Passwort vergeben
        if commit:
            user.save()
        tracker = json.loads(self.cleaned_data["tracker"])
        for t in tracker:
            d: Device = Device.objects.get(sn=t)
            user.devices.add(d)
        if commit:
            user.save()
        return user


class TrackerSettingsForm(ModelForm):
    class Meta:
        model = Device
        fields = ("alias", "sleeptime", "sleeptime_unit")
