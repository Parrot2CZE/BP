let pickr = null;
let suppressPickerEvent = false;

function clamp255(v) {
  const n = Number(v);
  if (Number.isNaN(n)) return 0;
  return Math.max(0, Math.min(255, Math.round(n)));
}

function rgbToHex(r, g, b) {
  return "#" + [r, g, b].map(v => clamp255(v).toString(16).padStart(2, "0")).join("");
}

function getCurrentRgb() {
  return {
    r: clamp255(document.getElementById('r').value),
    g: clamp255(document.getElementById('g').value),
    b: clamp255(document.getElementById('b').value)
  };
}

function updatePickrFromRgb(r, g, b) {
  if (!pickr) return;
  suppressPickerEvent = true;
  pickr.setColor(rgbToHex(r, g, b), true);
  suppressPickerEvent = false;
}

function applyRgbToControls(r, g, b, syncPickr = true) {
  r = clamp255(r); g = clamp255(g); b = clamp255(b);
  document.getElementById('r').value = r;
  document.getElementById('g').value = g;
  document.getElementById('b').value = b;
  document.getElementById('r_num').value = r;
  document.getElementById('g_num').value = g;
  document.getElementById('b_num').value = b;
  document.getElementById('r_val').textContent = r;
  document.getElementById('g_val').textContent = g;
  document.getElementById('b_val').textContent = b;
  document.getElementById('color_preview').style.background = `rgb(${r}, ${g}, ${b})`;
  if (syncPickr) updatePickrFromRgb(r, g, b);
}

function updatePreviewFromSliders() {
  const { r, g, b } = getCurrentRgb();
  applyRgbToControls(r, g, b, true);
}

function updateFromNumberInputs() {
  applyRgbToControls(
    clamp255(document.getElementById('r_num').value),
    clamp255(document.getElementById('g_num').value),
    clamp255(document.getElementById('b_num').value),
    true
  );
}

function initPickr() {
  pickr = Pickr.create({
    el: '#pickr', theme: 'classic', default: '#ff0000',
    useAsButton: false, inline: true, showAlways: true, comparison: false,
    components: { preview: true, opacity: false, hue: true,
      interaction: { hex:false, rgba:false, hsla:false, hsva:false, cmyk:false,
                     input:false, clear:false, save:false } }
  });
  pickr.on('change', (color) => {
    if (suppressPickerEvent) return;
    const rgb = color.toRGBA();
    applyRgbToControls(rgb[0], rgb[1], rgb[2], false);
  });
}

async function loadState() {
  const res = await fetch('/api/state');
  const data = await res.json();
  document.getElementById('state_raw').textContent = JSON.stringify(data, null, 2);
  document.getElementById('device_time').textContent = data.device_time;
  document.getElementById('enabled_text').textContent = data.enabled ? 'Ano' : 'Ne';
  document.getElementById('pir_text').textContent = data.use_pir ? 'Zapnuto' : 'Vypnuto';
  document.getElementById('motion_text').textContent = data.last_motion ? 'Detekován' : 'Bez pohybu';
  document.getElementById('last_motion_text').textContent = data.last_motion_text;
  document.getElementById('use_pir').checked = data.use_pir;
  applyRgbToControls(data.rgb.r, data.rgb.g, data.rgb.b, true);
}

async function setEnabled(enabled) {
  await fetch('/api/enabled', { method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ enabled }) });
  await loadState();
}

async function setPir() {
  const use_pir = document.getElementById('use_pir').checked;
  await fetch('/api/pir', { method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ use_pir }) });
  await loadState();
}

async function sendRgb() {
  const { r, g, b } = getCurrentRgb();
  await fetch('/api/rgb', { method: 'POST',
    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ r, g, b }) });
  await loadState();
}

document.addEventListener('DOMContentLoaded', () => {
  initPickr();
  document.getElementById('r').addEventListener('input', updatePreviewFromSliders);
  document.getElementById('g').addEventListener('input', updatePreviewFromSliders);
  document.getElementById('b').addEventListener('input', updatePreviewFromSliders);
  document.getElementById('r_num').addEventListener('input', updateFromNumberInputs);
  document.getElementById('g_num').addEventListener('input', updateFromNumberInputs);
  document.getElementById('b_num').addEventListener('input', updateFromNumberInputs);
  loadState();
});
