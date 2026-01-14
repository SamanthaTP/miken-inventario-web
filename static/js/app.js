// Auto-oculta mensajes flash
window.addEventListener("DOMContentLoaded", () => {
  const el = document.querySelector(".flash");
  if (!el) return;

  // Botón cerrar
  const closeBtn = el.querySelector("[data-close]");
  if (closeBtn) {
    closeBtn.addEventListener("click", () => el.remove());
  }

  // Auto-hide en 2.2s
  setTimeout(() => {
    if (el && el.parentNode) el.remove();
  }, 2200);
});
