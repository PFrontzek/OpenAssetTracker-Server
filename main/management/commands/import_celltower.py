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
from django.core.management.base import BaseCommand

from main.models import Celltower
from main.models import Radio


class Command(BaseCommand):
    help = "Importiert die angegebene csv Tabelle in die Datenbank"

    def add_arguments(self, parser):
        parser.add_argument("--file", type=str)

    def handle(self, *args, **options):
        added = 0
        from django.utils import timezone

        import pytz

        with open(options["file"]) as file:
            reader = csv.reader(file)
            for i, row in enumerate(reader):
                if i == 0:
                    continue
                radio, _ = Radio.objects.get_or_create(name=row[0])
                celltower, created = Celltower.objects.get_or_create(
                    radio=radio,
                    mcc=int(row[1]),
                    mnc=int(row[2]),
                    lac=int(row[3]),
                    cid=int(row[4]),
                    unit=int(row[5]),
                    lon=float(row[6]),
                    lat=float(row[7]),
                    range=float(row[8]),
                    samples=int(row[9]),
                    changeable=bool(row[10]),
                    created=timezone.datetime.fromtimestamp(int(row[11]), pytz.utc),
                    updated=timezone.datetime.fromtimestamp(int(row[12]), pytz.utc),
                )
                if created:
                    added += 1
        return f"Es wurden {added} Celltower importiert"
