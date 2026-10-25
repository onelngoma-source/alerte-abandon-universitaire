/* Affichage d'un resultat d'estimation : saisie individuelle et fiche d'un etudiant. */
(function () {
  const NIVEAUX = { faible: 'Faible', moyen: 'Moyen', eleve: 'Élevé' };
  const COULEURS = { faible: 'bg-green', moyen: 'bg-orange', eleve: 'bg-red' };
  const f3 = (x) => Number(x).toFixed(3).replace('.', ',');
  const f2 = (x) => Number(x).toFixed(2).replace('.', ',');
  const echapper = (t) => String(t).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  function rendreVoisins($, v) {
    const carte = $('carte-voisins');
    if (!v || !v.plus_proches.length) { carte.hidden = true; return; }
    carte.hidden = false;
    $('voisins-entetes').innerHTML = '<tr><th>#</th><th>Profil</th><th>Abandon</th>'
      + v.colonnes.map((c) => `<th class="num">${echapper(c)}</th>`).join('') + '</tr>';
    $('voisins-lignes').innerHTML = v.plus_proches.map((l) => `<tr>
      <td>${l.rang}</td>
      <td>${l.reel ? 'Réel' : '<span class="badge bg-secondary-lt" title="Profil de référence créé pour équilibrer les données">Synthétique</span>'}</td>
      <td>${l.abandon ? '<span class="text-danger">Oui</span>' : 'Non'}</td>
      ${l.valeurs.map((x) => `<td class="num">${echapper(String(x).replace('.', ','))}</td>`).join('')}</tr>`).join('');
    $('voisins-bas').textContent = `Parmi ces ${v.plus_proches.length} étudiants, ${v.abandons_parmi_plus_proches} ont abandonné.`;
  }

  function rendre(racine, json, options) {
    const choix = options || {};
    const $ = (role) => racine.querySelector(`[data-role="${role}"]`);
    $('bandeau-precoce').hidden = !json.mode_precoce;
    [['noyau', json.probabilite_noyau, json.categorie_noyau], ['ml', json.probabilite_ml, json.categorie_ml]].forEach(([cle, proba, cat]) => {
      $('p-' + cle).textContent = f3(proba);
      const badge = $('b-' + cle); badge.textContent = NIVEAUX[cat]; badge.className = 'badge badge-risque mt-1 risque-' + cat;
      const barre = $('barre-' + cle); barre.style.width = Math.round(proba * 100) + '%'; barre.className = 'progress-bar ' + COULEURS[cat];
      const v = $('v-' + cle);
      if (json.verification && json.verification[cle] !== undefined) {
        v.innerHTML = json.verification[cle]
          ? '<span class="concordance-ok">&#10003;</span> conforme au devenir réel'
          : '<span class="text-danger">&#10007;</span> différent du devenir réel';
      } else { v.textContent = ''; }
    });
    // Sur la saisie individuelle, le formulaire ne demande jamais les 23 variables
    // secondaires : la note serait affichee a chaque fois et n'apprendrait rien.
    // Elle n'a de sens que pour un etudiant venu d'un fichier, ou elle distingue les cas.
    $('note-estimees').textContent = (choix.noteEstimees !== false && json.nb_variables_estimees)
      ? 'Certaines informations n\'ont pas été fournies : elles sont estimées automatiquement.' : '';
    rendreVoisins($, json.voisins_noyau);
    $('facteurs').innerHTML = json.facteurs_contributifs.map((f) => {
      const hausse = f.sens === 'augmente';
      return `<div class="list-group-item d-flex align-items-center">
        <span class="${hausse ? 'facteur-hausse' : 'facteur-baisse'} me-2">${hausse ? '&#9650;' : '&#9660;'}</span>
        <div class="flex-fill">${echapper(f.variable)} <span class="text-secondary">(${echapper(String(f.valeur).replace('.', ','))})</span>
          ${f.estimee ? '<span class="badge bg-secondary-lt ms-1">estimée</span>' : ''}</div>
        <span class="text-secondary small">${hausse ? 'augmente' : 'diminue'} le risque</span></div>`;
    }).join('');
    $('conseils').innerHTML = json.conseils.map((c) => `<div class="list-group-item">${echapper(c.message)}</div>`).join('');
  }

  window.Resultat = { rendre };
})();
