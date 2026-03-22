document.addEventListener('DOMContentLoaded', () => {
    const videoElement    = document.getElementById('videoElement');
    const captureBtn      = document.getElementById('captureBtn');
    const statusMessage   = document.getElementById('statusMessage');
    const logList         = document.getElementById('logList');
    const logCountBadge   = document.getElementById('logCountBadge');
    const statTotal       = document.getElementById('statTotal');
    const statSession     = document.getElementById('statSession');
    const statDate        = document.getElementById('statDate');
    const navClock        = document.getElementById('navClock');

    let sessionCount = 0;

    // ── Clock ───────────────────────────────────────────
    function updateClock() {
        const now = new Date();
        navClock.textContent = now.toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
        statDate.textContent = now.toLocaleDateString('id-ID', { day: '2-digit', month: 'short', year: 'numeric' });
    }
    updateClock();
    setInterval(updateClock, 1000);

    // ── Load existing logs from CSV ───────────────────────
    function fetchExistingLogs() {
        fetch('/logs')
            .then(r => r.json())
            .then(data => {
                if (!data.success || !data.logs.length) return;

                // Remove empty placeholder
                const emptyEl = logList.querySelector('.log-empty');
                if (emptyEl) emptyEl.remove();

                data.logs.forEach(entry => {
                    const li = document.createElement('li');
                    const nameSpan = document.createElement('span');
                    nameSpan.className   = 'log-name';
                    nameSpan.textContent = `👤 ${entry.name}`;
                    const timeSpan = document.createElement('span');
                    timeSpan.className   = 'log-time';
                    timeSpan.textContent = `🕒 ${entry.datetime}`;
                    li.appendChild(nameSpan);
                    li.appendChild(timeSpan);
                    logList.appendChild(li);
                });

                statTotal.textContent = data.logs.length;
                logCountBadge.textContent = logList.children.length;
            })
            .catch(err => console.warn('Gagal memuat log lama:', err));
    }
    fetchExistingLogs();


    // ── Particles ────────────────────────────────────────
    const particleContainer = document.getElementById('particles');
    function createParticle() {
        const p = document.createElement('div');
        p.className = 'particle';
        const size = Math.random() * 4 + 1;
        const left = Math.random() * 100;
        const duration = Math.random() * 15 + 10;
        const delay = Math.random() * 10;
        p.style.cssText = `
            width: ${size}px;
            height: ${size}px;
            left: ${left}vw;
            bottom: -10px;
            animation-duration: ${duration}s;
            animation-delay: ${delay}s;
            opacity: ${Math.random() * 0.5 + 0.2};
        `;
        particleContainer.appendChild(p);
        setTimeout(() => p.remove(), (duration + delay) * 1000);
    }
    // Spawn particles continuously
    for (let i = 0; i < 22; i++) createParticle();
    setInterval(createParticle, 1200);

    // ── Webcam ────────────────────────────────────────────
    if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
        navigator.mediaDevices.getUserMedia({ video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } } })
            .then(stream => { videoElement.srcObject = stream; })
            .catch(err => {
                console.error('Kamera error:', err);
                showStatus('Gagal mengakses kamera. Pastikan izin sudah diberikan.', 'error');
                captureBtn.disabled = true;
            });
    } else {
        showStatus('Browser Anda tidak mendukung akses kamera.', 'error');
        captureBtn.disabled = true;
    }

    // ── Capture ───────────────────────────────────────────
    captureBtn.addEventListener('click', () => {
        const canvas = document.createElement('canvas');
        canvas.width  = videoElement.videoWidth;
        canvas.height = videoElement.videoHeight;
        const ctx = canvas.getContext('2d');

        // Mirror-flip to compensate for CSS scaleX(-1)
        ctx.scale(-1, 1);
        ctx.drawImage(videoElement, -canvas.width, 0, canvas.width, canvas.height);

        const dataURL = canvas.toDataURL('image/jpeg', 0.85);

        showStatus('⏳ Menganalisis wajah...', 'loading');
        captureBtn.disabled = true;

        fetch('/recognize', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image: dataURL })
        })
        .then(r => r.json())
        .then(data => {
            captureBtn.disabled = false;
            if (data.success) {
                showStatus(`✅ ${data.message}`, 'success');
                addLogItem(data.name, data.datetime);
                sessionCount++;
                statSession.textContent = sessionCount;
                // Increment total (best-effort, local counter)
                statTotal.textContent = parseInt(statTotal.textContent || '0') + 1;
            } else {
                showStatus(`❌ ${data.message}`, 'error');
            }
        })
        .catch(err => {
            console.error(err);
            captureBtn.disabled = false;
            showStatus('❌ Terjadi kesalahan pada server.', 'error');
        });
    });

    // ── Status helper ─────────────────────────────────────
    function showStatus(message, type) {
        statusMessage.textContent = message;
        statusMessage.className   = `status-msg ${type}`;
        if (type !== 'loading') {
            setTimeout(() => {
                statusMessage.className   = 'status-msg';
                statusMessage.textContent = '';
            }, 5000);
        }
    }

    // ── Add log item ──────────────────────────────────────
    function addLogItem(name, datetime) {
        // Remove empty placeholder
        const emptyEl = logList.querySelector('.log-empty');
        if (emptyEl) emptyEl.remove();

        const li = document.createElement('li');

        const nameSpan = document.createElement('span');
        nameSpan.className   = 'log-name';
        nameSpan.textContent = `👤 ${name}`;

        const timeSpan = document.createElement('span');
        timeSpan.className   = 'log-time';
        timeSpan.textContent = `🕒 ${datetime}`;

        li.appendChild(nameSpan);
        li.appendChild(timeSpan);

        logList.insertBefore(li, logList.firstChild);

        // Keep max 8 entries visible
        while (logList.children.length > 8) {
            logList.removeChild(logList.lastChild);
        }

        // Update badge
        logCountBadge.textContent = logList.children.length;
    }
});
