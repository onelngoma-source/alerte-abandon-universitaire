/* Suivi de cohorte : file des etudiants a accompagner, selon la capacite disponible.
   Les risques viennent du serveur ; ce fichier les classe, les filtre et les affiche. */
(function () {
  'use strict';
  const { echapper, nombre, pct, niveau, enAlerte, badge, jauge, MOMENTS, MOMENTS_COURTS } = window.Commun;
  const $ = (id) => document.getElementById(id);
  const PAR_LOT = 60;  // lignes ajoutees a chaque fois que l'on approche du bas de la liste
  const DOMAINES = { resultats: 'Résultats', finances: 'Finances', parcours: "Parcours d'entrée", profil: 'Profil' };

  const etat = { cohorte: null, lignes: [], metriques: {}, capacite: 20, niveau: 'tous', filiere: '', recherche: '', prioritaires: false, devenir: false, affichees: 0, actif: null };

  function lireCapacite() {
    try { const v = Number(localStorage.getItem('capacite')); if (v >= 5 && v <= 60) etat.capacite = v; } catch (e) { /* rien */ }
    $('capacite').value = etat.capacite;
  }

  const nbAccompagnes = () => Math.max(1, Math.round(etat.capacite / 100 * etat.lignes.length));

  function signaux(l) {
    const s = [];
    if (l.debiteur === 1) s.push('<span class="etiquette alerte">Débiteur</span>');
    if (l.frais_a_jour === 0) s.push('<span class="etiquette alerte">Frais en retard</span>');
    for (const [k, nom] of [['1', 'S1'], ['2', 'S2']]) {
      const i = l['inscrites_s' + k], v = l['validees_s' + k];
      if (i > 0 && v !== null && v !== undefined) s.push(`<span class="etiquette ${v / i < 0.5 ? 'attention' : ''}">${nom} ${v}/${i}</span>`);
    }
    if (l.boursier === 1) s.push('<span class="etiquette">Boursier</span>');
    return s.join('');
  }

  function filtrees() {
    const N = nbAccompagnes();
    const q = etat.recherche.trim().toLowerCase();
    return etat.lignes.filter((l) => {
      if (etat.prioritaires && l.rang > N) return false;
      if (etat.filiere && (l.filiere || 'Non renseignée') !== etat.filiere) return false;
      if (q && !(String(l.reference) + ' ' + (l.nom || '')).toLowerCase().includes(q)) return false;
      if (etat.niveau === 'alerte') return enAlerte(l.p_ml);
      if (etat.niveau !== 'tous') return niveau(l.p_ml) === etat.niveau;
      return true;
    });
  }

  function indicateurs() {
    const n = etat.lignes.length;
    const alertes = etat.lignes.filter((l) => enAlerte(l.p_ml)).length;
    const eleves = etat.lignes.filter((l) => niveau(l.p_ml) === 'eleve').length;
    const kpi = (id, k, part) => {
      $(id).innerHTML = `<span>0</span>${part === undefined ? '' : `<small>${pct(part)}</small>`}`;
      Commun.compter($(id).firstChild, k);
    };
    kpi('kpi-effectif', n); kpi('kpi-alerte', alertes, alertes / n); kpi('kpi-eleve', eleves, eleves / n); kpi('kpi-faible', n - alertes, (n - alertes) / n);
    const moments = {};
    etat.lignes.forEach((l) => { moments[l.mode] = (moments[l.mode] || 0) + 1; });
    const cles = Object.keys(moments).sort();
    $('kpi-moment').textContent = cles.length === 1 ? MOMENTS[cles[0]]
      : cles.map((m) => `${MOMENTS_COURTS[m]} : ${nombre(moments[m])}`).join(' · ');
  }

  function capacite() {
    const n = etat.lignes.length, N = nbAccompagnes();
    const alertes = etat.lignes.filter((l) => enAlerte(l.p_ml)).length;
    $('capacite-valeur').textContent = etat.capacite + ' %';
    const dernier = etat.lignes[N - 1];
    let phrase = `<b>${nombre(N)} étudiants</b> accompagnés, de ${pct(etat.lignes[0].p_ml)} à ${pct(dernier.p_ml)} de risque. `;
    if (N >= alertes) {
      phrase += alertes ? `Toutes les alertes sont couvertes${N > alertes ? ` et ${nombre(N - alertes)} places restent libres` : ''}.`
        : 'Aucun étudiant en alerte.';
    } else {
      phrase += `<b>${nombre(alertes - N)} en alerte</b> restent hors capacité.`;
    }
    $('capacite-phrase').innerHTML = phrase;
    const accompagnes = N, horsCapacite = Math.max(0, alertes - N), reste = n - accompagnes - horsCapacite;
    $('barre-file').innerHTML = `<i style="width:${100 * accompagnes / n}%;background:var(--marine)"></i><i style="width:${100 * horsCapacite / n}%;background:var(--moyen)"></i><i style="width:${100 * reste / n}%;background:var(--trait-fort)"></i>`;
  }

  function verification() {
    const connues = etat.lignes.filter((l) => l.abandon_reel !== null && l.abandon_reel !== undefined);
    const bloc = $('carte-verification');
    $('bascule-devenir').hidden = !connues.length;
    if (connues.length < 30 || !etat.metriques.ml) { bloc.hidden = true; return; }
    const N = nbAccompagnes();
    const abandons = connues.filter((l) => l.abandon_reel === 1).length;
    const dansFile = connues.filter((l) => l.abandon_reel === 1 && l.rang <= N).length;
    const m = etat.metriques.ml;
    $('verification').innerHTML = `Le devenir réel de ces étudiants est connu (${nombre(abandons)} abandons). Au seuil d'alerte, l'outil en avait repéré
      <b>${pct(m.rappel)}</b>, et <b>${pct(m.precision)}</b> des alertes étaient justes. Avec une capacité de ${etat.capacite} %,
      la file d'accompagnement contient <b>${nombre(dansFile)} des ${nombre(abandons)} abandons</b> (${pct(dansFile / abandons)}).`;
    bloc.hidden = false;
  }

  function barresFilieres() {
    const groupes = {};
    etat.lignes.forEach((l) => {
      const f = l.filiere || 'Non renseignée';
      groupes[f] = groupes[f] || { n: 0, a: 0 };
      groupes[f].n += 1; if (enAlerte(l.p_ml)) groupes[f].a += 1;
    });
    const liste = Object.entries(groupes).sort((x, y) => y[1].a - x[1].a || y[1].n - x[1].n);
    $('par-filiere').innerHTML = liste.map(([f, g]) => `<div class="barre-ligne">
      <button type="button" class="nom" data-filiere="${echapper(f)}" title="${echapper(f)}">${echapper(f)}</button>
      <span class="val">${g.a} / ${g.n} · ${pct(g.a / g.n)}</span>
      <span class="piste"><i style="width:${100 * g.a / g.n}%"></i></span></div>`).join('');
    const sel = $('filiere');
    const actuelle = sel.value;
    sel.innerHTML = '<option value="">Toutes les filières</option>' + Object.keys(groupes).sort((a, b) => a.localeCompare(b, 'fr'))
      .map((f) => `<option value="${echapper(f)}">${echapper(f)}</option>`).join('');
    sel.value = actuelle && groupes[actuelle] ? actuelle : '';

    const domaines = {};
    const enAlerteListe = etat.lignes.filter((l) => enAlerte(l.p_ml) && l.domaine_facteur);
    enAlerteListe.forEach((l) => { domaines[l.domaine_facteur] = (domaines[l.domaine_facteur] || 0) + 1; });
    $('par-domaine').innerHTML = enAlerteListe.length ? Object.entries(domaines).sort((a, b) => b[1] - a[1]).map(([d, k]) => `<div class="barre-ligne">
      <span class="nom">${DOMAINES[d] || d}${d === 'resultats' || d === 'finances' ? ' <span class="levier petit">· levier</span>' : ''}</span>
      <span class="val">${nombre(k)} · ${pct(k / enAlerteListe.length)}</span>
      <span class="piste"><i class="${d === 'resultats' || d === 'finances' ? 'or' : ''}" style="width:${100 * k / enAlerteListe.length}%"></i></span></div>`).join('')
      : '<p class="discret petit">Aucun étudiant en alerte.</p>';
  }

  function ligneHTML(l, N) {
    const alerte = enAlerte(l.p_ml);
    const classes = [l.rang > N ? 'hors-file' : '', l.rang === N ? 'limite' : '', l.id === etat.actif ? 'actif' : ''].join(' ');
    const devenir = l.abandon_reel === 1 ? '<span class="badge eleve">Abandon</span>' : l.abandon_reel === 0 ? '<span class="badge faible">Poursuite</span>' : '–';
    return `<tr class="${classes}" data-id="${l.id}" tabindex="0" aria-label="Aperçu de ${echapper(l.nom || l.reference)}">
      <td class="rang tnum">${l.rang}</td>
      <td class="etudiant"><b>${echapper(l.nom || l.reference)}</b><span>${echapper(l.filiere || 'Filière non renseignée')} · ${{ T0: 'inscription', T1: 'semestre 1', T2: 'semestre 2' }[l.mode]}</span></td>
      <td><div class="risque-cellule"><span class="pct tnum">${Math.round(100 * l.p_ml)} %</span>${jauge(l.p_ml)}${badge(l.p_ml)}</div></td>
      <td class="facteur col-large">${alerte && l.facteur ? `${echapper(l.facteur)}` : '<span class="discret">–</span>'}<div class="signaux">${signaux(l)}</div></td>
      <td class="cellule-suivi col-large">${l.dossier_statut ? `${Commun.statut(l.dossier_statut)}<span class="dom">${echapper(l.conseiller || 'non attribué')}</span>` : '<span class="discret">–</span>'}</td>
      <td class="col-devenir" ${etat.devenir ? '' : 'hidden'}>${devenir}</td></tr>`;
  }

  /* La liste defile dans sa feuille : on ajoute des lignes par lots quand on approche du bas. */
  function completer() {
    const N = nbAccompagnes();
    const lot = etat.liste.slice(etat.affichees, etat.affichees + PAR_LOT);
    if (!lot.length) return;
    const ancienne = $('lignes').querySelector('.sentinelle');
    if (ancienne) ancienne.remove();
    $('lignes').insertAdjacentHTML('beforeend', lot.map((l) => ligneHTML(l, N)).join(''));
    etat.affichees += lot.length;
    if (etat.affichees < etat.liste.length) {
      $('lignes').insertAdjacentHTML('beforeend', `<tr class="sentinelle"><td colspan="6">${nombre(etat.liste.length - etat.affichees)} étudiants de plus…</td></tr>`);
      observateur.observe($('lignes').querySelector('.sentinelle'));
    }
  }
  const observateur = new IntersectionObserver((entrees) => {
    if (entrees.some((e) => e.isIntersecting)) completer();
  }, { root: document.querySelector('.liste-cohorte .tableau-wrap'), rootMargin: '400px' });

  function tableau(garderDefilement = false) {
    const zone = document.querySelector('.liste-cohorte .tableau-wrap');
    const position = zone.scrollTop, deja = etat.affichees;
    etat.liste = filtrees();
    document.querySelectorAll('.col-devenir').forEach((c) => { c.hidden = !etat.devenir; });
    $('lignes').innerHTML = ''; etat.affichees = 0;
    completer();
    while (garderDefilement && etat.affichees < Math.min(deja, etat.liste.length)) completer();
    zone.scrollTop = garderDefilement ? position : 0;
    $('aucun').hidden = etat.liste.length > 0;
    $('compte').textContent = `${nombre(etat.liste.length)} étudiant${etat.liste.length > 1 ? 's' : ''}` + (etat.liste.length !== etat.lignes.length ? ` sur ${nombre(etat.lignes.length)}` : '');
  }

  function toutAfficher() { indicateurs(); capacite(); verification(); barresFilieres(); tableau(); }

  function surligner(id) {
    etat.actif = id;
    $('lignes').querySelectorAll('tr.actif').forEach((tr) => tr.classList.remove('actif'));
    const tr = $('lignes').querySelector(`tr[data-id="${id}"]`);
    if (tr) { tr.classList.add('actif'); tr.scrollIntoView({ block: 'nearest', behavior: Commun.calme() ? 'auto' : 'smooth' }); }
  }

  function ouvrir(id) {
    const ids = etat.liste.map((l) => l.id);
    try { sessionStorage.setItem('file-' + etat.cohorte.id, JSON.stringify(ids)); } catch (e) { /* rien */ }
    Apercu.ouvrir(id, ids, {
      surSelection: surligner,
      surChangement: () => charger(etat.cohorte.id, true),
      surFermeture: () => { etat.actif = null; $('lignes').querySelectorAll('tr.actif').forEach((tr) => tr.classList.remove('actif')); },
    });
  }

  function brancher() {
    $('capacite').addEventListener('input', (e) => {
      etat.capacite = Number(e.target.value);
      try { localStorage.setItem('capacite', String(etat.capacite)); } catch (err) { /* rien */ }
      capacite(); verification(); tableau(true);
    });
    $('niveaux').addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b) return;
      etat.niveau = b.dataset.niveau;
      $('niveaux').querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      tableau();
    });
    $('filiere').addEventListener('change', (e) => { etat.filiere = e.target.value; tableau(); });
    $('par-filiere').addEventListener('click', (e) => {
      const b = e.target.closest('[data-filiere]'); if (!b) return;
      etat.filiere = etat.filiere === b.dataset.filiere ? '' : b.dataset.filiere;
      $('filiere').value = etat.filiere; tableau();
    });
    $('recherche').addEventListener('input', (e) => { etat.recherche = e.target.value; tableau(); });
    $('prioritaires').addEventListener('change', (e) => { etat.prioritaires = e.target.checked; tableau(); });
    $('devenir').addEventListener('change', (e) => { etat.devenir = e.target.checked; tableau(true); });
    $('lignes').addEventListener('click', (e) => { const tr = e.target.closest('tr[data-id]'); if (tr) ouvrir(Number(tr.dataset.id)); });
    $('lignes').addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return; const tr = e.target.closest('tr[data-id]'); if (tr) ouvrir(Number(tr.dataset.id));
    });
  }

  let branche = false;
  async function charger(id, discret = false) {
    const res = await fetch('/api/cohortes/' + id);
    if (!res.ok) { location.href = '/tableau'; return; }
    const d = await res.json();
    etat.cohorte = d.cohorte; etat.metriques = d.metriques || {};
    etat.lignes = d.lignes.slice().sort((a, b) => b.p_ml - a.p_ml || a.id - b.id);
    etat.lignes.forEach((l, i) => { l.rang = i + 1; });
    if (!branche) { lireCapacite(); brancher(); branche = true; }
    if (discret) { tableau(true); return; }  // apres une operation dans l'apercu : on garde la place dans la liste
    etat.filiere = '';
    toutAfficher();
  }

  window.Cohorte = { charger };
})();
