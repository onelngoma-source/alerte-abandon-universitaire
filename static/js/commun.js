/* Outils d'affichage partages par toutes les pages. Aucun calcul de risque ici :
   le risque est toujours calcule par le serveur, avec un seul moteur. */
(function () {
  'use strict';
  const SEUIL_ALERTE = 1 / 6;
  const SEUIL_ELEVE = 0.5;

  const echapper = (t) => String(t ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const nombre = (n) => Number(n).toLocaleString('fr-FR');
  const pct = (p, d = 0) => (100 * p).toLocaleString('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d }) + ' %';
  const dec = (x, d = 3) => Number(x).toLocaleString('fr-FR', { minimumFractionDigits: d, maximumFractionDigits: d });
  const NIVEAUX = { eleve: 'Élevé', moyen: 'Moyen', faible: 'Faible' };
  const MOMENTS = { T0: "À l'inscription", T1: 'Fin du 1er semestre', T2: 'Fin du 2e semestre' };
  const MOMENTS_COURTS = { T0: 'Inscription', T1: 'Semestre 1', T2: 'Semestre 2' };

  function niveau(p) {
    const r = Math.round(p * 1000) / 1000;
    return r >= SEUIL_ELEVE ? 'eleve' : r >= Math.round(SEUIL_ALERTE * 1000) / 1000 ? 'moyen' : 'faible';
  }
  const enAlerte = (p) => Math.round(p * 1000) / 1000 >= Math.round(SEUIL_ALERTE * 1000) / 1000;

  function badge(p) {
    const n = niveau(p);
    return `<span class="badge ${n}">${NIVEAUX[n]}</span>`;
  }

  function jauge(p, reperes = false) {
    const n = niveau(p);
    const marques = reperes ? `<span class="repere" style="left:16.67%"></span><span class="repere" style="left:50%"></span>` : '';
    return `<div class="jauge ${n}" role="img" aria-label="Risque ${pct(p)}"><i style="width:${Math.max(2, 100 * p)}%"></i>${marques}</div>`;
  }

  const Chargement = {
    afficher(texte) {
      const v = document.querySelector('[data-role="voile"]'); if (!v) return;
      if (texte) v.querySelector('[data-role="texte-chargement"]').textContent = texte;
      v.dataset.visible = '1';
    },
    masquer() { const v = document.querySelector('[data-role="voile"]'); if (v) v.dataset.visible = '0'; },
  };

  window.Commun = { SEUIL_ALERTE, SEUIL_ELEVE, echapper, nombre, pct, dec, niveau, enAlerte, badge, jauge, NIVEAUX, MOMENTS, MOMENTS_COURTS };
  window.Chargement = Chargement;
})();
