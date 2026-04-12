// ===== SafeSite AI — Main JavaScript =====

let isMonitoring = false;
let isDrawingZone = false;
let currentZonePoints = [];
let detectionActive = true;
let voiceEnabled = true;
let pollInterval = null;

const videoFeed = document.getElementById('videoFeed');
const noFeedOverlay = document.getElementById('noFeedOverlay');
const zoneCanvas = document.getElementById('zoneCanvas');
const ctx = zoneCanvas ? zoneCanvas.getContext('2d') : null;

// ===== Video Controls =====

function startMonitoring() {
    const sourceSelect = document.getElementById('videoSource');
    const source = sourceSelect.value;

    fetch('/api/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: source })
    })
    .then(res => {
        if (!res.ok) return res.json().then(d => { throw new Error(d.error); });
        return res.json();
    })
    .then(data => {
        isMonitoring = true;
        videoFeed.src = '/video_feed?' + Date.now();
        noFeedOverlay.classList.add('hidden');
        startPolling();
    })
    .catch(err => alert('Error: ' + err.message));
}

function uploadVideo(input) {
    const file = input.files[0];
    if (!file) return;

    const status = document.getElementById('uploadStatus');
    status.style.display = 'block';
    status.className = 'status-message status-info';
    status.textContent = `Uploading ${file.name}...`;

    const formData = new FormData();
    formData.append('video', file);

    fetch('/api/upload_video', { method: 'POST', body: formData })
    .then(res => {
        if (!res.ok) return res.json().then(d => { throw new Error(d.error); });
        return res.json();
    })
    .then(data => {
        status.className = 'status-message status-success';
        status.textContent = `Uploaded: ${data.filename}`;
        setTimeout(() => { status.style.display = 'none'; }, 3000);
        loadVideoList();
        input.value = '';
    })
    .catch(err => {
        status.className = 'status-message status-error';
        status.textContent = 'Upload failed: ' + err.message;
    });
}

function loadVideoList() {
    fetch('/api/videos')
    .then(res => res.json())
    .then(data => {
        const select = document.getElementById('videoSource');
        // Remove old video options but keep Webcam
        Array.from(select.options).forEach(opt => {
            if (opt.value !== '0') opt.remove();
        });
        data.videos.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v.filename;
            opt.textContent = `${v.filename} (${v.size_mb} MB)`;
            select.appendChild(opt);
        });
    });
}

function stopMonitoring() {
    fetch('/api/stop', { method: 'POST' })
    .then(res => res.json())
    .then(data => {
        isMonitoring = false;
        videoFeed.src = '';
        noFeedOverlay.classList.remove('hidden');
        stopPolling();
    });
}

function toggleDetection() {
    fetch('/api/toggle_detection', { method: 'POST' })
    .then(res => res.json())
    .then(data => {
        detectionActive = data.detection_active;
        const btn = document.getElementById('btnToggleDetection');
        btn.textContent = `Detection: ${detectionActive ? 'ON' : 'OFF'}`;
        btn.className = `btn ${detectionActive ? 'btn-secondary' : 'btn-danger'}`;
    });
}

function toggleVoice() {
    fetch('/api/toggle_voice', { method: 'POST' })
    .then(res => res.json())
    .then(data => {
        voiceEnabled = data.voice_enabled;
        const btn = document.getElementById('btnToggleVoice');
        btn.textContent = `Voice: ${voiceEnabled ? 'ON' : 'OFF'}`;
        btn.className = `btn ${voiceEnabled ? 'btn-secondary' : 'btn-danger'}`;
    });
}

// ===== Zone Drawing =====

function initCanvas() {
    if (!zoneCanvas || !videoFeed) return;

    const resizeCanvas = () => {
        const container = document.getElementById('videoContainer');
        zoneCanvas.width = container.clientWidth;
        zoneCanvas.height = container.clientHeight;
        drawExistingZones();
    };

    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);

    zoneCanvas.addEventListener('click', function(e) {
        if (!isDrawingZone) return;

        const rect = zoneCanvas.getBoundingClientRect();
        const scaleX = zoneCanvas.width / rect.width;
        const scaleY = zoneCanvas.height / rect.height;
        const x = (e.clientX - rect.left) * scaleX;
        const y = (e.clientY - rect.top) * scaleY;

        currentZonePoints.push([Math.round(x), Math.round(y)]);
        drawCurrentZone();
    });

    // Load existing zones
    loadZones();
}

function drawExistingZones() {
    if (!ctx) return;
    ctx.clearRect(0, 0, zoneCanvas.width, zoneCanvas.height);

    // Draw saved zones
    if (typeof zones !== 'undefined') {
        zones.forEach(zone => {
            if (zone.points.length < 3) return;
            ctx.beginPath();
            ctx.moveTo(zone.points[0][0], zone.points[0][1]);
            zone.points.forEach(p => ctx.lineTo(p[0], p[1]));
            ctx.closePath();
            ctx.fillStyle = zone.color + '33'; // semi-transparent
            ctx.fill();
            ctx.strokeStyle = zone.color;
            ctx.lineWidth = 2;
            ctx.stroke();

            // Label
            const cx = zone.points.reduce((s, p) => s + p[0], 0) / zone.points.length;
            const cy = zone.points.reduce((s, p) => s + p[1], 0) / zone.points.length;
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 14px Segoe UI';
            ctx.textAlign = 'center';
            ctx.fillText(zone.name, cx, cy);
        });
    }

    // Draw current in-progress zone
    drawCurrentZone();
}

function drawCurrentZone() {
    if (!ctx || currentZonePoints.length === 0) return;

    // Redraw all first
    drawExistingZones_only();

    const color = document.getElementById('zoneColor').value;

    // Draw points
    currentZonePoints.forEach((p, i) => {
        ctx.beginPath();
        ctx.arc(p[0], p[1], 5, 0, Math.PI * 2);
        ctx.fillStyle = color;
        ctx.fill();

        // Number the point
        ctx.fillStyle = '#fff';
        ctx.font = 'bold 11px Segoe UI';
        ctx.textAlign = 'center';
        ctx.fillText(String(i + 1), p[0], p[1] - 10);
    });

    // Draw lines
    if (currentZonePoints.length > 1) {
        ctx.beginPath();
        ctx.moveTo(currentZonePoints[0][0], currentZonePoints[0][1]);
        currentZonePoints.forEach(p => ctx.lineTo(p[0], p[1]));
        ctx.strokeStyle = color;
        ctx.lineWidth = 2;
        ctx.setLineDash([6, 4]);
        ctx.stroke();
        ctx.setLineDash([]);
    }

    // If 3+ points, show filled preview
    if (currentZonePoints.length >= 3) {
        ctx.beginPath();
        ctx.moveTo(currentZonePoints[0][0], currentZonePoints[0][1]);
        currentZonePoints.forEach(p => ctx.lineTo(p[0], p[1]));
        ctx.closePath();
        ctx.fillStyle = color + '22';
        ctx.fill();
    }
}

function drawExistingZones_only() {
    if (!ctx) return;
    ctx.clearRect(0, 0, zoneCanvas.width, zoneCanvas.height);

    if (typeof zones !== 'undefined') {
        zones.forEach(zone => {
            if (zone.points.length < 3) return;
            ctx.beginPath();
            ctx.moveTo(zone.points[0][0], zone.points[0][1]);
            zone.points.forEach(p => ctx.lineTo(p[0], p[1]));
            ctx.closePath();
            ctx.fillStyle = zone.color + '33';
            ctx.fill();
            ctx.strokeStyle = zone.color;
            ctx.lineWidth = 2;
            ctx.stroke();

            const cx = zone.points.reduce((s, p) => s + p[0], 0) / zone.points.length;
            const cy = zone.points.reduce((s, p) => s + p[1], 0) / zone.points.length;
            ctx.fillStyle = '#fff';
            ctx.font = 'bold 14px Segoe UI';
            ctx.textAlign = 'center';
            ctx.fillText(zone.name, cx, cy);
        });
    }
}

function startDrawingZone() {
    isDrawingZone = true;
    currentZonePoints = [];
    zoneCanvas.classList.add('drawing');
}

function finishZone() {
    if (currentZonePoints.length < 3) {
        alert('A zone requires at least 3 points. Click on the video to add points.');
        return;
    }

    const name = document.getElementById('zoneName').value || `Zone ${zones.length + 1}`;
    const color = document.getElementById('zoneColor').value;

    // Scale points to match actual video resolution (server-side coordinates)
    const videoEl = document.getElementById('videoFeed');
    const container = document.getElementById('videoContainer');
    const scaleX = (videoEl.naturalWidth || 1280) / container.clientWidth;
    const scaleY = (videoEl.naturalHeight || 720) / container.clientHeight;

    const scaledPoints = currentZonePoints.map(p => [
        Math.round(p[0] * scaleX),
        Math.round(p[1] * scaleY)
    ]);

    fetch('/api/zones', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, points: scaledPoints, color })
    })
    .then(res => res.json())
    .then(data => {
        zones.push({ name, points: currentZonePoints, color });
        isDrawingZone = false;
        currentZonePoints = [];
        zoneCanvas.classList.remove('drawing');
        document.getElementById('zoneName').value = '';
        drawExistingZones();
        loadZones();
    });
}

function cancelZone() {
    isDrawingZone = false;
    currentZonePoints = [];
    zoneCanvas.classList.remove('drawing');
    drawExistingZones();
}

function loadZones() {
    fetch('/api/zones')
    .then(res => res.json())
    .then(data => {
        const list = document.getElementById('zoneList');
        if (!list) return;
        list.innerHTML = '';
        data.zones.forEach(z => {
            const tag = document.createElement('div');
            tag.className = 'zone-tag';
            tag.style.background = z.color || '#457B9D';
            tag.innerHTML = `${z.name} <span class="zone-delete" onclick="deleteZone('${z.name}')">&times;</span>`;
            list.appendChild(tag);
        });
    });
}

function deleteZone(name) {
    fetch(`/api/zones/${encodeURIComponent(name)}`, { method: 'DELETE' })
    .then(res => res.json())
    .then(() => {
        // Remove from local array
        const idx = zones.findIndex(z => z.name === name);
        if (idx !== -1) zones.splice(idx, 1);
        drawExistingZones();
        loadZones();
    });
}

// ===== Live Violation Feed Polling =====

function startPolling() {
    pollInterval = setInterval(fetchRecentViolations, 3000);
}

function stopPolling() {
    if (pollInterval) clearInterval(pollInterval);
}

function fetchRecentViolations() {
    fetch('/api/recent_violations')
    .then(res => res.json())
    .then(data => {
        const feed = document.getElementById('violationFeed');
        if (!feed || !data.violations.length) return;

        feed.innerHTML = '';
        data.violations.forEach(v => {
            const item = document.createElement('div');
            item.className = 'violation-item';
            item.innerHTML = `
                <div class="v-type">${v.violation_type}</div>
                <div class="v-time">${v.timestamp}</div>
                ${v.zone_name ? `<div class="v-zone">Zone: ${v.zone_name}</div>` : ''}
            `;
            feed.appendChild(item);
        });

        // Update stats
        updateStats(data.violations);
    })
    .catch(() => {});
}

function updateStats(violations) {
    const total = document.getElementById('statTotal');
    const helmet = document.getElementById('statHelmet');
    const zone = document.getElementById('statZone');

    if (!total) return;

    fetch('/api/stats')
    .then(res => res.json())
    .then(stats => {
        total.textContent = stats.total || 0;
        helmet.textContent = stats.by_type?.['No Helmet'] || 0;
        zone.textContent = stats.by_type?.['Zone Intrusion'] || 0;
    })
    .catch(() => {});
}

// ===== Init =====
document.addEventListener('DOMContentLoaded', () => {
    initCanvas();
    loadVideoList();
});
