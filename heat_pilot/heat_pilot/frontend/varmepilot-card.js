/* Varmepilot dashboard card: the house's rooms - temperature now, what it should be and why - read live from
   Home Assistant. Fed by sensor.varmepilot (which room has which sensors); add it as "custom:varmepilot-card". */
const VP_T = {
  da: { title: "Varmepilot", off: "Slukket", shadow: "Skygge", why: { comfort: "Komfort", setback: "Sænket", night: "Nat", away: "Alle ude", window: "Vindue åbent", manual: "Skruet", preheat: "Varmer op", occupied: "Nogen er her", shower: "Efter bad", sun: "Solen varmer", summer: "Sommer", holiday: "Ferie", owner_away: "Ejeren er væk", spread: "Varmer roligt", cheap: "Billig strøm", dear: "Dyr strøm", cooling: "Køler" } },
  en: { title: "Heat Pilot", off: "Off", shadow: "Shadow", why: { comfort: "Comfort", setback: "Setback", night: "Night", away: "Away", window: "Window open", manual: "By hand", preheat: "Heating up", occupied: "Someone here", shower: "After shower", sun: "Sun warms", summer: "Summer", holiday: "Holiday", owner_away: "Owner away", spread: "Gentle", cheap: "Cheap power", dear: "Dear power", cooling: "Cooling" } },
};
const VP_COL = { comfort: "#ff8a3d", preheat: "#ffb347", occupied: "#ff8a3d", shower: "#ff9f6e", setback: "#5ab8ff", night: "#8b7bff", away: "#5ab8ff",
  window: "#6b7280", manual: "#f5b544", sun: "#f5c451", summer: "#f5c451", holiday: "#5ab8ff", owner_away: "#5ab8ff", spread: "#ffb347", cheap: "#3ddc97", dear: "#5ab8ff", cooling: "#5ab8ff" };

class VarmepilotCard extends HTMLElement {
  setConfig(config) { this.config = config || {}; }
  getCardSize() { return 4; }
  static getStubConfig() { return {}; }
  set hass(hass) {
    this._hass = hass;
    const s = hass.states["sensor.varmepilot"];
    const key = JSON.stringify([s && s.last_updated, ...(s ? (s.attributes.rooms || []).map((r) => hass.states[r.sensor]?.state) : [])]);
    if (key === this._key) return;
    this._key = key;
    this.render();
  }
  render() {
    const hass = this._hass, s = hass.states["sensor.varmepilot"];
    const T = VP_T[(hass.language || "en").slice(0, 2)] || VP_T.en;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    if (!s) { this.shadowRoot.innerHTML = `<ha-card><div style="padding:16px">sensor.varmepilot …</div></ha-card>`; return; }
    const a = s.attributes, num = (v) => v == null || isNaN(v) ? "–" : Number(v).toFixed(1).replace(".", T === VP_T.da ? "," : ".");
    const tiles = (a.rooms || []).map((r) => {
      const live = parseFloat(hass.states[r.sensor]?.state), temp = isNaN(live) ? r.temp : live, col = VP_COL[r.why] || "#ff8a3d";
      return `<div class="t" style="--c:${col}" data-area="${r.area_id}"><div class="n">${r.name}${r.heating ? ' <span class="f">●</span>' : ""}</div>
        <div class="v">${num(temp)}°</div><div class="w">${r.want == null ? T.off : "→ " + num(r.want) + "°"} · ${T.why[r.why] || r.why}</div></div>`;
    }).join("");
    this.shadowRoot.innerHTML = `<style>
      ha-card { padding:16px; } .h { display:flex; justify-content:space-between; align-items:center; margin-bottom:6px; }
      .h b { font-size:16px; } .b { font-size:11px; padding:3px 8px; border-radius:10px; border:1px solid var(--divider-color); color:var(--secondary-text-color); }
      .s { color:var(--secondary-text-color); font-size:13px; margin-bottom:12px; }
      .g { display:grid; grid-template-columns:repeat(auto-fill, minmax(120px, 1fr)); gap:8px; }
      .t { border-radius:14px; padding:10px 12px; background:color-mix(in srgb, var(--c) 14%, var(--card-background-color)); border:1px solid color-mix(in srgb, var(--c) 40%, transparent); cursor:pointer; }
      .n { font-size:12px; font-weight:600; color:var(--secondary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .v { font-size:24px; font-weight:650; letter-spacing:-.02em; margin:2px 0; } .w { font-size:11.5px; font-weight:600; color:var(--c); }
      .f { color:#ff8a3d; }
    </style><ha-card><div class="h"><b>${this.config.title || T.title}</b>${a.mode === "shadow" ? `<span class="b">${T.shadow}</span>` : ""}</div>
      <div class="s">${a.sentence || ""}</div><div class="g">${tiles}</div></ha-card>`;
    this.shadowRoot.querySelectorAll("[data-area]").forEach((el) => el.onclick = () => {
      const r = (a.rooms || []).find((x) => x.area_id === el.dataset.area);
      if (r && r.sensor) this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId: r.sensor } }));
    });
  }
}
customElements.define("varmepilot-card", VarmepilotCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "varmepilot-card", name: "Varmepilot", description: "Rummene: temperatur nu, mål og hvorfor", preview: true });
