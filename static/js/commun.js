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

  /* Jeton anti-CSRF : ajoute a toute requete qui modifie quelque chose sur le serveur de l'application. */
  const jeton = (document.querySelector('meta[name="csrf"]') || {}).content;
  const fetchOrigine = window.fetch.bind(window);
  window.fetch = (url, options = {}) => {
    const methode = (options.method || 'GET').toUpperCase();
    if (jeton && methode !== 'GET' && String(url).startsWith('/')) {
      options.headers = Object.assign({}, options.headers, { 'X-CSRF-Token': jeton });
    }
    return fetchOrigine(url, options);
  };

  /* Appel JSON : rend les donnees, ou leve une erreur portant le message du serveur. */
  async function api(url, corps, methode) {
    const options = corps === undefined ? { method: methode || 'GET' }
      : { method: methode || 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(corps) };
    const res = await fetch(url, options);
    const json = await res.json().catch(() => ({}));
    if (res.status === 401) { location.href = '/connexion?suivant=' + encodeURIComponent(location.pathname + location.search); }
    if (!res.ok) throw new Error(json.erreur || 'Erreur du serveur');
    return json;
  }

  const date = (iso) => iso ? new Date(iso.length === 10 ? iso + 'T12:00:00' : iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short', year: 'numeric' }) : '–';
  const dateHeure = (iso) => iso ? new Date(iso).toLocaleString('fr-FR', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '–';
  function relatif(iso) {
    if (!iso) return '';
    const jours = Math.round((new Date(iso.length === 10 ? iso + 'T12:00:00' : iso) - new Date()) / 86400000);
    if (jours === 0) return "aujourd'hui";
    if (jours === 1) return 'demain';
    if (jours === -1) return 'hier';
    return jours > 0 ? `dans ${jours} j` : `il y a ${-jours} j`;
  }
  const STATUTS = { a_contacter: 'À contacter', contacte: 'Contacté', entretien: 'Entretien réalisé', accompagnement: 'Accompagnement en cours', clos: 'Clos' };
  const statut = (s) => s ? `<span class="statut s-${s}">${STATUTS[s]}</span>` : '<span class="discret">–</span>';

  function notifier(message, type = 'ok') {
    let zone = document.getElementById('notifications');
    if (!zone) { zone = document.createElement('div'); zone.id = 'notifications'; zone.setAttribute('aria-live', 'polite'); document.body.appendChild(zone); }
    const n = document.createElement('div'); n.className = 'notification ' + type; n.textContent = message;
    zone.appendChild(n); setTimeout(() => n.remove(), 4200);
  }

  window.Commun = { SEUIL_ALERTE, SEUIL_ELEVE, echapper, nombre, pct, dec, niveau, enAlerte, badge, jauge, NIVEAUX, MOMENTS, MOMENTS_COURTS,
    api, date, dateHeure, relatif, STATUTS, statut, notifier };
  window.Chargement = Chargement;
})();
