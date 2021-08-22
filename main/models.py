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

import math
from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.template import Template
from django.utils import timezone
from typing import List
from typing import Optional
from typing import Tuple

import geopy
import numpy as np
from geopy import Nominatim
from geopy import Point
from geopy import distance as gd
from geopy.distance import Distance

# User = settings.AUTH_USER_MODEL


class CustomTemplate(models.Model):
    id = models.SlugField(primary_key=True)
    template_str = models.TextField(verbose_name="Template String")

    def get_template(self) -> Template:
        return Template(self.template_str)


class Country(models.Model):
    name = models.CharField(max_length=64)
    code = models.CharField(max_length=8)

    def __str__(self):
        return f"{self.name}"


class City(models.Model):
    name = models.CharField(verbose_name="Stadtname", max_length=64)
    country = models.ForeignKey(
        Country, models.SET_NULL, related_name="cities", null=True
    )

    def __str__(self):
        return f"{self.name} ({self.country})"


class Device(models.Model):
    class SleeptimeUnit(models.IntegerChoices):
        seconds = 1, "Sekunden"
        minutes = 60, "Minuten"
        hours = 60 * 60, "Stunden"
        days = 60 * 60 * 24, "Tage"

    sn = models.CharField(
        verbose_name="Seriennummer", max_length=64, unique=True, db_index=True
    )
    last_position = models.ForeignKey(
        "Status",
        on_delete=models.DO_NOTHING,
        verbose_name="Last Position",
        null=True,
        related_name="+",
        blank=True,
    )
    users = models.ManyToManyField(
        User, related_name="devices", verbose_name="Benutzer", blank=True, default=None
    )
    alias = models.CharField(
        verbose_name="Alias", max_length=128, default=str, blank=True
    )
    sleeptime = models.FloatField(verbose_name="Wartezeit", default=2.0)
    sleeptime_unit = models.IntegerField(
        verbose_name="Wartezeit Einheit",
        choices=SleeptimeUnit.choices,
        default=SleeptimeUnit.hours,
    )
    waketime_offset = models.IntegerField(verbose_name="Vorlauf (s)", default=30)
    next_wake = models.DateTimeField(
        verbose_name="Nächstes Update", default=timezone.now
    )
    voltage_offset = models.FloatField(
        verbose_name="Spannungsverschiebung (V)", default=0.0
    )
    vcc_arduino = models.FloatField(verbose_name="Arduino VCC", default=4.46)

    battery = property(
        lambda self: self.get_last_position().voltage
        if self.get_last_position()
        else None
    )
    battery_percentage = property(
        lambda self: self.get_last_position().battery_percentage
        if self.get_last_position()
        else None
    )

    def get_next_waketime(self):
        from django.utils import timezone

        now = timezone.now()
        next = now - timezone.timedelta(
            seconds=int(now.timestamp()) % int(self.sleeptime * self.sleeptime_unit)
        )

        next -= timezone.timedelta(seconds=self.waketime_offset)
        while next < timezone.now():
            next += timezone.timedelta(seconds=self.sleeptime * self.sleeptime_unit)

        # next = self.next_wake if self.next_wake + timezone.timedelta(seconds=self.sleeptime*self.sleeptime_unit*10) > timezone.now() else timezone.now()
        # next -= timezone.timedelta(seconds=self.waketime_offset)
        # while next < timezone.now():
        #     next += timezone.timedelta(seconds=self.sleeptime * self.sleeptime_unit)
        #
        return next

    def next_update_expected(self):
        next = self.next_wake + timezone.timedelta(seconds=self.waketime_offset)
        while next < timezone.now():
            next += timezone.timedelta(minutes=5, seconds=self.waketime_offset / 2)
        return next

    def __str__(self):
        return f"{self.alias} - {self.sn}"

    def save(self, *args, **kwargs):
        if "update_position" in kwargs:
            if kwargs["update_position"]:
                self.last_position = self.get_last_position()
            del kwargs["update_position"]
        super(Device, self).save(*args, **kwargs)

    def get_last_position(self) -> Optional["Status"]:
        if self.status_set.exists():
            return self.status_set.latest("timestamp")
        else:
            return None

    def get_json_data(self, include_users=False):
        data = {
            "imei": self.sn,
            "alias": self.alias,
            "sleeptime": self.sleeptime,
            "sleeptime_unit": self.sleeptime_unit,
        }
        if include_users:
            data["users"] = list(self.users.values_list("id", flat=True))

        return data


class Status(models.Model):
    device = models.ForeignKey("Device", on_delete=models.CASCADE, null=False)
    lat = models.FloatField(verbose_name="Latitude")
    lon = models.FloatField(verbose_name="Longitude")
    radius = models.FloatField(verbose_name="Radius")
    timestamp = models.DateTimeField(verbose_name="Timestamp", db_index=True)
    raw_data = models.TextField(max_length=1024, blank=True, default=str)
    parsed_data = models.TextField(max_length=4096, blank=True, default=str)
    voltage_raw = models.FloatField(verbose_name="Spannung", default=0.0)
    city = models.ForeignKey(City, models.SET_NULL, null=True, blank=True)
    celltower = models.ManyToManyField(
        "Celltower", through="Measurement", verbose_name="Funkmasten"
    )
    temp = models.FloatField(verbose_name="Temperatur", default=-math.inf)
    voltage_ref = models.IntegerField(default=-1)
    measurements: models.Manager

    @property
    def cleaned_measurements(self) -> List["Measurement"]:
        from geopy import distance

        measurements: List[Measurement] = []
        min_distance = 1
        for m in self.measurements.all():
            found = False
            for i in range(len(measurements)):
                if (
                    distance.distance(
                        m.celltower.point, measurements[i].celltower.point
                    ).meters
                    < min_distance
                ):
                    found = True
                    if m.rxl > measurements[i].rxl:
                        measurements[i] = m
            if not found:
                measurements.append(m)
        return sorted(measurements, key=lambda obj: obj.rxl, reverse=True)

    @property
    def country(self):
        if self.city:
            return self.city.country
        else:
            return Country.objects.get_or_create(name="UNKNOWN", code="???")[0]

    @property
    def voltage(self):
        if self.voltage_ref > -1:
            return (
                11
                * (1.1 * self.device.vcc_arduino / (1.10 * 1023 / (self.voltage_ref)))
                / 1023
                * self.voltage_raw
            ) + self.device.voltage_offset
        return self.voltage_raw + self.device.voltage_offset

    @property
    def battery_percentage(self):
        n = 3708
        abschnitte = {
            0: 8.35221210479736,
            115: 8.23313919067382,
            483: 7.98308769226074,
            966: 7.69731489181518,
            1817: 7.28056255340576,
            2760: 7.10195461273193,
            3427: 6.81618181228637,
            3542: 6.66138807296752,
            3634: 6.25654283523559,
            3680: 5.80406871795654,
            n: 5.35,
        }
        last_u, last_base = 0.0, 0.0
        for i, u in abschnitte.items():
            base = (n - i) / n
            if self.voltage >= u:
                if i == 0:
                    return 100
                return (
                    base + (last_base - base) * ((self.voltage - u) / (last_u - u))
                ) * 100

            last_u, last_base = u, base
        # return 0
        # 6.5V Minimum; 6.5 + 1.9 = 8.4
        return min(max((round((self.voltage - 6.5) / 1.9 * 100)), 0.0), 100.0)

    class Meta:
        ordering = ("-timestamp",)

    @property
    def point(self):
        from geopy import Point

        return Point(self.lat, self.lon)

    def __str__(self):
        return f"{self.device}: {self.timestamp}" + (
            f" - Errors: {len(self.errors.all())}" if len(self.errors.all()) > 0 else ""
        )

    def save(self, *args, **kwargs):
        super(Status, self).save(*args, **kwargs)
        if (
            self.device.last_position is None
            or self.device.last_position.timestamp < self.timestamp
        ):
            self.device.last_position = self
            self.device.save(update_position=False)

    def set_city(self, geolocator: Nominatim = None):
        if not geolocator:
            geolocator = Nominatim(user_agent="open_asset_tracker_webserver")
        if not self.city:
            from geopy import Location
            from geopy import Point

            unknown_country = Country.objects.get_or_create(name="UNKNOWN", code="???")[
                0
            ]
            unknown_city = City.objects.get_or_create(
                name="UNKNOWN", country=unknown_country
            )[0]
            self.city = unknown_city
            try:
                location: Location = geolocator.reverse(
                    Point(latitude=self.lat, longitude=self.lon), exactly_one=True
                )
                if "country" in location.raw["address"]:
                    country = Country.objects.get_or_create(
                        name=location.raw["address"]["country"]
                    )[0]
                    if "country_code" in location.raw["address"]:
                        country.code = str(
                            location.raw["address"]["country_code"]
                        ).upper()
                        country.save()
                else:
                    country = unknown_country
                place = None
                if "city" in location.raw["address"]:
                    place = "city"
                elif "town" in location.raw["address"]:
                    place = "town"
                elif "village" in location.raw["address"]:
                    place = "village"
                if place:
                    self.city = City.objects.get_or_create(
                        name=location.raw["address"][place], country=country
                    )[0]
                else:
                    self.city = City.objects.get_or_create(
                        name="UNKNOWN", country=country
                    )[0]
            except Exception as e:
                print(e)
        self.save()

    def calc_location(self):
        from .utils import ErrorFunction
        from .utils import Measurement
        from .utils import OptimizationAlgorithm
        from .utils import lateration_new

        if len(self.cleaned_measurements) > 1:
            point, distance = lateration_new(
                [
                    Measurement(m.celltower.point, m.distance.kilometers)
                    for m in self.cleaned_measurements
                ],
                error_function=ErrorFunction.MAE,
                method=OptimizationAlgorithm.NELDER_MEAD,
            )
        else:
            cell = self.measurements.first().celltower
            point = cell.point
            distance = self.measurements.first().distance
        self.lat = point.latitude
        self.lon = point.longitude
        self.radius = distance.kilometers
        self.save()

    def new_calc_location(self):
        from .utils import ErrorFunction
        from .utils import Measurement
        from .utils import OptimizationAlgorithm
        from .utils import lateration_new

        if len(self.cleaned_measurements) > 1:
            point, distance = lateration_new(
                [
                    Measurement(m.celltower.point, m.distance.kilometers)
                    for m in self.cleaned_measurements
                ],
                error_function=ErrorFunction.ME,
                method=OptimizationAlgorithm.NELDER_MEAD,
            )
        else:
            cell = self.measurements.first().celltower
            point = cell.point
            distance = self.measurements.first().distance
        self.lat = point.latitude
        self.lon = point.longitude
        self.radius = distance.kilometers
        self.save()

    def get_point(
        self,
        error_function,
        distance_function,
        oa,
        max_tower: int = None,
        random_tower=False,
    ) -> Tuple[geopy.Point, geopy.distance.Distance]:
        measurements = self.measurements.all()
        if max_tower and max_tower != 1:
            if random_tower:
                measurements = measurements.order_by("?")
            else:
                measurements = measurements.order_by("rxl").reverse()
            measurements = list(measurements)[:max_tower]
        measurements = list(measurements)
        measurements.sort(key=lambda s: s.rxl, reverse=True)
        if len(measurements) > 1:
            from .utils import Measurement
            from .utils import lateration_new

            return lateration_new(
                [
                    Measurement(
                        m.celltower.point,
                        m.get_distance(
                            distance_function, dbm=m.dbm, frequency=m.frequency_downlink
                        ).kilometers,
                    )
                    for m in measurements
                ],
                error_function,
                method=oa,
            )
        else:
            m = measurements[0]
            return m.celltower.point, m.get_distance(distance_function)


class Error(models.Model):
    status = models.ForeignKey(Status, models.CASCADE, related_name="errors")
    nr = models.IntegerField()
    flags = models.PositiveSmallIntegerField()
    code = models.PositiveSmallIntegerField()

    class Meta:
        unique_together = (("status", "nr"),)

    def __str__(self):
        from .api import ErrorFlags

        return f"{self.status}: Nr. {self.nr} - {repr(ErrorFlags(self.flags))} - Code {self.code}"

    def listable_str(self) -> str:
        from .api import ErrorFlags

        return f"{self.nr}: {repr(ErrorFlags(self.flags))} - {self.code}"


class Measurement(models.Model):
    status = models.ForeignKey(Status, models.CASCADE, related_name="measurements")
    celltower = models.ForeignKey(
        "Celltower",
        models.CASCADE,
        related_name="measurements",
        verbose_name="Funkmasten",
    )
    rxl = models.IntegerField()
    arfcn = models.IntegerField(default=None, null=True, blank=True)

    @property
    def frequency_uplink(self):
        arfcn = self.arfcn if self.arfcn and self.arfcn != (2 ** 16) - 1 else 0
        if 0 <= arfcn <= 124:
            return 890.0 + 0.2 * (arfcn - 0)
        elif 128 <= arfcn <= 251:
            return 824.2 + 0.2 * (arfcn - 128)
        elif 259 <= arfcn <= 293:
            return 450.6 + 0.2 * (arfcn - 259)
        elif 306 <= arfcn <= 340:
            return 479.0 + 0.2 * (arfcn - 306)
        elif 438 <= arfcn <= 511:
            return 747.2 + 0.2 * (arfcn - 438)
        elif 512 <= arfcn <= 885:
            return 1710.2 + 0.2 * (arfcn - 512)
        elif 955 <= arfcn <= 1023:
            return 890.0 + 0.2 * (arfcn - 1024)

    @property
    def frequency_downlink(self):
        # return 900
        arfcn = self.arfcn if self.arfcn and self.arfcn != (2 ** 16) - 1 else 0
        if 0 <= arfcn <= 124:
            return self.frequency_uplink + 45
        elif 128 <= arfcn <= 251:
            return self.frequency_uplink + 45
        elif 259 <= arfcn <= 293:
            return self.frequency_uplink + 10
        elif 306 <= arfcn <= 340:
            return self.frequency_uplink + 10
        elif 438 <= arfcn <= 511:
            return self.frequency_uplink + 30
        elif 512 <= arfcn <= 885:
            return self.frequency_uplink + 95
        elif 955 <= arfcn <= 1023:
            return self.frequency_uplink + 45

    @property
    def frequency_band(self):
        arfcn = self.arfcn if self.arfcn and self.arfcn != (2 ** 16) - 1 else 0
        if 0 <= arfcn <= 124:
            return "GSM 900"
        elif 128 <= arfcn <= 251:
            return "GSM 850"
        elif 259 <= arfcn <= 293:
            return "GSM 500"
        elif 306 <= arfcn <= 340:
            return "GSM 500"
        elif 438 <= arfcn <= 511:
            return "GSM 700"
        elif 512 <= arfcn <= 885:
            return "GSM 1800"
        elif 955 <= arfcn <= 1023:
            return "GSM 900"

    @property
    def dbm(self) -> int:
        return -(113 - self.rxl)

    @property
    def mw(self) -> float:
        from numpy import float_power

        return float(float_power(10, self.dbm / 10))

    def get_path_loss(
        self, max_tx_mw: float = 20_000, max_tx_dbm=None, dbm: float = None
    ) -> float:
        if dbm is None:
            dbm = self.dbm
        key = f"path_loss_dbm{max_tx_mw}{max_tx_dbm}{dbm}"
        PL = cache.get(key)
        if PL:
            return PL
        TX = max_tx_dbm if max_tx_dbm else 10 * np.log10(max_tx_mw)
        PL = TX - dbm
        cache.set(key, PL, None)
        return PL

    def path_loss(
        self, v: float = 2, C: float = 0, dbm: float = None, frequency: float = None
    ) -> Distance:
        if dbm is None:
            dbm = self.dbm
        if frequency is None:
            frequency = self.frequency_downlink
        key = f"path_loss_new{v}{C}{dbm}{frequency}"
        distance = cache.get(key)
        if distance:
            return Distance(distance)

        # v = 2: Free Space (vacuum)
        # v = 2.5: Outdoor - rural
        # v = 3-4: Outdoor - urban
        # v = 4-5: Outdoor - dense urban
        # v = 1.6 - 1.8: Indoor - large open areas
        # v = 4-6: Indoor - no line of sight

        # PL = 10 * v * np.log10(d) + C
        # PL - C = 10 * v * np.log10(d)
        # (PL - C) / (10 * v) = np.log10(d)
        # np.float_power(10, (PL - C) / (10 * v)) = d
        # distance = np.float_power(10, (self.get_path_loss() - C) / (10 * v))

        # lambda = c / f
        # PL = 10 * v * np.log10((4 * pi * d) / lambda)
        # PL / (10 * v) = np.log10((4 * pi * d) / lambda)
        # np.power(10, PL / (10 * v)) = (4 * pi * d) / lambda
        # np.power(10, PL / (10 * v)) / lambda = 4 * pi * d
        # (np.power(10, PL / (10 * v)) / lambda) / 4 * pi = d
        from scipy.constants import c
        from scipy.constants import kilo
        from scipy.constants import mega
        from scipy.constants import pi

        f = frequency * mega
        _lambda = c / f
        distance = (
            (np.power(10, self.get_path_loss(dbm=dbm) / (10 * v)) / _lambda) / 4 * pi
        )

        cache.set(key, distance, None)
        return Distance(distance * kilo)

    def hata(
        self,
        enviroment: str = "open",
        h_M: float = 3.0,
        h_B: float = 80.0,
        dbm: float = None,
        frequency: float = None,
    ) -> Distance:
        if dbm is None:
            dbm = self.dbm
        if frequency is None:
            frequency = self.frequency_downlink
        key = f"hata{enviroment}{h_B}{h_M}{dbm}{frequency}"
        distance = cache.get(key)
        if distance:
            return gd.distance(distance)

        if not enviroment.startswith("urban") or (
            enviroment.endswith("small") or enviroment.endswith("medium")
        ):
            # Small / medium city
            C_H = (
                0.8
                + (1.1 * np.log10(frequency) - 0.7) * h_M
                - 1.56 * np.log10(frequency)
            )
        else:
            # large city
            C_H = 3.2 * np.power(np.log10(11.75 * h_M), 2) - 4.97

        # L_U = 69.55 + 26.16 * np.log10(self.frequency_downlink) - 13.82 * np.log10(h_B) - C_H + (44.9 - 6.55 * np.log10(h_B)) * np.log10(d)

        if enviroment == "open":
            # L_O = L_U - 4.78 * np.power(np.log10(self.frequency_downlink), 2) + 18.33 * np.log10(self.frequency_downlink) - 40.94
            # L_O + 4.78 * np.power(np.log10(self.frequency_downlink), 2) - 18.33 * np.log10(self.frequency_downlink) + 40.94 = 69.55 + 26.16 * np.log10(self.frequency_downlink) - 13.82 * np.log10(h_B) - C_H + (44.9 - 6.55 * np.log10(h_B)) * np.log10(d)
            # L_O + 4.78 * np.power(np.log10(self.frequency_downlink), 2) - 18.33 * np.log10(self.frequency_downlink) + 40.94 - 69.55 - 26.16 * np.log10(self.frequency_downlink) + 13.82 * np.log10(h_B) + C_H = (44.9 - 6.55 * np.log10(h_B)) * np.log10(d)
            # (L_O + 4.78 * np.power(np.log10(self.frequency_downlink), 2) - 18.33 * np.log10(self.frequency_downlink) + 40.94 - 69.55 - 26.16 * np.log10(self.frequency_downlink) + 13.82 * np.log10(h_B) + C_H) / (44.9 - 6.55 * np.log10(h_B)) = np.log10(d)
            # np.power(10, (L_O + 4.78 * np.power(np.log10(self.frequency_downlink), 2) - 18.33 * np.log10(self.frequency_downlink) + 40.94 - 69.55 - 26.16 * np.log10(self.frequency_downlink) + 13.82 * np.log10(h_B) + C_H) / (44.9 - 6.55 * np.log10(h_B))) = d
            distance = np.float_power(
                10,
                (
                    self.get_path_loss(dbm=dbm)
                    + 4.78 * np.power(np.log10(frequency), 2)
                    - 18.33 * np.log10(frequency)
                    + 40.94
                    - 69.55
                    - 26.16 * np.log10(frequency)
                    + 13.82 * np.log10(h_B)
                    + C_H
                )
                / (44.9 - 6.55 * np.log10(h_B)),
            )
        elif enviroment == "suburban":
            # L_SU = L_U - 2 * np.power(np.log10(self.frequency_downlink/28), 2) - 5.4
            # L_SU + 2 * np.power(np.log10(self.frequency_downlink/28), 2) + 5.4 = 69.55 + 26.16 * np.log10(self.frequency_downlink) - 13.82 * np.log10(h_B) - C_H + (44.9 - 6.55 * np.log10(h_B)) * np.log10(d)
            # L_SU + 2 * np.power(np.log10(self.frequency_downlink/28), 2) + 5.4 - 69.55 - 26.16 * np.log10(self.frequency_downlink) + 13.82 * np.log10(h_B) + C_H = (44.9 - 6.55 * np.log10(h_B)) * np.log10(d)
            # (L_SU + 2 * np.power(np.log10(self.frequency_downlink/28), 2) + 5.4 - 69.55 - 26.16 * np.log10(self.frequency_downlink) + 13.82 * np.log10(h_B) + C_H) / (44.9 - 6.55 * np.log10(h_B)) = np.log10(d)
            # np.power(10, (L_SU + 2 * np.power(np.log10(self.frequency_downlink/28), 2) + 5.4 - 69.55 - 26.16 * np.log10(self.frequency_downlink) + 13.82 * np.log10(h_B) + C_H) / (44.9 - 6.55 * np.log10(h_B))) = d
            distance = np.float_power(
                10,
                (
                    self.get_path_loss(dbm=dbm)
                    + 2 * np.power(np.log10(frequency / 28), 2)
                    + 5.4
                    - 69.55
                    - 26.16 * np.log10(frequency)
                    + 13.82 * np.log10(h_B)
                    + C_H
                )
                / (44.9 - 6.55 * np.log10(h_B)),
            )
        elif enviroment.startswith("urban"):
            # L_U = 69.55 + 26.16 * np.log10(self.frequency_downlink) - 13.82 * np.log10(h_B) - C_H + (44.9 - 6.55 * np.log10(h_B)) * np.log10(d)
            # L_U - 69.55 - 26.16 * np.log10(self.frequency_downlink) + 13.82 * np.log10(h_B) + C_H = (44.9 - 6.55 * np.log10(h_B)) * np.log10(d)
            # (L_U - 69.55 - 26.16 * np.log10(self.frequency_downlink) + 13.82 * np.log10(h_B) + C_H) / (44.9 - 6.55 * np.log10(h_B)) = np.log10(d)
            # np.power(10, (L_U - 69.55 - 26.16 * np.log10(self.frequency_downlink) + 13.82 * np.log10(h_B) + C_H) / (44.9 - 6.55 * np.log10(h_B))) = d
            distance = np.float_power(
                10,
                (
                    self.get_path_loss(dbm=dbm)
                    - 69.55
                    - 26.16 * np.log10(frequency)
                    + 13.82 * np.log10(h_B)
                    + C_H
                )
                / (44.9 - 6.55 * np.log10(h_B)),
            )

        cache.set(key, distance, None)
        return gd.distance(distance)

    def hata_cost_231(
        self,
        urban: bool = False,
        h_b: float = 80.0,
        h_r: float = 3.0,
        dbm: float = None,
        frequency: float = None,
    ) -> Distance:
        if dbm is None:
            dbm = self.dbm
        if frequency is None:
            frequency = self.frequency_downlink
        key = f"hataCost{urban}{h_b}{h_r}{dbm}{frequency}"
        distance = cache.get(key)
        if distance:
            return Distance(distance)

        f = frequency
        ah_m: float
        c_m: float = 3.0 if urban else 0.0

        # COST-231 Hata
        # PL = 46.3 + 33.9 log10(f) - 13.82 log10(hb) - ahm + (44.9 - 6.55 log10(hb)) log10(d) + cm
        # PL = TX - self.dbm = 46.3 + 33.9 log10(f) - 13.82 log10(hb) - ahm + (44.9 - 6.55 log10(hb)) log10(d) + cm
        # TX - self.dbm - cm - 46.4 - 33.9 log10(f) + 13.82 log10(hb) + ahm = (44.9 - 6.55 log10(hb)) log10(d)
        # log10(d) = (TX - self.dbm - cm - 46.4 - 33.9 log10(f) + 13.82 log10(hb) + ahm) / (44.9 - 6.55 log10(hb))
        # d = 10 ^ ((TX - self.dbm - cm - 46.4 - 33.9 log10(f) + 13.82 log10(hb) + ahm) / (44.9 - 6.55 log10(hb)))

        if urban:
            ah_m = 3.20 * np.power(np.log10(11.75 * h_r), 2) - 4.97  # urban
        else:
            ah_m = (1.1 * np.log10(f) - 0.7) * h_r - (
                1.56 * np.log10(f) - 0.8
            )  # suburban / rural
        distance = np.float_power(
            10,
            (
                self.get_path_loss(dbm=dbm)
                - c_m
                - 46.4
                - 33.9 * np.log10(f)
                + 13.82 * np.log10(h_b)
                + ah_m
            )
            / (44.9 - 6.55 * np.log10(h_b)),
        )

        cache.set(key, distance, None)
        return Distance(distance)

    def get_distance(
        self, distance_function, dbm: float = None, frequency: float = None
    ):
        from .utils import DistanceFunction

        if distance_function == DistanceFunction.path_loss_free:
            return self.path_loss(v=2, dbm=dbm, frequency=frequency)
        elif distance_function == DistanceFunction.path_loss_outdoor:
            return self.path_loss(v=3.5, dbm=dbm, frequency=frequency)
        elif distance_function == DistanceFunction.path_loss_indoor:
            return self.path_loss(v=6, dbm=dbm, frequency=frequency)
        elif distance_function == DistanceFunction.hata_open:
            return self.hata("open", dbm=dbm, frequency=frequency)
        elif distance_function == DistanceFunction.hata_suburban:
            return self.hata("suburban", dbm=dbm, frequency=frequency)
        elif distance_function == DistanceFunction.hata_urban_small:
            return self.hata("urban_small", dbm=dbm, frequency=frequency)
        elif distance_function == DistanceFunction.hata_urban_big:
            return self.hata("urban_big", dbm=dbm, frequency=frequency)
        elif distance_function == DistanceFunction.hata_cost_urban:
            return self.hata_cost_231(urban=True, dbm=dbm, frequency=frequency)
        elif distance_function == DistanceFunction.hata_cost_rural:
            return self.hata_cost_231(urban=False, dbm=dbm, frequency=frequency)

    @property
    def distance(self) -> Distance:
        from .utils import DistanceFunction

        return self.get_distance(DistanceFunction.hata_urban_small)


class Radio(models.Model):
    name = models.CharField(max_length=7, db_index=True)

    def __str__(self):
        return self.name


def default_min_time():
    return timezone.datetime(1970, 1, 1, tzinfo=timezone.utc)


class BaseTransceiverStation(models.Model):
    mcc = models.IntegerField()
    mnc = models.IntegerField()
    lac = models.IntegerField()
    bsic = models.IntegerField()
    latitude = models.FloatField(null=True, blank=True)
    longitude = models.FloatField(null=True, blank=True)

    class Meta:
        unique_together = (("mcc", "mnc", "lac", "bsic"),)

    @property
    def point(self):
        return Point(self.latitude, self.longitude)

    def calc_location(self):
        self.latitude = sum([c.lat for c in self.cells.all()]) / self.cells.count()
        self.longitude = sum([c.lon for c in self.cells.all()]) / self.cells.count()
        self.save()

    def __str__(self):
        return f"LAC: {self.lac} BSIC: {self.bsic} Cells: {self.cells.count()}"


class Celltower(models.Model):
    radio = models.ForeignKey(Radio, on_delete=models.SET_NULL, null=True)
    mcc = models.IntegerField(verbose_name="Mobile Country Code", db_index=True)
    mnc = models.IntegerField(verbose_name="Mobile Network Code", db_index=True)
    lac = models.IntegerField(verbose_name="Location Area Code", db_index=True)
    cid = models.IntegerField(verbose_name="Cell Identification", db_index=True)
    bsic = models.IntegerField(
        verbose_name="Base Station Identity Code",
        db_index=True,
        null=True,
        blank=True,
        default=None,
    )
    unit = models.IntegerField(default=0)
    lat = models.FloatField(verbose_name="Latitude", null=True)
    lon = models.FloatField(verbose_name="Longitude", null=True)
    range = models.FloatField(verbose_name="Reichweite", default=0.0)
    samples = models.IntegerField(default=0)
    changeable = models.BooleanField(default=True)
    created = models.DateTimeField(default=default_min_time)
    updated = models.DateTimeField(default=default_min_time)
    bts = models.ForeignKey(
        BaseTransceiverStation,
        on_delete=models.SET_NULL,
        related_name="cells",
        null=True,
        verbose_name="Base Transceiver Station",
    )

    class Meta:
        unique_together = (("mcc", "mnc", "lac", "cid"),)

    @property
    def point(self):
        return Point(self.lat, self.lon)

    def __str__(self):
        return f"mcc: {self.mcc}, mnc: {self.mnc}, lac: {hex(self.lac)}, cid: {hex(self.cid)}"


@receiver(post_save, sender=Celltower)
def on_celltower_update(sender, instance: Celltower, created: bool, **kwargs):
    if instance.bts is None and instance.bsic:
        instance.bts, bts_created = BaseTransceiverStation.objects.get_or_create(
            mcc=instance.mcc, mnc=instance.mnc, lac=instance.lac, bsic=instance.bsic
        )
        instance.save()
    if instance.bts:
        instance.bts.calc_location()
