(function () {
  const $ = (id) => document.getElementById(id);
  const vue = Cohorte.monter($('cohorte-vue'));

  /* --- le parcours en trois etapes, affiche dans la barre de contexte --- */
  function etape(n) {
    document.querySelectorAll('#etapes li').forEach((li) => {
      const k = Number(li.dataset.etape);
      if (k === n) li.setAttribute('aria-current', 'step'); else li.removeAttribute('aria-current');
      li.dataset.fait = k < n ? 'oui' : 'non';
    });
    $('etape-1').hidden = n !== 1;
    $('bloc-mapping').hidden = n !== 2;
    $('assistant-import').hidden = n === 3;
    $('cohorte-vue').hidden = n !== 3;
    $('compte-rendu').hidden = n !== 3;
    ['lien-exemple', 'lien-gabarit'].forEach((id) => { $(id).hidden = n === 3; });
  }

  $('fichier').addEventListener('change', () => {
    const cible = document.querySelector('[data-role="nom-fichier"]');
    const f = $('fichier').files[0];
    if (cible) { cible.textContent = f ? f.name : ''; cible.hidden = !f; }
  });

  /* --- glisser-deposer sur la zone --- */
  const depot = $('depot');
  ['dragenter', 'dragover'].forEach((n) => depot.addEventListener(n, (e) => {
    e.preventDefault(); depot.classList.add('survol');
  }));
  ['dragleave', 'drop'].forEach((n) => depot.addEventListener(n, (e) => {
    e.preventDefault(); depot.classList.remove('survol');
  }));
  depot.addEventListener('drop', (e) => {
    if (!e.dataTransfer.files.length) return;
    $('fichier').files = e.dataTransfer.files;
    $('fichier').dispatchEvent(new Event('change'));
  });
  const echapper = (t) => String(t).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const nombre = (n) => Number(n).toLocaleString('fr-FR');

  function erreur(message) { $('erreur').textContent = message; $('erreur').hidden = !message; }

  function reinitialiser() { erreur(''); etape(1); }

  async function analyser() {
    reinitialiser();
    const fichier = $('fichier').files[0];
    if (!fichier) { erreur('Choisissez un fichier CSV.'); return; }
    const formulaire = new FormData(); formulaire.append('fichier', fichier);
    $('btn-analyser').disabled = true;
    if (window.Chargement) window.Chargement.afficher('Lecture du fichier');
    try {
      const res = await fetch('/api/analyser-fichier', { method: 'POST', body: formulaire });
      const json = await res.json();
      if (!res.ok) throw new Error(json.erreur || 'Erreur du serveur');
      if (!json.mapping_necessaire) { await calculer(fichier, null); return; }
      const ligne = (champ, libelle) => {
        const options = json.colonnes_du_fichier.map((c) =>
          `<option value="${echapper(c)}" ${json.suggestions[champ] === c ? 'selected' : ''}>${echapper(c)}</option>`).join('');
        return `<div class="col-md-6"><div class="row g-2 align-items-center">
          <div class="col-6 small">${echapper(libelle)}</div>
          <div class="col-6"><select class="form-select form-select-sm" data-champ="${echapper(champ)}">
            <option value="__aucune__">Aucune correspondance (estimée)</option>${options}</select></div></div></div>`;
      };
      $('lignes-mapping').innerHTML = Object.entries(json.champs_attendus).map(([c, l]) => ligne(c, l)).join('');
      const supplementaires = Object.entries(json.champs_supplementaires);
      $('lignes-supplementaires').innerHTML = supplementaires.map(([c, l]) => ligne(c, l)).join('');
      $('nb-supplementaires').textContent = supplementaires.length;
      // la section repliee s'ouvre d'elle-meme si une variable supplementaire a ete reconnue ou si des colonnes restent a placer
      $('bloc-supplementaires').open = supplementaires.some(([c]) => json.suggestions[c]) || json.colonnes_non_reconnues.length > 0;
      $('info-non-reconnues').hidden = !json.colonnes_non_reconnues.length;
      $('liste-non-reconnues').textContent = json.colonnes_non_reconnues.length > 8
        ? json.colonnes_non_reconnues.length + ' colonnes' : json.colonnes_non_reconnues.join(', ');
      const f = $('fichier').files[0];
      $('fichier-lu').innerHTML = `<b>${echapper(f.name)}</b> · ${json.colonnes_du_fichier.length} colonnes`;
      etape(2);
    } catch (e) { erreur(e.message); } finally { $('btn-analyser').disabled = false;
      if (window.Chargement) window.Chargement.masquer(); }
  }

  async function calculer(fichier, correspondance) {
    erreur('');
    const formulaire = new FormData();
    formulaire.append('fichier', fichier);
    formulaire.append('nom', $('nom').value);
    if (correspondance) formulaire.append('mapping', JSON.stringify(correspondance));
    if (window.Chargement) window.Chargement.afficher('Calcul des scores');
    const res = await fetch('/api/import', { method: 'POST', body: formulaire });
    const json = await res.json();
    if (!res.ok) {
      let message = json.erreur || 'Erreur du serveur';
      if (json.colonnes_attendues) message += '\n\nColonnes attendues : ' + json.colonnes_attendues.join(', ');
      throw new Error(message);
    }
    const donnees = await (await fetch('/api/cohortes/' + json.cohorte_id)).json();
    $('resume').textContent = `${nombre(json.effectif)} étudiants importés`
      + (json.moyenne_estimees > 0 ? ', informations absentes estimées' : '');
    $('lien-tableau').href = '/tableau?cohorte=' + json.cohorte_id;
    const menu = $('menu-avertissements');
    if (json.nb_ignorees) {
      menu.hidden = false;
      $('avertissements').innerHTML = `<strong>${nombre(json.nb_ignorees)} ligne(s) ignorée(s)</strong> : `
        + json.lignes_ignorees.map((l) => `ligne ${l.ligne} (${echapper(l.motif)})`).join(' ; ')
        + (json.nb_ignorees > json.lignes_ignorees.length ? ' ; …' : '');
    } else { menu.hidden = true; }
    etape(3);
    vue.afficher(donnees);
    if (window.Chargement) window.Chargement.masquer();
  }

  $('btn-analyser').addEventListener('click', analyser);
  $('btn-retour').addEventListener('click', () => etape(1));
  $('nouvel-import').addEventListener('click', () => { $('fichier').value = ''; reinitialiser(); });
  const boutonAvert = $('bouton-avertissements'), panneauAvert = $('panneau-avertissements');
  boutonAvert.addEventListener('click', () => {
    const ouvert = panneauAvert.classList.toggle('on');
    boutonAvert.setAttribute('aria-expanded', String(ouvert));
  });
  document.addEventListener('click', (e) => {
    if (!panneauAvert.contains(e.target) && !boutonAvert.contains(e.target)) {
      panneauAvert.classList.remove('on'); boutonAvert.setAttribute('aria-expanded', 'false');
    }
  });
  $('btn-confirmer').addEventListener('click', async () => {
    const correspondance = {};
    document.querySelectorAll('#lignes-mapping select, #lignes-supplementaires select').forEach((s) => { correspondance[s.dataset.champ] = s.value; });
    $('btn-confirmer').disabled = true;
    try { await calculer($('fichier').files[0], correspondance); } catch (e) { erreur(e.message); }
    finally { $('btn-confirmer').disabled = false; if (window.Chargement) window.Chargement.masquer(); }
  });
  $('fichier').addEventListener('change', () => { erreur(''); });
  etape(1);
})();
