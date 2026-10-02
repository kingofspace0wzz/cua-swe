import { mountDashboard } from './dashboard.js';

mountDashboard(document.getElementById('console')).catch((err) => {
  const el = document.getElementById('console');
  if (el) el.innerHTML = '<p class="load-error">workspace unavailable</p>';
  console.error(err);
});
