from __future__ import annotations

from datetime import datetime
from typing import Dict, Any, List

from src.simulation import generate_products, load_station_master


AUTO_HEALING_ENABLED = True
MAX_EVENT_LOGS = 20


runtime_state: Dict[str, Any] = {
    "is_running": False,
    "products": [],
    "pending_index": 0,
    "station_slots": {},
    "alerts": [],
    "completed_products": [],
    "last_event": "System idle",
    "step_count": 0,
    "events": [],
    "healed_count": 0,
}


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _log_event(message: str) -> None:
    runtime_state["last_event"] = message
    runtime_state["events"].insert(0, f"{_timestamp()} {message}")
    runtime_state["events"] = runtime_state["events"][:MAX_EVENT_LOGS]


def build_empty_station_cards() -> List[Dict[str, Any]]:
    stations = load_station_master()
    cards = []

    for _, s in stations.iterrows():
        cards.append({
            "station_id": int(s["station_id"]),
            "station_name": str(s["station_name"]),
            "product_id": "-",
            "temperature": "-",
            "pressure": "-",
            "vibration": "-",
            "speed": "-",
            "cycle_time": "-",
            "status": "Idle",
        })

    return cards


def reset_runtime() -> None:
    runtime_state["is_running"] = False
    runtime_state["products"] = []
    runtime_state["pending_index"] = 0
    runtime_state["station_slots"] = {}
    runtime_state["alerts"] = []
    runtime_state["completed_products"] = []
    runtime_state["last_event"] = "System reset"
    runtime_state["step_count"] = 0
    runtime_state["events"] = []
    runtime_state["healed_count"] = 0


def start_simulation() -> Dict[str, Any]:
    products = generate_products()
    reset_runtime()
    runtime_state["products"] = products
    runtime_state["is_running"] = True
    _log_event("Simulation started")
    return runtime_state


def _create_alert(step: Dict[str, Any], resolved: bool = False) -> Dict[str, Any]:
    return {
        "product_id": step["product_id"],
        "current_station": step["station_id"],
        "station_name": step["station_name"],
        "risk_score": step["risk_score"],
        "risk_level": step.get("status", "Critical"),
        "predicted_failure": step.get("predicted_failure", "unknown_failure"),
        "confidence": step.get("confidence", 0.0),
        "root_cause_station": step.get("predicted_root_station", 0),
        "root_parameter": step.get("root_parameter", ""),
        "message": step.get("prediction_reason", ""),
        "recommended_action": step.get("recommended_action", ""),
        "resolved": resolved,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _already_alerted(product_id: str, station_id: int) -> bool:
    return any(
        a["product_id"] == product_id and a["current_station"] == station_id and not a.get("resolved", False)
        for a in runtime_state["alerts"]
    )


def _find_product(product_id: str) -> Dict[str, Any] | None:
    for product in runtime_state["products"]:
        if product["product_id"] == product_id:
            return product
    return None


def _write_back_history(product_id: str, station_id: int, updated_step: Dict[str, Any]) -> None:
    """
    Important:
    When healing happens at runtime, update the underlying product history too.
    That makes the Digital Twin Status page show corrected data.
    """
    product = _find_product(product_id)
    if not product:
        return

    history = product.get("history", [])
    for idx, step in enumerate(history):
        if int(step.get("station_id", -1)) == int(station_id):
            history[idx] = updated_step.copy()
            break


def _mark_future_history_as_post_healed(product_id: str, healed_station_id: int, root_parameter: str) -> None:
    """
    Optional but useful:
    once a critical station is healed, later stations should not still display the original
    unhealed critical interpretation.
    We soften downstream steps so the digital twin looks consistent with 'healed and continued'.
    """
    product = _find_product(product_id)
    if not product:
        return

    history = product.get("history", [])
    for idx, step in enumerate(history):
        station_id = int(step.get("station_id", -1))
        if station_id <= healed_station_id:
            continue

        updated = step.copy()

        # downgrade only if it was not already corrected
        if updated.get("status") == "Critical":
            updated["status"] = "Warning"
            updated["risk_score"] = min(float(updated.get("risk_score", 0.75)), 0.45)
        elif updated.get("status") == "Warning":
            updated["risk_score"] = min(float(updated.get("risk_score", 0.45)), 0.35)

        updated["prediction_reason"] = (
            f"Upstream issue was autonomously corrected at S{healed_station_id}. "
            f"Downstream propagation risk reduced."
        )
        updated["recommended_action"] = f"Continue monitoring {root_parameter or 'process parameter'} stability."

        history[idx] = updated


def _attempt_autonomous_heal(step: Dict[str, Any]) -> Dict[str, Any]:
    healed_step = step.copy()
    root_param = healed_step.get("root_parameter", "")
    station_name = healed_step.get("station_name", "")
    product_id = healed_step.get("product_id", "")
    station_id = healed_step.get("station_id", "")

    action = "No correction applied"

    if root_param == "pressure":
        try:
            healed_step["pressure"] = round(float(healed_step["pressure"]) + 12.0, 3)
        except Exception:
            pass
        healed_step["risk_score"] = 0.30
        action = "Pressure adjusted automatically"

    elif root_param == "vibration":
        try:
            healed_step["vibration"] = round(max(0.0, float(healed_step["vibration"]) - 0.18), 3)
        except Exception:
            pass
        healed_step["risk_score"] = 0.31
        action = "Vibration reduced automatically"

    elif root_param == "temperature":
        try:
            healed_step["temperature"] = round(float(healed_step["temperature"]) - 5.0, 3)
        except Exception:
            pass
        healed_step["risk_score"] = 0.30
        action = "Temperature corrected automatically"

    else:
        healed_step["risk_score"] = min(float(healed_step.get("risk_score", 0.8)), 0.35)
        action = "Process stabilized automatically"

    healed_step["status"] = "Corrected"
    healed_step["recommended_action"] = action
    healed_step["prediction_reason"] = (
        f"Critical risk detected at {station_name}. Autonomous healing applied successfully."
    )
    healed_step["healed"] = True

    runtime_state["healed_count"] += 1

    # write healed step back into product history
    _write_back_history(product_id, station_id, healed_step)

    # soften later propagation in digital twin history
    _mark_future_history_as_post_healed(product_id, int(station_id), root_param)

    _log_event(f"Critical risk detected for {product_id} at S{station_id} - {station_name}")
    _log_event(f"Autonomous healing applied for {product_id}: {action}")
    _log_event(f"Production resumed for {product_id} after successful correction")

    return healed_step


def _build_station_cards_from_slots() -> List[Dict[str, Any]]:
    stations = load_station_master()
    cards = []

    for _, s in stations.iterrows():
        sid = int(s["station_id"])
        sname = str(s["station_name"])

        if sid in runtime_state["station_slots"]:
            step = runtime_state["station_slots"][sid]
            cards.append({
                "station_id": sid,
                "station_name": sname,
                "product_id": step["product_id"],
                "temperature": step["temperature"],
                "pressure": step["pressure"],
                "vibration": step["vibration"],
                "speed": step["speed"],
                "cycle_time": step["cycle_time"],
                "status": step["status"],
            })
        else:
            cards.append({
                "station_id": sid,
                "station_name": sname,
                "product_id": "-",
                "temperature": "-",
                "pressure": "-",
                "vibration": "-",
                "speed": "-",
                "cycle_time": "-",
                "status": "Idle",
            })

    return cards


def next_step() -> Dict[str, Any]:
    if not runtime_state["is_running"]:
        return runtime_state

    runtime_state["step_count"] += 1

    products = runtime_state["products"]
    old_slots = runtime_state["station_slots"]
    new_slots: Dict[int, Dict[str, Any]] = {}

    latest_events: List[str] = []

    for station_id in range(10, 0, -1):
        if station_id not in old_slots:
            continue

        step = old_slots[station_id]
        product_id = step["product_id"]

        if station_id == 10:
            if product_id not in runtime_state["completed_products"]:
                runtime_state["completed_products"].append(product_id)
                latest_events.append(f"{product_id} completed final assembly")
            continue

        next_station_id = station_id + 1
        product = next(p for p in products if p["product_id"] == product_id)
        next_step_data = product["history"][next_station_id - 1].copy()

        if next_step_data.get("status") == "Critical":
            if not _already_alerted(product_id, next_station_id):
                runtime_state["alerts"].insert(0, _create_alert(next_step_data, resolved=False))

            if AUTO_HEALING_ENABLED:
                healed_step = _attempt_autonomous_heal(next_step_data)
                runtime_state["alerts"].insert(0, _create_alert(healed_step, resolved=True))
                new_slots[next_station_id] = healed_step
                latest_events.append(f"{product_id} healed at S{next_station_id} and continued")
                continue

            runtime_state["station_slots"] = old_slots
            runtime_state["is_running"] = False
            _log_event(
                f"Product {product_id} flagged at S{next_station_id} - "
                f"{next_step_data['station_name']}. Production halted due to predicted defect."
            )
            return runtime_state

        new_slots[next_station_id] = next_step_data
        latest_events.append(f"{product_id} moved to S{next_station_id}")

    if runtime_state["pending_index"] < len(products):
        product = products[runtime_state["pending_index"]]
        first_step = product["history"][0].copy()

        if first_step.get("status") == "Critical":
            if not _already_alerted(product["product_id"], 1):
                runtime_state["alerts"].insert(0, _create_alert(first_step, resolved=False))

            if AUTO_HEALING_ENABLED:
                healed_first = _attempt_autonomous_heal(first_step)
                runtime_state["alerts"].insert(0, _create_alert(healed_first, resolved=True))
                new_slots[1] = healed_first
                runtime_state["pending_index"] += 1
                latest_events.append(f"{product['product_id']} entered S1 and healed")
            else:
                old_slots[1] = first_step
                runtime_state["station_slots"] = old_slots
                runtime_state["is_running"] = False
                _log_event(
                    f"Product {product['product_id']} flagged at S1 - "
                    f"{first_step['station_name']}. Production halted due to predicted defect."
                )
                return runtime_state
        else:
            new_slots[1] = first_step
            runtime_state["pending_index"] += 1
            latest_events.append(f"{product['product_id']} entered S1")

    runtime_state["station_slots"] = new_slots

    if not new_slots and runtime_state["pending_index"] >= len(products):
        runtime_state["is_running"] = False
        _log_event("Simulation completed")
    else:
        _log_event(" | ".join(latest_events) if latest_events else "Line running")

    return runtime_state


def get_live_status() -> Dict[str, Any]:
    active_product_ids = [slot["product_id"] for slot in runtime_state["station_slots"].values()]
    station_cards = _build_station_cards_from_slots()

    unresolved_alerts = [a for a in runtime_state["alerts"] if not a.get("resolved", False)]

    system_state = "IDLE"
    if runtime_state["is_running"]:
        system_state = "RUNNING"
    elif unresolved_alerts:
        system_state = "HALTED"
    elif runtime_state["products"] and len(runtime_state["completed_products"]) == len(runtime_state["products"]):
        system_state = "COMPLETED"

    return {
        "is_running": runtime_state["is_running"],
        "active_products": active_product_ids,
        "station_cards": station_cards,
        "alerts_count": len(runtime_state["alerts"]),
        "completed_count": len(runtime_state["completed_products"]),
        "total_products": len(runtime_state["products"]),
        "last_event": runtime_state["last_event"],
        "step_count": runtime_state["step_count"],
        "events": runtime_state["events"],
        "healed_count": runtime_state["healed_count"],
        "auto_healing_enabled": AUTO_HEALING_ENABLED,
        "system_state": system_state,
    }


def get_admin_alerts() -> Dict[str, Any]:
    return {"alerts": runtime_state["alerts"]}


def get_product_detail(product_id: str) -> Dict[str, Any]:
    for product in runtime_state["products"]:
        if product["product_id"] == product_id:
            return product
    return {"product_id": product_id, "history": []}


reset_runtime()