/* Importer une cohorte : fichier, association des colonnes, compte rendu. */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const { echapper, nombre, MOMENTS } = window.Commun;

  function etape(n) {
    document.querySelectorAll('#etapes li').forEach((li) => {
      const k = Number(li.dataset.etape);
      if (k === n) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
      li.dataset.fait = k < n ? 'oui' : 'non';
    });
    [1, 2, 3].forEach((k) => { $('etape-' + k).hidden = k !== n; });
  }
  const erreur = (m) => { $('erreur').textContent = m || ''; $('erreur').hidden = !m; };

  $('fichier').addEventListener('change', () => {
    const f = $('fichier').files[0];
    $('nom-fichier').textContent = f ? f.name : ''; $('nom-fichier').hidden = !f; erreur('');
  });
  const depot = $('depot');
  ['dragenter', 'dragover'].forEach((n) => depot.addEventListener(n, (e) => { e.preventDefault(); depot.classList.add('survol'); }));
  ['dragleave', 'drop'].forEach((n) => depot.addEventListener(n, (e) => { e.preventDefault(); depot.classList.remove('survol'); }));
  depot.addEventListener('drop', (e) => {
    if (!e.dataTransfer.files.length) return;
    $('fichier').files = e.dataTransfer.files; $('fichier').dispatchEvent(new Event('change'));
  });

  function ligne(json, champ, libelle) {
    const options = json.colonnes_du_fichier.map((c) => `<option value="${echapper(c)}" ${json.suggestions[champ] === c ? 'selected' : ''}>${echapper(c)}</option>`).join('');
    return `<label class="correspondance"><span>${echapper(libelle)}</span>
      <select class="champ" data-champ="${echapper(champ)}"><option value="__aucune__">Aucune (complétée)</option>${options}</select></label>`;
  }

  async function analyser() {
    erreur('');
    const fichier = $('fichier').files[0];
    if (!fichier) { erreur('Choisissez un fichier CSV.'); return; }
    const f = new FormData(); f.append('fichier', fichier);
    $('btn-analyser').disabled = true; Chargement.afficher('Lecture du fichier');
    try {
      const res = await fetch('/api/analyser-fichier', { method: 'POST', body: f });
      const json = await res.json();
      if (!res.ok) throw new Error(json.erreur || 'Erreur du serveur');
      if (!json.mapping_necessaire) { await calculer(fichier, null); return; }
      $('lignes-mapping').innerHTML = Object.entries(json.champs_attendus).map(([c, l]) => ligne(json, c, l)).join('');
      const sup = Object.entries(json.champs_supplementaires);
      $('lignes-supplementaires').innerHTML = sup.map(([c, l]) => ligne(json, c, l)).join('');
      $('nb-supplementaires').textContent = sup.length;
      $('bloc-supplementaires').open = sup.some(([c]) => json.suggestions[c]) || json.colonnes_non_reconnues.length > 0;
      $('info-non-reconnues').hidden = !json.colonnes_non_reconnues.length;
      $('liste-non-reconnues').textContent = json.colonnes_non_reconnues.length > 8 ? json.colonnes_non_reconnues.length + ' colonnes' : json.colonnes_non_reconnues.join(', ');
      $('fichier-lu').textContent = `${fichier.name} · ${json.colonnes_du_fichier.length} colonnes · ${nombre(json.nombre_lignes)} lignes`;
      etape(2);
    } catch (e) { erreur(e.message); } finally { $('btn-analyser').disabled = false; Chargement.masquer(); }
  }

  async function calculer(fichier, correspondance) {
    const f = new FormData();
    f.append('fichier', fichier); f.append('nom', $('nom').value);
    if ($('promotion').value) f.append('promotion', $('promotion').value);
    if (correspondance) f.append('mapping', JSON.stringify(correspondance));
    Chargement.afficher('Calcul du risque de chaque étudiant');
    const res = await fetch('/api/import', { method: 'POST', body: f });
    const json = await res.json();
    Chargement.masquer();
    if (!res.ok) {
      let m = json.erreur || 'Erreur du serveur';
      if (json.colonnes_attendues) m += '\n\nColonnes attendues : ' + json.colonnes_attendues.join(', ');
      etape(1); throw new Error(m);
    }
    $('resume').textContent = json.mis_a_jour
      ? `${nombre(json.mis_a_jour)} étudiants mis à jour` + (json.nouveaux ? `, ${nombre(json.nouveaux)} ajoutés` : '')
      : `${nombre(json.nouveaux)} étudiants importés`;
    const moments = Object.entries(json.par_moment).filter(([, k]) => k > 0).map(([m, k]) => `${nombre(k)} ${MOMENTS[m].toLowerCase()}`);
    $('resume-detail').textContent = 'Risque estimé : ' + moments.join(', ') + '. '
      + `${nombre(json.dossiers_ouverts)} dossier(s) de suivi ouvert(s)` + (json.relances ? `, ${nombre(json.relances)} dossier(s) signalé(s) en hausse` : '') + '.'
      + (json.moyenne_estimees > 0 ? ` En moyenne ${String(json.moyenne_estimees).replace('.', ',')} informations complétées par étudiant.` : '');
    $('lien-tableau').href = '/tableau?cohorte=' + json.cohorte_id;
    const av = $('avertissements');
    av.hidden = !json.nb_ignorees;
    if (json.nb_ignorees) {
      av.innerHTML = `<div><b>${nombre(json.nb_ignorees)} ligne(s) ignorée(s)</b> : ` + json.lignes_ignorees.map((l) => `ligne ${l.ligne} (${echapper(l.motif)})`).join(' ; ')
        + (json.nb_ignorees > json.lignes_ignorees.length ? ' ; …' : '') + '</div>';
    }
    etape(3);
  }

  $('btn-analyser').addEventListener('click', analyser);
  $('btn-retour').addEventListener('click', () => etape(1));
  $('nouvel-import').addEventListener('click', () => { $('fichier').value = ''; $('nom-fichier').hidden = true; erreur(''); etape(1); });
  $('btn-confirmer').addEventListener('click', async () => {
    const c = {};
    document.querySelectorAll('#lignes-mapping select, #lignes-supplementaires select').forEach((s) => { c[s.dataset.champ] = s.value; });
    $('btn-confirmer').disabled = true;
    try { await calculer($('fichier').files[0], c); } catch (e) { erreur(e.message); } finally { $('btn-confirmer').disabled = false; }
  });
  const majNom = () => { $('bloc-nom').hidden = Boolean($('promotion').value); };
  $('promotion').addEventListener('change', majNom); majNom();
  etape(1);
})();
