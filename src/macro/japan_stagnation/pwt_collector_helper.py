"""PWT 10.01 labsh の年次補間ヘルパー."""
from __future__ import annotations

import numpy as np


PWT_LABSH = {
    "USA": {1995: 0.626, 2000: 0.633, 2005: 0.628, 2010: 0.605, 2015: 0.596, 2019: 0.601},
    "JPN": {1995: 0.633, 2000: 0.624, 2005: 0.591, 2010: 0.570, 2015: 0.554, 2019: 0.561},
    "DEU": {1995: 0.667, 2000: 0.661, 2005: 0.624, 2010: 0.617, 2015: 0.626, 2019: 0.643},
    "FRA": {1995: 0.683, 2000: 0.661, 2005: 0.661, 2010: 0.659, 2015: 0.667, 2019: 0.670},
    "GBR": {1995: 0.671, 2000: 0.685, 2005: 0.659, 2010: 0.625, 2015: 0.620, 2019: 0.624},
    "ITA": {1995: 0.601, 2000: 0.587, 2005: 0.583, 2010: 0.582, 2015: 0.557, 2019: 0.560},
    "CAN": {1995: 0.609, 2000: 0.601, 2005: 0.580, 2010: 0.585, 2015: 0.581, 2019: 0.580},
    "KOR": {1995: 0.546, 2000: 0.544, 2005: 0.527, 2010: 0.516, 2015: 0.557, 2019: 0.582},
}


def interp_labsh_year(country: str, year: int) -> float:
    if country not in PWT_LABSH:
        return float("nan")
    pts = sorted(PWT_LABSH[country].items())
    years = np.array([y for y, _ in pts])
    vals = np.array([v for _, v in pts])
    if year < years.min():
        return float(vals[0])
    if year > years.max():
        return float(vals[-1])
    return float(np.interp(year, years, vals))
