// State management
let activitiesData = [];
let selectedActivityIds = new Set();
let filterDebounceTimer = null;

// Sport Icons Mapping (icon only — color comes from typography, not backgrounds)
const SPORT_ICONS = {
    running: { icon: "activity", label: "Course à pied" },
    cycling: { icon: "bike", label: "Cyclisme" },
    road_biking: { icon: "bike", label: "Vélo de route" },
    gravel_cycling: { icon: "bike", label: "Gravel" },
    mountain_biking: { icon: "bike", label: "VTT" },
    hiking: { icon: "mountain", label: "Randonnée" },
    walking: { icon: "footprints", label: "Marche" },
    swimming: { icon: "waves", label: "Natation" },
    fitness_equipment: { icon: "dumbbell", label: "Musculation" },
    strength_training: { icon: "dumbbell", label: "Renforcement" },
    other: { icon: "zap", label: "Autre sport" }
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
                gBadge.textContent = `Garmin · ${data.garmin.email || 'connecté'}`;
                gBadge.className = "text-neutral-500";
                if (gAlert) gAlert.classList.add("hidden");
            } else {
                gBadge.textContent = "Garmin · déconnecté";
                gBadge.className = "text-neutral-400";
                if (gAlert) gAlert.classList.remove("hidden");
            }
        }

        // Update Strava status badge in header
        const sBadge = document.getElementById("strava-status-badge");
        const sAlert = document.getElementById("strava-alert");
        if (sBadge) {
            if (data.strava.connected) {
                sBadge.textContent = `Strava · ${data.strava.athlete_name || 'connecté'}`;
                sBadge.className = "text-neutral-500";
                if (sAlert) sAlert.classList.add("hidden");
            } else {
                sBadge.textContent = "Strava · déconnecté";
                sBadge.className = "text-neutral-400";
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
                    paceDisplay = `<span class="text-[11px] text-neutral-400 font-mono block">${pMin}:${pSec.toString().padStart(2, "0")}/100m</span>`;
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
                <span class="inline-flex items-center gap-1.5 text-xs text-neutral-600">
                    <span class="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                    <span>Sur Strava</span>
                </span>
            `;
            actionBtn = `
                <div class="flex items-center justify-end gap-3">
                    ${act.strava_activity_id ? `
                    <a href="${stravaUrl}" target="_blank" class="text-neutral-400 hover:text-neutral-900 transition" title="Voir sur Strava">
                        <i data-lucide="external-link" class="w-4 h-4"></i>
                    </a>` : ''}
                    <button onclick="openPushModal('${act.garmin_activity_id}', '${escapeHtml(act.activity_name)}')" class="text-neutral-400 hover:text-neutral-900 transition" title="Re-pousser">
                        <i data-lucide="refresh-cw" class="w-4 h-4"></i>
                    </button>
                </div>
            `;
        } else if (act.status === "uploading") {
            statusBadge = `
                <span class="inline-flex items-center gap-1.5 text-xs text-neutral-600">
                    <i data-lucide="loader-2" class="w-3 h-3 animate-spin"></i>
                    <span>Envoi en cours…</span>
                </span>
            `;
            actionBtn = `<span class="text-xs text-neutral-400">Traitement…</span>`;
        } else if (act.status === "error") {
            statusBadge = `
                <span class="inline-flex items-center gap-1.5 text-xs text-rose-600" title="${escapeHtml(act.error_message || '')}">
                    <span class="w-1.5 h-1.5 rounded-full bg-rose-500"></span>
                    <span>Erreur</span>
                </span>
            `;
            actionBtn = `
                <div class="flex items-center justify-end gap-3">
                    <button onclick="pushSingleActivity('${act.garmin_activity_id}', this)" class="text-xs font-medium text-strava hover:underline">
                        Réessayer
                    </button>
                    <button onclick="openPushModal('${act.garmin_activity_id}', '${escapeHtml(act.activity_name)}')" class="text-neutral-400 hover:text-neutral-900 transition" title="Options">
                        <i data-lucide="sliders" class="w-4 h-4"></i>
                    </button>
                </div>
            `;
        } else {
            // Not synced
            statusBadge = `
                <span class="inline-flex items-center gap-1.5 text-xs text-neutral-400">
                    <span class="w-1.5 h-1.5 rounded-full bg-neutral-300"></span>
                    <span>Non envoyé</span>
                </span>
            `;
            actionBtn = `
                <div class="flex items-center justify-end gap-3">
                    <button onclick="pushSingleActivity('${act.garmin_activity_id}', this)" class="text-xs font-medium text-strava hover:underline">
                        Push Strava
                    </button>
                    <button onclick="openPushModal('${act.garmin_activity_id}', '${escapeHtml(act.activity_name)}')" class="text-neutral-400 hover:text-neutral-900 transition" title="Options / Modifier distance">
                        <i data-lucide="sliders" class="w-4 h-4"></i>
                    </button>
                </div>
            `;
        }

        return `
            <tr class="hover:bg-neutral-50 transition">
                <td class="py-3 pl-5 pr-3">
                    <input type="checkbox" ${isChecked ? "checked" : ""} onchange="toggleSelectActivity('${act.garmin_activity_id}', this)" class="w-3.5 h-3.5 rounded-sm border-neutral-300 text-neutral-900 focus:ring-0 cursor-pointer">
                </td>
                <td class="py-3 pr-3">
                    <div class="flex items-center gap-2.5">
                        <i data-lucide="${sportCfg.icon}" class="w-4 h-4 text-neutral-400 flex-shrink-0"></i>
                        <div>
                            <p class="text-sm text-neutral-900">${sportCfg.label}</p>
                            <p class="text-[11px] text-neutral-400">${dateFormatted}</p>
                        </div>
                    </div>
                </td>
                <td class="py-3 pr-3 max-w-[200px] truncate" title="${escapeHtml(act.activity_name)}">
                    <span class="text-neutral-900">${escapeHtml(act.activity_name)}</span>
                    <span class="block text-[11px] font-mono text-neutral-400">ID: ${act.garmin_activity_id}</span>
                </td>
                <td class="py-3 pr-3">
                    <div class="text-neutral-900 tabular-nums">${distDisplay}</div>
                    ${paceDisplay}
                </td>
                <td class="py-3 pr-3 text-neutral-600 font-mono text-xs">${durationFormatted}</td>
                <td class="py-3 pr-3 text-xs text-neutral-500">
                    <div>${elev}</div>
                    <div>${hr}</div>
                </td>
                <td class="py-3 pr-3">${statusBadge}</td>
                <td class="py-3 pr-5 text-right">${actionBtn}</td>
            </tr>
        `;
    }).join("");

    lucide.createIcons();
}

// --- Push Actions ---

async function pushSingleActivity(activityId, btnEl) {
    if (btnEl) {
        btnEl.disabled = true;
        btnEl.textContent = "Envoi…";
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
    btn.textContent = "Envoi en cours…";

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

        showToast(result.message || "Activité poussée sur Strava", "success");
        closePushModal();
        checkAppStatus();
        loadActivities();
    } catch (err) {
        showToast("Erreur : " + err.message, "error");
    } finally {
        btn.disabled = false;
        btn.textContent = "Pousser sur Strava";
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
    batchBtn.textContent = `Envoi de ${ids.length} activités…`;

    try {
        const resp = await fetch("/api/push-batch", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ activity_ids: ids })
        });
        const result = await resp.json();

        if (!resp.ok) throw new Error(result.detail || "Erreur de traitement par lot");

        showToast(`${result.successful} / ${result.total} activités envoyées sur Strava`, "success");
        selectedActivityIds.clear();
        updateBatchUI();
        checkAppStatus();
        loadActivities();
    } catch (err) {
        showToast("Erreur lors de l'envoi groupé: " + err.message, "error");
    } finally {
        batchBtn.disabled = false;
        batchBtn.innerHTML = `<span>Envoyer la sélection (<span id="selected-count">0</span>)</span>`;
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
    btn.textContent = "Connexion…";

    try {
        const resp = await fetch("/api/garmin/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password })
        });
        const result = await resp.json();

        if (!resp.ok) throw new Error(result.detail || "Identifiants invalides");

        showToast("Connexion à Garmin Connect réussie", "success");
        closeGarminLoginModal();
        checkAppStatus();
        loadActivities();
    } catch (err) {
        showToast("Erreur Garmin: " + err.message, "error");
    } finally {
        btn.disabled = false;
        btn.textContent = "Se connecter";
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
            gStatus.className = "text-xs font-medium text-emerald-600";
            gForm.classList.add("hidden");
            gLoggedIn.classList.remove("hidden");
            gEmailDisplay.textContent = data.garmin.email || "Compte actif";
        } else {
            gStatus.textContent = "Non connecté";
            gStatus.className = "text-xs font-medium text-neutral-400";
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
            sStatus.className = "text-xs font-medium text-emerald-600";
            if (sConnectedView) sConnectedView.classList.remove("hidden");
            if (sDisconnectBtn) sDisconnectBtn.classList.remove("hidden");
            if (sOAuthBtn) sOAuthBtn.classList.add("hidden");
            if (sAthleteDisplay) sAthleteDisplay.textContent = `Athlète : ${data.strava.athlete_name || 'Inconnu'}`;
        } else {
            sStatus.textContent = "Non connecté";
            sStatus.className = "text-xs font-medium text-neutral-400";
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
    btn.textContent = "Connexion…";

    try {
        const resp = await fetch("/api/garmin/login", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password })
        });
        const res = await resp.json();
        if (!resp.ok) throw new Error(res.detail || "Erreur de connexion");

        showToast("Connecté à Garmin Connect", "success");
        initSettingsPage();
    } catch (err) {
        showToast("Erreur: " + err.message, "error");
    } finally {
        btn.disabled = false;
        btn.textContent = "Se connecter à Garmin";
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
    toast.className = `toast bg-white border rounded-md shadow-lg px-4 py-3 flex items-center gap-3 text-sm transition ${
        type === "error" ? "border-rose-300 text-rose-700" : "border-neutral-200 text-neutral-800"
    }`;

    toast.innerHTML = `
        <span class="flex-1">${escapeHtml(message)}</span>
        <button onclick="this.parentElement.remove()" class="text-neutral-400 hover:text-neutral-900">
            <i data-lucide="x" class="w-3.5 h-3.5"></i>
        </button>
    `;

    container.appendChild(toast);
    lucide.createIcons();

    setTimeout(() => {
        if (toast.parentElement) {
            toast.style.opacity = "0";
            setTimeout(() => toast.remove(), 200);
        }
    }, 4000);
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

