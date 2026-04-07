from flask import Flask, render_template, jsonify, request
from src.runtime import (
    start_simulation,
    next_step,
    reset_runtime,
    get_live_status,
    get_admin_alerts,
    runtime_state,
)

app = Flask(__name__)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/dashboard")
def dashboard():
    return render_template("dashboard.html")


@app.route("/admin")
def admin():
    return render_template("admin.html")


@app.route("/start_simulation", methods=["POST"])
def start_sim():
    try:
        state = start_simulation()
        return jsonify({
            "status": "started",
            "total_products": len(state["products"])
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/reset_simulation", methods=["POST"])
def reset_sim():
    try:
        reset_runtime()
        return jsonify({"status": "reset"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/next_step", methods=["POST"])
def step_forward():
    try:
        state = next_step()
        return jsonify({"status": "ok", "state": state})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/live_status")
def live_status():
    return jsonify(get_live_status())


@app.route("/api/admin_alerts")
def admin_alerts():
    return jsonify(get_admin_alerts())


@app.route("/api/product/<product_id>")
def product_detail(product_id: str):
    return jsonify(get_product_detail(product_id))

@app.route("/digital_twin")
def digital_twin_page():
    return render_template("digital_twin.html")


@app.route("/api/digital_twin_status")
def api_digital_twin_status():
    products = runtime_state.get("products", [])
    result = []

    for product in products:
        history = product.get("history", [])

        corrected_count = sum(1 for h in history if h.get("status") == "Corrected")
        warning_count = sum(1 for h in history if h.get("status") == "Warning")
        critical_count = sum(1 for h in history if h.get("status") == "Critical")

        if corrected_count > 0:
            final_status = "Healed & Completed"
        elif critical_count > 0:
            final_status = "Critical Event"
        elif warning_count > 0:
            final_status = "Warning Observed"
        else:
            final_status = "Completed"

        cleaned_history = []
        for step in history:
            step_copy = dict(step)

            if not step_copy.get("predicted_root_station"):
                step_copy["predicted_root_station"] = ""
            if not step_copy.get("root_parameter"):
                step_copy["root_parameter"] = ""
            if step_copy.get("actual_defect_type") == "none":
                step_copy["predicted_failure"] = "no_failure"
                if not step_copy.get("prediction_reason"):
                    step_copy["prediction_reason"] = "No clear upstream defect source identified."
                if not step_copy.get("recommended_action"):
                    step_copy["recommended_action"] = "Continue monitoring."

            cleaned_history.append(step_copy)

        result.append({
            "product_id": product.get("product_id"),
            "defect_type": product.get("defect_type"),
            "final_status": final_status,
            "corrected_count": corrected_count,
            "warning_count": warning_count,
            "critical_count": critical_count,
            "history": cleaned_history,
        })

    return jsonify({"products": result})

if __name__ == "__main__":
    app.run(debug=True)