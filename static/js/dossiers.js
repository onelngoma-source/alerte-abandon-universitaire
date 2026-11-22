/* Dossiers d'accompagnement : liste de travail, vues en onglets, attribution groupee, traitement dans l'apercu. */
(function () {
  'use strict';
  const { echapper, api, date, relatif, statut, badge, notifier, nombre } = window.Commun;
  const $ = (id) => document.getElementById(id);
  const VIDES = {
    mes: "Aucun dossier ouvert à votre nom. Les dossiers « Non attribués » attendent quelqu'un.",
    non_attribues: 'Tous les dossiers ouverts sont attribués.', retard: 'Aucun dossier en retard.',
    a_revoir: "Aucun risque en hausse sur les dossiers ouverts.", ouverts: 'Aucun dossier ouvert.', clos: 'Aucun dossier clos.',
  };
  let dossiers = [], actif = null;

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
    return `<tr data-etudiant="${d.etudiant_id}" tabindex="0" class="${d.etudiant_id === actif ? 'actif' : ''}">
      ${window.GESTION ? `<td class="col-selection"><input type="checkbox" data-dossier="${d.id}" aria-label="Sélectionner ${echapper(d.matricule)}" ${d.statut === 'clos' ? 'disabled' : ''}></td>` : ''}
      <td class="etudiant"><b>${echapper(d.nom || d.matricule)}</b><span>${echapper(d.nom ? d.matricule + ' · ' : '')}${echapper(d.filiere || '')}</span></td>
      <td><div class="risque-cellule" style="min-width:120px"><span class="pct tnum">${Math.round(100 * d.probabilite)} %</span>${badge(d.probabilite)}</div>
        ${d.relance && d.statut !== 'clos' ? '<span class="etiquette alerte" style="margin-top:4px">Risque en hausse</span>' : ''}</td>
      <td class="facteur col-large">${echapper(d.facteur || '–')}</td>
      <td class="nowrap">${statut(d.statut)}</td>
      <td class="nowrap conseiller col-large">${d.conseiller ? echapper(d.conseiller) : '<span class="etiquette or">Non attribué</span>'}</td>
      <td class="echeance">${echeance}</td></tr>`;
  }

  function compteurs() {
    for (const vue of ['mes', 'non_attribues', 'retard', 'a_revoir']) {
      const q = parametres(); q.set('vue', vue);
      api('/api/dossiers?' + q.toString()).then((r) => {
        const el = document.querySelector(`[data-compte="${vue}"]`); if (el) el.textContent = r.dossiers.length;
      }).catch(() => {});
    }
  }

  async function charger(garder = false) {
    const p = parametres();
    p.set('vue', window.VUE);
    $('export').href = '/api/dossiers/export.csv?' + p.toString();
    $('th-date').textContent = window.VUE === 'clos' ? 'Clos le' : 'Échéance';
    const zone = document.querySelector('#zone-dossiers .tableau-wrap');
    const position = zone.scrollTop;
    try { dossiers = (await api('/api/dossiers?' + p.toString())).dossiers; } catch (e) { notifier(e.message, 'erreur'); return; }
    $('lignes').innerHTML = dossiers.map(ligne).join('');
    zone.scrollTop = garder ? position : 0;
    $('aucun').hidden = dossiers.length > 0;
    $('aucun').textContent = VIDES[window.VUE];
    $('compte').textContent = `${nombre(dossiers.length)} dossier${dossiers.length > 1 ? 's' : ''}`;
    if (window.GESTION) $('tout').checked = false;
    majSelection();
    compteurs();
  }

  function majSelection() {
    if (!window.GESTION) return;
    const choisis = document.querySelectorAll('[data-dossier]:checked');
    $('barre-selection').hidden = choisis.length === 0;
    $('nb-selection').textContent = choisis.length;
  }

  function surligner(id) {
    actif = id;
    $('lignes').querySelectorAll('tr.actif').forEach((tr) => tr.classList.remove('actif'));
    const tr = $('lignes').querySelector(`tr[data-etudiant="${id}"]`);
    if (tr) { tr.classList.add('actif'); tr.scrollIntoView({ block: 'nearest', behavior: Commun.calme() ? 'auto' : 'smooth' }); }
  }

  function ouvrir(id) {
    Apercu.ouvrir(id, dossiers.map((d) => d.etudiant_id), {
      surSelection: surligner,
      surChangement: () => charger(true),
      surFermeture: () => { actif = null; $('lignes').querySelectorAll('tr.actif').forEach((tr) => tr.classList.remove('actif')); },
    });
  }

  $('lignes').addEventListener('click', (e) => {
    if (e.target.closest('input')) { majSelection(); return; }
    const tr = e.target.closest('tr[data-etudiant]');
    if (tr) ouvrir(Number(tr.dataset.etudiant));
  });
  $('lignes').addEventListener('keydown', (e) => {
    const tr = e.target.closest('tr[data-etudiant]');
    if (e.key === 'Enter' && tr && e.target === tr) ouvrir(Number(tr.dataset.etudiant));
  });
  ['filtre-promotion', 'filtre-conseiller'].forEach((id) => { if ($(id)) $(id).addEventListener('change', () => charger()); });
  if (window.GESTION) {
    $('tout').addEventListener('change', (e) => {
      document.querySelectorAll('[data-dossier]:not(:disabled)').forEach((c) => { c.checked = e.target.checked; }); majSelection();
    });
    $('attribuer-selection').addEventListener('click', async () => {
      const ids = [...document.querySelectorAll('[data-dossier]:checked')].map((c) => Number(c.dataset.dossier));
      try {
        const r = await api('/api/dossiers/attribution-groupee', { dossiers: ids, conseiller_id: Number($('cible-attribution').value) });
        notifier(`${r.nombre} dossier(s) attribué(s).`); charger(true);
      } catch (e) { notifier(e.message, 'erreur'); }
    });
  }

  // les vues sont des onglets : on change de liste sans recharger la page
  Commun.onglets($('zone-dossiers'), {
    initial: window.VUE,
    surChangement: (vue) => {
      if (vue === window.VUE && dossiers.length) return;
      window.VUE = vue;
      history.replaceState(null, '', '?vue=' + vue);
      charger();
    },
  });
})();
