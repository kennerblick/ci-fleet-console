"use strict";
const $ = s => document.querySelector(s);
let AUTH_TOKEN = null;   // Fallback, falls der Browser das Session-Cookie blockiert
const api = (url, opt) => {
  opt = opt || {};
  if (AUTH_TOKEN)
    opt.headers = Object.assign({}, opt.headers, {"Authorization": "Bearer " + AUTH_TOKEN});
  return fetch(url, opt).then(async r => {
  if (r.status === 401 && !url.startsWith("/api/auth/")){
    // Absicherung: erst verifizieren, ob wirklich die Session weg ist –
    // ein 401 aus einem Backend-Fehlerpfad darf nicht ausloggen.
    let d = {}; try { d = await r.json(); } catch(e){}
    const chk = await fetch("/api/auth/me", AUTH_TOKEN
      ? {headers: {"Authorization": "Bearer " + AUTH_TOKEN}} : {});
    if (!chk.ok){ showLogin(); throw new Error("Nicht angemeldet"); }
    throw new Error(d.detail || "401 Unauthorized");
  }
  if (!r.ok) { let d = {}; try { d = await r.json(); } catch(e){}
    throw new Error(d.detail || r.status + " " + r.statusText); }
  return r.json();
  });
};

let ME = null;   // {username, role, source}

function showLogin(){
  $("#login-bg").style.display = "flex";
  $("#login-err").textContent = "";
  setTimeout(() => $("#login-user").focus(), 50);
}

function onLoggedIn(){
  $("#login-bg").style.display = "none";
  $("#who").textContent = ME.username + (ME.role === "admin" ? " · Admin" : "") +
    (ME.source === "ad" ? " (AD)" : "");
  const admin = ME.role === "admin";
  $("#btn-settings").style.display = "";          // Konfiguration ist pro Benutzer
  $("#btn-users").style.display = admin ? "" : "none";
  loadTree(0);
}

async function doLogin(){
  $("#login-btn").disabled = true;
  try {
    ME = await api("/api/auth/login", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({username: $("#login-user").value.trim(),
                            password: $("#login-pass").value})
    });
    $("#login-pass").value = "";
    AUTH_TOKEN = ME.token || null;
    delete ME.token;
    onLoggedIn();
  } catch(e){ $("#login-err").textContent = e.message; }
  finally { $("#login-btn").disabled = false; }
}

async function init(){
  try { ME = await api("/api/auth/me"); onLoggedIn(); }
  catch(e){ showLogin(); }
}

let TREE = null;          // /api/tree Ergebnis
let CUR = null;           // ausgewähltes Projekt
let CUR_REF = null;       // angezeigte CI-Version (null = HEAD)
let pollTimer = null;

const stClass = s => "st-" + (["success","failed","running","pending","created",
  "canceled","skipped","manual"].includes(s) ? s : "none");
const stLabel = s => s === "manual" ? "wartet (manuell)" : s;
const fmtTime = iso => iso ? new Date(iso).toLocaleString("de-DE",
  {day:"2-digit",month:"2-digit",year:"2-digit",hour:"2-digit",minute:"2-digit"}) : "–";

function toast(msg, ms=3500){
  const t = $("#toast"); t.textContent = msg; t.style.display = "block";
  clearTimeout(t._h); t._h = setTimeout(() => t.style.display = "none", ms);
}

/* ---------------------------------------------------------- Baum */
let _staleTries = 0;
function scheduleStaleReload(){
  // Server hat veraltete Daten geliefert und baut im Hintergrund neu ->
  // in ein paar Sekunden still nachladen, bis frische Daten da sind.
  if (!TREE || !TREE.stale){ _staleTries = 0; return; }
  if (_staleTries >= 6) return;
  _staleTries++;
  setTimeout(() => loadTree(0), 4000);
}

async function loadTree(refresh){
  $("#loader").style.display = "block";
  try {
    TREE = await api("/api/tree" + (refresh ? "?refresh=1" : ""));
  } catch(e){
    toast("Fehler: " + e.message, 6000);
    if (/nicht konfiguriert|Token ungültig/.test(e.message)) openSettings();
    return;
  }
  finally { $("#loader").style.display = "none"; }
  $("#group-label").textContent = TREE.group + "/ · Stand " + TREE.generated_at
    + (TREE.stale ? " · aktualisiere im Hintergrund …" : (TREE.cached ? " (Cache)" : ""));
  renderTree();
  renderStats();
  cacheInfo();
  scheduleStaleReload();
}

function buildHierarchy(projects){
  const root = {groups:{}, projects:[]};
  for (const p of projects){
    const parts = p.rel_path.split("/");
    let node = root;
    for (let i = 0; i < parts.length - 1; i++){
      node.groups[parts[i]] ??= {groups:{}, projects:[]};
      node = node.groups[parts[i]];
    }
    node.projects.push(p);
  }
  return root;
}

const relevantPipe = p =>
  p.pipelines.find(x => x.status !== "skipped") || p.pipelines[0];

function projRow(p){
  const div = document.createElement("div");
  div.className = "proj"; div.dataset.id = p.id; div.title = p.rel_path;
  div.setAttribute("role","button"); div.tabIndex = 0;
  const last = relevantPipe(p);
  const dot = `<span class="dot ${stClass(last ? last.status : "none")}"></span>`;
  const spark = p.pipelines.length
    ? `<span class="spark">${p.pipelines.map(x=>`<i class="${stClass(x.status)}" title="${x.status}"></i>`).join("")}</span>`
    : (p.has_ci ? `<span class="spark"></span>` : `<span class="noci">kein CI</span>`);
  div.innerHTML = dot + `<span class="name">${p.name}</span>` + spark;
  const open = () => selectProject(p.id);
  div.onclick = open;
  div.onkeydown = e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); open(); } };
  return div;
}

// Offene Zweige merken (überlebt Neuladen der Seite via localStorage)
const openGroups = new Set(JSON.parse(localStorage.getItem("openGroups") || "[]"));
const saveOpenGroups = () =>
  localStorage.setItem("openGroups", JSON.stringify([...openGroups]));

function renderGroup(name, node, container, parentPath, forceOpen){
  const path = parentPath ? parentPath + "/" + name : name;
  const det = document.createElement("details");
  det.className = "grp";
  det.open = forceOpen || openGroups.has(path);
  const sum = document.createElement("summary");
  const nProjects = countProjects(node);
  sum.innerHTML = `${name}/ <span class="grp-count">${nProjects}</span>`;
  const jbtn = document.createElement("button");
  jbtn.className = "grp-jobs-btn";
  jbtn.textContent = "⊞";
  jbtn.title = "Gemeinsame Jobs aller Projekte dieser Gruppe";
  jbtn.onclick = e => { e.preventDefault(); e.stopPropagation(); openGroupJobs(path); };
  sum.appendChild(jbtn);
  det.appendChild(sum);
  det.addEventListener("toggle", () => {
    if (det.open) openGroups.add(path); else openGroups.delete(path);
    saveOpenGroups();
  });
  for (const g of Object.keys(node.groups).sort())
    renderGroup(g, node.groups[g], det, path, forceOpen);
  for (const p of node.projects) det.appendChild(projRow(p));
  container.appendChild(det);
}

function countProjects(node){
  return node.projects.length +
    Object.values(node.groups).reduce((s, g) => s + countProjects(g), 0);
}

function renderTree(){
  const pane = $("#tree-pane");
  pane.querySelectorAll("details,.proj").forEach(e => e.remove());
  const filter = $("#search").value.trim().toLowerCase();
  const onlyCi = $("#only-ci").checked;
  const list = TREE.projects.filter(p =>
    (!onlyCi || p.has_ci) &&
    (!filter || p.rel_path.toLowerCase().includes(filter)));
  const h = buildHierarchy(list);
  // Bei aktiver Suche alle Treffer-Zweige aufklappen, sonst nur gemerkte
  const forceOpen = !!filter;
  for (const g of Object.keys(h.groups).sort())
    renderGroup(g, h.groups[g], pane, "", forceOpen);
  for (const p of h.projects) pane.appendChild(projRow(p));
  if (CUR) pane.querySelector(`.proj[data-id="${CUR.id}"]`)?.classList.add("active");
}

function renderStats(){
  const ps = TREE.projects;
  const ok = ps.filter(p => relevantPipe(p)?.status === "success").length;
  const bad = ps.filter(p => relevantPipe(p)?.status === "failed").length;
  const ci = ps.filter(p => p.has_ci).length;
  $("#stats").textContent =
    `${ps.length} Projekte · ${ci} mit CI · ${ok} grün · ${bad} rot`;
  const rest = ps.length - ok - bad;
  $("#statbar").innerHTML =
    `<div style="flex:${ok};background:var(--ok)"></div>` +
    `<div style="flex:${bad};background:var(--fail)"></div>` +
    `<div style="flex:${rest};background:var(--other)"></div>`;
}

async function cacheInfo(){
  try { const i = await api("/api/cache/info");
    $("#cache-info").textContent = `${i.files} Cache-Dateien, ${(i.bytes/1024).toFixed(0)} kB`;
  } catch(e){}
}

/* ---------------------------------------------------------- Detail */
async function selectProject(id){
  CUR = TREE.projects.find(p => p.id === id);
  CUR_REF = null;
  GRP = null;
  $("#group-detail").style.display = "none";
  openJobs.clear(); closedJobs.clear(); showAllPipes = false;
  clearInterval(pollTimer);
  document.querySelectorAll(".proj.active").forEach(e => e.classList.remove("active"));
  document.querySelector(`.proj[data-id="${id}"]`)?.classList.add("active");
  $("#empty").style.display = "none";
  $("#detail").style.display = "block";
  $("#proj-title").textContent = CUR.full_path;
  $("#proj-meta").innerHTML =
    `Branch <b>${CUR.default_branch || "?"}</b> · letzte Aktivität ${fmtTime(CUR.last_activity_at)}`
    + ` · <a href="${CUR.web_url}" target="_blank" rel="noopener">in GitLab öffnen ↗</a>`;
  $("#run-ref").value = CUR.default_branch || "main";
  $("#run-vars").value = "";
  $("#commit-branch").textContent = CUR.default_branch || "main";
  $("#commit-msg").value = "";
  $("#versions").style.display = "none";
  $("#btn-versions-toggle").textContent = "Versionen anzeigen";
  loadPipelines();
  loadCi(null);
  loadVars();
}

let showAllPipes = false;            // "x weitere anzeigen" aufgeklappt?
const closedJobs = new Set();        // vom Nutzer bewusst zugeklappte Stage-Ansichten
const PIPES_VISIBLE = 3;

async function loadPipelines(refresh){
  const tbody = $("#pipes-table tbody");
  tbody.innerHTML = "";
  let data;
  try { data = await api(`/api/projects/${CUR.id}/pipelines` + (refresh ? "?refresh=1" : "")); }
  catch(e){ toast("Pipelines: " + e.message, 5000); return; }
  $("#pipes-empty").style.display = data.pipelines.length ? "none" : "block";

  const visible = showAllPipes ? data.pipelines : data.pipelines.slice(0, PIPES_VISIBLE);
  // Skip-Pipelines (z. B. aus ci.skip-Pushes der CI selbst) sind Rauschen –
  // die Stage-Ansicht bekommt die neueste Pipeline, die nicht "skipped" ist.
  let autoIdx = visible.findIndex(p => p.status !== "skipped");
  if (autoIdx === -1) autoIdx = 0;
  visible.forEach((p, i) => {
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td><span class="badge"><span class="dot ${stClass(p.status)}"></span>${stLabel(p.status)}</span></td>` +
      `<td>${p.ref || ""}</td><td class="muted">${p.sha}</td>` +
      `<td class="muted">${p.source || ""}</td><td class="muted">${fmtTime(p.created_at)}</td>` +
      `<td><a href="${p.web_url}" target="_blank" rel="noopener">#${p.id} ↗</a></td>`;
    tbody.appendChild(tr);

    // Nur die neueste relevante Pipeline bekommt die Stage-/Job-Ansicht
    // (auto-geöffnet, per Klick zuklappbar). Alle anderen bleiben einzeilig.
    if (i === autoIdx){
      tr.className = "piperow";
      tr.onclick = e => {
        if (e.target.tagName !== "A" && !e.target.closest("button")) toggleJobs(tr, p.id);
      };
      if (!closedJobs.has(p.id)){
        openJobs.add(p.id);
        toggleJobs(tr, p.id, true);
      }
    }
  });

  const hidden = data.pipelines.length - visible.length;
  if (hidden > 0 || showAllPipes){
    const tr = document.createElement("tr");
    tr.innerHTML = `<td colspan="6" style="text-align:center;border-bottom:none">
      <button id="btn-more-pipes">${showAllPipes
        ? "▴ weniger anzeigen"
        : `▾ ${hidden} weitere anzeigen`}</button></td>`;
    tr.querySelector("button").onclick = () => { showAllPipes = !showAllPipes; loadPipelines(); };
    tbody.appendChild(tr);
  }

  const active = data.pipelines.some(p => ["running","pending","created"].includes(p.status));
  clearInterval(pollTimer);
  if (active) pollTimer = setInterval(() => loadPipelines(1), 10000);
}

const openJobs = new Set();   // Pipeline-IDs mit aufgeklappter Stage-Ansicht

async function toggleJobs(tr, pid, forceOpen){
  const next = tr.nextElementSibling;
  if (!forceOpen && next?.classList.contains("jobsrow")){
    next.remove(); openJobs.delete(pid); closedJobs.add(pid); return;
  }
  openJobs.add(pid); closedJobs.delete(pid);
  let jr = next?.classList.contains("jobsrow") ? next : null;
  if (!jr){
    jr = document.createElement("tr");
    jr.className = "jobsrow";
    jr.innerHTML = `<td colspan="6" class="muted">Lade Jobs …</td>`;
    tr.after(jr);
  }
  try {
    const d = await api(`/api/projects/${CUR.id}/pipelines/${pid}/jobs`);
    jr.firstElementChild.innerHTML = renderStages(d.jobs, pid);
  } catch(e){ jr.firstElementChild.textContent = "Fehler: " + e.message; }
}

function jobButton(j, pid, projectId){
  const proj = projectId ?? (CUR && CUR.id);
  const base = `data-job="${j.id}" data-pipe="${pid}" data-project="${proj}"`;
  if (j.status === "manual")
    return `<button class="jbtn" data-act="play" ${base} title="Manuellen Job starten">▶ Run</button>`;
  if (["running","pending","created"].includes(j.status))
    return `<button class="jbtn" data-act="cancel" ${base} title="Job abbrechen">■</button>`;
  return `<button class="jbtn" data-act="retry" ${base} title="Job erneut ausführen">↻</button>`;
}

function renderStages(jobs, pid){
  if (!jobs.length) return "Keine Jobs.";
  const order = [], byStage = {};
  for (const j of jobs){                       // Backend liefert nach ID sortiert
    if (!byStage[j.stage]){ byStage[j.stage] = []; order.push(j.stage); }
    byStage[j.stage].push(j);
  }
  let out = `<div class="stages">` + order.map(st =>
    `<div class="stage"><div class="stage-name">${st}</div>` +
    byStage[st].map(j =>
      `<div class="job${j.bridge ? " bridge" : ""}">` +
      `<span class="dot ${stClass(j.status)}" title="${j.status}"></span>` +
      `<a class="jname" href="${j.web_url}" target="_blank" rel="noopener" ` +
      `title="${j.bridge ? "Trigger-Job" : "Job"}">${j.bridge ? "↳ " : ""}${j.name}</a>` +
      `<span class="dur">${j.duration ? Math.round(j.duration) + "s" : ""}</span>` +
      jobButton(j, pid) + `</div>`
    ).join("") + `</div>`
  ).join("") + `</div>`;

  // Getriggerte Child-/Downstream-Pipelines verschachtelt darstellen
  for (const j of jobs){
    if (!j.bridge || !j.downstream) continue;
    const d = j.downstream;
    out += `<div class="child">` +
      `<div class="child-head"><span class="dot ${stClass(d.status)}"></span>` +
      `↳ ${j.name} → Pipeline <a href="${d.web_url}" target="_blank" rel="noopener">#${d.id}</a>` +
      ` (${d.status})</div>` +
      (d.jobs && d.jobs.length ? renderStages(d.jobs, pid)
                               : `<span class="muted">keine Jobs / zu tief verschachtelt</span>`) +
      `</div>`;
  }
  return out;
}

document.addEventListener("click", async e => {
  const b = e.target.closest(".jbtn");
  if (!b) return;
  b.disabled = true;
  const projId = b.dataset.project || (CUR && CUR.id);
  try {
    await api(`/api/projects/${projId}/jobs/${b.dataset.job}/${b.dataset.act}`, {method:"POST"});
    toast({play:"Job gestartet.", retry:"Job neu gestartet.", cancel:"Job abgebrochen."}[b.dataset.act]);
    if (GRP !== null) openGroupJobs(GRP, 1);
    else loadPipelines(1);
  } catch(err){ toast("Fehler: " + err.message, 6000); b.disabled = false; }
});

/* ---------------------------------------------------------- CI-Datei */
async function loadCi(ref){
  CUR_REF = ref;
  let d;
  try { d = await api(`/api/projects/${CUR.id}/ci` + (ref ? "?ref=" + ref : "")); }
  catch(e){ toast("CI-Datei: " + e.message, 5000); return; }
  $("#editor").value = d.exists ? d.content
    : "# Noch keine .gitlab-ci.yml vorhanden – hier Inhalt eingeben und committen.\n";
  const ro = !!ref;
  CI_EXISTS = d.exists;
  $("#editor").readOnly = ro;
  $("#ro-banner").style.display = ro ? "block" : "none";
  $("#ro-sha").textContent = ref ? ref.slice(0,8) : "";
  $("#btn-save").disabled = ro;
  $("#tpl-bar").style.display = ro ? "none" : "flex";
  $("#tpl-bar").classList.toggle("replace", d.exists);
  $("#tpl-label").innerHTML = d.exists
    ? "Durch Standard-Vorlage <b>ersetzen</b>:"
    : "Keine <b>.gitlab-ci.yml</b> vorhanden – Vorlage einfügen:";
  if (!ro) loadTemplates();
  document.querySelectorAll("#versions li").forEach(li =>
    li.classList.toggle("current", li.dataset.sha === ref));
}

let CI_EXISTS = false;
let TPL_CATS = null;   // Kategorien einmal je Sitzung laden

async function loadTemplates(){
  const box = $("#tpl-buttons");
  if (TPL_CATS === null){
    try { TPL_CATS = (await api("/api/templates")).categories; }
    catch(e){ box.textContent = "Vorlagen nicht verfügbar: " + e.message; return; }
  }
  if (!TPL_CATS.length){ box.textContent = "Keine Vorlagen gefunden."; return; }
  box.innerHTML = "";
  for (const c of TPL_CATS){
    const b = document.createElement("button");
    b.textContent = c;
    b.onclick = () => insertTemplate(c, b);
    box.appendChild(b);
  }
}

async function insertTemplate(cat, btn){
  if (CI_EXISTS &&
      !confirm(`Der Inhalt im Editor wird durch die Vorlage "${cat}" ersetzt.\n` +
               `Committet wird erst mit "Committen". Fortfahren?`)) return;
  btn.disabled = true;
  try {
    const d = await api(`/api/templates/${encodeURIComponent(cat)}`);
    $("#editor").value = d.content;
    $("#commit-msg").value = CI_EXISTS
      ? `Replace .gitlab-ci.yml (Vorlage ${cat})`
      : `Add .gitlab-ci.yml (Vorlage ${cat})`;
    toast(`Vorlage ${cat} ${CI_EXISTS ? "übernommen" : "eingefügt"} (${d.file}) – prüfen und committen.`);
    $("#editor").focus();
  } catch(e){ toast("Vorlage: " + e.message, 6000); }
  finally { btn.disabled = false; }
}

async function toggleVersions(){
  const ul = $("#versions");
  if (ul.style.display !== "none"){
    ul.style.display = "none";
    $("#btn-versions-toggle").textContent = "Versionen anzeigen";
    return;
  }
  ul.innerHTML = "<li class='muted'>Lade Historie …</li>";
  ul.style.display = "block";
  $("#btn-versions-toggle").textContent = "Versionen ausblenden";
  try {
    const d = await api(`/api/projects/${CUR.id}/ci/versions`);
    ul.innerHTML = "";
    if (!d.versions.length){ ul.innerHTML = "<li class='muted'>Keine Historie (Datei fehlt?).</li>"; return; }
    d.versions.forEach((v, i) => {
      const li = document.createElement("li");
      li.dataset.sha = v.sha;
      li.innerHTML = `<span class="sha">${v.short}</span><span>${v.title}</span>` +
        `<span class="muted" style="margin-left:auto">${v.author} · ${fmtTime(v.created_at)}` +
        `${i === 0 ? " · HEAD" : ""}</span>`;
      li.onclick = () => loadCi(i === 0 ? null : v.sha);
      ul.appendChild(li);
    });
  } catch(e){ ul.innerHTML = `<li class='muted'>Fehler: ${e.message}</li>`; }
}

async function saveCi(restore){
  const content = $("#editor").value;
  const message = $("#commit-msg").value.trim() ||
    (restore ? `Restore ${$("#ro-sha").textContent} der .gitlab-ci.yml`
             : "Update .gitlab-ci.yml via CI Fleet Console");
  $("#btn-save").disabled = true;
  try {
    // Vor dem Commit: Pflicht-Variablen gegen den NEUEN Inhalt prüfen,
    // denn der Push löst die Pipeline sofort aus.
    const chk = await api(`/api/projects/${CUR.id}/vars/check-content`, {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({content})
    });
    if (varsBlock(chk, "Commit")) return;
    const d = await api(`/api/projects/${CUR.id}/ci`, {
      method: "PUT", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({content, message, branch: CUR.default_branch})
    });
    toast(`CI-Datei ${d.action} auf ${d.branch}.`);
    loadCi(null);
    loadVars();
    setTimeout(() => loadPipelines(1), 1500);   // Commit löst ggf. Pipeline aus
  } catch(e){ toast("Fehler: " + e.message, 6000); }
  finally { $("#btn-save").disabled = !!CUR_REF; }
}

async function runPipeline(){
  const ref = $("#run-ref").value.trim();
  const variables = $("#run-vars").value.split(",")
    .map(s => s.trim()).filter(Boolean)
    .map(s => { const i = s.indexOf("=");
      return i > 0 ? {key: s.slice(0, i).trim(), value: s.slice(i + 1).trim()} : null; })
    .filter(Boolean);
  $("#btn-run").disabled = true;
  try {
    // Erst prüfen, ob alle Pflicht-Variablen vorhanden sind
    const chk = await api(`/api/projects/${CUR.id}/vars/check`);
    if (varsBlock(chk, "Pipeline-Start")) return;
    const p = await api(`/api/projects/${CUR.id}/pipelines`, {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ref, variables})
    });
    if (p.status === "skipped")
      toast(`Pipeline #${p.id} wurde übersprungen – vermutlich lässt keine rules-Bedingung ` +
            `CI_PIPELINE_SOURCE == "api" zu.`, 8000);
    else
      toast(`Pipeline #${p.id} gestartet (${p.status}).`);
    loadPipelines(1);
  } catch(e){ toast("Fehler: " + e.message, 6000); }
  finally { $("#btn-run").disabled = false; }
}

/* ---------------------------------------------------------- Events */
$("#btn-refresh").onclick = () => loadTree(1);
$("#btn-cache").onclick = async () => {
  const d = await api("/api/cache/clear", {method:"POST"});
  toast(`${d.deleted} Cache-Dateien gelöscht.`); cacheInfo();
};
let _searchTimer;
$("#search").oninput = () => {
  clearTimeout(_searchTimer);
  _searchTimer = setTimeout(renderTree, 150);   // Debounce fuer fluessiges Tippen
};
$("#only-ci").onchange = () => renderTree();
$("#btn-expand-all").onclick = () => {
  document.querySelectorAll("#tree-pane details").forEach(d => d.open = true);
};
$("#btn-collapse-all").onclick = () => {
  document.querySelectorAll("#tree-pane details").forEach(d => d.open = false);
  openGroups.clear(); saveOpenGroups();
};
$("#btn-pipes-refresh").onclick = () => loadPipelines(1);
$("#btn-run").onclick = runPipeline;
$("#btn-versions-toggle").onclick = toggleVersions;
$("#btn-save").onclick = () => saveCi(false);
$("#btn-restore").onclick = () => { $("#editor").readOnly = false; saveCi(true); };
$("#btn-back-head").onclick = () => loadCi(null);
$("#editor").addEventListener("keydown", e => {   // Tab einfügen statt Fokuswechsel
  if (e.key === "Tab" && !e.shiftKey){
    e.preventDefault();
    const t = e.target, s = t.selectionStart;
    t.setRangeText("  ", s, t.selectionEnd, "end");
  }
});

/* ---------------------------------------------------- Konfiguration (⚙) */
let CFG_SELECTED = [];   // aktuell gespeicherte Auswahl (für Vorbelegung der Haken)

async function openSettings(){
  let s;
  try { s = await api("/api/settings"); }
  catch(e){ toast("Fehler: " + e.message, 5000); return; }
  $("#cfg-url").value = s.gitlab_url || "";
  $("#cfg-token").value = "";
  $("#cfg-token").placeholder = s.token_set ? "leer lassen = unverändert" : "glpat-…";
  const ts = $("#cfg-token-state");
  if (s.token_set){
    ts.style.color = "var(--ok)";
    ts.textContent = "✔ Eigenes Token gespeichert (wird nie angezeigt). " +
      "Feld leer lassen, um es zu behalten.";
  } else if (s.default_token_set){
    ts.style.color = "var(--pend)";
    ts.textContent = "○ Kein eigenes Token – es wird das Standard-Token verwendet. " +
      "Eigenes eintragen, um mit deinen GitLab-Rechten zu arbeiten.";
  } else {
    ts.style.color = "var(--fail)";
    ts.textContent = "✘ Weder eigenes noch Standard-Token vorhanden.";
  }
  $("#cfg-token-clear").style.display = s.token_set ? "inline-block" : "none";
  $("#cfg-default-label").style.display = s.is_admin ? "flex" : "none";
  $("#cfg-as-default").checked = false;
  $("#cfg-group").value = s.group_path || "";
  $("#cfg-tpl-project").value = s.templates_project || "";
  $("#cfg-tpl-project").placeholder =
    "leer = " + (s.group_path ? s.group_path + "/" : "<gruppe>/") + "ci-templates";
  $("#cfg-tpl-dir").value = s.templates_dir || "standard";
  CFG_SELECTED = s.selected_groups || [];
  $("#cfg-dirs-wrap").style.display = "none";
  $("#cfg-dirs").innerHTML = "";
  $("#cfg-scan-status").textContent = "";
  $("#modal-bg").style.display = "flex";
}

function closeSettings(){ $("#modal-bg").style.display = "none"; }

async function scanDirs(){
  const st = $("#cfg-scan-status");
  st.textContent = "lese …";
  $("#cfg-scan").disabled = true;
  try {
    const d = await api("/api/settings/scan", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({
        gitlab_url: $("#cfg-url").value.trim(),
        token: $("#cfg-token").value,          // leer = gespeichertes Token
        group_path: $("#cfg-group").value.trim(),
      })
    });
    st.textContent = `verbunden als ${d.user} – ${d.directories.length} Verzeichnisse`;
    const box = $("#cfg-dirs");
    box.innerHTML = "";
    const all = CFG_SELECTED.length === 0;   // gespeichert "alles" -> alles anhaken
    const entries = [...d.directories];
    if (d.has_root_projects)
      entries.unshift({path:".", name:`(Projekte direkt in ${d.group_path}/)`});
    for (const dir of entries){
      const lab = document.createElement("label");
      const cb = document.createElement("input");
      cb.type = "checkbox"; cb.value = dir.path;
      cb.checked = all || CFG_SELECTED.includes(dir.path);
      lab.appendChild(cb);
      lab.appendChild(document.createTextNode(
        dir.path === "." ? dir.name : dir.path + "/"));
      box.appendChild(lab);
    }
    $("#cfg-dirs-wrap").style.display = "block";
  } catch(e){ st.textContent = "Fehler: " + e.message; }
  finally { $("#cfg-scan").disabled = false; }
}

async function saveSettings(){
  const boxes = [...document.querySelectorAll("#cfg-dirs input")];
  let selected = null;
  if (boxes.length){                          // nur senden, wenn eingelesen wurde
    const checked = boxes.filter(b => b.checked).map(b => b.value);
    selected = (checked.length === boxes.length) ? [] : checked;  // alle = keine Einschränkung
    if (checked.length === 0){
      toast("Mindestens ein Verzeichnis anhaken (oder alle für keine Einschränkung).", 5000);
      return;
    }
  }
  const body = {
    gitlab_url: $("#cfg-url").value.trim(),
    token: $("#cfg-token").value,
    group_path: $("#cfg-group").value.trim(),
    templates_project: $("#cfg-tpl-project").value.trim(),
    templates_dir: $("#cfg-tpl-dir").value.trim(),
    as_default: $("#cfg-as-default").checked,
  };
  if (selected !== null) body.selected_groups = selected;
  $("#cfg-save").disabled = true;
  try {
    await api("/api/settings", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify(body)
    });
    closeSettings();
    toast("Konfiguration gespeichert – lade Baum neu …");
    CUR = null;
    GRP = null;
    TPL_CATS = null;                 // Vorlagen-Kategorien neu laden
    $("#detail").style.display = "none";
    $("#group-detail").style.display = "none";
    $("#empty").style.display = "block";
    loadTree(1);
  } catch(e){ toast("Fehler: " + e.message, 6000); }
  finally { $("#cfg-save").disabled = false; }
}

$("#btn-settings").onclick = openSettings;
$("#cfg-token-clear").onclick = async e => {
  e.preventDefault();
  if (!confirm("Eigenes Token entfernen und wieder das Standard-Token verwenden?")) return;
  try {
    await api("/api/settings", {method:"POST",
      headers:{"Content-Type":"application/json"},
      body: JSON.stringify({clear_token: true})});
    toast("Eigenes Token entfernt – Standard-Token aktiv.");
    openSettings();
    loadTree(1);
  } catch(err){ toast("Fehler: " + err.message, 6000); }
};
$("#cfg-cancel").onclick = closeSettings;
$("#cfg-scan").onclick = scanDirs;
$("#cfg-save").onclick = saveSettings;
$("#cfg-all").onclick = () =>
  document.querySelectorAll("#cfg-dirs input").forEach(b => b.checked = true);
$("#cfg-none").onclick = () =>
  document.querySelectorAll("#cfg-dirs input").forEach(b => b.checked = false);
$("#modal-bg").onclick = e => { if (e.target.id === "modal-bg") closeSettings(); };

/* ------------------------------------------- Benötigte Variablen (CI-VARS) */
async function loadVars(){
  const sec = $("#vars-sec");
  let d;
  try { d = await api(`/api/projects/${CUR.id}/vars/check`); }
  catch(e){ sec.style.display = "none"; return; }
  renderVarsData(d);
}

function renderVarsData(d){
  const sec = $("#vars-sec");
  if (!d.declared){ sec.style.display = "none"; return; }
  sec.style.display = "block";
  const list = $("#vars-list");
  list.innerHTML = "";
  let missingRequired = 0, inputs = 0;
  for (const r of d.required){
    const row = document.createElement("div");
    row.className = "var-row";
    const optional = r.default !== null && r.default !== undefined;
    const name = `<span class="var-name">${r.name}</span>`;
    if (r.present){
      row.innerHTML = `<span class="dot st-success"></span>${name}` +
        `<span class="muted">${r.hint || ""}</span>` +
        `<span class="var-src">${r.source || ""}</span>`;
    } else if (d.can_manage){
      if (optional){
        row.innerHTML = `<span class="dot st-pending" title="optional"></span>${name}` +
          `<span class="muted">optional · Default: ${r.default}</span>`;
      } else {
        missingRequired++;
        row.innerHTML = `<span class="dot st-failed"></span>${name}`;
      }
      const secret = /(PASSWORD|PASSPHRASE|SECRET|TOKEN|_KEY)/i.test(r.name);
      const inp = document.createElement("input");
      inp.className = "var-input";
      inp.type = secret ? "password" : "text";
      inp.dataset.key = r.name;
      inp.placeholder = optional
        ? "leer = Default verwenden"
        : (r.hint || "Wert eingeben");
      row.appendChild(inp);
      inputs++;
    } else {
      row.innerHTML = `<span class="dot st-none"></span>${name}` +
        `<span class="muted">${r.hint || ""}</span>` +
        `<span class="var-src">Status unbekannt</span>`;
    }
    list.appendChild(row);
  }
  $("#vars-note").style.display = d.can_manage ? "none" : "block";
  $("#vars-note").textContent =
    "Projekt-Variablen nicht lesbar – das Token braucht Maintainer-Rechte in diesem Projekt.";
  $("#btn-vars-save").textContent = missingRequired
    ? "Fehlende Variablen speichern" : "Variablen speichern";
  $("#vars-actions").style.display = inputs ? "block" : "none";
}

async function saveVars(){
  const variables = [...document.querySelectorAll("#vars-list .var-input")]
    .filter(i => i.value.trim() !== "")
    .map(i => ({key: i.dataset.key, value: i.value}));
  if (!variables.length){ toast("Keine Werte eingegeben."); return; }
  $("#btn-vars-save").disabled = true;
  try {
    const d = await api(`/api/projects/${CUR.id}/vars`, {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({variables})
    });
    const err = d.results.filter(r => r.action === "FEHLER");
    toast(err.length
      ? `Teilweise fehlgeschlagen: ${err.map(r => r.key).join(", ")}`
      : d.results.map(r => `${r.key} ${r.action}`).join(", "), 6000);
    loadVars();
  } catch(e){ toast("Fehler: " + e.message, 6000); }
  finally { $("#btn-vars-save").disabled = false; }
}

$("#btn-vars-refresh").onclick = loadVars;
$("#btn-vars-save").onclick = saveVars;

// true = blockieren. Zeigt die fehlenden Pflicht-Variablen und scrollt hin.
function varsBlock(chk, aktion){
  if (!chk || !chk.declared || !chk.can_manage) return false;   // unbekannt/keine Deklaration: nicht blockieren
  if (!chk.missing_required.length) return false;
  renderVarsData(chk);
  $("#vars-sec").scrollIntoView({behavior: "smooth", block: "center"});
  toast(`${aktion} blockiert – Pflicht-Variablen fehlen: ` +
        chk.missing_required.join(", "), 8000);
  return true;
}

/* ------------------------------------------------ Gruppen-Job-Matrix (⊞) */
let GRP = null;   // aktuell angezeigter Gruppenpfad, null = Projektansicht

async function openGroupJobs(path, refresh){
  GRP = path; CUR = null;
  clearInterval(pollTimer);
  document.querySelectorAll(".proj.active").forEach(el => el.classList.remove("active"));
  $("#empty").style.display = "none";
  $("#detail").style.display = "none";
  $("#group-detail").style.display = "block";
  $("#grp-title").textContent = TREE.group + "/" + path + "/";
  $("#grp-meta").textContent = "";
  $("#grp-matrix").innerHTML = `<span class="muted">Lade Jobs aller Projekte …</span>`;
  let d;
  try {
    d = await api(`/api/groups/jobs?path=${encodeURIComponent(path)}` +
                  (refresh ? "&refresh=1" : ""));
  } catch(e){ $("#grp-matrix").textContent = "Fehler: " + e.message; return; }
  if (GRP !== path) return;   // Nutzer hat inzwischen weitergeklickt
  $("#grp-meta").textContent = `${d.projects.length} Projekte mit Pipeline` +
    (d.excluded.length ? ` · ohne Pipeline/CI: ${d.excluded.join(", ")}` : "") +
    (d.stale ? " · aktualisiere im Hintergrund …" : "");
  renderMatrix(d);
  if (d.stale) setTimeout(() => { if (GRP === path) openGroupJobs(path, 0); }, 4000);
}

function renderMatrix(d){
  if (!d.projects.length){
    $("#grp-matrix").innerHTML = `<span class="muted">Kein Projekt mit Pipeline in dieser Gruppe.</span>`;
    return;
  }
  if (!d.jobs.length){
    $("#grp-matrix").innerHTML = `<span class="muted">Keine Jobs, die in allen Projekten vorkommen.</span>`;
    return;
  }
  let h = `<table class="matrix"><thead><tr><th>Job</th>`;
  for (const p of d.projects)
    h += `<th title="${p.rel_path} – Pipeline ${p.pipeline.status}">` +
         `<span class="dot ${stClass(p.pipeline.status)}"></span> ` +
         `<a href="${p.pipeline.web_url}" target="_blank" rel="noopener">${p.name}</a></th>`;
  h += `</tr></thead><tbody>`;
  let lastStage = null;
  for (const j of d.jobs){
    if (j.stage !== lastStage){
      lastStage = j.stage;
      h += `<tr class="stage-row"><td colspan="${d.projects.length + 1}">${j.stage}</td></tr>`;
    }
    h += `<tr><td class="${j.bridge ? "bridge-name" : ""}">${j.bridge ? "↳ " : ""}${j.name}</td>`;
    for (const p of d.projects){
      const c = j.cells[String(p.id)];
      h += `<td>` + (c
        ? `<span class="dot ${stClass(c.status)}" title="${c.status}` +
          `${c.duration ? " · " + Math.round(c.duration) + "s" : ""}"></span>` +
          `<a href="${c.web_url}" target="_blank" rel="noopener" class="muted">↗</a> ` +
          jobButton({id: c.job_id, status: c.status}, 0, p.id)
        : `<span class="muted">–</span>`) + `</td>`;
    }
    h += `</tr>`;
  }
  $("#grp-matrix").innerHTML = h + `</tbody></table>`;
}

$("#btn-grp-refresh").onclick = () => GRP !== null && openGroupJobs(GRP, 1);

/* --------------------------------------------------- Benutzerverwaltung (👤) */
async function openUsers(){
  $("#users-bg").style.display = "flex";
  await Promise.all([renderUsers(), loadAdCfg()]);
}

async function renderUsers(){
  const box = $("#users-list");
  box.innerHTML = `<div class="user-row muted">lade …</div>`;
  let d;
  try { d = await api("/api/users"); }
  catch(e){ box.innerHTML = `<div class="user-row">Fehler: ${e.message}</div>`; return; }
  box.innerHTML = "";
  for (const u of d.users){
    const row = document.createElement("div");
    row.className = "user-row";
    row.innerHTML = `<span class="uname">${u.username}</span>` +
      `<span class="utags">${u.role} · ${u.source}</span>` +
      `<span class="uactions"></span>`;
    const act = row.querySelector(".uactions");
    if (u.source === "local"){
      const pw = document.createElement("button");
      pw.textContent = "Passwort";
      pw.onclick = async () => {
        const np = prompt(`Neues Passwort für ${u.username} (min. 8 Zeichen):`);
        if (!np) return;
        try {
          await api(`/api/users/${encodeURIComponent(u.username)}/password`, {
            method:"POST", headers:{"Content-Type":"application/json"},
            body: JSON.stringify({password: np})});
          toast(`Passwort für ${u.username} gesetzt.`);
        } catch(e){ toast("Fehler: " + e.message, 6000); }
      };
      act.appendChild(pw);
    }
    const del = document.createElement("button");
    del.textContent = "Löschen";
    del.onclick = async () => {
      if (!confirm(`Benutzer ${u.username} löschen?`)) return;
      try {
        await api(`/api/users/${encodeURIComponent(u.username)}`, {method:"DELETE"});
        renderUsers();
      } catch(e){ toast("Fehler: " + e.message, 6000); }
    };
    act.appendChild(del);
    box.appendChild(row);
  }
}

async function loadAdCfg(){
  try {
    const c = await api("/api/authcfg");
    $("#ad-enabled").checked = !!c.ad_enabled;
    $("#ad-server").value = c.ad_server || "";
    $("#ad-upn").value = c.ad_upn_suffix || "";
    $("#ad-base").value = c.ad_base_dn || "";
    $("#ad-admin-grp").value = c.ad_admin_group || "";
    $("#ad-user-grp").value = c.ad_user_group || "";
  } catch(e){ toast("AD-Konfiguration: " + e.message, 5000); }
}

async function saveAdCfg(){
  $("#ad-save").disabled = true;
  try {
    await api("/api/authcfg", {
      method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({
        ad_enabled: $("#ad-enabled").checked,
        ad_server: $("#ad-server").value,
        ad_upn_suffix: $("#ad-upn").value,
        ad_base_dn: $("#ad-base").value,
        ad_admin_group: $("#ad-admin-grp").value,
        ad_user_group: $("#ad-user-grp").value,
      })});
    toast("AD-Einstellungen gespeichert.");
  } catch(e){ toast("Fehler: " + e.message, 6000); }
  finally { $("#ad-save").disabled = false; }
}

$("#btn-users").onclick = openUsers;
$("#users-close").onclick = () => $("#users-bg").style.display = "none";
$("#users-bg").onclick = e => { if (e.target.id === "users-bg") $("#users-bg").style.display = "none"; };
$("#nu-add").onclick = async () => {
  try {
    await api("/api/users", {method:"POST", headers:{"Content-Type":"application/json"},
      body: JSON.stringify({username: $("#nu-name").value.trim(),
        password: $("#nu-pass").value, role: $("#nu-role").value})});
    $("#nu-name").value = ""; $("#nu-pass").value = "";
    toast("Benutzer angelegt.");
    renderUsers();
  } catch(e){ toast("Fehler: " + e.message, 6000); }
};
$("#ad-save").onclick = saveAdCfg;
$("#ad-test").onclick = async () => {
  const res = $("#ad-test-result");
  res.style.color = "var(--muted)";
  res.textContent = "teste Verbindung …";
  $("#ad-test").disabled = true;
  try {
    const d = await api("/api/authcfg/test", {
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({
        ad_server: $("#ad-server").value,
        ad_upn_suffix: $("#ad-upn").value,
        ad_base_dn: $("#ad-base").value,
        ad_admin_group: $("#ad-admin-grp").value,
        ad_user_group: $("#ad-user-grp").value,
        username: $("#ad-test-user").value.trim(),
        password: $("#ad-test-pass").value,
      })});
    if (d.ok){
      res.style.color = "var(--ok)";
      res.textContent = `✔ ${d.message} – Rolle wäre: ${d.role}`;
    } else {
      res.style.color = "var(--fail)";
      res.textContent = "✘ " + d.message;
    }
  } catch(e){
    res.style.color = "var(--fail)";
    res.textContent = "✘ " + e.message;
  } finally {
    $("#ad-test").disabled = false;
    $("#ad-test-pass").value = "";     // Testpasswort nie stehen lassen
  }
};
$("#login-btn").onclick = doLogin;
$("#login-pass").addEventListener("keydown", e => { if (e.key === "Enter") doLogin(); });
$("#login-user").addEventListener("keydown", e => { if (e.key === "Enter") $("#login-pass").focus(); });
$("#btn-logout").onclick = async () => {
  try { await api("/api/auth/logout", {method:"POST"}); } catch(e){}
  ME = null;
  AUTH_TOKEN = null;
  showLogin();
};

init();
