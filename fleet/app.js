// =============================================================================
// Ouroboros Fleet - logica applicazione (gira interamente sul telefono)
// =============================================================================
// Tutto lo stato (chiavi API, agenti, conversazioni) vive in localStorage,
// quindi NON lascia mai il dispositivo se non per chiamare le API che scegli tu.
// =============================================================================

const LS = {
  keys: "of_keys",       // { providerId: "APIKEY" }
  accounts: "of_accts",  // { providerId: "accountId" } (es. Cloudflare)
  agents: "of_agents",   // [ {id,name,emoji,provider,model,system,temp} ]
  chats: "of_chats",     // { agentId: [ {role,content} ] }
};

const store = {
  get(k, def) { try { return JSON.parse(localStorage.getItem(k)) ?? def; } catch { return def; } },
  set(k, v) { localStorage.setItem(k, JSON.stringify(v)); },
};

let state = {
  keys: store.get(LS.keys, {}),
  accounts: store.get(LS.accounts, {}),
  agents: store.get(LS.agents, null),
  chats: store.get(LS.chats, {}),
  activeAgent: null,
  council: new Set(),
};

// ---- Agenti di default (al primo avvio) ------------------------------------
if (!state.agents) {
  state.agents = [
    { id: uid(), name: "Architetto", emoji: "🧭", provider: "gemini", model: "gemini-2.5-flash", temp: 0.4,
      system: "Sei l'Architetto. Leggi il task e proponi struttura, piano d'azione e i prossimi passi concreti. Sii diretto, niente fronzoli." },
    { id: uid(), name: "Analista", emoji: "🕵️", provider: "groq", model: "llama-3.3-70b-versatile", temp: 0.3,
      system: "Sei l'Analista. Analizza i dati in modo iper-razionale. Report conciso, fatti, nessuna divagazione." },
    { id: uid(), name: "Tattico", emoji: "♟️", provider: "openrouter", model: "deepseek/deepseek-r1:free", temp: 0.7,
      system: "Sei il Tattico, l'avvocato del diavolo. Trova i punti ciechi, smonta le idee deboli e dai un verdetto spietato ma utile." },
    { id: uid(), name: "Coder", emoji: "💻", provider: "cerebras", model: "qwen-3-235b-a22b-instruct-2507", temp: 0.2,
      system: "Sei un ingegnere software senior. Scrivi codice corretto e idiomatico, spiega solo l'essenziale." },
  ];
  store.set(LS.agents, state.agents);
}

function uid() { return Math.random().toString(36).slice(2, 10); }
function saveAgents() { store.set(LS.agents, state.agents); }
function saveChats() { store.set(LS.chats, state.chats); }
function saveKeys() { store.set(LS.keys, state.keys); store.set(LS.accounts, state.accounts); }
function esc(s) { return (s ?? "").replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])); }
function agentById(id) { return state.agents.find(a => a.id === id); }

// =============================================================================
// Client unificato OpenAI-compatible (streaming)
// =============================================================================
async function* streamChat(agent, messages) {
  const prov = PROVIDERS[agent.provider];
  if (!prov) throw new Error("Provider sconosciuto: " + agent.provider);
  const key = state.keys[agent.provider];
  if (!key) throw new Error(`Manca la chiave API per ${prov.name}. Vai su Provider → ${prov.name}.`);

  let base = prov.baseUrl;
  if (prov.needsAccount) {
    const acct = state.accounts[agent.provider];
    if (!acct) throw new Error(`${prov.name} richiede l'Account ID (impostalo in Provider).`);
    base = base.replace("{account}", acct);
  }

  const body = {
    model: agent.model,
    messages: [{ role: "system", content: agent.system }, ...messages],
    temperature: agent.temp ?? 0.5,
    stream: true,
  };

  const res = await fetch(base + "/chat/completions", {
    method: "POST",
    headers: {
      "Authorization": "Bearer " + key,
      "Content-Type": "application/json",
      "HTTP-Referer": location.origin,
      "X-Title": "Ouroboros Fleet",
    },
    body: JSON.stringify(body),
  });

  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    throw new Error(`HTTP ${res.status} da ${prov.name}: ${txt.slice(0, 300)}`);
  }

  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (!line.startsWith("data:")) continue;
      const data = line.slice(5).trim();
      if (data === "[DONE]") return;
      try {
        const json = JSON.parse(data);
        const delta = json.choices?.[0]?.delta?.content;
        if (delta) yield delta;
      } catch { /* riga parziale, ignora */ }
    }
  }
}

// Versione non-streaming (per la modalità Council, raccoglie tutto)
async function chatOnce(agent, messages) {
  let out = "";
  for await (const chunk of streamChat(agent, messages)) out += chunk;
  return out;
}

// =============================================================================
// SCAN & IMPORT delle TUE chiavi (riconosce il provider, valida dal vivo)
// =============================================================================
// NB: opera SOLO su chiavi che incolli tu (backup .env, testo, clipboard).
// Non cerca nulla sul web: non esistono chiavi "gratis" da trovare online,
// e usare chiavi altrui trapelate e' furto di credenziali. Qui importiamo
// solo cio' che gia' possiedi, mettendolo nel provider giusto.

// Pattern per riconoscere a quale provider appartiene una chiave (dal prefisso).
const KEY_PATTERNS = [
  { provider: "openrouter", re: /sk-or-v1-[A-Za-z0-9]{32,}/g },
  { provider: "groq",       re: /gsk_[A-Za-z0-9]{20,}/g },
  { provider: "gemini",     re: /AIza[0-9A-Za-z\-_]{35}/g },
  { provider: "nvidia",     re: /nvapi-[A-Za-z0-9_\-]{20,}/g },
  { provider: "huggingface",re: /hf_[A-Za-z0-9]{20,}/g },
  { provider: "cerebras",   re: /csk-[A-Za-z0-9]{20,}/g },
  { provider: "github",     re: /(?:ghp_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{40,})/g },
];
// Chiavi generiche (sk-..., esadecimali lunghe) le proviamo dal vivo contro i
// provider candidati e le assegniamo a chi risponde 200.
const GENERIC_RE = /\b(sk-[A-Za-z0-9]{20,}|[A-Fa-f0-9]{48,})\b/g;
const GENERIC_CANDIDATES = ["deepseek", "mistral", "cohere", "together"];

function detectKeysByPrefix(text) {
  const found = [];
  const seen = new Set();
  for (const { provider, re } of KEY_PATTERNS) {
    const matches = text.match(re) || [];
    for (const k of matches) {
      if (seen.has(k)) continue;
      seen.add(k); found.push({ provider, key: k, sure: true });
    }
  }
  // candidati generici (provider incerto)
  const gen = text.match(GENERIC_RE) || [];
  for (const k of gen) {
    if (seen.has(k)) continue;
    seen.add(k); found.push({ provider: null, key: k, sure: false });
  }
  return found;
}

// Valida una chiave (read-only): GET {baseUrl}/models con Bearer.
async function validateKey(providerId, key) {
  const p = PROVIDERS[providerId];
  if (!p || p.needsAccount) return { ok: null }; // cloudflare richiede account: skip auto
  try {
    const res = await fetch(p.baseUrl + "/models", {
      headers: { "Authorization": "Bearer " + key },
    });
    if (res.ok) {
      let models = 0;
      try { const j = await res.json(); models = (j.data || j.models || j).length || 0; } catch {}
      return { ok: true, models };
    }
    return { ok: false, status: res.status };
  } catch (e) {
    return { ok: null, error: e.message }; // probabile CORS, non e' detto sia invalida
  }
}

// Crediti residui (solo dove l'API li espone con la TUA chiave).
async function fetchCredits(providerId, key) {
  if (providerId === "openrouter") {
    try {
      const r = await fetch("https://openrouter.ai/api/v1/key", { headers: { "Authorization": "Bearer " + key } });
      if (r.ok) {
        const d = (await r.json()).data || {};
        if (d.limit == null) return "crediti illimitati / pay-as-you-go";
        const rem = (d.limit - (d.usage || 0)).toFixed(4);
        return `residui ~$${rem} (usati $${(d.usage || 0).toFixed(4)})`;
      }
    } catch {}
  }
  return null;
}

// Apre il dialog di scansione e import.
function openScanDialog() {
  const dlg = document.getElementById("dialog");
  dlg.innerHTML = `
    <div class="dlg-card">
      <h3>🔍 Scansiona &amp; importa chiavi</h3>
      <p class="hint">Incolla qui le <strong>tue</strong> chiavi (un backup .env, testo, o tocca "Da clipboard"). L'app riconosce il provider e le testa.</p>
      <textarea id="scan-text" rows="6" placeholder="Es:\nGROQ_API_KEY=gsk_...\nGEMINI=AIza...\nsk-or-v1-..."></textarea>
      <div class="dlg-actions">
        <button class="ghost" id="scan-clip">📋 Da clipboard</button>
        <div>
          <button class="ghost" id="scan-cancel">Chiudi</button>
          <button id="scan-go">Scansiona</button>
        </div>
      </div>
      <div id="scan-results"></div>
    </div>`;
  dlg.classList.remove("hidden");
  dlg.querySelector("#scan-cancel").onclick = closeDialog;
  dlg.querySelector("#scan-clip").onclick = async () => {
    try {
      const t = await navigator.clipboard.readText();
      dlg.querySelector("#scan-text").value = t;
      toast("Clipboard incollata");
    } catch { toast("Permesso clipboard negato: incolla a mano"); }
  };
  dlg.querySelector("#scan-go").onclick = runScan;
}

async function runScan() {
  const text = document.getElementById("scan-text").value;
  const out = document.getElementById("scan-results");
  const found = detectKeysByPrefix(text);
  if (!found.length) { out.innerHTML = '<p class="hint">Nessuna chiave riconosciuta nel testo.</p>'; return; }
  out.innerHTML = '<p class="hint">Verifico le chiavi dal vivo…</p>';

  // assegna i candidati generici provando i provider possibili
  for (const item of found) {
    if (item.provider) {
      item.check = await validateKey(item.provider, item.key);
    } else {
      for (const cand of GENERIC_CANDIDATES) {
        if (state.keys[cand]) continue; // gia' configurato, salta
        const c = await validateKey(cand, item.key);
        if (c.ok) { item.provider = cand; item.check = c; break; }
        item.check = c;
      }
    }
  }

  out.innerHTML = "";
  found.forEach((item, i) => {
    const pname = item.provider ? PROVIDERS[item.provider].name : "provider ignoto";
    const ok = item.check?.ok;
    const badge = ok === true ? '<span class="ok">✓ valida</span>'
      : ok === false ? '<span class="warn">✗ rifiutata</span>'
      : '<span class="hint">? non verificabile (CORS)</span>';
    const masked = item.key.slice(0, 8) + "…" + item.key.slice(-4);
    const row = document.createElement("div");
    row.className = "card";
    row.innerHTML = `
      <div class="prov-head"><div class="prov-name">${esc(pname)} ${badge}</div></div>
      <div class="hint">${esc(masked)}${item.check?.models ? ` · ${item.check.models} modelli` : ""}</div>
      ${item.provider ? `<button class="mini" data-imp="${i}">Importa in ${esc(PROVIDERS[item.provider].name)}</button>` : '<span class="hint">Non riconosciuto: importalo a mano dalla scheda del provider.</span>'}`;
    if (item.provider) row.querySelector(`[data-imp="${i}"]`).onclick = () => {
      state.keys[item.provider] = item.key; saveKeys();
      toast(`Chiave ${PROVIDERS[item.provider].name} importata`);
      renderProviders();
    };
    out.appendChild(row);
  });
}

// Verifica TUTTE le chiavi salvate + crediti.
async function verifyAllKeys() {
  const out = document.getElementById("verify-out");
  const ids = Object.keys(state.keys);
  if (!ids.length) { out.innerHTML = '<p class="hint">Nessuna chiave salvata da verificare.</p>'; return; }
  out.innerHTML = '<div class="card"><p class="hint">Verifico ' + ids.length + ' chiavi…</p></div>';
  const rows = [];
  for (const id of ids) {
    const check = await validateKey(id, state.keys[id]);
    const credits = check.ok ? await fetchCredits(id, state.keys[id]) : null;
    const status = check.ok === true ? `<span class="ok">✓ attiva${check.models ? ` · ${check.models} modelli` : ""}</span>`
      : check.ok === false ? `<span class="warn">✗ errore ${check.status || ""}</span>`
      : '<span class="hint">? non verificabile dal browser (CORS)</span>';
    rows.push(`<div class="stat-row"><span>${esc(PROVIDERS[id]?.name || id)}</span><span>${status}</span></div>${credits ? `<div class="hint">💳 ${esc(credits)}</div>` : ""}`);
  }
  out.innerHTML = `<div class="card">${rows.join("")}</div>`;
}

// =============================================================================
// Routing tab
// =============================================================================
const views = ["fleet", "chat", "council", "providers", "settings"];
function show(view) {
  views.forEach(v => {
    document.getElementById("view-" + v).classList.toggle("hidden", v !== view);
  });
  document.querySelectorAll(".tab").forEach(t => {
    t.classList.toggle("active", t.dataset.view === view);
  });
  if (view === "fleet") renderFleet();
  if (view === "council") renderCouncil();
  if (view === "providers") renderProviders();
  if (view === "settings") renderSettings();
}

// =============================================================================
// Vista: Flotta
// =============================================================================
function renderFleet() {
  const el = document.getElementById("fleet-list");
  el.innerHTML = "";
  state.agents.forEach(a => {
    const prov = PROVIDERS[a.provider];
    const hasKey = !!state.keys[a.provider];
    const card = document.createElement("div");
    card.className = "card agent";
    card.innerHTML = `
      <div class="agent-emoji">${a.emoji || "🤖"}</div>
      <div class="agent-meta">
        <div class="agent-name">${esc(a.name)}</div>
        <div class="agent-sub">${esc(prov?.name || a.provider)} · ${esc(a.model)}
          ${hasKey ? "" : '<span class="warn">· chiave mancante</span>'}</div>
      </div>
      <div class="agent-actions">
        <button class="mini" data-act="chat">Chat</button>
        <button class="mini ghost" data-act="edit">✎</button>
      </div>`;
    card.querySelector('[data-act="chat"]').onclick = () => openChat(a.id);
    card.querySelector('[data-act="edit"]').onclick = () => editAgent(a.id);
    el.appendChild(card);
  });
}

// =============================================================================
// Editor agente
// =============================================================================
function editAgent(id) {
  const a = id ? agentById(id) : { id: "", name: "", emoji: "🤖", provider: "groq", model: "", temp: 0.5, system: "" };
  const provOpts = Object.entries(PROVIDERS).map(([k, p]) =>
    `<option value="${k}" ${k === a.provider ? "selected" : ""}>${p.name}</option>`).join("");

  const dlg = document.getElementById("dialog");
  dlg.innerHTML = `
    <div class="dlg-card">
      <h3>${id ? "Modifica agente" : "Nuovo agente"}</h3>
      <label>Nome <input id="f-name" value="${esc(a.name)}"></label>
      <label>Emoji <input id="f-emoji" value="${esc(a.emoji)}" maxlength="4"></label>
      <label>Provider <select id="f-prov">${provOpts}</select></label>
      <label>Modello <input id="f-model" value="${esc(a.model)}" placeholder="es. llama-3.3-70b-versatile"></label>
      <div class="hint" id="f-models"></div>
      <label>Temperatura <input id="f-temp" type="number" step="0.1" min="0" max="2" value="${a.temp}"></label>
      <label>System prompt (personalità)
        <textarea id="f-system" rows="5" placeholder="Sei un assistente che...">${esc(a.system)}</textarea>
      </label>
      <div class="dlg-actions">
        ${id ? '<button class="danger" id="f-del">Elimina</button>' : "<span></span>"}
        <div>
          <button class="ghost" id="f-cancel">Annulla</button>
          <button id="f-save">Salva</button>
        </div>
      </div>
    </div>`;
  dlg.classList.remove("hidden");

  const provSel = dlg.querySelector("#f-prov");
  const modelsHint = dlg.querySelector("#f-models");
  const modelInput = dlg.querySelector("#f-model");
  function refreshModels() {
    const p = PROVIDERS[provSel.value];
    modelsHint.innerHTML = "Suggeriti: " + p.models.map(m =>
      `<a href="#" data-m="${esc(m)}">${esc(m)}</a>`).join(" · ");
    modelsHint.querySelectorAll("a").forEach(link => {
      link.onclick = (e) => { e.preventDefault(); modelInput.value = link.dataset.m; };
    });
  }
  provSel.onchange = refreshModels;
  refreshModels();

  dlg.querySelector("#f-cancel").onclick = closeDialog;
  if (id) dlg.querySelector("#f-del").onclick = () => {
    if (confirm("Eliminare questo agente?")) {
      state.agents = state.agents.filter(x => x.id !== id);
      delete state.chats[id]; saveAgents(); saveChats(); closeDialog(); renderFleet();
    }
  };
  dlg.querySelector("#f-save").onclick = () => {
    const data = {
      name: dlg.querySelector("#f-name").value.trim() || "Agente",
      emoji: dlg.querySelector("#f-emoji").value.trim() || "🤖",
      provider: provSel.value,
      model: modelInput.value.trim() || PROVIDERS[provSel.value].models[0],
      temp: parseFloat(dlg.querySelector("#f-temp").value) || 0.5,
      system: dlg.querySelector("#f-system").value.trim(),
    };
    if (id) Object.assign(agentById(id), data);
    else state.agents.push({ id: uid(), ...data });
    saveAgents(); closeDialog(); renderFleet();
  };
}
function closeDialog() { document.getElementById("dialog").classList.add("hidden"); }

// =============================================================================
// Vista: Chat
// =============================================================================
function openChat(id) {
  state.activeAgent = id;
  const a = agentById(id);
  document.getElementById("chat-title").textContent = `${a.emoji} ${a.name}`;
  document.getElementById("chat-sub").textContent = `${PROVIDERS[a.provider]?.name} · ${a.model}`;
  renderMessages();
  show("chat");
  document.getElementById("chat-input").focus();
}

function renderMessages() {
  const log = document.getElementById("chat-log");
  const msgs = state.chats[state.activeAgent] || [];
  log.innerHTML = msgs.map(m =>
    `<div class="msg ${m.role}"><div class="bubble">${renderMd(m.content)}</div></div>`).join("");
  log.scrollTop = log.scrollHeight;
}

function renderMd(text) {
  // mini-markdown sicuro: blocchi di codice, inline code, grassetto, a-capo
  let html = esc(text);
  html = html.replace(/```([\s\S]*?)```/g, (_, c) => `<pre>${c.replace(/^\n/, "")}</pre>`);
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  html = html.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\n/g, "<br>");
  return html;
}

async function sendMessage() {
  const input = document.getElementById("chat-input");
  const text = input.value.trim();
  if (!text || !state.activeAgent) return;
  const agent = agentById(state.activeAgent);
  const msgs = state.chats[state.activeAgent] || (state.chats[state.activeAgent] = []);

  msgs.push({ role: "user", content: text });
  input.value = ""; input.style.height = "auto";
  renderMessages();

  const assistantMsg = { role: "assistant", content: "" };
  msgs.push(assistantMsg);
  renderMessages();
  const log = document.getElementById("chat-log");
  const bubble = log.querySelector(".msg:last-child .bubble");
  bubble.classList.add("typing");

  try {
    for await (const chunk of streamChat(agent, msgs.slice(0, -1))) {
      assistantMsg.content += chunk;
      bubble.innerHTML = renderMd(assistantMsg.content);
      log.scrollTop = log.scrollHeight;
    }
  } catch (e) {
    assistantMsg.content = "⚠️ " + e.message;
    bubble.innerHTML = renderMd(assistantMsg.content);
  } finally {
    bubble.classList.remove("typing");
    saveChats();
  }
}

// =============================================================================
// Vista: Council (più agenti rispondono in sequenza allo stesso task)
// =============================================================================
function renderCouncil() {
  const el = document.getElementById("council-agents");
  el.innerHTML = "";
  state.agents.forEach(a => {
    const chip = document.createElement("button");
    chip.className = "chip" + (state.council.has(a.id) ? " on" : "");
    chip.textContent = `${a.emoji} ${a.name}`;
    chip.onclick = () => {
      state.council.has(a.id) ? state.council.delete(a.id) : state.council.add(a.id);
      renderCouncil();
    };
    el.appendChild(chip);
  });
}

async function runCouncil() {
  const topic = document.getElementById("council-input").value.trim();
  const out = document.getElementById("council-out");
  if (!topic) { out.innerHTML = '<p class="hint">Scrivi prima un task.</p>'; return; }
  if (state.council.size === 0) { out.innerHTML = '<p class="hint">Seleziona almeno un agente.</p>'; return; }

  out.innerHTML = "";
  const selected = state.agents.filter(a => state.council.has(a.id));
  const transcript = [{ role: "user", content: topic }];

  for (const a of selected) {
    const block = document.createElement("div");
    block.className = "council-block";
    block.innerHTML = `<div class="council-who">${a.emoji} ${esc(a.name)} <span class="hint">${esc(a.model)}</span></div><div class="bubble typing"></div>`;
    out.appendChild(block);
    const bubble = block.querySelector(".bubble");
    let acc = "";
    try {
      // ogni agente vede il task + cosa hanno detto gli agenti precedenti
      for await (const chunk of streamChat(a, transcript)) {
        acc += chunk; bubble.innerHTML = renderMd(acc); out.scrollTop = out.scrollHeight;
      }
    } catch (e) { acc = "⚠️ " + e.message; bubble.innerHTML = renderMd(acc); }
    bubble.classList.remove("typing");
    transcript.push({ role: "assistant", content: `[${a.name}]: ${acc}` });
  }
}

// =============================================================================
// Vista: Provider (catalogo + inserimento chiavi)
// =============================================================================
function renderProviders() {
  const el = document.getElementById("providers-list");
  el.innerHTML = "";
  // Ordina per facilità (rank basso = più facile, senza carta); il resto dopo.
  const entries = Object.entries(PROVIDERS).sort((a, b) =>
    (a[1].rank || 99) - (b[1].rank || 99));
  entries.forEach(([k, p]) => {
    const hasKey = !!state.keys[k];
    const card = document.createElement("div");
    card.className = "card prov";
    const stepsHtml = p.steps ? `<ol class="prov-steps">${p.steps.map(s => `<li>${esc(s)}</li>`).join("")}</ol>` : "";
    card.innerHTML = `
      <div class="prov-head">
        <div class="prov-name">${p.rank ? `<span class="rankbadge">${p.rank}</span> ` : ""}${p.name} ${hasKey ? '<span class="ok">✓ chiave salvata</span>' : ""}</div>
        ${p.cors ? "" : '<span class="warn" title="Potrebbe servire un proxy">⚠ CORS</span>'}
      </div>
      <div class="prov-tag">${esc(p.tagline)}</div>
      <div class="prov-free">🎁 ${esc(p.free)}</div>
      <div class="prov-links">
        <a href="${p.signup}" target="_blank" rel="noopener">Ottieni chiave →</a>
        <a href="${p.docs}" target="_blank" rel="noopener">Limiti/docs</a>
      </div>
      ${stepsHtml}
      ${p.needsAccount ? `<input class="key-in" id="acct-${k}" placeholder="Account ID" value="${esc(state.accounts[k] || "")}">` : ""}
      <div class="key-row">
        <input class="key-in" id="key-${k}" type="password" placeholder="Incolla qui la tua API key" value="${esc(state.keys[k] || "")}">
        <button class="mini" data-save="${k}">Salva</button>
      </div>`;
    card.querySelector(`[data-save="${k}"]`).onclick = () => {
      const v = card.querySelector(`#key-${k}`).value.trim();
      if (v) state.keys[k] = v; else delete state.keys[k];
      if (p.needsAccount) {
        const av = card.querySelector(`#acct-${k}`).value.trim();
        if (av) state.accounts[k] = av; else delete state.accounts[k];
      }
      saveKeys(); renderProviders();
      toast(v ? `Chiave ${p.name} salvata sul telefono` : `Chiave ${p.name} rimossa`);
    };
    el.appendChild(card);
  });
}

// =============================================================================
// Vista: Impostazioni (export/import/reset)
// =============================================================================
function renderSettings() {
  document.getElementById("stat-agents").textContent = state.agents.length;
  document.getElementById("stat-keys").textContent = Object.keys(state.keys).length;
}

function exportConfig() {
  const data = JSON.stringify({ keys: state.keys, accounts: state.accounts, agents: state.agents }, null, 2);
  const blob = new Blob([data], { type: "application/json" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "ouroboros-fleet-backup.json";
  a.click();
}

function importConfig(file) {
  const r = new FileReader();
  r.onload = () => {
    try {
      const d = JSON.parse(r.result);
      if (d.agents) { state.agents = d.agents; saveAgents(); }
      if (d.keys) { state.keys = d.keys; }
      if (d.accounts) { state.accounts = d.accounts; }
      saveKeys();
      toast("Configurazione importata");
      renderSettings();
    } catch { toast("File non valido"); }
  };
  r.readAsText(file);
}

// =============================================================================
// UI helper
// =============================================================================
function toast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg; t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2200);
}

// =============================================================================
// Bootstrap
// =============================================================================
document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll(".tab").forEach(t => t.onclick = () => show(t.dataset.view));
  document.getElementById("add-agent").onclick = () => editAgent(null);
  document.getElementById("chat-back").onclick = () => show("fleet");
  document.getElementById("chat-send").onclick = sendMessage;
  document.getElementById("council-run").onclick = runCouncil;
  document.getElementById("export-btn").onclick = exportConfig;
  document.getElementById("import-file").onchange = (e) => e.target.files[0] && importConfig(e.target.files[0]);
  document.getElementById("scan-btn").onclick = openScanDialog;
  document.getElementById("verify-btn").onclick = verifyAllKeys;
  document.getElementById("clear-chats").onclick = () => {
    if (confirm("Cancellare tutte le conversazioni?")) { state.chats = {}; saveChats(); toast("Conversazioni cancellate"); }
  };

  const input = document.getElementById("chat-input");
  input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 140) + "px"; });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  });

  show("fleet");

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("./sw.js").catch(() => {});
  }
});
