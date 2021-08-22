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

import csv
import json
import math
from datetime import timedelta
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Count
from django.db.models import F
from django.db.models import Q
from django.http import HttpRequest
from django.http import HttpResponseBadRequest
from django.http import HttpResponseForbidden
from django.http import JsonResponse
from django.shortcuts import HttpResponse
from django.shortcuts import redirect
from django.shortcuts import render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.base import TemplateView
from django.views.generic.base import View
from random import shuffle
from typing import List

from .forms import UserCreationFormWithoutPassword
from .models import Device
from .models import Measurement
from .models import Status
from .models import User


@method_decorator(csrf_exempt, "dispatch")
class echoView(View):
    def get(self, request):
        return HttpResponse("Hello World!")

    def post(self, request):
        print(request.POST)
        print(request.body)
        return HttpResponse(request.body)


class UpdateStatuses(View):
    def get(self, request: HttpRequest):
        from geopy.geocoders import Nominatim

        geolocator = Nominatim(user_agent="open_asset_tracker_webserver")
        for s in Status.objects.filter(city=None):
            s.set_city(geolocator)
            import time

            time.sleep(1)
        return HttpResponse("OK")


@method_decorator(login_required, "dispatch")
class MapView(View):
    def get(self, request: HttpRequest) -> str:
        context = {"title": "OpenAssetTracker"}
        if request.session.get("debug"):
            context["debug"] = True
            context["title"] = "OpenAssetTracker | Debug"
        return render(request=request, template_name="main/map.html", context=context)
        # return HttpResponse("\n".join([f"{d}: {d.last_position}" for d in Device.objects.all()]), status=200)


@method_decorator(login_required, "dispatch")
class DebugView(View):
    def get(self, request: HttpRequest):
        if request.session.get("debug"):
            del request.session["debug"]
        else:
            request.session["debug"] = True
        return redirect("index")


class DetailInfoView(View):
    def post(self, request: HttpRequest):
        if request.POST["type"] == "status":
            status = Status.objects.get(id=request.POST["id"])
            response = {"lat": status.lat, "lon": status.lon, "radius": status.radius}

            if request.session.get("debug"):
                measurements: List[Measurement] = status.cleaned_measurements
                response["cells"] = [
                    {
                        "lat": m.celltower.lat,
                        "lon": m.celltower.lon,
                        "radius": m.distance.meters,
                    }
                    for m in measurements
                ]
            return JsonResponse(response)

        return HttpResponseBadRequest()


@method_decorator(login_required, "dispatch")
class TabledataView(View):
    def post(self, request: HttpRequest):
        data = json.loads(request.body)
        response = {
            "draw": int(data["draw"]),
            "data": [],
            "recordsTotal": 0,
            "recordsFiltered": 0,
            "error": None,
        }

        if data["type"] == "status":
            col_map = [
                F("timestamp"),
                F("city__country__code"),
                F("city__name"),
                F("celltower__count"),
                F("temp"),
                F("voltage_raw"),
            ]
            device = None

            if data["imei"] == 0:
                response["data"] = []
                response["recordsFiltered"] = 0
                response["recordsTotal"] = 0
            else:
                try:
                    device = Device.objects.get(sn=int(data["imei"]))
                    if request.user not in device.users.all():
                        return HttpResponseForbidden()
                    status_query = Status.objects.filter(device=device).annotate(Count("celltower"))
                    if data["timespan"]["start"] != 0:
                        status_query = status_query.filter(
                            timestamp__gt=timezone.datetime.fromtimestamp(data["timespan"]["start"])
                        )
                    if data["timespan"]["end"] != 0:
                        status_query = status_query.filter(
                            timestamp__lt=timezone.datetime.fromtimestamp(data["timespan"]["end"])
                        )
                    if len(data["search"]["value"]) > 0:
                        status_query = status_query.filter(
                            Q(city__name__contains=data["search"]["value"])
                            | Q(city__country__code__contains=data["search"]["value"])
                            | Q(city__country__name__contains=data["search"]["value"])
                        )
                    status_query = (
                        status_query.all()
                        .order_by(*[col_map[o["column"]].__getattribute__(o["dir"])() for o in data["order"]])
                        .all()
                    )
                except Exception as e:
                    response["error"] = str(e)
                    status_query = Status.objects.none()

                paginator = Paginator(status_query, data["length"])
                response["data"] = [
                    {
                        "timestamp": {
                            "display": str(timezone.localtime(s.timestamp).strftime("%d.%m.%Y %H:%M:%S")),
                            "timestamp": int(s.timestamp.timestamp()),
                        },
                        "battery": {
                            "voltage": s.voltage,
                            "percentage": s.battery_percentage,
                            "display": "",
                        },
                        "lon": s.lon,
                        "lat": s.lat,
                        "id": s.id,
                        "radius": s.radius * 1000,
                        "city": s.city.name if s.city else "???",
                        "celltower": len(s.cleaned_measurements),
                        "country": s.country.code if s.country else "???",
                        "temp": s.temp if s.temp != -math.inf else "???",
                    }
                    for s in paginator.get_page(int(data["start"]) / paginator.per_page + 1)
                ]
                if request.session.get("debug"):
                    nextwake = device.next_update_expected()
                    response["data"].insert(
                        0,
                        {
                            "timestamp": {
                                "display": str(timezone.localtime(nextwake).strftime("%d.%m.%Y %H:%M:%S")),
                                "timestamp": int(nextwake.timestamp()),
                            },
                            "battery": {"voltage": 0, "percentage": 0, "display": "-"},
                            "lon": 0.0,
                            "lat": 0.0,
                            "id": 0,
                            "radius": 0,
                            "city": "...",
                            "celltower": "...",
                            "country": "...",
                            "temp": "...",
                        },
                    )
                response["recordsFiltered"] = paginator.count
                response["recordsTotal"] = Status.objects.filter(device=device).count() if data["imei"] != 0 else 0

        elif data["type"] == "tracker":
            col_map = ["sn", "alias", "last_position__voltage_raw"]
            try:
                devices = (
                    request.user.devices.filter(
                        Q(sn__contains=data["search"]["value"]) | Q(alias__contains=data["search"]["value"])
                    )
                    .all()
                    .order_by(*[F(col_map[o["column"]]).__getattribute__(o["dir"])() for o in data["order"]])
                )
            except Exception as e:
                devices = []
                response["error"] = str(e)
            paginator = Paginator(devices, int(data["length"]))
            response["data"] = [
                {
                    "imei": d.sn,
                    "alias": d.alias,
                    "battery": {
                        "percentage": d.battery_percentage,
                        "voltage": d.battery,
                        "display": "",
                    },
                }
                for d in paginator.get_page(int(data["start"]) / paginator.per_page + 1)
            ]

            response["recordsTotal"] = len(request.user.devices.all())
            response["recordsFiltered"] = len(devices)
        else:
            return HttpResponseBadRequest()
        for d in response["data"]:
            if not d["battery"]["percentage"] is None:
                percentage = d["battery"]["percentage"]
                voltage = d["battery"]["voltage"]
                display = f'<span class="tooltipped" data-toggle="tooltip" data-placement="left" title="{voltage:.1f}V  {percentage:.0f}%"><i class="fas fa-battery-{{}} {{}}"></i></span>'
                if percentage > 85:
                    display = display.format("full", "text-success")
                elif percentage > 65:
                    display = display.format("three-quarters", "text-success")
                elif percentage > 35:
                    display = display.format("half", "text-success")
                elif percentage > 10:
                    display = display.format("quarter", "text-warning")
                else:
                    display = display.format("empty", "text-danger")
                d["battery"]["display"] = display
            else:
                d["battery"]["display"] = "<span>???</span>"
        if response["error"] is None:
            del response["error"]
        return JsonResponse(response, safe=False)


@method_decorator(login_required, "dispatch")
class ExportDevice(View):
    def get(self, request: HttpRequest, imei: int, format: str):
        device = Device.objects.get(sn__exact=imei)
        if request.user not in device.users.all():
            return HttpResponseForbidden()
        start = timezone.datetime.fromtimestamp(int(request.GET["start"] or 0))
        end = timezone.datetime.fromtimestamp(int(request.GET["end"] or 0))
        if end == timezone.datetime.fromtimestamp(0):
            end = timezone.datetime.max

        status_query = device.status_set.all()
        if start != timezone.datetime.min:
            status_query = status_query.filter(timestamp__gt=start)
        if end != timezone.datetime.max:
            status_query = status_query.filter(timestamp__lt=end)

        response = HttpResponse(content_type=f"text/{format}")
        fmt = "%Y%m%d%H%M"
        response[
            "Content-Disposition"
        ] = f'attachment; filename="OpenAssetTracker_{imei}_{start.strftime(fmt)}-{end.strftime(fmt)}.{format}"'

        if format == "csv":
            writer = csv.writer(response)
            writer.writerow(
                [
                    "Time",
                    "Timestamp_UTC",
                    "City",
                    "Country",
                    "Temperature",
                    "Battery",
                    "Latitude",
                    "Longitude",
                ]
            )
            for s in status_query:
                s: Status
                writer.writerow(
                    [
                        str(s.timestamp),
                        int(s.timestamp.timestamp()),
                        s.city.name if s.city else "???",
                        s.country.name if s.country else "???",
                        s.temp if s.temp else "???",
                        s.voltage,
                        s.lat,
                        s.lon,
                    ]
                )
        elif format == "gpx":
            import gpxpy

            gpx = gpxpy.gpx.GPX()
            gpx.tracks.append(gpxpy.gpx.GPXTrack())
            from .utils import DistanceFunction
            from .utils import ErrorFunction
            from .utils import OptimizationAlgorithm

            kwargs_list = []
            for i, df in enumerate(DistanceFunction):
                for j, ef in enumerate(ErrorFunction):
                    for k, oa in enumerate(OptimizationAlgorithm):
                        for max_tower in range(1, 8):
                            for r in (False, True):
                                kwargs_list.append(
                                    {
                                        "error_function": ef,
                                        "distance_function": df,
                                        "oa": oa,
                                        "max_tower": max_tower,
                                        "random_tower": r,
                                    }
                                )
            shuffle(kwargs_list)
            status_ids = status_query.values_list("id", flat=True)

            from multiprocessing import Pool

            from .utils import _mp_count
            from .utils import get_locations

            with Pool() as p:
                _mp_count.value = 0
                for kwargs in kwargs_list:
                    kwargs["len"] = len(kwargs_list)
                    kwargs["status_ids"] = status_ids

                locations = p.map(get_locations, kwargs_list)
                for (points, distances, times), kwargs in zip(locations, kwargs_list):
                    if points is None:
                        continue
                    track = gpxpy.gpx.GPXTrack(
                        f"{kwargs['distance_function'].name}-{kwargs['error_function'].name}-{kwargs['oa'].name}-{kwargs['max_tower']}{'-random' if kwargs['random_tower'] else ''}"
                    )
                    segment = gpxpy.gpx.GPXTrackSegment()
                    for (latitude, longitude), distance, time in zip(points, distances, times):
                        segment.points.append(
                            gpxpy.gpx.GPXTrackPoint(
                                latitude=latitude,
                                longitude=longitude,
                                position_dilution=distance,
                                time=time.astimezone(timezone.utc),
                            )
                        )
                    track.segments.append(segment)
                    gpx.tracks.append(track)
            response.write(gpx.to_xml())
        else:
            return HttpResponseBadRequest()

        return response


class WebManifestView(TemplateView):
    template_name = "main/manifest.webmanifest"
    content_type = "application/manifest+json"


class CelltowerView(View):
    def get(self, request: HttpRequest, stunden: int):
        devices = Device.objects.all()
        response = {}

        for device in devices:
            response[device.alias] = []
            status_set = device.status_set.filter(timestamp__gte=timezone.now() - timedelta(hours=stunden))
            celltower_set = set()
            for s in status_set:
                for m in s.measurements.all():
                    celltower_set.add(m.celltower)

            for celltower in celltower_set:
                response[device.alias].append(
                    {
                        "count": status_set.filter(measurements__celltower=celltower).count(),
                        "lat": celltower.lat,
                        "lon": celltower.lon,
                        "cid": hex(celltower.cid),
                        "lac": hex(celltower.lac),
                        "url": f"https://maps.google.com/?daddr={celltower.lat},{celltower.lon}",
                    }
                )

            response[device.alias].sort(key=lambda o: o["count"], reverse=True)

            # response[device.alias] = {(f"{c} lat: {c.lat} lon: {c.lon}", c.measurements.filter(status__timestamp__gte=timezone.now() - timedelta(hours=12)).count()) for c in celltower_set}

            # response[device.alias] = models.Measurement.objects.filter(status__in=status_set).aggregate(Count("celltower"))
            # celltower_set = set([s.celltower for s in status_set])
            # response[device.alias] = ()
            # response[device.alias] = [f"{tower} LAT: {tower.lat} LON: {tower.lon}" for tower in celltower.filter(measurements__status__device=device)]

        return JsonResponse(response)


@method_decorator(staff_member_required, "dispatch")
class AdminControlView(View):
    def get(self, request: HttpRequest):
        usercreationform = UserCreationFormWithoutPassword()
        context = {
            "users": User.objects.all(),
            "usercreationform": usercreationform,
            "devices": Device.objects.all(),
            "sleeptimeUnits": Device.SleeptimeUnit.choices,
        }
        return render(request, "main/admin.html", context=context)


@method_decorator(login_required, "dispatch")
class TrackerDataView(View):
    def get(self, request: HttpRequest, imei: int):
        device = Device.objects.get(sn__exact=imei)
        if not device.users.filter(id=request.user.id).exists() and not request.user.is_staff:
            return HttpResponseForbidden()
        return JsonResponse(device.get_json_data(include_users=request.user.is_staff))

    def post(self, request: HttpRequest, imei: int):
        device = Device.objects.get(sn__exact=imei)
        if int(request.POST["imei"]) != imei or (
            not device.users.filter(id=request.user.id).exists() and not request.user.is_staff
        ):
            return HttpResponseForbidden()
        device.alias = request.POST["alias"]
        device.sleeptime = int(request.POST["sleeptime"])
        if int(request.POST["sleeptime_unit"]) in Device.SleeptimeUnit.choices:
            device.sleeptime_unit = int(request.POST["sleeptime_unit"])
        device.save()
        return HttpResponse(status=200)


class IndexView(View):
    def get(self, request: HttpRequest):
        return redirect("map")
