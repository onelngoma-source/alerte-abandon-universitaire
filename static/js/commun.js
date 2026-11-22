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
  const STATUTS = { a_contacter: 'À contacter', contacte: 'Contacté', entretien: 'Entretien réalisé', accompagnement: 'En accompagnement', clos: 'Clos' };
  const statut = (s) => s ? `<span class="statut s-${s}">${STATUTS[s]}</span>` : '<span class="discret">–</span>';

  function notifier(message, type = 'ok') {
    let zone = document.getElementById('notifications');
    if (!zone) { zone = document.createElement('div'); zone.id = 'notifications'; zone.setAttribute('aria-live', 'polite'); document.body.appendChild(zone); }
    const n = document.createElement('div'); n.className = 'notification ' + type; n.textContent = message;
    zone.appendChild(n);
    setTimeout(() => { n.classList.add('sortie'); setTimeout(() => n.remove(), 320); }, 3800);
  }

  const calme = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* Les chiffres montent jusqu'a leur valeur : une seule fois, a l'affichage. */
  function compter(el, valeur, format = nombre, duree = 900) {
    if (!el) return;
    if (calme()) { el.textContent = format(valeur); return; }
    const debut = performance.now();
    const pas = (t) => {
      const x = Math.min(1, (t - debut) / duree);
      const v = valeur * (1 - Math.pow(1 - x, 3));
      el.textContent = format(Number.isInteger(valeur) && x < 1 ? Math.round(v) : (x < 1 ? v : valeur));
      if (x < 1) requestAnimationFrame(pas);
    };
    requestAnimationFrame(pas);
  }

  /* Onglets : un curseur blanc glisse sous l'onglet choisi, le panneau entre en douceur.
     Structure : .onglets [role=tab][data-onglet=x] et [data-panneau=x]. */
  function onglets(racine, options = {}) {
    const barre = racine.querySelector('.onglets');
    const tabs = [...barre.querySelectorAll('[role="tab"]')];
    let curseur = barre.querySelector('.curseur-onglet');
    if (!curseur) { curseur = document.createElement('span'); curseur.className = 'curseur-onglet'; barre.prepend(curseur); }
    barre.classList.add('anime');
    const placer = (tab) => {
      curseur.style.width = tab.offsetWidth + 'px';
      curseur.style.transform = `translateX(${tab.offsetLeft - 4}px)`;
      curseur.style.left = '4px';
    };
    function choisir(nom, focus = false) {
      const tab = tabs.find((t) => t.dataset.onglet === nom) || tabs[0];
      tabs.forEach((t) => { const oui = t === tab; t.setAttribute('aria-selected', String(oui)); t.tabIndex = oui ? 0 : -1; });
      racine.querySelectorAll('[data-panneau]').forEach((p) => {
        const oui = p.dataset.panneau === tab.dataset.onglet;
        if (oui && p.hidden) { p.hidden = false; p.classList.remove('entre'); void p.offsetWidth; p.classList.add('entre'); }
        else p.hidden = !oui;
      });
      placer(tab);
      if (focus) tab.focus();
      if (options.memoire) { try { sessionStorage.setItem(options.memoire, tab.dataset.onglet); } catch (e) { /* rien */ } }
      if (options.surChangement) options.surChangement(tab.dataset.onglet);
    }
    tabs.forEach((t, i) => {
      t.addEventListener('click', () => choisir(t.dataset.onglet));
      t.addEventListener('keydown', (e) => {
        const k = { ArrowRight: 1, ArrowLeft: -1 }[e.key];
        if (k) { e.preventDefault(); choisir(tabs[(i + k + tabs.length) % tabs.length].dataset.onglet, true); }
      });
    });
    const replacer = () => { const t = tabs.find((x) => x.getAttribute('aria-selected') === 'true'); if (t) placer(t); };
    window.addEventListener('resize', replacer);
    if (window.ResizeObserver) { const ro = new ResizeObserver(replacer); tabs.forEach((t) => ro.observe(t)); }
    let depart = options.initial;
    if (!depart && options.memoire) { try { depart = sessionStorage.getItem(options.memoire); } catch (e) { /* rien */ } }
    choisir(depart || tabs[0].dataset.onglet);
    return { choisir };
  }

  /* Tiroir d'apercu, a droite : ouvert depuis une liste, ferme avec Echap ou un clic a cote. */
  const Tiroir = {
    ouvrir(titre, sousTitre) {
      const t = document.getElementById('tiroir'); if (!t) return null;
      document.getElementById('tiroir-titre').textContent = titre || '';
      document.getElementById('tiroir-sous-titre').textContent = sousTitre || '';
      t.classList.add('ouvert'); document.getElementById('voile-tiroir').classList.add('ouvert');
      this.precedent = document.activeElement;
      setTimeout(() => document.getElementById('fermer-tiroir').focus({ preventScroll: true }), 60);
      return document.getElementById('tiroir-corps');
    },
    fermer() {
      const t = document.getElementById('tiroir'); if (!t || !t.classList.contains('ouvert')) return;
      t.classList.remove('ouvert'); document.getElementById('voile-tiroir').classList.remove('ouvert');
      if (this.precedent && this.precedent.focus) this.precedent.focus({ preventScroll: true });
      if (this.surFermeture) this.surFermeture();
    },
    estOuvert() { const t = document.getElementById('tiroir'); return Boolean(t && t.classList.contains('ouvert')); },
  };
  document.addEventListener('DOMContentLoaded', () => {
    const f = document.getElementById('fermer-tiroir');
    if (f) f.addEventListener('click', () => Tiroir.fermer());
    const v = document.getElementById('voile-tiroir');
    if (v) v.addEventListener('click', () => Tiroir.fermer());
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') Tiroir.fermer(); });

  window.Commun = { SEUIL_ALERTE, SEUIL_ELEVE, echapper, nombre, pct, dec, niveau, enAlerte, badge, jauge, NIVEAUX, MOMENTS, MOMENTS_COURTS,
    api, date, dateHeure, relatif, STATUTS, statut, notifier, compter, onglets, calme };
  window.Tiroir = Tiroir;
  window.Chargement = Chargement;
})();
