/* Varmepilot dashboard card: the house's rooms - temperature now, what it should be and why - read live from
   Home Assistant. Fed by sensor.varmepilot (which room has which sensors); add it as "custom:varmepilot-card". */
const VP_T = {
  da: { title: "Varmepilot", off: "Slukket", shadow: "Skygge", why: { comfort: "Komfort", setback: "Sænket", night: "Nat", away: "Alle ude", window: "Vindue åbent", manual: "Skruet", preheat: "Varmer op", occupied: "Nogen er her", shower: "Efter bad", sun: "Solen varmer", summer: "Sommer", holiday: "Ferie", owner_away: "Ejeren er væk", spread: "Varmer roligt", cheap: "Billig strøm", dear: "Dyr strøm", cooling: "Køler" } },
  en: { title: "Heat Pilot", off: "Off", shadow: "Shadow", why: { comfort: "Comfort", setback: "Setback", night: "Night", away: "Away", window: "Window open", manual: "By hand", preheat: "Heating up", occupied: "Someone here", shower: "After shower", sun: "Sun warms", summer: "Summer", holiday: "Holiday", owner_away: "Owner away", spread: "Gentle", cheap: "Cheap power", dear: "Dear power", cooling: "Cooling" } },
};
Object.assign(VP_T, {
  de: { title: "Heat Pilot", off: "Aus", shadow: "Schatten", why: { comfort: "Komfort", setback: "Abgesenkt", night: "Nacht", away: "Alle weg", window: "Fenster offen", manual: "Von Hand", preheat: "Heizt auf", occupied: "Jemand da", shower: "Nach Dusche", sun: "Sonne wärmt", summer: "Sommer", holiday: "Urlaub", owner_away: "Bewohner weg", spread: "Sanft", cheap: "Günstig", dear: "Teuer", cooling: "Kühlt" } },
  fr: { title: "Heat Pilot", off: "Arrêt", shadow: "Ombre", why: { comfort: "Confort", setback: "Abaissé", night: "Nuit", away: "Absents", window: "Fenêtre ouverte", manual: "À la main", preheat: "Préchauffe", occupied: "Quelqu'un", shower: "Après douche", sun: "Soleil", summer: "Été", holiday: "Vacances", owner_away: "Occupant absent", spread: "Doux", cheap: "Bon marché", dear: "Cher", cooling: "Rafraîchit" } },
  nl: { title: "Heat Pilot", off: "Uit", shadow: "Schaduw", why: { comfort: "Comfort", setback: "Verlaagd", night: "Nacht", away: "Iedereen weg", window: "Raam open", manual: "Met de hand", preheat: "Warmt op", occupied: "Iemand hier", shower: "Na douche", sun: "Zon warmt", summer: "Zomer", holiday: "Vakantie", owner_away: "Bewoner weg", spread: "Rustig", cheap: "Goedkoop", dear: "Duur", cooling: "Koelt" } },
  sv: { title: "Heat Pilot", off: "Av", shadow: "Skugga", why: { comfort: "Komfort", setback: "Sänkt", night: "Natt", away: "Alla borta", window: "Fönster öppet", manual: "För hand", preheat: "Värmer upp", occupied: "Någon här", shower: "Efter dusch", sun: "Solen värmer", summer: "Sommar", holiday: "Semester", owner_away: "Ägaren borta", spread: "Lugnt", cheap: "Billig el", dear: "Dyr el", cooling: "Kyler" } },
  nb: { title: "Heat Pilot", off: "Av", shadow: "Skygge", why: { comfort: "Komfort", setback: "Senket", night: "Natt", away: "Alle borte", window: "Vindu åpent", manual: "For hånd", preheat: "Varmer opp", occupied: "Noen her", shower: "Etter dusj", sun: "Solen varmer", summer: "Sommer", holiday: "Ferie", owner_away: "Beboer borte", spread: "Rolig", cheap: "Billig strøm", dear: "Dyr strøm", cooling: "Kjøler" } },
});
const VP_COL = { comfort: "#ff8a3d", preheat: "#ffb347", occupied: "#ff8a3d", shower: "#ff9f6e", setback: "#5ab8ff", night: "#8b7bff", away: "#5ab8ff",
  window: "#6b7280", manual: "#f5b544", sun: "#f5c451", summer: "#f5c451", holiday: "#5ab8ff", owner_away: "#5ab8ff", spread: "#ffb347", cheap: "#3ddc97", dear: "#5ab8ff", cooling: "#5ab8ff" };

/* reasons the house card didn't name yet */
const VPR_WHY = {
  da: { comfort_evening: "Aftenkomfort", hold: "Holder varmen", floor: "Gulvvarme", floor_keep: "Gulvvarme", door: "Dør åben", buffer: "Gemmer varme", phones: "På vej hjem", noshow: "Ingen i dag", cold_snap: "Kulde på vej" },
  en: { comfort_evening: "Evening comfort", hold: "Keeping warm", floor: "Floor heating", floor_keep: "Floor heating", door: "Door open", buffer: "Storing heat", phones: "On the way home", noshow: "Nobody today", cold_snap: "Cold coming" },
  de: { comfort_evening: "Abendkomfort", hold: "Hält warm", floor: "Fußbodenheizung", floor_keep: "Fußbodenheizung", door: "Tür offen", buffer: "Speichert Wärme", phones: "Auf dem Heimweg", noshow: "Heute niemand", cold_snap: "Kälte kommt" },
  fr: { comfort_evening: "Confort du soir", hold: "Garde la chaleur", floor: "Plancher chauffant", floor_keep: "Plancher chauffant", door: "Porte ouverte", buffer: "Stocke la chaleur", phones: "En route", noshow: "Personne aujourd'hui", cold_snap: "Froid annoncé" },
  nl: { comfort_evening: "Avondcomfort", hold: "Houdt warm", floor: "Vloerverwarming", floor_keep: "Vloerverwarming", door: "Deur open", buffer: "Slaat warmte op", phones: "Onderweg naar huis", noshow: "Vandaag niemand", cold_snap: "Kou op komst" },
  sv: { comfort_evening: "Kvällskomfort", hold: "Håller värmen", floor: "Golvvärme", floor_keep: "Golvvärme", door: "Dörr öppen", buffer: "Lagrar värme", phones: "På väg hem", noshow: "Ingen i dag", cold_snap: "Kyla på väg" },
  nb: { comfort_evening: "Kveldskomfort", hold: "Holder varmen", floor: "Gulvvarme", floor_keep: "Gulvvarme", door: "Dør åpen", buffer: "Lagrer varme", phones: "På vei hjem", noshow: "Ingen i dag", cold_snap: "Kulde på vei" },
};
for (const k of Object.keys(VP_T)) Object.assign(VP_T[k].why, VPR_WHY[k] || VPR_WHY.en);
Object.assign(VP_COL, { comfort_evening: "#ff8a3d", hold: "#ffb347", floor: "#ff9f6e", floor_keep: "#ff9f6e", door: "#5ab8ff", buffer: "#ffb347", phones: "#ffb347", noshow: "#5ab8ff", cold_snap: "#ff8a3d" });

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
    const code = (hass.language || "en").slice(0, 2).replace(/^(no|nn)$/, "nb");
    const T = VP_T[code] || VP_T.en;
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    if (!s) { this.shadowRoot.innerHTML = `<ha-card><div style="padding:16px">sensor.varmepilot …</div></ha-card>`; return; }
    const a = s.attributes, num = (v) => v == null || isNaN(v) ? "–" : Number(v).toFixed(1).replace(".", ["en"].includes(code) ? "." : ",");
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

/* ---------- One room: the dial, + / - / boost and the day - "custom:varmepilot-room-card", area: <area id> ----------
   The buttons call the companion integration's services (heat_pilot.*), so Heat Pilot never learns from them. */
const VPR_T = {
  da: { target: "Mål", until: "til", heating: "Varmer", idle: "Varmer ikke", boost: "Boost 1 t", stop: "Stop boost", back: "Tilbage til planen",
        note: "− / + gælder 1 time · derefter tager Varmepilot over", hum: "Fugt", win: "Vindue", open: "Åbent", closed: "Lukket", next: "Næste",
        now: "Nu", shadow: "Skygge – Varmepilot styrer ikke rummet", noint: "Tilføj Varmepilot-integrationen for at styre", pick: "Vælg et rum",
        temp: "Midlertidig", boosting: "Boost", off: "Slukket", room: "Rum", controls: "Varmepilot styrer" },
  en: { target: "Target", until: "until", heating: "Heating", idle: "Not heating", boost: "Boost 1 h", stop: "Stop boost", back: "Back to the plan",
        note: "− / + last 1 hour · then Heat Pilot takes over", hum: "Humidity", win: "Window", open: "Open", closed: "Closed", next: "Next",
        now: "Now", shadow: "Shadow – Heat Pilot isn't controlling this room", noint: "Add the Varmepilot integration to control", pick: "Pick a room",
        temp: "For a while", boosting: "Boost", off: "Off", room: "Room", controls: "Heat Pilot in control" },
  de: { target: "Ziel", until: "bis", heating: "Heizt", idle: "Heizt nicht", boost: "Boost 1 Std", stop: "Boost stoppen", back: "Zurück zum Plan",
        note: "− / + gilt 1 Stunde · dann übernimmt Heat Pilot", hum: "Feuchte", win: "Fenster", open: "Offen", closed: "Zu", next: "Nächstes",
        now: "Jetzt", shadow: "Schatten – Heat Pilot steuert diesen Raum nicht", noint: "Varmepilot-Integration hinzufügen, um zu steuern", pick: "Raum wählen",
        temp: "Vorübergehend", boosting: "Boost", off: "Aus", room: "Raum", controls: "Heat Pilot steuert" },
  fr: { target: "Cible", until: "jusqu'à", heating: "Chauffe", idle: "Ne chauffe pas", boost: "Boost 1 h", stop: "Arrêter le boost", back: "Retour au plan",
        note: "− / + valent 1 heure · puis Heat Pilot reprend", hum: "Humidité", win: "Fenêtre", open: "Ouverte", closed: "Fermée", next: "Ensuite",
        now: "Maint.", shadow: "Ombre – Heat Pilot ne pilote pas cette pièce", noint: "Ajoutez l'intégration Varmepilot pour piloter", pick: "Choisir une pièce",
        temp: "Temporaire", boosting: "Boost", off: "Arrêt", room: "Pièce", controls: "Heat Pilot pilote" },
  nl: { target: "Doel", until: "tot", heating: "Verwarmt", idle: "Verwarmt niet", boost: "Boost 1 u", stop: "Boost stoppen", back: "Terug naar het plan",
        note: "− / + geldt 1 uur · daarna neemt Heat Pilot het over", hum: "Vocht", win: "Raam", open: "Open", closed: "Dicht", next: "Volgende",
        now: "Nu", shadow: "Schaduw – Heat Pilot stuurt deze kamer niet", noint: "Voeg de Varmepilot-integratie toe om te sturen", pick: "Kies een kamer",
        temp: "Tijdelijk", boosting: "Boost", off: "Uit", room: "Kamer", controls: "Heat Pilot stuurt" },
  sv: { target: "Mål", until: "till", heating: "Värmer", idle: "Värmer inte", boost: "Boost 1 h", stop: "Stoppa boost", back: "Tillbaka till planen",
        note: "− / + gäller 1 timme · sedan tar Heat Pilot över", hum: "Fukt", win: "Fönster", open: "Öppet", closed: "Stängt", next: "Nästa",
        now: "Nu", shadow: "Skugga – Heat Pilot styr inte rummet", noint: "Lägg till Varmepilot-integrationen för att styra", pick: "Välj ett rum",
        temp: "Tillfälligt", boosting: "Boost", off: "Av", room: "Rum", controls: "Heat Pilot styr" },
  nb: { target: "Mål", until: "til", heating: "Varmer", idle: "Varmer ikke", boost: "Boost 1 t", stop: "Stopp boost", back: "Tilbake til planen",
        note: "− / + gjelder 1 time · så tar Heat Pilot over", hum: "Fukt", win: "Vindu", open: "Åpent", closed: "Lukket", next: "Neste",
        now: "Nå", shadow: "Skygge – Heat Pilot styrer ikke rommet", noint: "Legg til Varmepilot-integrasjonen for å styre", pick: "Velg et rom",
        temp: "Midlertidig", boosting: "Boost", off: "Av", room: "Rom", controls: "Heat Pilot styrer" },
};
const VPR_FLAME = '<path d="M12 2s5 5 5 10a5 5 0 0 1-10 0c0-2 1-3.5 1-3.5S9 11 11 11c0-4 1-9 1-9z"/>';
const VPR_BOLT = '<path d="M13 2 4 14h7l-1 8 9-12h-7z"/>';

class VarmepilotRoomCard extends HTMLElement {
  setConfig(config) {
    this.config = config || {};
    this._hist = null; this._histAt = 0; this._key = null;
  }
  getCardSize() { return 7; }
  getGridOptions() { return { columns: 12, rows: "auto", min_columns: 6 }; }  // full width of a section by default
  static getStubConfig(hass) {
    const r = (hass?.states["sensor.varmepilot"]?.attributes?.rooms || [])[0];
    return { area: r ? r.area_id : "" };
  }
  static getConfigElement() { return document.createElement("varmepilot-room-card-editor"); }
  get _lang() { return ((this._hass?.language || "en").slice(0, 2)).replace(/^(no|nn)$/, "nb"); }
  get _room() {
    const rooms = this._hass?.states["sensor.varmepilot"]?.attributes?.rooms || [];
    const area = this.config?.area;
    return rooms.find((r) => r.area_id === area || r.name === area) || (area ? undefined : rooms[0]);  // no room chosen yet: the first
  }
  set hass(hass) {
    this._hass = hass;
    if (!this.config) this.config = {};
    const r = this._room;
    const live = r ? hass.states[r.sensor] : null;
    const extra = r ? [r.humidity, ...(r.windows || [])].map((e) => hass.states[e]?.state) : [];
    const key = JSON.stringify([r, live?.state, extra, hass.themes?.darkMode, this._pending]);
    if (Date.now() - this._histAt > 600000 && r?.sensor) this._loadHistory(r.sensor);
    if (key === this._key) return;
    this._key = key;
    this.render();
  }
  async _loadHistory(sensor) {
    this._histAt = Date.now();
    const start = new Date(); start.setHours(0, 0, 0, 0);
    try {
      const res = await this._hass.callWS({ type: "history/history_during_period", start_time: start.toISOString(), entity_ids: [sensor],
                                            minimal_response: true, no_attributes: true, significant_changes_only: false });
      this._hist = (res[sensor] || []).map((p) => [new Date((p.lu || p.lc) * 1000), parseFloat(p.s)]).filter((p) => !isNaN(p[1]));
    } catch (e) { this._hist = []; }
    this._key = null; this.render();
  }
  _num(v, d = 1) {
    if (v == null || isNaN(v)) return "–";
    return Number(v).toFixed(d).replace(".", this._lang === "en" ? "." : ",");
  }
  _clock(iso) { if (!iso) return ""; const d = new Date(iso); return d.toLocaleTimeString(this._hass.locale?.language || this._lang, { hour: "2-digit", minute: "2-digit" }); }
  async _call(service, data) {
    this._pending = service + JSON.stringify(data);
    this.render();
    try { await this._hass.callService("heat_pilot", service, { area_id: this._room?.area_id, ...data }); }
    catch (e) { this._error = e.message || String(e); setTimeout(() => { this._error = null; this._key = null; this.render(); }, 5000); }
    this._pending = null; this._key = null; this.render();
  }
  render() {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    if (!this._hass) return;
    this.config = this.config || {};
    const hass = this._hass, T = VPR_T[this._lang] || VPR_T.en, r = this._room;
    if (!r) { this.shadowRoot.innerHTML = `<ha-card><div style="padding:16px">${hass?.states["sensor.varmepilot"] ? T.pick : "sensor.varmepilot …"}</div></ha-card>`; return; }
    const why = VP_T[this._lang]?.why || VP_T.en.why;
    const live = parseFloat(hass.states[r.sensor]?.state), temp = isNaN(live) ? r.temp : live;
    const col = r.boost ? "#ff5a3d" : (VP_COL[r.why] || "#ff8a3d");
    const want = r.want;
    const vals = [temp, want].filter((v) => v != null && !isNaN(v));
    const lo = Math.min(15, Math.floor(Math.min(...vals, 99)) - 1), hi = Math.max(25, Math.ceil(Math.max(...vals, 0)) + 1);
    const R = 100, C = 118, A0 = 135, SPAN = 270, frac = (v) => Math.max(0, Math.min(1, (v - lo) / (hi - lo)));
    const pt = (f) => { const a = (A0 + SPAN * f) * Math.PI / 180; return [C + R * Math.cos(a), C + R * Math.sin(a)]; };
    const arc = (f) => { const [x0, y0] = pt(0), [x1, y1] = pt(f); return `M ${x0.toFixed(1)} ${y0.toFixed(1)} A ${R} ${R} 0 ${SPAN * f > 180 ? 1 : 0} 1 ${x1.toFixed(1)} ${y1.toFixed(1)}`; };
    const fNow = temp == null || isNaN(temp) ? 0 : frac(temp), [tx, ty] = want == null ? [0, 0] : pt(frac(want));
    const can = !!hass.services?.heat_pilot, ctl = r.mode === "control";
    const off = want == null;
    const pill = r.boost ? T.boosting : r.card ? T.temp : (why[r.why] || r.why || "");
    const untilTxt = r.until ? `${T.until} ${this._clock(r.until)}` : (r.next ? `${T.until} ${this._clock(r.next.t)}` : "");
    const hum = parseFloat(hass.states[r.humidity]?.state);
    const winOpen = (r.windows || []).some((w) => hass.states[w]?.state === "on");
    // the day: today's temperature so far and the plan ahead
    const d0 = new Date(); d0.setHours(0, 0, 0, 0); const DAY = 86400000, W = 320, H = 70;
    const xs = (t) => (t - d0) / DAY * W;
    const ys = (v) => H - 6 - (v - lo) / (hi - lo) * (H - 12);
    const hist = (this._hist || []).concat(temp != null && !isNaN(temp) ? [[new Date(), temp]] : []);
    let line = "", area = "";
    if (hist.length > 1) {
      line = hist.map((p, i) => `${i ? "L" : "M"}${xs(p[0]).toFixed(1)} ${ys(p[1]).toFixed(1)}`).join(" ");
      area = `${line} L${xs(hist[hist.length - 1][0]).toFixed(1)} ${H} L${xs(hist[0][0]).toFixed(1)} ${H} Z`;
    }
    const plan = (r.plan || []).filter((p) => p[1] != null).map((p) => [new Date(p[0]), p[1]]).filter((p) => p[0] - d0 < DAY);
    let pl = "";
    if (plan.length) {
      const pts = [[new Date(), want ?? plan[0][1]], ...plan];
      pl = pts.map((p, i) => i ? `H${xs(p[0]).toFixed(1)} V${ys(p[1]).toFixed(1)}` : `M${xs(p[0]).toFixed(1)} ${ys(p[1]).toFixed(1)}`).join(" ") + ` H${W}`;
    }
    const nx = xs(new Date());
    const busy = (s) => this._pending && this._pending.startsWith(s) ? " busy" : "";
    this.shadowRoot.innerHTML = `<style>
      :host { --vp-c:${col}; }
      ha-card { display:block; border-radius:var(--ha-card-border-radius, 24px); padding:18px 18px 16px; overflow:hidden; position:relative;
        background:radial-gradient(120% 70% at 50% -12%, color-mix(in srgb, var(--vp-c) 22%, transparent), transparent 62%), var(--ha-card-background, var(--card-background-color)); }
      .top { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; }
      .name { font-size:18px; font-weight:700; letter-spacing:-.01em; }
      .sub { font-size:12px; color:var(--secondary-text-color); margin-top:2px; display:flex; gap:6px; align-items:center; }
      .dot { width:7px; height:7px; border-radius:50%; background:${ctl ? "#3ddc97" : "#9aa3b2"}; box-shadow:0 0 8px ${ctl ? "#3ddc97" : "transparent"}; }
      .pill { font-size:12px; font-weight:650; padding:6px 11px; border-radius:20px; color:var(--vp-c); white-space:nowrap;
        background:color-mix(in srgb, var(--vp-c) 13%, transparent); border:1px solid color-mix(in srgb, var(--vp-c) 32%, transparent); display:flex; gap:6px; align-items:center; }
      .pill svg { width:13px; height:13px; fill:currentColor; }
      .dial { position:relative; width:236px; height:236px; margin:4px auto -8px; }
      .dial > svg { position:absolute; inset:0; }
      .track { stroke:color-mix(in srgb, var(--primary-text-color) 9%, transparent); }
      .mid { position:absolute; inset:0; display:flex; flex-direction:column; align-items:center; justify-content:center; }
      .now { font-size:60px; font-weight:250; letter-spacing:-.04em; line-height:1; }
      .now sup { font-size:23px; font-weight:400; vertical-align:top; position:relative; top:8px; margin-left:2px; }
      .tgt { font-size:13px; color:var(--secondary-text-color); margin-top:6px; } .tgt b { color:var(--vp-c); font-weight:650; }
      .st { margin-top:8px; font-size:12px; font-weight:600; display:flex; gap:5px; align-items:center; color:var(--secondary-text-color); }
      .st.on { color:#ff8a3d; } .st svg { width:12px; height:12px; fill:currentColor; }
      .st.on svg { animation:flick 1.4s ease-in-out infinite; transform-origin:50% 90%; }
      @keyframes flick { 0%,100% { transform:scale(1); } 50% { transform:scale(1.18) rotate(-4deg); } }
      .lo { font-size:11px; fill:var(--secondary-text-color); }
      .ctl { display:flex; align-items:center; justify-content:center; gap:14px; }
      button { font:inherit; cursor:pointer; -webkit-tap-highlight-color:transparent; }
      button:disabled { opacity:.4; cursor:default; }
      .btn { width:52px; height:52px; border-radius:50%; border:1px solid var(--divider-color); color:var(--primary-text-color); font-size:26px; font-weight:300;
        background:color-mix(in srgb, var(--primary-text-color) 5%, transparent); display:flex; align-items:center; justify-content:center; transition:transform .12s; }
      .btn:active:not(:disabled), .boost:active:not(:disabled) { transform:scale(.93); }
      .boost { height:52px; padding:0 22px; border-radius:26px; border:0; font-size:14px; font-weight:700; color:#fff; display:flex; gap:7px; align-items:center;
        background:linear-gradient(135deg,#ff6a3d,#ffb347); box-shadow:0 8px 22px rgba(255,120,60,.35); transition:transform .12s; }
      .boost.stop { background:linear-gradient(135deg,#5ab8ff,#8b7bff); box-shadow:0 8px 22px rgba(90,140,255,.32); }
      .boost svg { width:15px; height:15px; fill:#fff; }
      .busy { animation:pulse .9s ease-in-out infinite; } @keyframes pulse { 50% { opacity:.55; } }
      .note { text-align:center; font-size:11.5px; color:var(--secondary-text-color); margin-top:8px; min-height:15px; }
      .note a { color:var(--vp-c); font-weight:650; cursor:pointer; text-decoration:none; }
      .note.err { color:var(--error-color, #e5484d); }
      .chart { margin-top:12px; padding-top:10px; border-top:1px solid var(--divider-color); }
      .ax { display:flex; justify-content:space-between; font-size:10.5px; color:var(--secondary-text-color); margin-top:2px; }
      .chips { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; margin-top:12px; }
      .chip { border:1px solid var(--divider-color); border-radius:14px; padding:9px 10px; background:color-mix(in srgb, var(--primary-text-color) 4%, transparent); min-width:0; }
      .chip i { display:block; font-style:normal; font-size:11px; color:var(--secondary-text-color); }
      .chip b { font-size:14.5px; font-weight:650; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; display:block; }
      .chip b.open { color:#5ab8ff; }
    </style><ha-card>
      <div class="top"><div><div class="name">${this.config.name || r.name}</div><div class="sub"><span class="dot"></span>${ctl ? T.controls : T.shadow}</div></div>
        <div class="pill"><svg viewBox="0 0 24 24">${r.boost ? VPR_BOLT : VPR_FLAME}</svg>${pill}</div></div>
      <div class="dial"><svg viewBox="0 0 236 236">
        <defs><linearGradient id="g" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stop-color="#5ab8ff"/><stop offset=".55" stop-color="#ffb347"/><stop offset="1" stop-color="#ff5a3d"/></linearGradient>
        <filter id="glow" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="4"/></filter></defs>
        <path d="${arc(1)}" fill="none" class="track" stroke-width="14" stroke-linecap="round"/>
        ${fNow > 0.005 ? `<path d="${arc(fNow)}" fill="none" stroke="url(#g)" stroke-width="14" stroke-linecap="round" opacity=".38" filter="url(#glow)"/>
        <path d="${arc(fNow)}" fill="none" stroke="url(#g)" stroke-width="14" stroke-linecap="round"/>` : ""}
        ${want != null ? `<circle cx="${tx.toFixed(1)}" cy="${ty.toFixed(1)}" r="9" fill="var(--card-background-color, #fff)" stroke="${col}" stroke-width="4"/>` : ""}
        <text x="${(pt(0)[0] - 6).toFixed(0)}" y="${(pt(0)[1] + 24).toFixed(0)}" class="lo">${lo}°</text>
        <text x="${(pt(1)[0] - 8).toFixed(0)}" y="${(pt(1)[1] + 24).toFixed(0)}" class="lo">${hi}°</text>
      </svg>
        <div class="mid"><div class="now">${this._num(temp)}<sup>°</sup></div>
          <div class="tgt">${off ? T.off : `${T.target} <b>${this._num(want)}°</b>${untilTxt ? " · " + untilTxt : ""}`}</div>
          <div class="st ${r.heating ? "on" : ""}"><svg viewBox="0 0 24 24">${VPR_FLAME}</svg>${r.heating ? T.heating : T.idle}</div></div>
      </div>
      <div class="ctl">
        <button class="btn${busy("set_temperature{\"step\":-")}" data-step="-0.5" ${can && ctl ? "" : "disabled"} aria-label="−">−</button>
        ${r.boost ? `<button class="boost stop${busy("resume")}" data-resume ${can && ctl ? "" : "disabled"}>${T.stop}</button>`
                  : `<button class="boost${busy("boost")}" data-boost ${can && ctl ? "" : "disabled"}><svg viewBox="0 0 24 24">${VPR_BOLT}</svg>${T.boost}</button>`}
        <button class="btn${busy("set_temperature{\"step\":0.5")}" data-step="0.5" ${can && ctl ? "" : "disabled"} aria-label="+">+</button>
      </div>
      <div class="note ${this._error ? "err" : ""}">${this._error ? this._error : !can ? T.noint : !ctl ? "" : r.card && !r.boost ? `<a data-resume>${T.back}</a>` : T.note}</div>
      <div class="chart"><svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" preserveAspectRatio="none">
        <defs><linearGradient id="a" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ff8a3d" stop-opacity=".32"/><stop offset="1" stop-color="#ff8a3d" stop-opacity="0"/></linearGradient></defs>
        ${pl ? `<path d="${pl}" fill="none" stroke="#5ab8ff" stroke-width="1.6" stroke-dasharray="4 3" opacity=".85" vector-effect="non-scaling-stroke"/>` : ""}
        ${area ? `<path d="${area}" fill="url(#a)"/><path d="${line}" fill="none" stroke="#ff8a3d" stroke-width="2.2" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>` : ""}
        <line x1="${nx.toFixed(1)}" y1="2" x2="${nx.toFixed(1)}" y2="${H - 2}" stroke="var(--primary-text-color)" stroke-width="1" opacity=".3" vector-effect="non-scaling-stroke"/>
        ${temp != null && !isNaN(temp) ? `<circle cx="${nx.toFixed(1)}" cy="${ys(temp).toFixed(1)}" r="3.5" fill="#ff8a3d"/>` : ""}
      </svg><div class="ax"><span>00</span><span>06</span><span>12</span><span>18</span><span>24</span></div></div>
      <div class="chips">
        <div class="chip"><i>${T.hum}</i><b>${isNaN(hum) ? "–" : Math.round(hum) + " %"}</b></div>
        <div class="chip"><i>${T.win}</i><b class="${winOpen ? "open" : ""}">${(r.windows || []).length ? (winOpen ? T.open : T.closed) : "–"}</b></div>
        <div class="chip"><i>${T.next}</i><b>${r.next ? `${r.next.temp == null ? T.off : this._num(r.next.temp, r.next.temp % 1 ? 1 : 0) + "°"} ${this._clock(r.next.t)}` : "–"}</b></div>
      </div>
    </ha-card>`;
    this.shadowRoot.querySelectorAll("[data-step]").forEach((b) => b.onclick = () => this._call("set_temperature", { step: Number(b.dataset.step) }));
    this.shadowRoot.querySelectorAll("[data-boost]").forEach((b) => b.onclick = () => this._call("boost", {}));
    this.shadowRoot.querySelectorAll("[data-resume]").forEach((b) => b.onclick = () => this._call("resume", {}));
    this.shadowRoot.querySelector(".dial").onclick = () => r.sensor && this.dispatchEvent(new CustomEvent("hass-more-info", { bubbles: true, composed: true, detail: { entityId: r.sensor } }));
  }
}
customElements.define("varmepilot-room-card", VarmepilotRoomCard);

class VarmepilotRoomCardEditor extends HTMLElement {
  setConfig(config) { this._config = config || {}; this.render(); }
  set hass(hass) { const first = !this._hass; this._hass = hass; if (first) this.render(); }
  render() {
    if (!this._hass) return;
    this._config = this._config || {};
    const lang = ((this._hass.language || "en").slice(0, 2)).replace(/^(no|nn)$/, "nb"), T = VPR_T[lang] || VPR_T.en;
    const rooms = this._hass.states["sensor.varmepilot"]?.attributes?.rooms || [];
    this.innerHTML = `<div style="padding:8px 0"><label style="display:block;font-size:12px;color:var(--secondary-text-color);margin-bottom:4px">${T.room}</label>
      <select style="width:100%;padding:10px;border-radius:8px;font:inherit">${rooms.map((r) => `<option value="${r.area_id}" ${r.area_id === this._config.area ? "selected" : ""}>${r.name}</option>`).join("")}</select></div>`;
    if (!this._config.area && rooms[0]) {  // nothing chosen yet: the first room, so the card shows at once
      this._config = { ...this._config, area: rooms[0].area_id };
      this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true }));
    }
    this.querySelector("select").onchange = (e) => {
      this._config = { ...this._config, area: e.target.value };
      this.dispatchEvent(new CustomEvent("config-changed", { detail: { config: this._config }, bubbles: true, composed: true }));
    };
  }
}
customElements.define("varmepilot-room-card-editor", VarmepilotRoomCardEditor);

/* ---------- The ventilation: one slim line - the step the unit runs on, why, and what matters now.
   "custom:varmepilot-vent-card". Turquoise when calm, yellow when a room's air is getting poor, blue in boost. ---------- */
const VV_T = {
  da: { title: "Ventilation", lv: { low: "Lav", normal: "Normal", high: "Høj", boost: "Boost" }, step: "TRIN", shadow: "skygge", rec: "{x} % genvundet",
        why: { shower: "Bad i gang", damp: "Fugt fra madlavning", dust: "Støv i luften", co2: "CO₂ i {r}", humidity: "Fugt i {r}", free_cooling: "Køler huset",
               away: "Ingen hjemme", night: "Stille om natten", save_heat: "Sparer på varmen", normal: "God luft" }, min: "{x} min",
        boostT: "Boost kommer, når Varmepilot styrer ventilationen", would: "Varmepilot ville: {x}", agree: "{x} % enig med det, der styrer i dag", ok: "Luften er god i alle rum" },
  en: { title: "Ventilation", lv: { low: "Low", normal: "Normal", high: "High", boost: "Boost" }, step: "STEP", shadow: "shadow", rec: "{x} % recovered",
        why: { shower: "Shower running", damp: "Damp from cooking", dust: "Dust in the air", co2: "CO₂ in {r}", humidity: "Damp in {r}", free_cooling: "Cooling the house",
               away: "Nobody home", night: "Quiet at night", save_heat: "Saving heat", normal: "Good air" }, min: "{x} min",
        boostT: "Boost comes when Heat Pilot runs the ventilation", would: "Heat Pilot would: {x}", agree: "{x} % agree with what runs it today", ok: "The air is good in every room" },
};
const VV_FAN = '<path d="M12 12c0-3 1.5-6 4-6 2 0 2.5 2.5.5 3.5L12 12Zm0 0c3 0 6 1.5 6 4 0 2-2.5 2.5-3.5.5L12 12Zm0 0c0 3-1.5 6-4 6-2 0-2.5-2.5-.5-3.5L12 12Zm0 0c-3 0-6-1.5-6-4 0-2 2.5-2.5 3.5-.5L12 12Z"/>';
class VarmepilotVentCard extends HTMLElement {
  setConfig(config) { this.config = config || {}; this._open = false; }
  getCardSize() { return 1; }
  getGridOptions() { return { columns: 12, rows: 1, min_rows: 1 }; }
  static getStubConfig() { return {}; }
  set hass(hass) {
    this._hass = hass;
    const v = hass.states["sensor.varmepilot"]?.attributes?.vent;
    const key = JSON.stringify([v, hass.themes?.darkMode, this._open]);
    if (key === this._key) return;
    this._key = key;
    this._render(v);
  }
  _render(v) {
    if (!this.shadowRoot) this.attachShadow({ mode: "open" });
    const L = (this._hass.locale?.language || this._hass.language || "en").slice(0, 2), T = VV_T[L] || VV_T.en;
    if (!v) { this.shadowRoot.innerHTML = `<ha-card><div style="padding:12px 16px;color:var(--secondary-text-color)">${T.title} …</div></ha-card>`; return; }
    const strong = v.level === "boost" || v.level === "high", warn = (v.warn || []).length > 0;
    const a = strong ? "#6ea8fe" : warn ? "#f5b544" : "#47c7d8";
    const n = Math.max(1, Math.min(4, v.step || { low: 1, normal: 2, high: 3, boost: 4 }[v.current || v.level] || 1));
    const spin = n >= 4 ? .5 : n === 3 ? .9 : n === 2 ? 2 : 4;
    const lead = v.lead || {}, room = lead.name || "";
    let why = (T.why[v.why] || v.why || "").replace("{r}", room.toLowerCase());
    if (lead.minutes != null && (v.why === "shower" || v.why === "damp")) why += " · " + T.min.replace("{x}", lead.minutes);
    // in shadow the unit runs on what something else chose: say what Heat Pilot would do, and why
    if (v.mode !== "control" && v.current && v.current !== v.level) why = T.would.replace("{x}", (T.lv[v.level] || v.level).toLowerCase()) + " · " + why.charAt(0).toLowerCase() + why.slice(1);
    const R = 15, c = 16, seg = (i) => { const p = (x) => [c + R * Math.cos(x), c + R * Math.sin(x)], a0 = Math.PI * .75 + Math.PI * 1.5 * i / 4 + .1, a1 = Math.PI * .75 + Math.PI * 1.5 * (i + 1) / 4 - .1;
      const [x0, y0] = p(a0), [x1, y1] = p(a1); return `M${x0.toFixed(1)} ${y0.toFixed(1)} A${R} ${R} 0 0 1 ${x1.toFixed(1)} ${y1.toFixed(1)}`; };
    const ring = `<svg class="ring" viewBox="0 0 32 32">${[0, 1, 2, 3].map((i) => `<path d="${seg(i)}" fill="none" stroke="${i < n ? "var(--a)" : "var(--sbg)"}" stroke-width="2.6" stroke-linecap="round"/>`).join("")}</svg>`;
    const bars = [1, 2, 3, 4].map((k) => `<u class="${k <= n ? "l" : ""}" style="height:${4 + k * 2.5}px;animation-delay:${k * .12}s"></u>`).join("");
    const chip = (t, k) => `<span class="chip" style="--k:${k}"><i></i>${t}</span>`;
    const val = lead.value != null ? `${lead.value}${lead.unit === "%" ? " %" : " " + (lead.unit || "")}` : null;
    const w0 = (v.warn || [])[0] || {};
    const right = strong && val ? chip(val, v.why === "co2" ? "#f5b544" : "#ff6a4a")
      : warn ? chip(w0.co2 != null && w0.co2 >= 1000 ? `${w0.co2} ppm` : `${w0.hum} %`, w0.air === "bad" ? "#ff6a4a" : "#f5b544")
      : v.outdoor != null && v.supply != null ? `<span class="mini">${v.outdoor}° <s></s> ${v.supply}°${v.efficiency != null ? ` · ${v.efficiency} %` : ""}</span>` : "";
    const air = strong ? `<svg class="air" viewBox="0 0 400 60" preserveAspectRatio="none">${[0, 1, 2].map((k) => `<path d="M-30 ${14 + k * 16} C 100 ${4 + k * 16}, 220 ${26 + k * 14}, 430 ${10 + k * 16}" style="animation-delay:${-k * .8}s"/>`).join("")}</svg>` : "";
    const shadow = v.mode !== "control";
    const open = this._open ? `<div class="more">${v.efficiency != null ? `<span>${v.outdoor}° → ${v.supply}° · ${T.rec.replace("{x}", v.efficiency)}</span>` : ""}
      ${warn ? (v.warn || []).map((w) => chip(`${w.name} ${w.co2 != null && w.co2 >= 1000 ? w.co2 + " ppm" : w.hum + " %"}`, w.air === "bad" ? "#ff6a4a" : "#f5b544")).join("") : `<span>${T.ok}</span>`}
      ${shadow && v.agree != null ? `<span>${T.agree.replace("{x}", v.agree)}</span>` : ""}</div>` : "";
    this.shadowRoot.innerHTML = `<style>
      :host { --a:${a}; --sbg:color-mix(in srgb, var(--primary-text-color) 9%, transparent); }
      ha-card { position:relative; overflow:hidden; cursor:pointer; ${strong ? `background:radial-gradient(120% 160% at 0% 0%, color-mix(in srgb, var(--a) 28%, transparent), transparent 55%), radial-gradient(80% 140% at 100% 100%, color-mix(in srgb, var(--a) 12%, transparent), transparent 60%), var(--ha-card-background, var(--card-background-color));` : ""} }
      .air { position:absolute; inset:0; width:100%; height:100%; pointer-events:none; }
      .air path { fill:none; stroke:var(--a); stroke-width:2; stroke-linecap:round; opacity:.22; stroke-dasharray:70 330; animation:flow 2.4s linear infinite; }
      @keyframes flow { from { stroke-dashoffset:400; } to { stroke-dashoffset:0; } }
      .row { position:relative; display:flex; align-items:center; gap:10px; padding:7px 10px 7px 12px; min-height:46px; box-sizing:border-box; }
      .fan { position:relative; width:32px; height:32px; flex:none; }
      .ring { position:absolute; inset:0; }
      .b { position:absolute; inset:8px; width:16px; height:16px; color:var(--a); animation:sp ${spin}s linear infinite; filter:drop-shadow(0 0 5px color-mix(in srgb, var(--a) 70%, transparent)); }
      @keyframes sp { to { transform:rotate(360deg); } }
      .txt { min-width:0; flex:1; }
      .lv { font-size:14px; font-weight:700; display:flex; align-items:center; gap:6px; white-space:nowrap; }
      .bars { display:inline-flex; align-items:flex-end; gap:2px; height:14px; }
      .bars u { width:4px; border-radius:2px; background:var(--sbg); text-decoration:none; }
      .bars u.l { background:var(--a); box-shadow:0 0 6px color-mix(in srgb, var(--a) 70%, transparent); animation:eq ${Math.max(.4, spin / 3)}s ease-in-out infinite alternate; }
      @keyframes eq { to { opacity:.55; } }
      .trin { font-size:10.5px; font-weight:750; color:var(--a); letter-spacing:.02em; }
      .tag { font-size:10px; font-weight:700; letter-spacing:.08em; text-transform:uppercase; color:var(--a); background:color-mix(in srgb, var(--a) 15%, transparent); padding:2px 6px; border-radius:6px; }
      .why { font-size:11.5px; color:var(--secondary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
      .mini { font-size:11px; color:var(--secondary-text-color); white-space:nowrap; display:flex; align-items:center; gap:4px; }
      .mini s { text-decoration:none; display:inline-block; width:14px; height:3px; border-radius:2px; background:linear-gradient(90deg,#6ea8fe,#f5b544); }
      .chip { display:inline-flex; align-items:center; gap:5px; font-size:11px; font-weight:650; padding:3px 8px; border-radius:9px; white-space:nowrap; background:color-mix(in srgb, var(--k) 15%, transparent); }
      .chip i { width:7px; height:7px; border-radius:50%; background:var(--k); box-shadow:0 0 6px var(--k); }
      .bt { width:30px; height:30px; border-radius:50%; flex:none; display:flex; align-items:center; justify-content:center; background:var(--sbg); color:var(--secondary-text-color); border:0; padding:0; }
      .bt.on { background:linear-gradient(135deg, var(--a), color-mix(in srgb, var(--a) 55%, #7b6dff)); color:#fff; box-shadow:0 3px 10px color-mix(in srgb, var(--a) 45%, transparent); }
      .bt:disabled { opacity:.45; } .bt svg { width:15px; height:15px; fill:currentColor; }
      .more { position:relative; display:flex; flex-wrap:wrap; gap:6px 10px; align-items:center; padding:0 12px 10px 54px; font-size:11.5px; color:var(--secondary-text-color); }
      @media (prefers-reduced-motion: reduce) { .b, .bars u.l, .air path { animation:none; } }
    </style><ha-card>${air}<div class="row">
      <div class="fan">${ring}<svg class="b" viewBox="0 0 24 24" fill="currentColor">${VV_FAN}</svg></div>
      <div class="txt"><div class="lv">${T.lv[v.current || v.level] || v.level}<span class="bars">${bars}</span><span class="trin">${T.step} ${n}</span>${shadow ? `<span class="tag">${T.shadow}</span>` : ""}</div><div class="why">${why}</div></div>
      ${right}
      <button class="bt ${strong ? "on" : ""}" ${shadow ? "disabled" : ""} title="${shadow ? T.boostT : ""}"><svg viewBox="0 0 24 24"><path d="M13 2 4 14h7l-1 8 9-12h-7z"/></svg></button>
    </div>${open}</ha-card>`;
    this.shadowRoot.querySelector("ha-card").onclick = (e) => { if (e.target.closest(".bt")) return; this._open = !this._open; this._key = ""; this.hass = this._hass; };
  }
}
customElements.define("varmepilot-vent-card", VarmepilotVentCard);
window.customCards = window.customCards || [];
window.customCards.push({ type: "varmepilot-card", name: "Varmepilot", description: "All rooms at a glance" },
                        { type: "varmepilot-room-card", name: "Varmepilot – room", description: "One room: temperature, boost and + / −", preview: true },
                        { type: "varmepilot-vent-card", name: "Varmepilot – ventilation", description: "The ventilation in one line: the step, why and what matters now", preview: true });
