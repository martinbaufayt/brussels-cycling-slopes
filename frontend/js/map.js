/**
 * map.js — Logique de la carte Leaflet
 * --------------------------------------
 * Responsabilités :
 *   1. Initialiser la carte avec la basemap UrbIS 2024
 *   2. Charger les pentes depuis l'API FastAPI (GeoJSON)
 *   3. Colorier les segments selon leur difficulté
 *   4. Gérer les popups au clic sur un segment
 *   5. Synchroniser avec le widget checklist
 */

// ── Configuration ─────────────────────────────────────────────────────────────

const API_URL = "http://localhost:8000";

// Couleurs par classe de difficulté — cohérentes avec style.css
const DIFFICULTY_COLORS = {
    leger:          "#4CAF50",   // vert
    modere:         "#FFC107",   // jaune-orange
    difficile:      "#FF5722",   // orange-rouge
    tres_difficile: "#B71C1C",   // rouge foncé
};

// Épaisseur de ligne par difficulté (les pentes plus dures sont plus visibles)
const DIFFICULTY_WEIGHT = {
    leger:          2,
    modere:         3,
    difficile:      4,
    tres_difficile: 5,
};

// ── État de l'application ──────────────────────────────────────────────────────
let slopesLayer   = null;    // couche GeoJSON interactive (API FastAPI)
let checkedSlopes = new Set(); // IDs des pentes cochées (mis à jour depuis l'API)
let currentFilter = "all";   // filtre actif

// ── 1. Initialisation de la carte ─────────────────────────────────────────────
//
// L.map("map") crée une carte dans l'élément HTML id="map"
// setView([lat, lng], zoom) centre la carte sur Bruxelles, zoom 13
// layers:[] — on n'ajoute aucune couche par défaut, on le fait manuellement
// pour pouvoir les passer au contrôle de couches ensuite.

const map = L.map("map", {
    center: [50.846, 4.352],
    zoom: 13,
    zoomControl: true,
    layers: [],
});

// ── 2. Couches de base (basemaps) ─────────────────────────────────────────────
//
// On définit deux basemaps que l'utilisateur pourra alterner via le contrôle
// de couches Leaflet (L.control.layers).
//
// UrbIS WMTS : photo aérienne 2024, service officiel Bruxelles (CC-0)
// OSM        : carte schématique, utile pour identifier les rues

const urbisLayer = L.tileLayer(
    "https://geoservices-grid.irisnet.be/geowebcache/service/wmts" +
    "?service=wmts&request=GetTile&version=1.0.0" +
    "&layer=Ortho2024NS&format=image/jpeg" +
    "&tilematrixset=EPSG:900913" +
    "&tilematrix=EPSG:900913:{z}&tilerow={y}&tilecol={x}",
    {
        attribution: '© <a href="https://bric.brussels" target="_blank">UrbIS – Bruxelles-Capitale</a> (CC-0)',
        maxZoom: 21,
    }
);

// CartoDB Positron : fond de carte neutre gris clair, libre et sans API key.
// Contrairement aux tuiles OSM officielles, CartoDB n'exige pas de header Referer —
// ce qui le rend compatible avec une ouverture locale (file://).
// Les données restent © OpenStreetMap contributors.
const osmLayer = L.tileLayer(
    "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    {
        attribution: '© <a href="https://carto.com/">CARTO</a> · © <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        subdomains: "abcd",
        maxZoom: 20,
    }
);

// UrbIS est la basemap par défaut
urbisLayer.addTo(map);

// ── 3. Couche WMS GeoServer ───────────────────────────────────────────────────
//
// L.tileLayer.wms() est le plugin Leaflet natif pour les couches WMS.
// Contrairement au GeoJSON chargé depuis l'API, le WMS :
//   - est rendu côté SERVEUR (GeoServer applique le style SLD)
//   - retourne des images PNG, pas des données vectorielles
//   - est très rapide à tous les niveaux de zoom
//   - n'est PAS cliquable (pas d'accès aux attributs)
//
// C'est complémentaire : WMS pour la vue d'ensemble, GeoJSON pour l'interaction.
//
// Paramètres WMS importants :
//   layers      → nom de la couche dans GeoServer (workspace:nom)
//   styles      → style SLD à utiliser (vide = style par défaut)
//   format      → format d'image retourné
//   transparent → fond transparent pour superposer sur la basemap
//   version     → version du protocole WMS

const wmsLayer = L.tileLayer.wms(
    "http://localhost:8080/geoserver/cycling_brussels/wms",
    {
        layers:      "cycling_brussels:slopes",
        styles:      "slopes_style",
        format:      "image/png",
        transparent: true,
        version:     "1.1.1",
        opacity:     0.85,
        attribution: "GeoServer – pentes cyclables",
    }
);

// Couche WFS légère via GeoServer pour le réseau cyclable complet
// On utilise le WMS (pas le WFS) pour l'affichage — plus performant
const roadsWmsLayer = L.tileLayer.wms(
    "http://localhost:8080/geoserver/cycling_brussels/wms",
    {
        layers:      "cycling_brussels:cycling_roads",
        format:      "image/png",
        transparent: true,
        version:     "1.1.1",
        opacity:     0.5,
        attribution: "GeoServer – réseau cyclable OSM",
    }
);

// ── 4. Contrôle de couches Leaflet ────────────────────────────────────────────
//
// L.control.layers(basemaps, overlays) ajoute un widget en haut à droite
// permettant de basculer entre les couches de base et d'activer/désactiver
// les couches superposées.
//
// basemaps  → boutons radio (une seule couche active à la fois)
// overlays  → cases à cocher (plusieurs couches actives simultanément)

const baseMaps = {
    "Photo aérienne UrbIS 2024": urbisLayer,
    "CartoDB Positron":          osmLayer,
};

const overlayMaps = {
    "Pentes WMS (GeoServer)":        wmsLayer,
    "Réseau cyclable complet (WMS)": roadsWmsLayer,
};

// Le contrôle de couches est stocké pour qu'on puisse y ajouter
// la couche GeoJSON interactive après son chargement asynchrone.
const layerControl = L.control.layers(baseMaps, overlayMaps, {
    position:  "topright",
    collapsed: false,
}).addTo(map);

// ── 5. Chargement des pentes depuis l'API ─────────────────────────────────────
//
// fetch() est l'API moderne du navigateur pour faire des requêtes HTTP.
// Elle retourne une Promise — une valeur qui arrivera plus tard (asynchrone).
// async/await simplifie l'écriture des Promises.

async function loadSlopes(difficulty = null) {
    document.getElementById("loader").style.display = "block";

    // "léger" = 2–4% : on ne peut pas appliquer min_slope=4 sinon tout est exclu.
    // Pour les autres difficultés (≥ 4%), min_slope=4 correspond à la réalité.
    // min_slope=2 pour inclure les segments "léger" (2–4%) dans tous les cas
    const minSlope = 2;

    let url = `${API_URL}/slopes/geojson?min_slope=${minSlope}&max_slope=25&min_length=30`;
    if (difficulty && difficulty !== "all") {
        url += `&difficulty=${difficulty}`;
    }

    try {
        const response = await fetch(url);
        const geojson  = await response.json();

        if (slopesLayer === null) {
            // Premier chargement : créer la couche et l'enregistrer dans le contrôle.
            // On garde le même objet layer pour toute la session — le contrôle de couches
            // conserve cette référence et peut ainsi activer/désactiver correctement.
            slopesLayer = L.geoJSON(geojson, {
                style: (feature) => styleSlope(feature),
                onEachFeature: (feature, layer) => bindPopup(feature, layer),
            }).addTo(map);
            layerControl.addOverlay(slopesLayer, "Pentes interactives (API)");
        } else {
            // Rechargement (changement de filtre) : on réutilise le même objet layer.
            // clearLayers() vide la couche sans la retirer de la carte ni du contrôle.
            // addData() recharge les nouvelles features — style et onEachFeature
            // sont réappliqués automatiquement car ils sont stockés dans l'objet layer.
            slopesLayer.clearLayers();
            slopesLayer.addData(geojson);
        }

        document.getElementById("loader").style.display = "none";
        console.log(`${geojson.features.length} segments chargés`);

    } catch (err) {
        console.error("Erreur chargement pentes :", err);
        document.getElementById("loader").textContent = "Erreur : API inaccessible";
    }
}

// ── 4. Style des segments ──────────────────────────────────────────────────────
//
// Chaque segment reçoit une couleur et une épaisseur selon sa difficulté.
// Les pentes cochées dans la checklist sont affichées en blanc/tirets.

function styleSlope(feature) {
    const diff    = feature.properties.difficulty;
    const isChecked = checkedSlopes.has(feature.properties.id);

    return {
        color:     isChecked ? "#ffffff" : (DIFFICULTY_COLORS[diff] || "#888"),
        weight:    DIFFICULTY_WEIGHT[diff] || 3,
        opacity:   isChecked ? 0.5 : 0.85,
        dashArray: isChecked ? "6, 6" : null,  // tirets si déjà fait
    };
}

// ── 5. Popup au clic sur un segment ───────────────────────────────────────────
//
// Quand l'utilisateur clique sur un segment, on affiche une popup avec :
//   - Le nom de la rue
//   - La pente%, le dénivelé, la longueur
//   - Un bouton pour cocher/décocher dans la checklist

function bindPopup(feature, layer) {
    const p = feature.properties;

    layer.on("click", async () => {
        const isDone = checkedSlopes.has(p.id);

        // Formatter le nom : si vide, afficher le type de voie
        const name = p.road_name || `[${p.highway}]`;

        // Badge de difficulté lisible
        const diffLabels = {
            leger: "Léger", modere: "Modéré",
            difficile: "Difficile", tres_difficile: "Très difficile"
        };

        const content = `
            <div class="popup-content">
                <h3>${name}</h3>
                <table>
                    <tr><td>Pente</td><td><b>${p.slope_pct}%</b></td></tr>
                    <tr><td>Difficulté</td><td>${diffLabels[p.difficulty] || p.difficulty}</td></tr>
                    <tr><td>Dénivelé</td><td>${p.elevation_diff > 0 ? "+" : ""}${p.elevation_diff} m</td></tr>
                    <tr><td>Longueur</td><td>${p.length_m} m</td></tr>
                    <tr><td>Direction</td><td>${p.direction}</td></tr>
                    <tr><td>Surface</td><td>${p.surface || "—"}</td></tr>
                </table>
                <button
                    class="popup-btn ${isDone ? "done" : ""}"
                    onclick="toggleChecklist(${p.id}, this)"
                >
                    ${isDone ? "✓ Déjà fait — Décocher" : "Marquer comme fait"}
                </button>
            </div>
        `;

        layer.bindPopup(content, { maxWidth: 260 }).openPopup();
    });
}

// ── 6. Checklist : cocher / décocher ──────────────────────────────────────────
//
// Appelé depuis le bouton dans la popup ET depuis le widget sidebar.
// Fait un POST ou DELETE vers l'API, puis met à jour l'affichage.

async function toggleChecklist(slopeId, btn) {
    const isDone = checkedSlopes.has(slopeId);

    try {
        if (isDone) {
            // Décocher : DELETE /checklist/{id}
            await fetch(`${API_URL}/checklist/${slopeId}`, { method: "DELETE" });
            checkedSlopes.delete(slopeId);
        } else {
            // Cocher : POST /checklist/{id}
            await fetch(`${API_URL}/checklist/${slopeId}`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ note: null }),
            });
            checkedSlopes.add(slopeId);
        }

        // Mettre à jour le style du segment sur la carte
        if (slopesLayer) {
            slopesLayer.eachLayer((layer) => {
                if (layer.feature?.properties?.id === slopeId) {
                    layer.setStyle(styleSlope(layer.feature));
                }
            });
        }

        // Mettre à jour le bouton dans la popup
        if (btn) {
            const nowDone = checkedSlopes.has(slopeId);
            btn.textContent = nowDone ? "✓ Déjà fait — Décocher" : "Marquer comme fait";
            btn.className   = `popup-btn ${nowDone ? "done" : ""}`;
        }

        // Rafraîchir la checklist dans la sidebar
        await loadChecklist();

    } catch (err) {
        console.error("Erreur checklist :", err);
    }
}

// ── 7. Chargement de la checklist (sidebar) ────────────────────────────────────
//
// Récupère les pentes cochées depuis l'API et peuple le widget sidebar.

async function loadChecklist() {
    const res  = await fetch(`${API_URL}/checklist`);
    const data = await res.json();

    // Mettre à jour le Set d'IDs cochés (pour le style carte)
    checkedSlopes = new Set(data.entries.map(e => e.slope_id));

    // Afficher le compteur
    document.getElementById("checklist-count").textContent = data.count;

    // Remplir la liste
    const list = document.getElementById("checklist-list");
    list.innerHTML = "";

    if (data.entries.length === 0) {
        list.innerHTML = `<p style="padding:16px;color:#888;font-size:12px;">
            Clique sur un segment de la carte pour marquer une pente comme faite.
        </p>`;
        return;
    }

    data.entries.forEach(entry => {
        const item = document.createElement("div");
        item.className = "checklist-item";

        const name = entry.road_name || "[sans nom]";
        const diffLabel = {
            leger: "Léger", modere: "Modéré",
            difficile: "Difficile", tres_difficile: "Très difficile"
        }[entry.difficulty] || entry.difficulty;

        item.innerHTML = `
            <input type="checkbox" checked onchange="toggleChecklist(${entry.slope_id}, null)">
            <div class="item-info">
                <div class="item-name">${name}</div>
                <div class="item-meta">${entry.slope_pct}% · ${entry.slope_direction}</div>
            </div>
            <span class="difficulty-badge badge-${entry.difficulty}">${diffLabel}</span>
        `;

        list.appendChild(item);
    });
}

// ── 8. Filtres de difficulté ───────────────────────────────────────────────────
//
// Les boutons dans la sidebar filtrent les segments affichés sur la carte.

function setFilter(difficulty) {
    currentFilter = difficulty;

    // Mettre à jour le style des boutons
    document.querySelectorAll(".filter-btn").forEach(btn => {
        btn.classList.toggle("active", btn.dataset.difficulty === difficulty);
    });

    // Recharger les pentes avec le nouveau filtre
    loadSlopes(difficulty === "all" ? null : difficulty);
}

// ── Démarrage ──────────────────────────────────────────────────────────────────

// Charger toutes les pentes intéressantes au démarrage
loadSlopes();

// Charger la checklist
loadChecklist();
