// State management
let activitiesData = [];
let selectedActivityIds = new Set();
let filterDebounceTimer = null;

// Sport Icons Mapping
const SPORT_ICONS = {
    running: { icon: "activity", label: "Course à pied", color: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20" },
    cycling: { icon: "bike", label: "Cyclisme", color: "text-amber-400 bg-amber-500/10 border-amber-500/20" },
    road_biking: { icon: "bike", label: "Vélo de route", color: "text-amber-400 bg-amber-500/10 border-amber-500/20" },
    gravel_cycling: { icon: "bike", label: "Gravel", color: "text-amber-400 bg-amber-500/10 border-amber-500/20" },
    mountain_biking: { icon: "bike", label: "VTT", color: "text-amber-400 bg-amber-500/10 border-amber-500/20" },
    hiking: { icon: "mountain", label: "Randonnée", color: "text-indigo-400 bg-indigo-500/10 border-indigo-500/20" },
    walking: { icon: "footprints", label: "Marche", color: "text-teal-400 bg-teal-500/10 border-teal-500/20" },
    swimming: { icon: "waves", label: "Natation", color: "text-cyan-400 bg-cyan-500/10 border-cyan-500/20" },
    fitness_equipment: { icon: "dumbbell", label: "Musculation", color: "text-purple-400 bg-purple-500/10 border-purple-500/20" },
    strength_training: { icon: "dumbbell", label: "Renforcement", color: "text-purple-400 bg-purple-500/10 border-purple-500/20" },
    other: { icon: "zap", label: "Autre sport", color: "text-slate-400 bg-slate-800 border-slate-700" }
};

// --- Initialization ---

function initApp() {
    // Check for Strava OAuth callback success in query param
    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.get("strava_connected") === "1") {
        showToast("Compte Strava connecté avec succès !", "success");
        window.history.replaceState({}, document.title, window.location.pathname);
    }

    if (document.getElementById("activities-table-body")) {
        checkAppStatus();
        loadActivities();
    }

    if (document.getElementById("garmin-settings-status") || document.getElementById("strava-settings-status")) {
        initSettingsPage();
    }
}

if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initApp);
} else {
    initApp();
}

// --- Status & Connectivity ---

async function checkAppStatus() {
    try {
        const resp = await fetch("/api/status");
        if (!resp.ok) return;
        const data = await resp.json();

        // Update Garmin status badge in header
        const gBadge = document.getElementById("garmin-status-badge");
        const gAlert = document.getElementById("garmin-alert");
        if (gBadge) {
            if (data.garmin.connected) {
                gBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400"></span><span class="text-emerald-300">Garmin: Connecté (${data.garmin.email || 'OK'})</span>`;
                if (gAlert) gAlert.classList.add("hidden");
            } else {
                gBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-rose-400"></span><span class="text-rose-300">Garmin: Déconnecté</span>`;
                if (gAlert) gAlert.classList.remove("hidden");
            }
        }

        // Update Strava status badge in header
        const sBadge = document.getElementById("strava-status-badge");
        const sAlert = document.getElementById("strava-alert");
        if (sBadge) {
            if (data.strava.connected) {
                sBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-emerald-400"></span><span class="text-emerald-300">Strava: ${data.strava.athlete_name || 'Connecté'}</span>`;
                if (sAlert) sAlert.classList.add("hidden");
            } else {
                sBadge.innerHTML = `<span class="w-2 h-2 rounded-full bg-amber-400"></span><span class="text-amber-300">Strava: Déconnecté</span>`;
                if (sAlert) sAlert.classList.remove("hidden");
            }
        }

        // Show/Hide top alerts wrapper
        const alertsContainer = document.getElementById("connection-alerts");
        if (alertsContainer) {
            if (!data.garmin.connected || !data.strava.connected) {
                alertsContainer.classList.remove("hidden");
            } else {
                alertsContainer.classList.add("hidden");
            }
        }

        // Update Stats Counters
        if (data.stats) {
            updateStatElement("stat-total", data.stats.total || 0);
            updateStatElement("stat-synced", data.stats.synced || 0);
            updateStatElement("stat-not-synced", data.stats.not_synced || 0);
            updateStatElement("stat-error", data.stats.error || 0);
        }

    } catch (err) {
        console.error("Failed to check status:", err);
    }
}

function updateStatElement(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

// --- Loading Activities ---

async function loadActivities() {
    const tableBody = document.getElementById("activities-table-body");
    const emptyState = document.getElementById("empty-state");
    const spinner = document.getElementById("loading-spinner");
    const countEl = document.getElementById("activities-count");

    const statusFilter = document.getElementById("filter-status")?.value || "all";
    const typeFilter = document.getElementById("filter-type")?.value || "all";
    const search = document.getElementById("filter-search")?.value || "";

    if (spinner) spinner.classList.remove("hidden");

    try {
        const queryParams = new URLSearchParams({
            limit: 100,
            offset: 0,
            status: statusFilter,
            activity_type: typeFilter
        });
        if (search.trim()) {
            queryParams.append("search", search.trim());
        }

        const resp = await fetch(`/api/activities?${queryParams.toString()}`);
        const data = await resp.json();

        activitiesData = data.activities || [];
        if (countEl) countEl.textContent = data.total || 0;

        if (activitiesData.length === 0) {
            if (tableBody) tableBody.innerHTML = "";
            if (emptyState) emptyState.classList.remove("hidden");
        } else {
            if (emptyState) emptyState.classList.add("hidden");
            renderActivitiesTable(activitiesData);
        }
    } catch (err) {
        showToast("Erreur lors du chargement des activités: " + err.message, "error");
    } finally {
        if (spinner) spinner.classList.add("hidden");
    }
}

function debounceFilter() {
    clearTimeout(filterDebounceTimer);
    filterDebounceTimer = setTimeout(() => {
        loadActivities();
    }, 300);
}

// --- Render Table ---

function renderActivitiesTable(activities) {
    const tableBody = document.getElementById("activities-table-body");
    if (!tableBody) return;

    tableBody.innerHTML = activities.map(act => {
        const sportKey = (act.sport_type_key || act.activity_type || "other").toLowerCase();
        const isSwim = sportKey.includes("swim") || sportKey.includes("natation");
        const sportCfg = SPORT_ICONS[sportKey] || SPORT_ICONS.other;
        
        let distDisplay = "-";
        let paceDisplay = "";

        if (act.distance_meters > 0) {
            if (isSwim) {
                distDisplay = `${Math.round(act.distance_meters)} m`;
                if (act.duration_seconds > 0) {
                    const pace100 = act.duration_seconds / (act.distance_meters / 100);
                    const pMin = Math.floor(pace100 / 60);
                    const pSec = Math.floor(pace100 % 60);
                    paceDisplay = `<span class="text-[11px] text-cyan-400 font-mono block">${pMin}:${pSec.toString().padStart(2, "0")}/100m</span>`;
                }
            } else {
                distDisplay = `${(act.distance_meters / 1000).toFixed(2)} km`;
            }
        }

        const durationFormatted = formatDuration(act.duration_seconds);
        const elev = act.elevation_gain_meters ? Math.round(act.elevation_gain_meters) + " m D+" : "-";
        const hr = act.average_hr ? Math.round(act.average_hr) + " bpm" : "-";
        const dateFormatted = formatDate(act.start_time);

        const isChecked = selectedActivityIds.has(act.garmin_activity_id);

        let statusBadge = "";
        let actionBtn = "";

        if (act.status === "synced") {
            const stravaUrl = act.strava_activity_id ? `https://www.strava.com/activities/${act.strava_activity_id}` : "#";
            statusBadge = `
                <div class="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 border border-emerald-500/30 text-emerald-400">
                    <i data-lucide="check" class="w-3.5 h-3.5"></i>
                    <span>Sur Strava</span>
                </div>
            `;
            actionBtn = `
                <div class="flex items-center justify-end space-x-2">
                    ${act.strava_activity_id ? `
                    <a href="${stravaUrl}" target="_blank" class="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-strava transition border border-slate-700/80" title="Voir sur Strava">
                        <i data-lucide="external-link" class="w-4 h-4"></i>
                    </a>` : ''}
                    <button onclick="openPushModal('${act.garmin_activity_id}', '${escapeHtml(act.activity_name)}')" class="p-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 transition border border-slate-700/80" title="Re-pousser">
                        <i data-lucide="refresh-cw" class="w-4 h-4"></i>
                    </button>
                </div>
            `;
        } else if (act.status === "uploading") {
            statusBadge = `
                <div class="inline-flex items-center space-x-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-sky-500/15 border border-sky-500/30 text-sky-400">
                    <i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i>
                    <span>Envoi en cours...</span>
                </div>
            `;
            actionBtn = `<span class="text-xs text-slate-500">Traitement...</span>`;
        } else if (act.status === "error") {
            statusBadge = `
                <div class="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-500/15 border border-rose-500/30 text-rose-400" title="${escapeHtml(act.error_message || '')}">
                    <i data-lucide="alert-circle" class="w-3.5 h-3.5"></i>
                    <span>Erreur</span>
                </div>
            `;
            actionBtn = `
                <div class="flex items-center justify-end space-x-2">
                    <button onclick="pushSingleActivity('${act.garmin_activity_id}', this)" class="flex items-center space-x-1.5 px-3 py-1.5 rounded-lg bg-strava hover:bg-strava-hover text-white text-xs font-semibold transition shadow-sm">
                        <i data-lucide="rotate-ccw" class="w-3.5 h-3.5"></i>
                        <span>Réessayer</span>
                    </button>
                    <button onclick="openPushModal('${act.garmin_activity_id}', '${escapeHtml(act.activity_name)}')" class="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 border border-slate-700/80">
                        <i data-lucide="more-vertical" class="w-4 h-4"></i>
                    </button>
                </div>
            `;
        } else {
            // Not synced
            statusBadge = `
                <div class="inline-flex items-center space-x-1 px-2.5 py-1 rounded-full text-xs font-medium bg-slate-800 border border-slate-700 text-slate-400">
                    <i data-lucide="circle-dashed" class="w-3.5 h-3.5"></i>
                    <span>Non envoyé</span>
                </div>
            `;
            actionBtn = `
                <div class="flex items-center justify-end space-x-2">
                    <button onclick="pushSingleActivity('${act.garmin_activity_id}', this)" class="flex items-center space-x-1.5 px-3.5 py-1.5 rounded-xl bg-strava hover:bg-strava-hover text-white text-xs font-semibold transition shadow-sm active:scale-95">
                        <i data-lucide="upload-cloud" class="w-3.5 h-3.5"></i>
                        <span>Push Strava</span>
                    </button>
                    <button onclick="openPushModal('${act.garmin_activity_id}', '${escapeHtml(act.activity_name)}')" class="p-1.5 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-slate-200 transition border border-slate-700/80" title="Options / Modifier distance">
                        <i data-lucide="sliders" class="w-4 h-4"></i>
                    </button>
                </div>
            `;
        }

        return `
            <tr class="hover:bg-slate-800/40 transition group">
                <td class="p-4">
                    <input type="checkbox" ${isChecked ? "checked" : ""} onchange="toggleSelectActivity('${act.garmin_activity_id}', this)" class="w-4 h-4 rounded border-slate-700 text-strava focus:ring-strava bg-slate-800 cursor-pointer">
                </td>
                <td class="p-4">
                    <div class="flex items-center space-x-3">
                        <div class="p-2 rounded-xl border ${sportCfg.color}">
                            <i data-lucide="${sportCfg.icon}" class="w-4 h-4"></i>
                        </div>
                        <div>
                            <p class="text-xs font-semibold text-slate-200">${sportCfg.label}</p>
                            <p class="text-[11px] text-slate-400">${dateFormatted}</p>
                        </div>
                    </div>
                </td>
                <td class="p-4 font-medium text-slate-200 max-w-[200px] truncate" title="${escapeHtml(act.activity_name)}">
                    ${escapeHtml(act.activity_name)}
                    <span class="block text-[11px] font-mono text-slate-500">ID: ${act.garmin_activity_id}</span>
                </td>
                <td class="p-4">
                    <div class="font-semibold text-slate-100">${distDisplay}</div>
                    ${paceDisplay}
                </td>
                <td class="p-4 text-slate-300 font-mono text-xs">${durationFormatted}</td>
                <td class="p-4 text-xs text-slate-400">
                    <div>${elev}</div>
                    <div>${hr}</div>
                </td>
                <td class="p-4">${statusBadge}</td>
                <td class="p-4 text-right">${actionBtn}</td>
            </tr>
        `;
    }).join("");

    lucide.createIcons();
}

// --- Push Actions ---

async function pushSingleActivity(activityId, btnEl) {
    if (btnEl) {
        btnEl.disabled = true;
        btnEl.innerHTML = `<i data-lucide="loader-2" class="w-3.5 h-3.5 animate-spin"></i><span>Envoi...</span>`;
        lucide.createIcons();
    }

    try {
        const resp = await fetch(`/api/push/${activityId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({})
        });

        const result = await resp.json();
        if (!resp.ok) {
            throw new Error(result.detail || "Échec de l'envoi");
        }

        showToast("Activité envoyée avec succès sur Strava !", "success");
        checkAppStatus();
        loadActivities();
    } catch (err) {
        showToast("Erreur lors de l'envoi vers Strava: " + err.message, "error");
        loadActivities();
    }
}

function openPushModal(activityId, currentName) {
    const modal = document.getElementById("push-modal");
    const act = activitiesData.find(a => a.garmin_activity_id === activityId);

    document.getElementById("modal-activity-id").value = activityId;
    document.getElementById("modal-activity-name").value = currentName || (act ? act.activity_name : "");
    document.getElementById("modal-activity-desc").value = "";
    document.getElementById("modal-is-commute").checked = false;
    document.getElementById("modal-is-trainer").checked = false;

    const distInput = document.getElementById("modal-activity-distance");
    const uploadModeSelect = document.getElementById("modal-upload-mode");
    const swimHint = document.getElementById("modal-swim-hint");

    const sportKey = act ? (act.sport_type_key || act.activity_type || "").toLowerCase() : "";
    const isSwim = sportKey.includes("swim") || sportKey.includes("natation");

    if (distInput) {
        distInput.value = (act && act.distance_meters > 0) ? Math.round(act.distance_meters) : "";
    }

    if (uploadModeSelect) {
        uploadModeSelect.value = isSwim ? "manual" : "auto";
    }

    if (swimHint) {
        if (isSwim) {
            swimHint.classList.remove("hidden");
        } else {
            swimHint.classList.add("hidden");
        }
    }

    if (modal) modal.classList.remove("hidden");
    lucide.createIcons();
}

function closePushModal() {
    const modal = document.getElementById("push-modal");
    if (modal) modal.classList.add("hidden");
}

async function submitCustomPush(e) {
    e.preventDefault();
    const activityId = document.getElementById("modal-activity-id").value;
    const name = document.getElementById("modal-activity-name").value;
    const desc = document.getElementById("modal-activity-desc").value;
    const distVal = document.getElementById("modal-activity-distance").value;
    const uploadMode = document.getElementById("modal-upload-mode").value;
    const isCommute = document.getElementById("modal-is-commute").checked ? 1 : 0;
    const isTrainer = document.getElementById("modal-is-trainer").checked ? 1 : 0;

    const customDist = distVal ? parseFloat(distVal) : null;

    const btn = document.getElementById("modal-submit-btn");
    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Envoi en cours...</span>`;
    lucide.createIcons();

    try {
        const resp = await fetch(`/api/push/${activityId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                custom_name: name,
                custom_description: desc,
                custom_distance: customDist,
                upload_mode: uploadMode,
                commute: isCommute,
                trainer: isTrainer
            })
        });

        const result = await resp.json();
        if (!resp.ok) throw new Error(result.detail || "Erreur de transmission");

        showToast(result.message || "Activité poussée sur Strava avec succès !", "success");
        closePushModal();
        checkAppStatus();
        loadActivities();
    } catch (err) {
        showToast("Erreur : " + err.message, "error");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<i data-lucide="upload-cloud" class="w-4 h-4"></i><span>Pousser sur Strava</span>`;
        lucide.createIcons();
    }
}

// --- Garmin Sync ---

async function triggerGarminSync() {
    const btn = document.getElementById("btn-sync-garmin");
    const icon = document.getElementById("sync-icon");

    if (btn) btn.disabled = true;
    if (icon) icon.classList.add("animate-spin");

    try {
        const resp = await fetch("/api/garmin/sync?limit=50", { method: "POST" });
        const result = await resp.json();

        if (!resp.ok) throw new Error(result.detail || "Échec de la synchronisation");

        showToast(result.message || "Synchronisation Garmin terminée !", "success");
        checkAppStatus();
        loadActivities();
    } catch (err) {
        showToast("Erreur synchronisation Garmin: " + err.message, "error");
    } finally {
        if (btn) btn.disabled = false;
        if (icon) icon.classList.remove("animate-spin");
    }
}

// --- Batch Selection & Push ---

function toggleSelectActivity(activityId, checkbox) {
    if (checkbox.checked) {
        selectedActivityIds.add(activityId);
    } else {
        selectedActivityIds.delete(activityId);
    }
    updateBatchUI();
}

function toggleSelectAll(masterCheckbox) {
    if (masterCheckbox.checked) {
        activitiesData.forEach(a => selectedActivityIds.add(a.garmin_activity_id));
    } else {
        selectedActivityIds.clear();
    }
    renderActivitiesTable(activitiesData);
    updateBatchUI();
}

function updateBatchUI() {
    const batchBtn = document.getElementById("btn-batch-push");
    const countEl = document.getElementById("selected-count");
    if (!batchBtn || !countEl) return;

    countEl.textContent = selectedActivityIds.size;
    if (selectedActivityIds.size > 0) {
        batchBtn.classList.remove("hidden");
    } else {
        batchBtn.classList.add("hidden");
    }
}

async function pushSelectedActivities() {
    if (selectedActivityIds.size === 0) return;

    const ids = Array.from(selectedActivityIds);
    const batchBtn = document.getElementById("btn-batch-push");
    batchBtn.disabled = true;
    batchBtn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Envoi de ${ids.length} activités...</span>`;
    lucide.createIcons();

    try {
        const resp = await fetch("/api/push-batch", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ activity_ids: ids })
        });
        const result = await resp.json();

        if (!resp.ok) throw new Error(result.detail || "Erreur de traitement par lot");

        showToast(`${result.successful} / ${result.total} activités envoyées sur Strava !`, "success");
        selectedActivityIds.clear();
        updateBatchUI();
        checkAppStatus();
        loadActivities();
    } catch (err) {
        showToast("Erreur lors de l'envoi groupé: " + err.message, "error");
    } finally {
        batchBtn.disabled = false;
        batchBtn.innerHTML = `<i data-lucide="upload-cloud" class="w-4 h-4"></i><span>Envoyer la sélection (<span id="selected-count">0</span>)</span>`;
        lucide.createIcons();
    }
}

// --- Garmin Login Modal ---

function openGarminLoginModal() {
    const modal = document.getElementById("garmin-login-modal");
    if (modal) modal.classList.remove("hidden");
}

function closeGarminLoginModal() {
    const modal = document.getElementById("garmin-login-modal");
    if (modal) modal.classList.add("hidden");
}

async function submitGarminLogin(e) {
    e.preventDefault();
    const email = document.getElementById("login-garmin-email").value;
    const password = document.getElementById("login-garmin-password").value;
    const btn = document.getElementById("login-garmin-btn");

    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Connexion...</span>`;
    lucide.createIcons();

    try {
        const resp = await fetch("/api/garmin/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password })
        });
        const result = await resp.json();

        if (!resp.ok) throw new Error(result.detail || "Identifiants invalides");

        showToast("Connexion à Garmin Connect réussie !", "success");
        closeGarminLoginModal();
        checkAppStatus();
        loadActivities();
    } catch (err) {
        showToast("Erreur Garmin: " + err.message, "error");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<span>Se connecter</span>`;
    }
}

// --- Settings Page JS ---

async function initSettingsPage() {
    try {
        const resp = await fetch("/api/status");
        const data = await resp.json();

        // Garmin section
        const gStatus = document.getElementById("garmin-settings-status");
        const gForm = document.getElementById("garmin-settings-form");
        const gLoggedIn = document.getElementById("garmin-logged-in-view");
        const gEmailDisplay = document.getElementById("garmin-connected-email");

        if (data.garmin.connected) {
            gStatus.textContent = "Connecté";
            gStatus.className = "px-3.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 border border-emerald-500/30 text-emerald-400";
            gForm.classList.add("hidden");
            gLoggedIn.classList.remove("hidden");
            gEmailDisplay.textContent = data.garmin.email || "Compte actif";
        } else {
            gStatus.textContent = "Non connecté";
            gStatus.className = "px-3.5 py-1 rounded-full text-xs font-semibold bg-slate-800 border border-slate-700 text-slate-400";
            gForm.classList.remove("hidden");
            gLoggedIn.classList.add("hidden");
        }

        // Strava section
        const sStatus = document.getElementById("strava-settings-status");
        const sConnectedView = document.getElementById("strava-connected-view");
        const sDisconnectBtn = document.getElementById("btn-strava-disconnect");
        const sOAuthBtn = document.getElementById("btn-strava-oauth");
        const sAthleteDisplay = document.getElementById("strava-athlete-name-display");

        if (data.strava.connected) {
            sStatus.textContent = "Connecté";
            sStatus.className = "px-3.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/15 border border-emerald-500/30 text-emerald-400";
            if (sConnectedView) sConnectedView.classList.remove("hidden");
            if (sDisconnectBtn) sDisconnectBtn.classList.remove("hidden");
            if (sOAuthBtn) sOAuthBtn.classList.add("hidden");
            if (sAthleteDisplay) sAthleteDisplay.textContent = `Athlète : ${data.strava.athlete_name || 'Inconnu'}`;
        } else {
            sStatus.textContent = "Non connecté";
            sStatus.className = "px-3.5 py-1 rounded-full text-xs font-semibold bg-slate-800 border border-slate-700 text-slate-400";
            if (sConnectedView) sConnectedView.classList.add("hidden");
            if (sDisconnectBtn) sDisconnectBtn.classList.add("hidden");
            if (sOAuthBtn) sOAuthBtn.classList.remove("hidden");
        }

        lucide.createIcons();
    } catch (err) {
        console.error("Failed to load settings data:", err);
    }
}

async function handleGarminSettingsLogin(e) {
    e.preventDefault();
    const email = document.getElementById("settings-garmin-email").value;
    const password = document.getElementById("settings-garmin-password").value;
    const btn = document.getElementById("btn-save-garmin");

    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i><span>Connexion...</span>`;
    lucide.createIcons();

    try {
        const resp = await fetch("/api/garmin/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password })
        });
        const res = await resp.json();
        if (!resp.ok) throw new Error(res.detail || "Erreur de connexion");

        showToast("Connecté à Garmin Connect !", "success");
        initSettingsPage();
    } catch (err) {
        showToast("Erreur: " + err.message, "error");
    } finally {
        btn.disabled = false;
        btn.innerHTML = `<span>Se connecter à Garmin</span>`;
    }
}

async function handleGarminLogout() {
    if (!confirm("Voulez-vous vraiment vous déconnecter de Garmin Connect ?")) return;

    try {
        await fetch("/api/garmin/logout", { method: "POST" });
        showToast("Déconnecté de Garmin Connect.", "info");
        initSettingsPage();
    } catch (err) {
        showToast("Erreur: " + err.message, "error");
    }
}

async function handleStravaOAuthConnect() {
    try {
        const resp = await fetch("/api/strava/auth-url");
        const data = await resp.json();
        if (!resp.ok) throw new Error(data.detail || "Impossible d'obtenir l'URL d'autorisation");

        // Redirect to Strava OAuth authorization
        window.location.href = data.url;
    } catch (err) {
        showToast("Erreur OAuth Strava: " + err.message, "error");
    }
}

async function handleStravaDisconnect() {
    if (!confirm("Voulez-vous vraiment déconnecter votre compte Strava ?")) return;

    try {
        await fetch("/api/strava/disconnect", { method: "POST" });
        showToast("Compte Strava déconnecté.", "info");
        initSettingsPage();
    } catch (err) {
        showToast("Erreur: " + err.message, "error");
    }
}

// --- Helpers & UI ---

function formatDate(isoStr) {
    if (!isoStr) return "-";
    try {
        const d = new Date(isoStr);
        return d.toLocaleDateString("fr-FR", {
            day: "2-digit",
            month: "short",
            year: "numeric",
            hour: "2-digit",
            minute: "2-digit"
        });
    } catch {
        return isoStr;
    }
}

function formatDuration(seconds) {
    if (!seconds || seconds <= 0) return "-";
    const hrs = Math.floor(seconds / 3600);
    const mins = Math.floor((seconds % 3600) / 60);
    const secs = Math.floor(seconds % 60);

    if (hrs > 0) {
        return `${hrs}h ${mins.toString().padStart(2, "0")}m ${secs.toString().padStart(2, "0")}s`;
    }
    return `${mins}m ${secs.toString().padStart(2, "0")}s`;
}

function escapeHtml(str) {
    if (!str) return "";
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    if (!container) return;

    const toast = document.createElement("div");
    toast.className = `toast p-4 rounded-xl shadow-xl flex items-center space-x-3 text-sm border backdrop-blur transition ${
        type === "success" ? "bg-emerald-950/90 border-emerald-500/30 text-emerald-200" :
        type === "error" ? "bg-rose-950/90 border-rose-500/30 text-rose-200" :
        "bg-slate-900/90 border-slate-700 text-slate-200"
    }`;

    const iconName = type === "success" ? "check-circle-2" : type === "error" ? "alert-circle" : "info";
    toast.innerHTML = `
        <i data-lucide="${iconName}" class="w-5 h-5 flex-shrink-0"></i>
        <span class="flex-1">${escapeHtml(message)}</span>
        <button onclick="this.parentElement.remove()" class="text-slate-400 hover:text-slate-200 ml-2">
            <i data-lucide="x" class="w-4 h-4"></i>
        </button>
    `;

    container.appendChild(toast);
    lucide.createIcons();

    setTimeout(() => {
        if (toast.parentElement) {
            toast.style.opacity = "0";
            setTimeout(() => toast.remove(), 300);
        }
    }, 4500);
}

// --- User Authentication Handlers ---

async function handleLogout() {
    try {
        await fetch("/api/auth/logout", { method: "POST" });
        showToast("Déconnexion réussie.", "info");
        setTimeout(() => {
            window.location.href = "/login";
        }, 300);
    } catch (err) {
        window.location.href = "/login";
    }
}

