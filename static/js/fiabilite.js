/* Fiabilite du modele : indicateurs recalcules par le serveur sur les cohortes 2015 a 2017. */
(async function () {
  'use strict';
  const { nombre, pct, dec, MOMENTS } = window.Commun;
  const $ = (id) => document.getElementById(id);
  const d = await (await fetch('/api/fiabilite')).json();
  const t2 = d.moments.find((m) => m.moment === 'T2');
  const t1 = d.moments.find((m) => m.moment === 'T1');
  const lr = t2.logistique;

  $('intro-effectif').textContent = nombre(d.effectif);
  $('kpis').innerHTML = `
    <div class="carte indicateur accent"><div class="libelle">ROC-AUC, fin du 2e semestre</div><div class="valeur tnum">${dec(lr.auc)}</div><div class="detail">capacité à classer un abandon avant une réussite</div></div>
    <div class="carte indicateur"><div class="libelle">Abandons repérés au seuil</div><div class="valeur tnum">${pct(lr.rappel)}</div><div class="detail">${nombre(Math.round(lr.rappel * d.abandons))} sur ${nombre(d.abandons)} abandons réels</div></div>
    <div class="carte indicateur"><div class="libelle">Alertes justes</div><div class="valeur tnum">${pct(lr.precision)}</div><div class="detail">${nombre(lr.alertes)} étudiants en alerte</div></div>
    <div class="carte indicateur"><div class="libelle">Score de Brier</div><div class="valeur tnum">${dec(lr.brier)}</div><div class="detail">écart moyen entre risque annoncé et réalité (0 = parfait)</div></div>`;

  $('table-moments').innerHTML = `<thead><tr><th>Moment</th><th>ROC-AUC</th><th>En alerte</th><th>Repérés</th><th>Alertes justes</th></tr></thead><tbody>`
    + d.moments.map((m) => `<tr${m.moment === 'T2' ? ' class="retenu"' : ''}><td>${MOMENTS[m.moment]}</td><td class="tnum">${dec(m.logistique.auc)}</td>
      <td class="tnum">${pct(m.logistique.part_alertes)}</td><td class="tnum">${pct(m.logistique.rappel)}</td><td class="tnum">${pct(m.logistique.precision)}</td></tr>`).join('') + '</tbody>';

  const c1 = t1.logistique.capacite;
  $('phrase-capacite').innerHTML = `Avec une capacité de <b>${Math.round(100 * d.capacite_repere)} %</b> (${nombre(c1.accompagnes)} étudiants), dès la fin du 1er semestre,
    l'outil repère <b>${pct(c1.rappel)} des abandons</b>, et <b>${pct(c1.precision)}</b> des étudiants accompagnés auraient effectivement abandonné.
    Choisis au hasard, ces étudiants n'en couvriraient que ${Math.round(100 * d.capacite_repere)} %.`;

  const axe = (titre, max = 1) => ({ min: 0, max, title: { display: true, text: titre, color: '#5A6A79' }, grid: { color: '#EEF1F5' },
    ticks: { color: '#5A6A79', callback: (v) => Math.round(v * 100) + ' %' } });
  Chart.defaults.font.family = 'Inter, system-ui, sans-serif';
  Chart.defaults.animation.duration = Commun.calme() ? 0 : 900;
  const parts = d.courbe_capacite.parts;
  const serie = (m, couleur) => ({ label: MOMENTS[m], data: parts.map((x, i) => ({ x, y: d.courbe_capacite[m][i] })), borderColor: couleur, backgroundColor: couleur, borderWidth: 2.5, pointRadius: 0, tension: 0.25 });
  const graphiques = {};
  graphiques.capacite = () => new Chart($('graphique-capacite'), {
    type: 'line',
    data: { datasets: [serie('T2', '#0D3863'), serie('T1', '#3281E0'), serie('T0', '#D8B85C'),
      { label: 'Au hasard', data: [{ x: 0, y: 0 }, { x: 1, y: 1 }], borderColor: '#CED6DF', borderDash: [5, 5], borderWidth: 1.5, pointRadius: 0 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false },
      tooltip: { callbacks: { label: (c) => `${c.dataset.label} : ${pct(c.parsed.y)} des abandons pour ${pct(c.parsed.x)} accompagnés` } } },
      scales: { x: { type: 'linear', ...axe('Part des étudiants accompagnés') }, y: axe('Part des abandons repérés') } },
  });

  const points = (liste) => liste.map((b) => ({ x: b.predit, y: b.observe, n: b.effectif }));
  graphiques.calibration = () => new Chart($('graphique-calibration'), {
    type: 'scatter',
    data: { datasets: [
      { label: 'Régression logistique', data: points(d.calibration.logistique), backgroundColor: '#0D3863', pointRadius: 5.5, showLine: true, borderColor: '#0D3863', borderWidth: 1.5 },
      { label: 'Approche à noyau', data: points(d.calibration.noyau), backgroundColor: '#D8B85C', pointRadius: 5.5, showLine: true, borderColor: '#D8B85C', borderWidth: 1.5 },
      { label: 'Parfait', data: [{ x: 0, y: 0 }, { x: 1, y: 1 }], showLine: true, borderColor: '#CED6DF', borderDash: [5, 5], borderWidth: 1.5, pointRadius: 0 }] },
    options: { maintainAspectRatio: false, plugins: { legend: { display: false },
      tooltip: { callbacks: { label: (c) => c.raw.n ? `${c.dataset.label} : annoncé ${pct(c.parsed.x)}, observé ${pct(c.parsed.y)} (${c.raw.n} étudiants)` : '' } } },
      scales: { x: axe('Risque annoncé'), y: axe('Abandons observés') } },
  });

  const ref = lr.rappel;
  $('table-equite').innerHTML = `<thead><tr><th>Groupe</th><th>Étudiants</th><th>Taux d'abandon</th><th>Repérés</th><th>Alertes justes</th></tr></thead><tbody>`
    + d.equite.map((g) => `<tr><td colspan="5" style="font-weight:700;color:#0B1626;padding-top:12px">${g.critere}</td></tr>`
      + g.lignes.map((l) => `<tr><td>${l.groupe}</td><td class="tnum">${nombre(l.effectif)}</td><td class="tnum">${pct(l.taux_abandon)}</td>
        <td class="tnum ${l.rappel < ref - 0.1 ? 'faible-detection' : ''}">${pct(l.rappel)}</td><td class="tnum">${pct(l.precision)}</td></tr>`).join('')).join('') + '</tbody>';
  const bourse = (d.equite.find((g) => g.critere === 'Bourse') || { lignes: [] }).lignes;
  const b = bourse.find((l) => l.groupe === 'Boursiers'), nb = bourse.find((l) => l.groupe === 'Non boursiers');
  $('encart-equite').innerHTML = b && nb ? `<div>Chez les <b>boursiers</b>, l'outil ne repère que <b>${pct(b.rappel)}</b> des abandons, contre ${pct(nb.rappel)}
    chez les non-boursiers : leurs abandons sont plus rares (${pct(b.taux_abandon)}) et ressemblent moins aux autres. La fiche d'un boursier le rappelle.</div>` : '';

  $('table-comparaison').innerHTML = `<thead><tr><th>Modèle</th><th>Inscription</th><th>Semestre 1</th><th>Semestre 2</th><th>Brier S2</th></tr></thead><tbody>`
    + d.comparaison.map((m, i) => `<tr${i === 0 ? ' class="retenu"' : ''}><td>${m.modele}${m.role ? `<br><span class="discret" style="font-weight:400">${m.role}</span>` : ''}</td>
      ${['T0', 'T1', 'T2'].map((k) => `<td class="tnum">${m.auc[k] === null ? '–' : dec(m.auc[k])}</td>`).join('')}<td class="tnum">${dec(m.brier_t2)}</td></tr>`).join('') + '</tbody>';

  const s = await (await fetch('/api/surveillance')).json();
  const demo = s.etablissement.devenirs_connus === 0 && s.demonstration.devenirs_connus > 0;
  const etat = demo ? s.demonstration : s.etablissement;
  $('table-surveillance').innerHTML = `<thead><tr><th>Moment</th><th>Devenirs connus</th><th>ROC-AUC (référence)</th><th>Risque annoncé / abandons observés</th><th>Repérés</th><th>Alertes justes</th></tr></thead><tbody>`
    + etat.moments.map((m) => m.suffisant
      ? `<tr><td>${MOMENTS[m.moment]}</td><td class="tnum">${nombre(m.effectif)} (${nombre(m.abandons)} abandons)</td>
         <td class="tnum ${m.auc < m.reference.auc - 0.05 ? 'faible-detection' : ''}">${dec(m.auc)} (${dec(m.reference.auc)})</td>
         <td class="tnum">${pct(m.risque_moyen)} / ${pct(m.taux_observe)}</td><td class="tnum">${pct(m.rappel)}</td><td class="tnum">${pct(m.precision)}</td></tr>`
      : `<tr><td>${MOMENTS[m.moment]}</td><td class="tnum">${nombre(m.effectif)}</td><td colspan="4" class="discret">Pas encore assez de devenirs connus
         (${s.etablissement.effectif_min} étudiants et ${s.etablissement.abandons_min} abandons au moins).</td></tr>`).join('') + '</tbody>';
  const signaux = etat.moments.flatMap((m) => (m.signaux || []).map((x) => `<b>${MOMENTS[m.moment]}</b> : ${x}`));
  $('signaux-surveillance').innerHTML = (demo ? '<div class="encart">Démonstration : faute de devenirs connus dans l\'établissement, le tableau montre le calcul sur la promotion de démonstration.</div>' : '')
    + (signaux.length ? signaux.map((x) => `<div class="encart rouge"><div>${x}</div></div>`).join('')
      : etat.moments.some((m) => m.suffisant) ? '<div class="encart"><div>Aucun écart notable avec la référence.</div></div>' : '');

  // les graphiques sont dessines quand leur onglet s'ouvre pour la premiere fois (un canevas cache n'a pas de taille)
  const dessines = {};
  Commun.onglets($('zone-fiabilite'), {
    memoire: 'onglet-fiabilite',
    surChangement: (nom) => {
      if (graphiques[nom] && !dessines[nom]) { dessines[nom] = true; requestAnimationFrame(() => graphiques[nom]()); }
    },
  });
})();
