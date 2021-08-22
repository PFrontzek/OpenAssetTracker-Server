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

from dataclasses import dataclass
from django.core.cache import cache
from django.utils import timezone
from enum import Enum
from enum import auto
from multiprocessing import Value
from typing import List
from typing import Tuple

import geopy
import requests
from geopy import distance

from . import models


@dataclass
class Measurement:
    point: geopy.Point
    dist: float


class DistanceFunction(Enum):
    hata_urban_big = auto()
    hata_urban_small = auto()
    hata_open = auto()
    hata_suburban = auto()
    hata_cost_urban = auto()
    hata_cost_rural = auto()
    path_loss_free = auto()
    path_loss_outdoor = auto()
    path_loss_indoor = auto()


class ErrorFunction(Enum):
    RMSE = auto()
    MSE = auto()
    ME = auto()
    MAE = auto()


class OptimizationAlgorithm(Enum):
    L_BFGS_B = "L-BFGS-B"
    BFGS = "BFGS"
    CG = "CG"
    # NEWTON_CG = "Newton-CG"
    SLSQP = "SLSQP"
    NELDER_MEAD = "Nelder-Mead"


def lateration_new(
    measurements: List[Measurement],
    error_function: ErrorFunction = ErrorFunction.ME,
    method: OptimizationAlgorithm = OptimizationAlgorithm.L_BFGS_B,
) -> Tuple[geopy.Point, distance.Distance]:
    key = f"lateration{measurements}{error_function.name}{method}"
    result = cache.get(key)
    if result:
        return geopy.Point(result[0], result[1]), distance.distance(result[2])
    import numpy as np
    from scipy.optimize import Bounds
    from scipy.optimize import minimize

    if error_function == ErrorFunction.ME:

        def me(x, measurements: List[Measurement]) -> float:
            e = 0.0
            latitude = ((x[0] + 90) % 180) - 90
            longitude = ((x[1] + 90) % 180) - 90
            p = geopy.Point(latitude=latitude, longitude=longitude)
            for m in measurements:
                distance_calculated = distance.geodesic(p, m.point).kilometers
                e += distance_calculated - m.dist
            return e / len(measurements)

        error_function = me
    elif error_function == ErrorFunction.MAE:

        def mae(x, measurements: List[Measurement]) -> float:
            e = 0.0
            latitude = ((x[0] + 90) % 180) - 90
            longitude = ((x[1] + 90) % 180) - 90
            p = geopy.Point(latitude=latitude, longitude=longitude)
            for m in measurements:
                distance_calculated = distance.geodesic(p, m.point).kilometers
                e += np.abs(distance_calculated - m.dist)
            return e / len(measurements)

        error_function = mae
    elif error_function == ErrorFunction.MSE or ErrorFunction.RMSE:

        def mse(x, measurements: List[Measurement]) -> float:
            e = 0.0
            latitude = ((x[0] + 90) % 180) - 90
            longitude = ((x[1] + 90) % 180) - 90
            p = geopy.Point(latitude=latitude, longitude=longitude)
            for m in measurements:
                distance_calculated = distance.geodesic(p, m.point).kilometers
                e += np.power(distance_calculated - m.dist, 2)
            return e / len(measurements)

        if error_function == ErrorFunction.MSE:
            error_function = mse
        else:

            def rmse(x, measurements: List[Measurement]) -> float:
                return np.sqrt(mse(x=x, measurements=measurements))

            error_function = rmse

    initial_location = np.array(
        (
            np.sum([m.point.latitude for m in measurements]) / len(measurements),
            np.sum([m.point.longitude for m in measurements]) / len(measurements),
        )
    )

    # print(initial_location)
    minimize_extra_args = {
        "options": {"maxiter": 1e5},
    }
    if method == OptimizationAlgorithm.L_BFGS_B:
        minimize_extra_args["bounds"] = Bounds(-90, 90)

    elif method == OptimizationAlgorithm.SLSQP:
        minimize_extra_args["bounds"] = Bounds(-90, 90)

    result = minimize(
        fun=error_function,
        x0=initial_location,
        args=(measurements,),
        method=method.value,
        tol=1e-6,
        **minimize_extra_args,
    )
    # print(result)
    latitude = ((result.x[0] + 90) % 180) - 90
    longitude = ((result.x[1] + 90) % 180) - 90
    cache.set(key, (latitude, longitude, abs(result.fun) + 0.1), None)
    result_point = geopy.Point(latitude, longitude)

    return result_point, distance.distance(abs(result.fun) + 0.1)


def update_cell(cell: models.Celltower):
    from django.conf import settings

    url = "https://eu1.unwiredlabs.com/v2/process.php"
    data = {
        "token": settings.OPEN_CELL_ID_TOKEN,
        "radio": "GSM",
        "mcc": cell.mcc,
        "mnc": cell.mnc,
        "cells": [
            {
                "lac": int(cell.lac),
                "cid": int(cell.cid),
            },
        ],
        "address": 0,
    }

    response = requests.post(url=url, json=data)
    response.raise_for_status()
    response = response.json()
    print(response)
    cell.lat, cell.lon = response["lat"], response["lon"]
    cell.save()


_mp_count = Value("i", 0)


def get_locations(
    kwargs: dict,
) -> Tuple[List[Tuple[float, float]], List[float], List[timezone.datetime]]:
    try:
        from django import db

        db.connections.close_all()
        from .models import Status

        _mp_count
        i = 0
        with _mp_count.get_lock():
            _mp_count.value += 1
            i = _mp_count.value
        total_len = kwargs.pop("len")
        status_ids = kwargs.pop("status_ids")
        points = []
        distances = []
        times = []
        print("start", i, "/", total_len)
        for status_id in status_ids:
            status = Status.objects.get(id=status_id)
            point, distance = status.get_point(**kwargs)
            points.append((point.latitude, point.longitude))
            distances.append(distance.kilometers)
            times.append(status.timestamp)
        print("finish", i, "/", total_len)
        return points, distances, times
    except Exception as e:
        print(e, e.args)
        return None, None, None
