// theme-toggle.js — sitewide dark/light mode handler
document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('theme-toggle-btn');
  const root = document.documentElement;
  const current = localStorage.getItem('theme') || 'light';

  root.setAttribute('data-theme', current);
  btn.textContent = current === 'dark' ? 'Light Mode' : 'Dark Mode';

  btn.addEventListener('click', () => {
    const newTheme = root.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    root.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
    btn.textContent = newTheme === 'dark' ? 'Light Mode' : 'Dark Mode';
  });
});
