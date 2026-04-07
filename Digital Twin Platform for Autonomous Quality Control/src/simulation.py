from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Any

import pandas as pd

from src.predict import predict_risk
from src.root_cause import get_root_cause


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

STATION_MASTER = DATA_DIR / "station_master.csv"
DEFECT_MASTER = DATA_DIR / "defect_master.csv"
UNIT_PLAN = DATA_DIR / "unit_plan.csv"

random.seed(42)


@dataclass
class DefectRule:
    defect_type: str
    source_station: int
    parameter: str
    condition: str
    defect_value_min: float
    defect_value_max: float
    propagation_start_station: int
    final_failure_station: int
    effect_description: str


def load_station_master() -> pd.DataFrame:
    return pd.read_csv(STATION_MASTER)


def load_defect_master() -> pd.DataFrame:
    return pd.read_csv(DEFECT_MASTER)


def load_unit_plan() -> pd.DataFrame:
    return pd.read_csv(UNIT_PLAN)


def build_defect_rules() -> Dict[str, DefectRule]:
    df = load_defect_master()
    rules: Dict[str, DefectRule] = {}

    for _, row in df.iterrows():
        rules[str(row["defect_type"])] = DefectRule(
            defect_type=str(row["defect_type"]),
            source_station=int(row["source_station"]),
            parameter=str(row["parameter"]),
            condition=str(row["condition"]),
            defect_value_min=float(row["defect_value_min"]),
            defect_value_max=float(row["defect_value_max"]),
            propagation_start_station=int(row["propagation_start_station"]),
            final_failure_station=int(row["final_failure_station"]),
            effect_description=str(row["effect_description"]),
        )

    return rules


def rand_between(lo: float, hi: float) -> float:
    return round(random.uniform(lo, hi), 3)


def station_value_row(station_row: pd.Series) -> Dict[str, float]:
    return {
        "temperature": rand_between(station_row["temp_min"], station_row["temp_max"]),
        "pressure": rand_between(station_row["pressure_min"], station_row["pressure_max"]),
        "vibration": rand_between(station_row["vibration_min"], station_row["vibration_max"]),
        "speed": rand_between(station_row["speed_min"], station_row["speed_max"]),
        "cycle_time": rand_between(station_row["cycle_time_min"], station_row["cycle_time_max"]),
    }


def apply_source_defect(
    values: Dict[str, float],
    rule: DefectRule,
    station_id: int
) -> tuple[Dict[str, float], int, str]:
    anomaly_flag = 0
    anomaly_reason = "Normal"

    if rule.defect_type == "none":
        return values, anomaly_flag, anomaly_reason

    if station_id == rule.source_station:
        values[rule.parameter] = rand_between(rule.defect_value_min, rule.defect_value_max)
        anomaly_flag = 1

        if rule.defect_type == "pressure_low_s3":
            anomaly_reason = "Low adhesive pressure detected"
        elif rule.defect_type == "vibration_high_s5":
            anomaly_reason = "High vibration anomaly detected"
        elif rule.defect_type == "temp_high_s7":
            anomaly_reason = "High heat treatment temperature detected"
        else:
            anomaly_reason = "Source defect detected"

    return values, anomaly_flag, anomaly_reason


def apply_propagation(values: Dict[str, float], rule: DefectRule, station_id: int) -> Dict[str, float]:
    if rule.defect_type == "none":
        return values

    if station_id < rule.propagation_start_station:
        return values

    if rule.defect_type == "pressure_low_s3":
        values["pressure"] = round(values["pressure"] - random.uniform(1.2, 3.0), 3)
        values["cycle_time"] = round(values["cycle_time"] + random.uniform(0.05, 0.18), 3)

    elif rule.defect_type == "vibration_high_s5":
        values["vibration"] = round(values["vibration"] + random.uniform(0.03, 0.09), 3)
        values["cycle_time"] = round(values["cycle_time"] + random.uniform(0.04, 0.16), 3)

    elif rule.defect_type == "temp_high_s7":
        values["temperature"] = round(values["temperature"] + random.uniform(0.8, 2.0), 3)
        values["cycle_time"] = round(values["cycle_time"] + random.uniform(0.03, 0.12), 3)

    return values


def generate_products() -> List[Dict[str, Any]]:
    stations_df = load_station_master()
    units_df = load_unit_plan()
    rules = build_defect_rules()

    products: List[Dict[str, Any]] = []

    for _, unit in units_df.iterrows():
        product_id = str(unit["product_id"])
        defect_type = str(unit["defect_type"])
        rule = rules[defect_type]

        history: List[Dict[str, Any]] = []

        for _, station in stations_df.iterrows():
            station_id = int(station["station_id"])
            station_name = str(station["station_name"])

            values = station_value_row(station)
            values, anomaly_flag, anomaly_reason = apply_source_defect(values, rule, station_id)
            values = apply_propagation(values, rule, station_id)

            current_step = {
                "product_id": product_id,
                "station_id": station_id,
                "station_name": station_name,
                "temperature": values["temperature"],
                "pressure": values["pressure"],
                "vibration": values["vibration"],
                "speed": values["speed"],
                "cycle_time": values["cycle_time"],
                "actual_defect_type": defect_type,
                "actual_effect_description": rule.effect_description,
                "anomaly_flag": anomaly_flag,
                "anomaly_reason": anomaly_reason,
            }

            prediction = predict_risk(current_step, history)
            root_cause = get_root_cause(current_step, prediction)

            final_defect = 0
            if rule.defect_type != "none" and station_id == rule.final_failure_station:
                final_defect = 1
                anomaly_reason = "Final defect manifested at end-of-line inspection"

            history.append({
                "product_id": product_id,
                "station_id": station_id,
                "station_name": station_name,
                "temperature": values["temperature"],
                "pressure": values["pressure"],
                "vibration": values["vibration"],
                "speed": values["speed"],
                "cycle_time": values["cycle_time"],
                "status": prediction["risk_level"],
                "risk_score": prediction["risk_score"],
                "predicted_failure": prediction["predicted_failure"],
                "confidence": prediction["confidence"],
                "predicted_root_station": root_cause["root_station"],
                "root_parameter": root_cause["root_parameter"],
                "prediction_reason": root_cause["explanation"],
                "recommended_action": root_cause["recommended_action"],
                "anomaly_flag": anomaly_flag,
                "anomaly_reason": anomaly_reason,
                "final_defect": final_defect,
                "actual_defect_type": defect_type,
                "actual_effect_description": rule.effect_description,
            })

        products.append({
            "product_id": product_id,
            "defect_type": defect_type,
            "history": history,
        })

    return products