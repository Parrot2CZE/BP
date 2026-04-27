import json
import os
import logging

import azure.functions as func
from azure.data.tables import TableServiceClient
from azure.core.exceptions import ResourceNotFoundError

app = func.FunctionApp(http_auth_level=func.AuthLevel.ANONYMOUS)

TABLE_NAME    = "sundial"
PARTITION_KEY = "config"
ROW_KEY       = "state"

log = logging.getLogger("sundial_api")

def _table_client():
    conn = os.environ["STORAGE_CONNECTION_STRING"]
    return TableServiceClient.from_connection_string(conn).get_table_client(TABLE_NAME)

def _get_state(client) -> dict:
    try:
        e = client.get_entity(PARTITION_KEY, ROW_KEY)
        return {
            "enabled":          bool(e.get("enabled", True)),
            "use_pir":          bool(e.get("use_pir", True)),
            "rgb": {
                "r": int(e.get("r", 255)),
                "g": int(e.get("g", 140)),
                "b": int(e.get("b", 0)),
            },
            "last_motion":      bool(e.get("last_motion", False)),
            "last_motion_text": str(e.get("last_motion_text", "—")),
            "device_time":      str(e.get("device_time", "—")),
        }
    except ResourceNotFoundError:
        return {"enabled": True, "use_pir": True, "rgb": {"r": 255, "g": 140, "b": 0},
                "last_motion": False, "last_motion_text": "—", "device_time": "—"}

def _save_state(client, state: dict):
    entity = {
        "PartitionKey": PARTITION_KEY, "RowKey": ROW_KEY,
        "enabled": state["enabled"], "use_pir": state["use_pir"],
        "r": state["rgb"]["r"], "g": state["rgb"]["g"], "b": state["rgb"]["b"],
        "last_motion": state.get("last_motion", False),
        "last_motion_text": state.get("last_motion_text", "—"),
        "device_time": state.get("device_time", "—"),
    }
    client.upsert_entity(entity)

def _json(data, status=200):
    return func.HttpResponse(json.dumps(data), status_code=status, mimetype="application/json")


@app.route(route="state", methods=["GET", "POST"])
def api_state(req: func.HttpRequest) -> func.HttpResponse:
    client = _table_client()
    if req.method == "GET":
        return _json(_get_state(client))
    try:
        data = req.get_json()
    except Exception:
        return _json({"error": "invalid JSON"}, 400)
    state = _get_state(client)
    for field in ("last_motion", "last_motion_text", "device_time"):
        if field in data:
            state[field] = data[field]
    _save_state(client, state)
    return _json({"ok": True})


@app.route(route="rgb", methods=["POST"])
def api_rgb(req: func.HttpRequest) -> func.HttpResponse:
    try:
        d = req.get_json()
        r, g, b = max(0, min(255, int(d["r"]))), max(0, min(255, int(d["g"]))), max(0, min(255, int(d["b"])))
    except Exception:
        return _json({"error": "invalid body"}, 400)
    client = _table_client()
    state = _get_state(client)
    state["rgb"] = {"r": r, "g": g, "b": b}
    _save_state(client, state)
    return _json({"ok": True})


@app.route(route="enabled", methods=["POST"])
def api_enabled(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
        enabled = bool(data["enabled"])
    except Exception:
        return _json({"error": "invalid body"}, 400)
    client = _table_client()
    state = _get_state(client)
    state["enabled"] = enabled
    _save_state(client, state)
    return _json({"ok": True})


@app.route(route="pir", methods=["POST"])
def api_pir(req: func.HttpRequest) -> func.HttpResponse:
    try:
        data = req.get_json()
        use_pir = bool(data["use_pir"])
    except Exception:
        return _json({"error": "invalid body"}, 400)
    client = _table_client()
    state = _get_state(client)
    state["use_pir"] = use_pir
    _save_state(client, state)
    return _json({"ok": True})
