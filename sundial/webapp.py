from flask import Flask, jsonify, request, render_template_string


HTML_PAGE = """
<!doctype html>
<html lang="cs">
<head>
  <meta charset="utf-8">
  <title>Ovládání hodin</title>
  <style>
    body {
      font-family: Arial, sans-serif;
      max-width: 800px;
      margin: 40px auto;
      padding: 20px;
    }
    .card {
      border: 1px solid #ccc;
      border-radius: 12px;
      padding: 20px;
      margin-bottom: 20px;
    }
    button {
      padding: 10px 16px;
      margin-right: 8px;
      margin-top: 8px;
    }
    input[type=range] {
      width: 100%;
    }
    .mono {
      font-family: monospace;
      white-space: pre-wrap;
    }
  </style>
</head>
<body>
  <h1>Interiérové sluneční hodiny</h1>

  <div class="card">
    <h2>Stav zařízení</h2>
    <div id="state" class="mono">Načítám...</div>
    <button onclick="loadState()">Obnovit</button>
  </div>

  <div class="card">
    <h2>Napájení logiky</h2>
    <button onclick="setEnabled(true)">Zapnout</button>
    <button onclick="setEnabled(false)">Vypnout</button>
  </div>

  <div class="card">
    <h2>PIR režim</h2>
    <label>
      <input type="checkbox" id="use_pir" onchange="setPir()">
      Aktivní PIR řízení
    </label>
  </div>

  <div class="card">
    <h2>RGB barva</h2>

    <label>R: <span id="r_val">255</span></label>
    <input type="range" id="r" min="0" max="255" value="255">

    <label>G: <span id="g_val">0</span></label>
    <input type="range" id="g" min="0" max="255" value="0">

    <label>B: <span id="b_val">0</span></label>
    <input type="range" id="b" min="0" max="255" value="0">

    <button onclick="sendRgb()">Nastavit RGB</button>
  </div>

<script>
async function loadState() {
  const res = await fetch('/api/state');
  const data = await res.json();

  document.getElementById('state').textContent = JSON.stringify(data, null, 2);
  document.getElementById('use_pir').checked = data.use_pir;

  document.getElementById('r').value = data.rgb.r;
  document.getElementById('g').value = data.rgb.g;
  document.getElementById('b').value = data.rgb.b;

  document.getElementById('r_val').textContent = data.rgb.r;
  document.getElementById('g_val').textContent = data.rgb.g;
  document.getElementById('b_val').textContent = data.rgb.b;
}

async function setEnabled(enabled) {
  await fetch('/api/enabled', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({enabled})
  });
  loadState();
}

async function setPir() {
  const use_pir = document.getElementById('use_pir').checked;
  await fetch('/api/pir', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({use_pir})
  });
  loadState();
}

async function sendRgb() {
  const r = document.getElementById('r').value;
  const g = document.getElementById('g').value;
  const b = document.getElementById('b').value;

  await fetch('/api/rgb', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({r, g, b})
  });
  loadState();
}

document.getElementById('r').addEventListener('input', e => {
  document.getElementById('r_val').textContent = e.target.value;
});
document.getElementById('g').addEventListener('input', e => {
  document.getElementById('g_val').textContent = e.target.value;
});
document.getElementById('b').addEventListener('input', e => {
  document.getElementById('b_val').textContent = e.target.value;
});

loadState();
setInterval(loadState, 3000);
</script>
</body>
</html>
"""


def create_app(controller):
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(HTML_PAGE)

    @app.route("/api/state")
    def api_state():
        return jsonify(controller.get_state())

    @app.route("/api/enabled", methods=["POST"])
    def api_enabled():
        data = request.get_json(force=True)
        controller.set_enabled(bool(data["enabled"]))
        return jsonify({"ok": True})

    @app.route("/api/pir", methods=["POST"])
    def api_pir():
        data = request.get_json(force=True)
        controller.set_use_pir(bool(data["use_pir"]))
        return jsonify({"ok": True})

    @app.route("/api/rgb", methods=["POST"])
    def api_rgb():
        data = request.get_json(force=True)
        controller.set_rgb(data["r"], data["g"], data["b"])
        return jsonify({"ok": True})

    return app