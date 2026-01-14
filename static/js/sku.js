function pad2(n){ return n.toString().padStart(2,"0"); }

function generarSKU(tipo){
  const d = new Date();
  const y = d.getFullYear().toString().slice(-2);
  const m = pad2(d.getMonth()+1);
  const day = pad2(d.getDate());
  const r = Math.random().toString(36).substring(2,6).toUpperCase();
  const pref = (tipo === "maquina") ? "MQ" : "IN";
  return `${pref}-${y}${m}${day}-${r}`;
}

window.addEventListener("DOMContentLoaded", () => {
  const skuInput = document.querySelector("#sku");
  const tipoInput = document.querySelector("#tipo_hidden");
  const btn = document.querySelector("#btnSku");

  if (!skuInput || !tipoInput || !btn) return;

  btn.addEventListener("click", () => {
    skuInput.value = generarSKU(tipoInput.value);
    skuInput.focus();
  });
});
