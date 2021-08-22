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

from django.contrib import admin
from django.http import HttpResponseRedirect

from . import models

# Register your models here.


@admin.register(models.CustomTemplate)
class CustomTemplateAdmin(admin.ModelAdmin):
    flieds = (("id"), ("template_str"))


@admin.register(models.Device)
class DeviceAdmin(admin.ModelAdmin):
    fields = (
        ("alias"),
        ("sn"),
        ("users"),
        ("sleeptime", "sleeptime_unit"),
        ("waketime_offset"),
        ("voltage_offset"),
        ("battery"),
        ("next_wake"),
    )
    readonly_fields = (
        ("battery"),
        ("next_wake"),
    )

    def battery(self, obj):
        return f"{obj.battery}V - {obj.battery_percentage}%"


admin.site.register(models.Celltower)


@admin.register(models.Error)
class ErrorAdmin(admin.ModelAdmin):
    fields = (
        ("nr"),
        ("code"),
        ("flags_str"),
        ("rel_status"),
    )
    readonly_fields = (
        ("flags_str"),
        ("rel_status"),
    )

    def flags_str(self, obj):
        from .api import ErrorFlags

        return f"{repr(ErrorFlags(obj.flags))}"

    def rel_status(self, obj):
        return obj.status


class MeasurementInline(admin.TabularInline):
    model = models.Measurement
    extra = 0

    def get_max_num(self, request, obj=None, **kwargs):
        if obj:
            return obj.measurements.count()
        return super().get_max_num(request, obj, **kwargs)


class CellInline(admin.TabularInline):
    model = models.Celltower

    fields = "radio", "mcc", "mnc", "lac", "cid", "bsic", "lat", "lon"
    readonly_fields = "radio", "mcc", "mnc", "lac", "cid", "bsic"

    extra = 0

    def get_max_num(self, request, obj=None, **kwargs):
        if obj:
            return obj.cells.count()
        return super().get_max_num(request, obj, **kwargs)


@admin.register(models.BaseTransceiverStation)
class BaseTransceiverStationAdmin(admin.ModelAdmin):
    readonly_fields = "mcc", "mnc", "lac", "bsic"
    inlines = (CellInline,)
    change_form_template = "main/admin/base_trasceiver_station.html"

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        if object_id:
            bts = models.BaseTransceiverStation.objects.get(id=object_id)
            extra_context["cells"] = [
                {
                    "latitude": c.lat,
                    "longitude": c.lon,
                    "title": str(c),
                    "range": c.range if c.range else 1.0,
                }
                for c in bts.cells.all()
            ]
            extra_context["location"] = {
                "longitude": bts.longitude,
                "latitude": bts.latitude,
            }
            try:
                bts2 = models.BaseTransceiverStation.objects.get(
                    mnc=bts.mnc, mcc=bts.mcc, lac=bts.lac, id=bts.bsic
                )
                extra_context["bts"] = {
                    "longitude": bts2.longitude,
                    "latitude": bts2.latitude,
                }
            except Exception as e:
                print(e)
                pass
        return super().changeform_view(
            request=request,
            object_id=object_id,
            form_url=form_url,
            extra_context=extra_context,
        )

    def response_change(self, request, obj):
        return super().response_change(request=request, obj=obj)


@admin.register(models.Status)
class StatusAdmin(admin.ModelAdmin):
    # inlines = [MeasurementInline,]
    change_form_template = "main/admin/status.html"

    readonly_fields = (("error_list"),)

    def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
        extra_context = extra_context or {}
        if object_id:
            status: models.Status = models.Status.objects.get(id=object_id)
            extra_context["location"] = {
                "longitude": status.lon,
                "latitude": status.lat,
                "radius": status.radius,
            }
            extra_context["cells"] = [
                {
                    "latitude": m.celltower.lat,
                    "longitude": m.celltower.lon,
                    "title": str(m.celltower),
                    "range": m.distance.meters,
                }
                for m in status.measurements.all()
            ]
        return super().changeform_view(
            request=request,
            object_id=object_id,
            form_url=form_url,
            extra_context=extra_context,
        )

    def response_change(self, request, obj):
        if "_update_location" in request.POST:
            status: models.Status = obj
            status.new_calc_location()
            return HttpResponseRedirect(".")
        return super().response_change(request=request, obj=obj)

    def voltage(self, obj):
        return obj.battery

    def error_list(self, obj):
        return "\r\n".join([e.listable_str() for e in obj.errors.all()])
