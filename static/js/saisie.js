/* Saisie individuelle : remplissage d'exemples, etat du formulaire, estimation.
   Le calcul reste entierement cote serveur ; ce fichier ne fait que de l'interface. */
(function () {
  const $ = (id) => document.getElementById(id);

  const S1 = (e, a, v, n) => ({ 'Curricular units 1st sem (enrolled)': e, 'Curricular units 1st sem (approved)': a, 'Curricular units 1st sem (evaluations)': v, 'Curricular units 1st sem (grade)': n });
  const S2 = (e, a, v, n) => ({ 'Curricular units 2nd sem (enrolled)': e, 'Curricular units 2nd sem (approved)': a, 'Curricular units 2nd sem (evaluations)': v, 'Curricular units 2nd sem (grade)': n });
  const EXEMPLES = {
    fragile: Object.assign(S1(6, 2, 8, 9.5), S2(6, 1, 7, 8.0), { 'Age at enrollment': 24, 'Scholarship holder': 0, 'Debtor': 1, 'Tuition fees up to date': 0, Course: 9119 }),
    intermediaire: Object.assign(S1(6, 4, 8, 11.5), S2(6, 4, 8, 11.0), { 'Age at enrollment': 20, 'Scholarship holder': 0, 'Debtor': 0, 'Tuition fees up to date': 1, Course: 9238 }),
    solide: Object.assign(S1(6, 6, 7, 14.5), S2(6, 6, 7, 14.0), { 'Age at enrollment': 18, 'Scholarship holder': 1, 'Debtor': 0, 'Tuition fees up to date': 1, Course: 9500 }),
    precoce: Object.assign(S1(6, 3, 8, 10.5), S2('', '', '', ''), { 'Age at enrollment': 19, 'Scholarship holder': 0, 'Debtor': 0, 'Tuition fees up to date': 1, Course: 9147 }),
  };

  const champs = Array.from(document.querySelectorAll('#formulaire [name]'));
  const champsS2 = champs.filter((c) => c.name.includes('2nd sem'));

  /* --- etat du formulaire : progression et portee de l'estimation --- */
  function majEtat() {
    const remplis = champs.filter((c) => String(c.value).trim() !== '').length;
    const barre = $('progression-barre');
    if (barre) barre.style.width = (remplis / champs.length * 100) + '%';
    const texte = $('progression-texte');
    if (texte) texte.textContent = `${remplis} champ${remplis > 1 ? 's' : ''} sur ${champs.length}`;

    const etat = $('etat-mode'), mot = $('etat-mode-texte');
    if (!etat || !mot) return;
    const sansS2 = champsS2.every((c) => String(c.value).trim() === '');
    // les listes deroulantes ont une valeur par defaut : le formulaire est dit
    // vide tant qu'aucun champ chiffre n'a ete renseigne
    const aucunChiffre = champs.filter((c) => c.type === 'number')
                               .every((c) => String(c.value).trim() === '');
    if (aucunChiffre) { etat.dataset.mode = 'vide'; mot.textContent = 'Formulaire vide'; }
    else if (sansS2) { etat.dataset.mode = 'premier'; mot.textContent = 'Premier semestre seul'; }
    else { etat.dataset.mode = 'complet'; mot.textContent = 'Deux semestres'; }
  }
  $('formulaire').addEventListener('input', majEtat);
  $('formulaire').addEventListener('change', majEtat);

  /* --- menu des exemples : il remplit le formulaire, sans lancer le calcul --- */
  const menu = $('liste-exemple'), bouton = $('bouton-exemple');
  if (menu && bouton) {
    bouton.addEventListener('click', () => {
      const ouvert = menu.classList.toggle('on');
      bouton.setAttribute('aria-expanded', String(ouvert));
    });
    document.addEventListener('click', (e) => {
      if (!menu.contains(e.target) && !bouton.contains(e.target)) {
        menu.classList.remove('on'); bouton.setAttribute('aria-expanded', 'false');
      }
    });
    menu.querySelectorAll('[data-exemple]').forEach((a) => a.addEventListener('click', () => {
      const valeurs = EXEMPLES[a.dataset.exemple];
      Object.keys(valeurs).forEach((k) => {
        const el = document.querySelector(`[name="${k}"]`); if (el) el.value = valeurs[k];
      });
      menu.classList.remove('on'); bouton.setAttribute('aria-expanded', 'false');
      $('erreur').hidden = true;
      majEtat();
      champs[0].focus();
    }));
  }

  const effacer = $('effacer');
  if (effacer) effacer.addEventListener('click', () => {
    champs.forEach((c) => { c.value = c.tagName === 'SELECT' ? c.querySelector('option').value : ''; });
    $('resultat').hidden = true; $('attente').hidden = false; $('erreur').hidden = true;
    $('deux-colonnes').dataset.resultat = 'visible';
    majEtat();
  });

  /* --- le panneau de resultat se replie, le formulaire prend toute la largeur --- */
  const colonnes = $('deux-colonnes');
  const fermer = $('fermer-resultat');
  if (fermer) fermer.addEventListener('click', () => {
    colonnes.dataset.resultat = 'masque';
    document.querySelector('#formulaire button[type=submit]').focus();
  });

  $('formulaire').addEventListener('submit', async (e) => {
    e.preventDefault();
    $('erreur').hidden = true;
    const donnees = {};
    new FormData(e.target).forEach((v, k) => { donnees[k] = v; });
    if (window.Chargement) window.Chargement.afficher('Estimation en cours');
    try {
      const res = await fetch('/api/predict', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(donnees) });
      const json = await res.json();
      if (!res.ok) throw new Error(json.erreur || 'Erreur du serveur');
      $('attente').hidden = true; $('resultat').hidden = false;
      colonnes.dataset.resultat = 'visible';   // une nouvelle estimation fait revenir le panneau
      Resultat.rendre($('resultat'), json, { noteEstimees: false });
    } catch (err) {
      $('erreur').textContent = err.message; $('erreur').hidden = false;
      colonnes.dataset.resultat = 'visible';
    } finally {
      if (window.Chargement) window.Chargement.masquer();
    }
  });

  majEtat();
})();
