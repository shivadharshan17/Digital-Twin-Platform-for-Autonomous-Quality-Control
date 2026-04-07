from __future__ import annotations

from typing import Dict, Any


ROOT_CAUSE_MAP = {
    "pressure_low_s3": {
        "root_station": 3,
        "root_parameter": "pressure",
        "explanation": "Adhesive pressure dropped below safe operating range, indicating weak bonding risk.",
        "recommended_action": "Inspect adhesive nozzle pressure and isolate affected product batch."
    },
    "vibration_high_s5": {
        "root_station": 5,
        "root_parameter": "vibration",
        "explanation": "Abnormal vibration suggests alignment instability that can propagate downstream.",
        "recommended_action": "Inspect alignment fixture and vibration control system."
    },
    "temp_high_s7": {
        "root_station": 7,
        "root_parameter": "temperature",
        "explanation": "Heat treatment exceeded stable limits, increasing thermal degradation risk.",
        "recommended_action": "Inspect heating chamber and thermal control settings."
    },
    "none": {
        "root_station": 0,
        "root_parameter": "",
        "explanation": "No clear upstream defect source identified.",
        "recommended_action": "Continue monitoring."
    }
}


def get_root_cause(current_step: Dict[str, Any], prediction: Dict[str, Any]) -> Dict[str, Any]:
    defect_type = current_step.get("actual_defect_type", "none")
    base = ROOT_CAUSE_MAP.get(defect_type, ROOT_CAUSE_MAP["none"])

    return {
        "root_station": base["root_station"],
        "root_parameter": base["root_parameter"],
        "explanation": base["explanation"],
        "recommended_action": base["recommended_action"],
        "risk_level": prediction["risk_level"],
        "predicted_failure": prediction["predicted_failure"],
    }