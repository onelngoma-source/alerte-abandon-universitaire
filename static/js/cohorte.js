/* Suivi de cohorte : file des etudiants a accompagner, selon la capacite disponible.
   Les risques viennent du serveur ; ce fichier les classe, les filtre et les affiche. */
(function () {
  'use strict';
  const { echapper, nombre, pct, niveau, enAlerte, badge, jauge, MOMENTS, MOMENTS_COURTS } = window.Commun;
  const $ = (id) => document.getElementById(id);
  const PAR_PAGE = 25;
  const DOMAINES = { resultats: 'Résultats', finances: 'Finances', parcours: "Parcours d'entrée", profil: 'Profil' };

  const etat = { cohorte: null, lignes: [], metriques: {}, capacite: 20, niveau: 'tous', filiere: '', recherche: '', prioritaires: false, devenir: false, page: 0 };

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
      if (q && !String(l.reference).toLowerCase().includes(q)) return false;
      if (etat.niveau === 'alerte') return enAlerte(l.p_ml);
      if (etat.niveau !== 'tous') return niveau(l.p_ml) === etat.niveau;
      return true;
    });
  }

  function indicateurs() {
    const n = etat.lignes.length;
    const alertes = etat.lignes.filter((l) => enAlerte(l.p_ml)).length;
    const eleves = etat.lignes.filter((l) => niveau(l.p_ml) === 'eleve').length;
    $('kpi-effectif').textContent = nombre(n);
    $('kpi-alerte').innerHTML = `${nombre(alertes)}<small>${pct(alertes / n)}</small>`;
    $('kpi-eleve').innerHTML = `${nombre(eleves)}<small>${pct(eleves / n)}</small>`;
    $('kpi-faible').innerHTML = `${nombre(n - alertes)}<small>${pct((n - alertes) / n)}</small>`;
    const moments = {};
    etat.lignes.forEach((l) => { moments[l.mode] = (moments[l.mode] || 0) + 1; });
    const cles = Object.keys(moments).sort();
    $('kpi-moment').textContent = cles.length === 1 ? 'Risque estimé ' + MOMENTS[cles[0]].toLowerCase()
      : cles.map((m) => `${MOMENTS_COURTS[m]} : ${nombre(moments[m])}`).join(' · ');
  }

  function capacite() {
    const n = etat.lignes.length, N = nbAccompagnes();
    const alertes = etat.lignes.filter((l) => enAlerte(l.p_ml)).length;
    $('capacite-valeur').textContent = etat.capacite + ' %';
    const dernier = etat.lignes[N - 1];
    let phrase = `Vous pouvez accompagner <b>${nombre(N)} étudiants</b> : les ${nombre(N)} premiers de la liste, dont le risque va de ${pct(etat.lignes[0].p_ml)} à ${pct(dernier.p_ml)}. `;
    if (N >= alertes) {
      phrase += alertes ? `Les <b>${nombre(alertes)} étudiants en alerte</b> sont tous couverts${N > alertes ? `, et ${nombre(N - alertes)} places restent pour des étudiants sous le seuil` : ''}.`
        : 'Aucun étudiant n\'est en alerte dans cette cohorte.';
    } else {
      phrase += `<b>${nombre(alertes - N)} étudiants en alerte</b> restent hors capacité : à surveiller, ou à confier à un autre dispositif.`;
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

  function tableau() {
    const N = nbAccompagnes();
    const liste = filtrees();
    const pages = Math.max(1, Math.ceil(liste.length / PAR_PAGE));
    etat.page = Math.min(etat.page, pages - 1);
    const visibles = liste.slice(etat.page * PAR_PAGE, (etat.page + 1) * PAR_PAGE);
    document.querySelectorAll('.col-devenir').forEach((c) => { c.hidden = !etat.devenir; });
    $('lignes').innerHTML = visibles.map((l) => {
      const alerte = enAlerte(l.p_ml);
      const classes = [l.rang > N ? 'hors-file' : '', l.rang === N ? 'limite' : ''].join(' ');
      const devenir = l.abandon_reel === 1 ? '<span class="badge eleve">Abandon</span>' : l.abandon_reel === 0 ? '<span class="badge faible">Poursuite</span>' : '–';
      return `<tr class="${classes}" data-id="${l.id}" tabindex="0" aria-label="Ouvrir la fiche de ${echapper(l.reference)}">
        <td class="rang tnum">${l.rang}</td>
        <td class="etudiant"><b>${echapper(l.reference)}</b><span>${echapper(l.filiere || 'Filière non renseignée')}</span></td>
        <td><div class="risque-cellule"><span class="pct tnum">${Math.round(100 * l.p_ml)} %</span>${jauge(l.p_ml)}${badge(l.p_ml)}</div></td>
        <td class="facteur">${alerte && l.facteur ? `${echapper(l.facteur)}<span class="dom">${DOMAINES[l.domaine_facteur] || ''}</span>` : '<span class="discret">–</span>'}</td>
        <td><div class="signaux">${signaux(l)}</div></td>
        <td class="petit discret">${{ T0: 'Inscr.', T1: 'S1', T2: 'S2' }[l.mode]}</td>
        <td class="col-devenir" ${etat.devenir ? '' : 'hidden'}>${devenir}</td></tr>`;
    }).join('');
    $('aucun').hidden = liste.length > 0;
    $('compte').textContent = `${nombre(liste.length)} étudiant${liste.length > 1 ? 's' : ''}` + (liste.length !== etat.lignes.length ? ` sur ${nombre(etat.lignes.length)}` : '');
    $('page-num').textContent = `${etat.page + 1} / ${pages}`;
    $('page-prec').disabled = etat.page === 0;
    $('page-suiv').disabled = etat.page >= pages - 1;
    etat.liste = liste;
  }

  function toutAfficher() { indicateurs(); capacite(); verification(); barresFilieres(); tableau(); }

  function ouvrir(id) {
    try { sessionStorage.setItem('file-' + etat.cohorte.id, JSON.stringify(etat.liste.map((l) => l.id))); } catch (e) { /* rien */ }
    location.href = '/etudiants/' + id;
  }

  function brancher() {
    $('capacite').addEventListener('input', (e) => {
      etat.capacite = Number(e.target.value);
      try { localStorage.setItem('capacite', String(etat.capacite)); } catch (err) { /* rien */ }
      capacite(); verification(); tableau();
    });
    $('niveaux').addEventListener('click', (e) => {
      const b = e.target.closest('button'); if (!b) return;
      etat.niveau = b.dataset.niveau; etat.page = 0;
      $('niveaux').querySelectorAll('button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      tableau();
    });
    $('filiere').addEventListener('change', (e) => { etat.filiere = e.target.value; etat.page = 0; tableau(); });
    $('par-filiere').addEventListener('click', (e) => {
      const b = e.target.closest('[data-filiere]'); if (!b) return;
      etat.filiere = etat.filiere === b.dataset.filiere ? '' : b.dataset.filiere;
      $('filiere').value = etat.filiere; etat.page = 0; tableau();
    });
    $('recherche').addEventListener('input', (e) => { etat.recherche = e.target.value; etat.page = 0; tableau(); });
    $('prioritaires').addEventListener('change', (e) => { etat.prioritaires = e.target.checked; etat.page = 0; tableau(); });
    $('devenir').addEventListener('change', (e) => { etat.devenir = e.target.checked; tableau(); });
    $('page-prec').addEventListener('click', () => { etat.page -= 1; tableau(); });
    $('page-suiv').addEventListener('click', () => { etat.page += 1; tableau(); });
    $('lignes').addEventListener('click', (e) => { const tr = e.target.closest('tr[data-id]'); if (tr) ouvrir(Number(tr.dataset.id)); });
    $('lignes').addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return; const tr = e.target.closest('tr[data-id]'); if (tr) ouvrir(Number(tr.dataset.id));
    });
  }

  let branche = false;
  async function charger(id) {
    const res = await fetch('/api/cohortes/' + id);
    if (!res.ok) { location.href = '/tableau'; return; }
    const d = await res.json();
    etat.cohorte = d.cohorte; etat.metriques = d.metriques || {};
    etat.lignes = d.lignes.slice().sort((a, b) => b.p_ml - a.p_ml || a.id - b.id);
    etat.lignes.forEach((l, i) => { l.rang = i + 1; });
    etat.page = 0; etat.filiere = '';
    if (!branche) { lireCapacite(); brancher(); branche = true; }
    toutAfficher();
  }

  window.Cohorte = { charger };
})();
