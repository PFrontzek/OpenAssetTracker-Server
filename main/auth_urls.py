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


from django.urls import path

from .auth_views import LoginView
from .auth_views import LogoutView
from .auth_views import PasswordChangeView
from .auth_views import PasswordResetConfirmView
from .auth_views import PasswordResetView
from .auth_views import UserCreationView

app_name = "auth"

urlpatterns = [
    path("login/", LoginView.as_view(), name="login"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path(
        "password_change/",
        PasswordChangeView.as_view(
            template_name="main/auth/password_reset.html", extra_context={"login": True}
        ),
        name="password_change",
    ),
    path(
        "password_reset/",
        PasswordResetView.as_view(
            template_name="main/auth/password_reset.html", extra_context={"login": True}
        ),
        name="password_reset",
    ),
    path(
        "reset/<uidb64>/<token>/",
        PasswordResetConfirmView.as_view(
            template_name="main/auth/password_reset.html", extra_context={"login": True}
        ),
        name="password_reset_confirm",
    ),
    path("create/", UserCreationView.as_view(), name="create_user"),
]
