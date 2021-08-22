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
from dataclasses import dataclass
from dataclasses import field
from django.db.models import Q
from django.http import HttpRequest
from django.http import HttpResponse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.csrf import csrf_exempt
from enum import IntFlag
from typing import List
from typing import Tuple
from typing import Union


class StructBase:
    def __init__(self, *args, **kwargs):
        pass

    @classmethod
    def __struct_format_string(cls) -> str:
        return "<"  # ATMega Arduino: Little Endian

    @classmethod
    def get_struct_format_string(cls) -> str:
        if issubclass(cls, StructBase) and cls is not StructBase:
            return f"{cls.__struct_format_string()}"
        else:
            return ""

    @classmethod
    def struct_size(cls) -> int:
        import struct

        return struct.calcsize(cls.__struct_format_string())

    @classmethod
    def from_struct(cls, buffer, offset=0):
        import struct

        return cls(*struct.unpack_from(cls.get_struct_format_string(), buffer, offset))


@dataclass
class TrackerUpdate(StructBase):
    imei_high: int
    imei_low: int
    spannung: float
    uplink: int
    uplink_success: int

    imei = property(lambda self: int(f"{self.imei_high}{self.imei_low}"))

    @classmethod
    def __struct_format_string(cls) -> str:
        return "< 2I f 2I"

    @classmethod
    def struct_size(cls) -> int:
        import struct

        return struct.calcsize(cls.__struct_format_string())

    @classmethod
    def from_struct(cls, buffer, offset=0):
        import struct

        data = struct.unpack_from(cls.__struct_format_string(), buffer, offset)
        return cls(
            imei_high=data[0],
            imei_low=data[1],
            spannung=data[2],
            uplink=data[3],
            uplink_success=data[4],
        )


class ExtrasFlags(IntFlag):
    VOLTAGE = 1 << 0
    TEMPERATURE = 1 << 1
    OPTION_NO_WAITTIME = 1 << 2
    VOLTAGE_RAW = 1 << 3
    ERROR_CODE = 1 << 4


@dataclass
class UpdateHeader(StructBase):
    imei: int
    uplink: int
    uplink_success: int
    version: int
    cells_length: int
    extras_flags: ExtrasFlags
    spannung: float = 0.0
    voltage_raw: int = 0
    voltage_ref: int = 0

    @property
    def has_raw_voltage(self):
        return ExtrasFlags.VOLTAGE_RAW in self.extras_flags

    @property
    def has_temperature(self):
        return ExtrasFlags.TEMPERATURE in self.extras_flags

    @property
    def has_voltage(self):
        return ExtrasFlags.VOLTAGE in self.extras_flags

    @classmethod
    def __struct_format_string(cls, voltage_raw=False) -> str:
        if voltage_raw:
            return "< Q 2H 2I 3B"
        else:
            return "< Q f 2I 3B"

    @classmethod
    def struct_size(cls, voltage_raw=False) -> int:
        import struct

        return struct.calcsize(cls.__struct_format_string(voltage_raw))

    @classmethod
    def from_struct(cls, buffer, offset=0):
        import struct

        data = struct.unpack_from(cls.__struct_format_string(), buffer, offset)
        obj = cls(
            imei=data[0],
            spannung=data[1],
            uplink=data[2],
            uplink_success=data[3],
            version=data[4],
            cells_length=data[5],
            extras_flags=ExtrasFlags(data[6]),
        )
        if obj.has_raw_voltage:
            data = struct.unpack_from(cls.__struct_format_string(True), buffer, offset)
            obj = cls(
                imei=data[0],
                voltage_ref=data[1],
                voltage_raw=data[2],
                uplink=data[3],
                uplink_success=data[4],
                version=data[5],
                cells_length=data[6],
                extras_flags=ExtrasFlags(data[7]),
            )
        return obj


@dataclass
class CengResult(StructBase):
    mode: int
    cells_length: int

    @classmethod
    def __struct_format_string(cls):
        return "< 2B"

    @classmethod
    def struct_size(cls) -> int:
        import struct

        return struct.calcsize(cls.__struct_format_string())

    @classmethod
    def from_struct(cls, buffer, offset=0):
        import struct

        data = struct.unpack_from(cls.__struct_format_string(), buffer, offset)
        return cls(mode=data[0], cells_length=data[1])


@dataclass
class Extras(StructBase):
    tempratur: float

    @classmethod
    def __struct_format_string(cls):
        return "< h"

    @classmethod
    def struct_size(cls) -> int:
        import struct

        return struct.calcsize(cls.__struct_format_string())

    @classmethod
    def from_struct(cls, buffer, offset=0):
        import struct

        data = struct.unpack_from(cls.__struct_format_string(), buffer, offset)
        return cls(tempratur=data[0] / 4)


@dataclass
class Cell(StructBase):
    mcc: int
    mnc: int
    lac: int
    cellid: int
    bsic: int
    rxl: int

    lac_str = property(lambda self: hex(self.lac))
    cellid_str = property(lambda self: hex(self.cellid))
    dbm = property(lambda self: -113 + self.rxl)
    rssi = property(lambda self: self.rxl / 2)

    @classmethod
    def __struct_format_string(cls):
        return "< 4H 2B"

    @classmethod
    def struct_size(cls) -> int:
        import struct

        return struct.calcsize(cls.__struct_format_string())

    @classmethod
    def from_struct(cls, buffer, offset=0):
        import struct

        data = struct.unpack_from(cls.__struct_format_string(), buffer, offset)
        return cls(
            mcc=data[0],
            mnc=data[1],
            lac=data[2],
            cellid=data[3],
            bsic=data[4],
            rxl=data[5],
        )


@dataclass
class CellV2(Cell):
    arfcn: int

    frequency_uplink: float = 0.0
    frequency_downlink: float = 0.0
    band: str = ""

    def __post_init__(self):
        if self.arfcn == (2 ** 16) - 1:
            self.arfcn = 0
        if 0 <= self.arfcn <= 124:
            self.frequency_uplink = 890.0 + 0.2 * (self.arfcn - 0)
            self.frequency_downlink = self.frequency_uplink + 45
            self.band = "GSM 900"
        elif 128 <= self.arfcn <= 251:
            self.frequency_uplink = 824.2 + 0.2 * (self.arfcn - 128)
            self.frequency_downlink = self.frequency_uplink + 45
            self.band = "GSM 850"
        elif 259 <= self.arfcn <= 293:
            self.frequency_uplink = 450.6 + 0.2 * (self.arfcn - 259)
            self.frequency_downlink = self.frequency_uplink + 10
            self.band = "GSM 500"
        elif 306 <= self.arfcn <= 340:
            self.frequency_uplink = 479.0 + 0.2 * (self.arfcn - 306)
            self.frequency_downlink = self.frequency_uplink + 10
            self.band = "GSM 500"
        elif 438 <= self.arfcn <= 511:
            self.frequency_uplink = 747.2 + 0.2 * (self.arfcn - 438)
            self.frequency_downlink = self.frequency_uplink + 30
            self.band = "GSM 700"
        elif 512 <= self.arfcn <= 885:
            self.frequency_uplink = 1710.2 + 0.2 * (self.arfcn - 512)
            self.frequency_downlink = self.frequency_uplink + 95
            self.band = "GSM 1800"
        elif 955 <= self.arfcn <= 1023:
            self.frequency_uplink = 890.0 + 0.2 * (self.arfcn - 1024)
            self.frequency_downlink = self.frequency_uplink + 45
            self.band = "GSM 900"

    @classmethod
    def __struct_format_string(cls):
        return "< 4H 2B H"

    @classmethod
    def struct_size(cls) -> int:
        import struct

        return struct.calcsize(cls.__struct_format_string())

    @classmethod
    def from_struct(cls, buffer, offset=0):
        import struct

        data = struct.unpack_from(cls.__struct_format_string(), buffer, offset)
        return cls(
            mcc=data[0],
            mnc=data[1],
            lac=data[2],
            cellid=data[3],
            bsic=data[4],
            rxl=data[5],
            arfcn=data[6],
        )


class ErrorFlags(IntFlag):
    EXEC = (1 << 0) << 3
    GSM = (1 << 1) << 3
    HTTP = (1 << 2) << 3
    POWERLOSS = 0b111
    TIMEOUT = 1 << 0
    TX = 1 << 1
    RX = 1 << 2


def parse_error(e: int) -> Tuple[ErrorFlags, int]:
    return ErrorFlags(e >> 10), e & 0b1111111111


@dataclass
class Errors:
    length: int = 0
    values: List[Tuple[ErrorFlags, int]] = field(default_factory=list)
    datatype = "H"

    @classmethod
    def build(cls, offset: int, buffer):
        import struct

        obj = cls(length=struct.unpack_from("< B", buffer, offset)[0])
        errors = struct.unpack_from(
            f"< {obj.length}{cls.datatype}", buffer, offset + struct.calcsize("< B")
        )
        obj.values = [parse_error(e) for e in errors]
        return obj

    def struct_format_string(self):
        return f"< B {self.length}{self.datatype}"

    def struct_size(self) -> int:
        import struct

        return struct.calcsize(self.struct_format_string())


def update_bts(request):
    from . import models

    cells = models.Celltower.objects.filter(Q(bsic__isnull=False) & Q(bts__isnull=True))
    for cell in cells:
        cell.save(force_update=True)
    return HttpResponse("OK")


@method_decorator(csrf_exempt, "dispatch")
class StatusView(View):
    def post(self, request: HttpRequest):
        print(len(request.body))
        import struct
        from datetime import timedelta
        from django.utils import timezone

        device = None
        header = None
        try:
            from base64 import b64encode

            from . import models

            cells: List[Union[Cell, CellV2]] = []
            version = struct.unpack_from(
                "< B", request.body, offset=TrackerUpdate.struct_size()
            )[0]
            status: models.Status

            if version == 3:
                trackerUpdate = TrackerUpdate.from_struct(request.body)
                print(trackerUpdate)
                cengResponse = CengResult.from_struct(
                    request.body, offset=TrackerUpdate.struct_size()
                )
                device, device_created = models.Device.objects.get_or_create(
                    sn=trackerUpdate.imei
                )
                for i in range(cengResponse.cells_length):
                    cell = Cell.from_struct(
                        request.body,
                        offset=TrackerUpdate.struct_size()
                        + CengResult.struct_size()
                        + i * Cell.struct_size(),
                    )
                    if cell.mcc != 0 and cell.mnc != 0:
                        found = False
                        for c in cells:
                            if (
                                c.mcc == cell.mcc
                                and c.mnc == cell.mnc
                                and c.cellid == cell.cellid
                                and c.lac == cell.lac
                            ):
                                found = True
                                c.rxl = c.rxl if c.rxl > cell.rxl else cell.rxl
                                if c.bsic != cell.bsic:
                                    print("BSIC MISMATCH")
                        if not found:
                            cells.append(cell)
                status = models.Status(
                    device=device,
                    lat=0.0,
                    lon=0.0,
                    timestamp=timezone.now(),
                    radius=0.0,
                    voltage_raw=trackerUpdate.spannung,
                    raw_data=b64encode(request.body),
                    parsed_data=json.dumps(
                        (repr(trackerUpdate), repr(cengResponse), repr(cells))
                    ),
                )
                if len(
                    request.body
                ) >= TrackerUpdate.struct_size() + CengResult.struct_size() + cengResponse.cells_length * Cell.struct_size() + struct.calcsize(
                    "< h"
                ):
                    status.temp = (
                        struct.unpack_from(
                            "< h",
                            request.body,
                            TrackerUpdate.struct_size()
                            + CengResult.struct_size()
                            + cengResponse.cells_length * Cell.struct_size(),
                        )[0]
                        / 4
                    )
                status.save()
            elif version == 4:
                header = UpdateHeader.from_struct(request.body)
                print(header)
                device, device_created = models.Device.objects.get_or_create(
                    sn=header.imei
                )

                for i in range(header.cells_length):
                    cell = CellV2.from_struct(
                        request.body,
                        offset=UpdateHeader.struct_size() + i * CellV2.struct_size(),
                    )
                    if cell.mcc != 0 and cell.mnc != 0:
                        found = False
                        for c in cells:
                            if (
                                c.mcc == cell.mcc
                                and c.mnc == cell.mnc
                                and c.cellid == cell.cellid
                                and c.lac == cell.lac
                            ):
                                found = True
                                if c.rxl < cell.rxl:
                                    c.rxl = cell.rxl
                                    c.arfcn = cell.arfcn
                                if c.bsic != cell.bsic:
                                    print("BSIC MISMATCH")
                        if not found:
                            cells.append(cell)

                extras = Extras.from_struct(
                    request.body,
                    offset=UpdateHeader.struct_size()
                    + header.cells_length * CellV2.struct_size(),
                )

                status = models.Status(
                    device=device,
                    lat=0.0,
                    lon=0.0,
                    timestamp=timezone.now(),
                    radius=0.0,
                    raw_data=b64encode(request.body),
                    parsed_data=json.dumps((repr(header), repr(extras), repr(cells))),
                )
                if ExtrasFlags.TEMPERATURE in header.extras_flags:
                    status.temp = extras.tempratur
                if ExtrasFlags.VOLTAGE in header.extras_flags:
                    if ExtrasFlags.VOLTAGE_RAW in header.extras_flags:
                        status.voltage_raw = header.voltage_raw
                        status.voltage_ref = header.voltage_ref
                    else:
                        status.voltage_raw = header.spannung
                status.save()
                if ExtrasFlags.ERROR_CODE in header.extras_flags:
                    try:
                        print(
                            UpdateHeader.struct_size()
                            + header.cells_length * CellV2.struct_size()
                        )
                        errors = Errors.build(
                            buffer=request.body,
                            offset=UpdateHeader.struct_size()
                            + header.cells_length * CellV2.struct_size()
                            + extras.struct_size(),
                        )
                        for i, error in enumerate(errors.values):
                            models.Error(
                                nr=i, status=status, flags=error[0].value, code=error[1]
                            ).save()
                    except Exception as e:
                        print(e)
                        pass
            for cell in cells:
                try:
                    celltower = models.Celltower.objects.get(
                        mnc=cell.mnc, mcc=cell.mcc, lac=cell.lac, cid=cell.cellid
                    )
                    if celltower.bsic is None or celltower.bsic != cell.bsic:
                        celltower.bsic = cell.bsic
                        celltower.save()
                    measurement = models.Measurement(
                        celltower=celltower, status=status, rxl=cell.rxl
                    )
                    if version == 4:
                        measurement.arfcn = cell.arfcn
                    measurement.save()
                except Exception as e:
                    print(e)
            status.new_calc_location()
            print(status.point)
            status.set_city()
            from asgiref.sync import async_to_sync
            from channels.layers import get_channel_layer

            async_to_sync(get_channel_layer().group_send)(
                "device",
                {
                    "type": "device_update",
                    "message": {"device": device.sn, "status": status.id},
                },
            )
            for user in device.users.all():
                async_to_sync(get_channel_layer().group_send)(
                    "user",
                    {"type": "user_update", "user": user.id, "device": device.sn},
                )
        except Exception as e:
            print(e)
        time_now = timezone.now()
        if device:
            if (
                header
                and ExtrasFlags.OPTION_NO_WAITTIME in header.extras_flags
                and device.sleeptime == 0
            ):
                time_next = time_now
            else:
                time_next = device.get_next_waketime()
        else:
            time_next = time_now + timedelta(minutes=1)
        time_diff = int(time_next.timestamp()) - int(time_now.timestamp())
        # time_next += timedelta(minutes=5)
        # time_next -= timedelta(minutes=time_next.minute % 5, seconds=time_next.second)
        print(f"{time_now} - {time_next} - {time_diff}")
        response = HttpResponse(
            struct.pack(
                "< 3L",
                int(timezone.now().timestamp()),
                int(time_next.timestamp()),
                time_diff,
            ),
            status=200,
        )
        device.next_wake = time_next
        device.save()
        return response
