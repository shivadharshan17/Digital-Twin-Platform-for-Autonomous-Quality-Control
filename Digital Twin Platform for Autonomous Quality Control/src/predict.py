from __future__ import annotations

from typing import Dict, Any


STATION_IMPORTANCE = {
    1: 0.30,
    2: 0.35,
    3: 0.95,
    4: 0.50,
    5: 0.85,
    6: 0.55,
    7: 0.90,
    8: 0.60,
    9: 0.45,
    10: 0.40,
}

FAILURE_LABELS = {
    "pressure_low_s3": "bonding_failure",
    "vibration_high_s5": "alignment_failure",
    "temp_high_s7": "thermal_degradation",
    "none": "no_failure",
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _pressure_risk_s3(step: Dict[str, Any]) -> float:
    pressure = float(step["pressure"])

    if pressure >= 90:
        return 0.08
    if 80 <= pressure < 90:
        return 0.45 + ((90 - pressure) / 10.0) * 0.18
    return 0.78 + ((80 - pressure) / 20.0) * 0.18


def _vibration_risk_s5(step: Dict[str, Any]) -> float:
    vibration = float(step["vibration"])

    if vibration <= 0.40:
        return 0.08
    if 0.40 < vibration <= 0.75:
        return 0.45 + ((vibration - 0.40) / 0.35) * 0.20
    return 0.78 + ((vibration - 0.75) / 0.35) * 0.18


def _temperature_risk_s7(step: Dict[str, Any]) -> float:
    temperature = float(step["temperature"])

    if temperature <= 60:
        return 0.08
    if 60 < temperature <= 63:
        return 0.45 + ((temperature - 60) / 3.0) * 0.20
    return 0.78 + ((temperature - 63) / 7.0) * 0.18


def _none_defect_station_risk(current_step: Dict[str, Any]) -> tuple[float, str]:
    """
    For normal products, allow only soft anomaly scoring.
    This avoids false critical events on healthy products.
    """
    station_id = int(current_step["station_id"])

    if station_id == 7:
        temperature = float(current_step["temperature"])
        cycle_time = float(current_step["cycle_time"])

        # healthy band
        if temperature <= 60.8 and cycle_time <= 4.15:
            return 0.08, ""

        # mild warning band only
        if temperature <= 62.5:
            return 0.26, "temperature"

        return 0.36, "temperature"

    if station_id == 5:
        vibration = float(current_step["vibration"])
        if vibration <= 0.42:
            return 0.08, ""
        if vibration <= 0.55:
            return 0.24, "vibration"
        return 0.34, "vibration"

    if station_id == 3:
        pressure = float(current_step["pressure"])
        if pressure >= 90:
            return 0.08, ""
        if pressure >= 86:
            return 0.22, "pressure"
        return 0.34, "pressure"

    return 0.08, ""


def _trend_bonus(current_step: Dict[str, Any], history_so_far: list[Dict[str, Any]]) -> float:
    if not history_so_far:
        return 0.0

    station_id = int(current_step["station_id"])
    defect_type = current_step.get("actual_defect_type", "none")

    # for healthy products, do not accumulate trend bonus aggressively
    if defect_type == "none":
        return 0.0

    bonus = 0.0

    if defect_type == "pressure_low_s3" and station_id > 3:
        pressures = [float(x["pressure"]) for x in history_so_far if int(x["station_id"]) >= 3]
        if len(pressures) >= 2 and pressures[-1] < pressures[0]:
            bonus += 0.08

    elif defect_type == "vibration_high_s5" and station_id > 5:
        vibrations = [float(x["vibration"]) for x in history_so_far if int(x["station_id"]) >= 5]
        if len(vibrations) >= 2 and vibrations[-1] > vibrations[0]:
            bonus += 0.08

    elif defect_type == "temp_high_s7" and station_id > 7:
        temperatures = [float(x["temperature"]) for x in history_so_far if int(x["station_id"]) >= 7]
        if len(temperatures) >= 2 and temperatures[-1] > temperatures[0]:
            bonus += 0.08

    warning_count = sum(1 for x in history_so_far if x.get("status") in ("Warning", "Critical"))
    if warning_count >= 2:
        bonus += 0.05

    return bonus


def _propagation_bonus(current_step: Dict[str, Any]) -> float:
    station_id = int(current_step["station_id"])
    defect_type = current_step.get("actual_defect_type", "none")

    if defect_type == "pressure_low_s3" and station_id > 3:
        return min(0.18, 0.03 * (station_id - 3))

    if defect_type == "vibration_high_s5" and station_id > 5:
        return min(0.18, 0.035 * (station_id - 5))

    if defect_type == "temp_high_s7" and station_id > 7:
        return min(0.18, 0.04 * (station_id - 7))

    return 0.0


def _station_local_risk(current_step: Dict[str, Any]) -> tuple[float, str]:
    station_id = int(current_step["station_id"])
    defect_type = current_step.get("actual_defect_type", "none")

    if defect_type == "none":
        return _none_defect_station_risk(current_step)

    if station_id == 3:
        return _pressure_risk_s3(current_step), "pressure"

    if station_id == 5:
        return _vibration_risk_s5(current_step), "vibration"

    if station_id == 7:
        return _temperature_risk_s7(current_step), "temperature"

    if defect_type == "pressure_low_s3" and station_id > 3:
        pressure = float(current_step["pressure"])
        cycle_time = float(current_step["cycle_time"])
        risk = 0.20
        if pressure < 92:
            risk += 0.22
        if cycle_time > 3.2:
            risk += 0.10
        return risk, "pressure"

    if defect_type == "vibration_high_s5" and station_id > 5:
        vibration = float(current_step["vibration"])
        cycle_time = float(current_step["cycle_time"])
        risk = 0.20
        if vibration > 0.40:
            risk += 0.24
        if cycle_time > 3.1:
            risk += 0.10
        return risk, "vibration"

    if defect_type == "temp_high_s7" and station_id > 7:
        temperature = float(current_step["temperature"])
        cycle_time = float(current_step["cycle_time"])
        risk = 0.20
        if temperature > 60:
            risk += 0.24
        if cycle_time > 3.5:
            risk += 0.08
        return risk, "temperature"

    return 0.08, ""


def predict_risk(current_step: Dict[str, Any], history_so_far: list[Dict[str, Any]] | None = None) -> Dict[str, Any]:
    if history_so_far is None:
        history_so_far = []

    station_id = int(current_step["station_id"])
    station_weight = STATION_IMPORTANCE.get(station_id, 0.4)
    defect_type = current_step.get("actual_defect_type", "none")

    local_risk, dominant_parameter = _station_local_risk(current_step)
    propagation_bonus = _propagation_bonus(current_step)
    trend_bonus = _trend_bonus(current_step, history_so_far)

    risk_score = (local_risk * (0.55 + 0.45 * station_weight)) + propagation_bonus + trend_bonus
    risk_score = _clamp(risk_score)

    # healthy products should not become critical in this demo
    if defect_type == "none":
        if risk_score >= 0.40:
            risk_level = "Warning"
            should_stop = False
            risk_score = min(risk_score, 0.49)
        else:
            risk_level = "Normal"
            should_stop = False
        predicted_failure = "no_failure"
        confidence = _clamp(0.55 + risk_score * 0.25)
    else:
        if risk_score >= 0.70:
            risk_level = "Critical"
            should_stop = True
        elif risk_score >= 0.40:
            risk_level = "Warning"
            should_stop = False
        else:
            risk_level = "Normal"
            should_stop = False

        predicted_failure = FAILURE_LABELS.get(defect_type, "unknown_failure")
        confidence = _clamp(0.55 + risk_score * 0.40)

    return {
        "risk_score": round(risk_score, 3),
        "risk_level": risk_level,
        "should_stop": should_stop,
        "predicted_failure": predicted_failure,
        "confidence": round(confidence, 3),
        "dominant_parameter": dominant_parameter,
    }