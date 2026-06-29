// VPS Manager - Main JavaScript

document.addEventListener('DOMContentLoaded', function() {

  // ─── Flash messages auto-dismiss ───
  const alerts = document.querySelectorAll('.alert');
  alerts.forEach(alert => {
    setTimeout(() => {
      alert.style.transition = 'opacity 0.3s';
      alert.style.opacity = '0';
      setTimeout(() => alert.remove(), 300);
    }, 5000);
  });

  // ─── Sidebar toggle ───
  const sidebarToggle = document.getElementById('sidebarToggle');
  const sidebar = document.getElementById('sidebar');
  if (sidebarToggle && sidebar) {
    sidebarToggle.addEventListener('click', () => {
      sidebar.classList.toggle('open');
    });
  }

  // ─── Modal overlay ───
  document.querySelectorAll('[data-modal-target]').forEach(btn => {
    btn.addEventListener('click', function() {
      const target = document.getElementById(this.dataset.modalTarget);
      if (target) target.classList.add('active');
    });
  });

  document.querySelectorAll('.modal-overlay .close, .modal-overlay .cancel').forEach(el => {
    el.addEventListener('click', function() {
      this.closest('.modal-overlay').classList.remove('active');
    });
  });

  document.querySelectorAll('.modal-overlay').forEach(overlay => {
    overlay.addEventListener('click', function(e) {
      if (e.target === this) this.classList.remove('active');
    });
  });

  // ─── Confirm dialogs ───
  document.querySelectorAll('[data-confirm]').forEach(el => {
    el.addEventListener('click', function(e) {
      if (!confirm(this.dataset.confirm || 'Are you sure?')) {
        e.preventDefault();
      }
    });
  });

  // ─── Auto-refresh status indicators ───
  function refreshStatus() {
    document.querySelectorAll('[data-status-url]').forEach(el => {
      const url = el.dataset.statusUrl;
      fetch(url)
        .then(r => r.json())
        .then(data => {
          const badge = el.querySelector('.status-badge');
          if (badge) {
            badge.className = 'badge badge-' + (data.status || 'unknown');
            badge.textContent = data.status || 'Unknown';
          }
        })
        .catch(() => {});
    });
  }

  setInterval(refreshStatus, 15000);

  // ─── System stats refresh (dashboard) ───
  function refreshSystemStats() {
    document.querySelectorAll('[data-stats-url]').forEach(el => {
      const url = el.dataset.statsUrl;
      fetch(url)
        .then(r => r.json())
        .then(data => {
          const cpuBar = el.querySelector('.cpu-fill');
          const ramBar = el.querySelector('.ram-fill');
          const diskBar = el.querySelector('.disk-fill');
          const cpuText = el.querySelector('.cpu-text');
          const ramText = el.querySelector('.ram-text');
          const diskText = el.querySelector('.disk-text');

          if (cpuBar) cpuBar.style.width = (data.cpu_percent || 0) + '%';
          if (ramBar) ramBar.style.width = (data.ram_percent || 0) + '%';
          if (diskBar) diskBar.style.width = (data.disk_percent || 0) + '%';
          if (cpuText) cpuText.textContent = (data.cpu_percent || 0).toFixed(1) + '%';
          if (ramText) ramText.textContent = data.ram_used + 'GB / ' + data.ram_total + 'GB';
          if (diskText) diskText.textContent = data.disk_used + 'GB / ' + data.disk_total + 'GB';
        })
        .catch(() => {});
    });
  }

  setInterval(refreshSystemStats, 5000);

  // ─── VPS live stats (detail page) ───
  function refreshVpsStats() {
    document.querySelectorAll('[data-vps-stats-url]').forEach(el => {
      const url = el.dataset.vpsStatsUrl;
      fetch(url)
        .then(r => r.json())
        .then(data => {
          const cpuBar = el.querySelector('.vps-cpu-fill');
          const ramBar = el.querySelector('.vps-ram-fill');
          const cpuText = el.querySelector('.vps-cpu-text');
          const ramText = el.querySelector('.vps-ram-text');
          const netRx = el.querySelector('.vps-net-rx');
          const netTx = el.querySelector('.vps-net-tx');

          if (cpuBar) cpuBar.style.width = Math.min(data.cpu_percent || 0, 100) + '%';
          if (ramBar) ramBar.style.width = Math.min(data.memory_percent || 0, 100) + '%';
          if (cpuText) cpuText.textContent = (data.cpu_percent || 0).toFixed(1) + '%';
          if (ramText) ramText.textContent = (data.memory_used || 0) + 'MB / ' + (data.memory_total || 0) + 'MB';
          if (netRx) netRx.textContent = formatBytes(data.net_rx || 0);
          if (netTx) netTx.textContent = formatBytes(data.net_tx || 0);
        })
        .catch(() => {});
    });
  }

  setInterval(refreshVpsStats, 3000);

  // ─── Utility: format bytes ───
  function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  // ─── Dynamic forms: confirm password match ───
  const registerForm = document.querySelector('form[action$="register"]');
  if (registerForm) {
    const password = registerForm.querySelector('input[name="password"]');
    const confirm = registerForm.querySelector('input[name="confirm_password"]');
    if (password && confirm) {
      confirm.addEventListener('input', function() {
        if (this.value !== password.value) {
          this.setCustomValidity('Passwords do not match');
        } else {
          this.setCustomValidity('');
        }
      });
    }
  }
});