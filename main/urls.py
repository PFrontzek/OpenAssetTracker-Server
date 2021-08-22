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


from django.contrib.auth import views as auth_views
from django.templatetags.static import static
from django.urls import include
from django.urls import path
from django.views.generic import RedirectView

from . import api
from . import consumers
from . import views
from .auth_views import PasswordResetConfirmView

urlpatterns = [
    path("", views.IndexView.as_view(), name="index"),
    path("admincontrol", views.AdminControlView.as_view(), name="admincontrol"),
    path("echo", views.echoView.as_view()),
    path("map", views.MapView.as_view(), name="map"),
    path("manifest.webmanifest", views.WebManifestView.as_view(), name="webmanifest"),
    path("map/tabledata", views.TabledataView.as_view(), name="tabledata"),
    path("update", api.StatusView.as_view(), name="update"),
    path("login", auth_views.LoginView.as_view(), name="login"),
    path("account/", include("main.auth_urls", namespace="auth")),
    path("update/statusses", views.UpdateStatuses.as_view()),
    path(
        "account/reset/<uidb64>/<token>/",
        PasswordResetConfirmView.as_view(
            template_name="main/auth/password_reset.html", extra_context={"login": True}
        ),
        name="password_reset_confirm",
    ),
    path(
        "device/<int:imei>/export/<str:format>",
        views.ExportDevice.as_view(),
        name="device_export",
    ),
    path("device/", lambda r: views.HttpResponseBadRequest(), name="device_base"),
    path("debug", views.DebugView.as_view(), name="debug"),
    path("detail", views.DetailInfoView.as_view(), name="detail"),
    path("celltower/<int:stunden>", views.CelltowerView.as_view(), name="celltower"),
    path("update_bts", api.update_bts),
    path("tracker/", lambda r: views.HttpResponseBadRequest(), name="trackerData_base"),
    path("tracker/<int:imei>", views.TrackerDataView.as_view(), name="trackerData"),
    path(
        "favicon.ico",
        RedirectView.as_view(url=static("main/img/favicon.png")),
        name="favicon.ico",
    ),
]

websocket_urlpatterns = [
    path("ws/device/<int:imei>/", consumers.DeviceUpdateConsumer),
    path("ws/user/<int:user_id>/", consumers.UserUpdateConsumer),
]
