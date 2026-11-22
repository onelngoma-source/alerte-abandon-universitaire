/* Dossiers d'accompagnement : liste de travail, filtres, attribution groupee. */
(function () {
  'use strict';
  const { echapper, api, date, relatif, statut, badge, notifier } = window.Commun;
  const $ = (id) => document.getElementById(id);
  const VIDES = {
    mes: "Aucun dossier ouvert à votre nom. Consultez les dossiers non attribués pour en prendre en charge.",
    non_attribues: 'Tous les dossiers ouverts sont attribués.', retard: 'Aucun dossier en retard.',
    a_revoir: "Aucun risque en hausse sur les dossiers ouverts.", ouverts: 'Aucun dossier ouvert.', clos: 'Aucun dossier clos.',
  };
  let dossiers = [], page = 0;
  const PAR_PAGE = 30;

  function parametres() {
    const p = new URLSearchParams();
    if ($('filtre-promotion').value) p.set('promotion', $('filtre-promotion').value);
    if ($('filtre-conseiller') && $('filtre-conseiller').value) p.set('conseiller', $('filtre-conseiller').value);
    return p;
  }

  function ligne(d) {
    const echeance = window.VUE === 'clos'
      ? `${date(d.clos_le)}<span class="dom">${echapper(d.motif || '')}</span>`
      : d.echeance ? `<span class="${d.en_retard ? 'retard' : ''}">${date(d.echeance)}</span><span class="dom">${relatif(d.echeance)}</span>` : '–';
    return `<tr data-etudiant="${d.etudiant_id}" tabindex="0">
      ${window.GESTION ? `<td><input type="checkbox" data-dossier="${d.id}" aria-label="Sélectionner ${echapper(d.matricule)}" ${d.statut === 'clos' ? 'disabled' : ''}></td>` : ''}
      <td class="etudiant"><b>${echapper(d.nom || d.matricule)}</b><span>${echapper(d.nom ? d.matricule + ' · ' : '')}${echapper(d.filiere || '')}</span></td>
      <td><div class="risque-cellule" style="min-width:120px"><span class="pct tnum">${Math.round(100 * d.probabilite)} %</span>${badge(d.probabilite)}</div>
        ${d.relance && d.statut !== 'clos' ? '<span class="etiquette alerte" style="margin-top:4px">Risque en hausse</span>' : ''}</td>
      <td class="facteur">${echapper(d.facteur || '–')}</td>
      <td>${statut(d.statut)}</td>
      <td>${d.conseiller ? echapper(d.conseiller) : '<span class="etiquette or">Non attribué</span>'}</td>
      <td class="facteur">${echeance}</td></tr>`;
  }

  async function charger() {
    const p = parametres();
    p.set('vue', window.VUE);
    $('export').href = '/api/dossiers/export.csv?' + p.toString();
    $('th-date').textContent = window.VUE === 'clos' ? 'Clos le' : 'Échéance';
    try {
      dossiers = (await api('/api/dossiers?' + p.toString())).dossiers;
    } catch (e) { notifier(e.message, 'erreur'); return; }
    page = 0; afficher();
    $('aucun').hidden = dossiers.length > 0;
    $('aucun').textContent = VIDES[window.VUE];
    majSelection();
    // compteurs des onglets (sans les dossiers clos, potentiellement nombreux)
    for (const vue of ['mes', 'non_attribues', 'retard', 'a_revoir']) {
      const q = parametres(); q.set('vue', vue);
      api('/api/dossiers?' + q.toString()).then((r) => {
        const el = document.querySelector(`[data-compte="${vue}"]`); if (el) el.textContent = r.dossiers.length;
      }).catch(() => {});
    }
  }

  function afficher() {
    const pages = Math.max(1, Math.ceil(dossiers.length / PAR_PAGE));
    page = Math.min(page, pages - 1);
    $('lignes').innerHTML = dossiers.slice(page * PAR_PAGE, (page + 1) * PAR_PAGE).map(ligne).join('');
    $('compte').textContent = `${dossiers.length} dossier${dossiers.length > 1 ? 's' : ''}`;
    $('page-num').textContent = `${page + 1} / ${pages}`;
    $('page-prec').disabled = page === 0; $('page-suiv').disabled = page >= pages - 1;
    if (window.GESTION) $('tout').checked = false;
    majSelection();
  }
  $('page-prec').addEventListener('click', () => { page -= 1; afficher(); });
  $('page-suiv').addEventListener('click', () => { page += 1; afficher(); });

  function majSelection() {
    if (!window.GESTION) return;
    const choisis = document.querySelectorAll('[data-dossier]:checked');
    $('barre-selection').hidden = choisis.length === 0;
    $('nb-selection').textContent = choisis.length;
  }

  $('lignes').addEventListener('click', (e) => {
    if (e.target.closest('input')) { majSelection(); return; }
    const tr = e.target.closest('tr[data-etudiant]');
    if (tr) location.href = '/etudiants/' + tr.dataset.etudiant;
  });
  $('lignes').addEventListener('keydown', (e) => {
    const tr = e.target.closest('tr[data-etudiant]');
    if (e.key === 'Enter' && tr && e.target === tr) location.href = '/etudiants/' + tr.dataset.etudiant;
  });
  ['filtre-promotion', 'filtre-conseiller'].forEach((id) => { if ($(id)) $(id).addEventListener('change', charger); });
  if (window.GESTION) {
    $('tout').addEventListener('change', (e) => {
      document.querySelectorAll('[data-dossier]:not(:disabled)').forEach((c) => { c.checked = e.target.checked; }); majSelection();
    });
    $('attribuer-selection').addEventListener('click', async () => {
      const ids = [...document.querySelectorAll('[data-dossier]:checked')].map((c) => Number(c.dataset.dossier));
      try {
        const r = await api('/api/dossiers/attribution-groupee', { dossiers: ids, conseiller_id: Number($('cible-attribution').value) });
        notifier(`${r.nombre} dossier(s) attribué(s).`); $('tout').checked = false; charger();
      } catch (e) { notifier(e.message, 'erreur'); }
    });
  }
  charger();
})();
