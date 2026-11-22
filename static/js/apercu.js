/* Aperçu d'un étudiant dans le tiroir de droite, depuis une liste : on traite un dossier sans quitter la liste.
   Flèches haut et bas : étudiant précédent ou suivant de la liste affichée. */
(function () {
  'use strict';
  const { echapper, api, badge, jauge, notifier } = window.Commun;
  const etat = { ids: [], index: -1, surChangement: null, numero: 0 };

  function squelette() {
    return `<div class="squelette" style="height:64px"></div><div class="squelette" style="height:150px"></div><div class="squelette" style="height:110px"></div>`;
  }

  function rendre(corps, f) {
    const r = f.resultat, p = r.probabilite_ml;
    const facteurs = (r.facteurs_hausse || []).slice(0, 3);
    const avert = (f.avertissements || []).map((a) => `<div class="encart or"><div>${echapper(a)}</div></div>`).join('');
    corps.innerHTML = `
      <div class="mini-risque"><span class="chiffre tnum">${Math.round(100 * p)}<small>%</small></span>
        <div style="flex:1;display:flex;flex-direction:column;gap:8px">
          <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">${badge(p)}<span class="etiquette or">Estimé ${echapper(r.libelle_moment)}</span></div>
          ${jauge(p, true)}</div></div>
      ${avert}
      <div class="bloc-doux">${window.Suivi.tiroirDossier(f)}</div>
      <div><div class="sous-titre-bloc"><span class="point eleve"></span>Ce qui pèse le plus</div>
        ${facteurs.length ? window.Fiche.listeFacteurs(facteurs, 'hausse') : '<p class="discret petit">Aucun facteur notable vers l\'abandon.</p>'}</div>`;
    window.Suivi.brancher(corps, f, () => charger(true));
  }

  async function charger(apresOperation = false) {
    const id = etat.ids[etat.index];
    const numero = ++etat.numero;
    const corps = document.getElementById('tiroir-corps');
    if (!apresOperation) corps.innerHTML = squelette();
    document.getElementById('tiroir-fiche').href = '/etudiants/' + id;
    const plusieurs = etat.ids.length > 1;
    document.getElementById('tiroir-position').textContent = plusieurs ? `${etat.index + 1} sur ${etat.ids.length}` : '';
    const prec = document.getElementById('tiroir-prec'), suiv = document.getElementById('tiroir-suiv');
    prec.hidden = suiv.hidden = !plusieurs;
    prec.disabled = etat.index <= 0; suiv.disabled = etat.index >= etat.ids.length - 1;
    let f;
    try { f = await api('/api/etudiants/' + id); } catch (e) { notifier(e.message, 'erreur'); return; }
    if (numero !== etat.numero) return;
    const filiere = (f.profil.find((x) => x.champ === 'Course') || {}).valeur;
    document.getElementById('tiroir-titre').textContent = f.nom || f.reference;
    document.getElementById('tiroir-sous-titre').textContent = [f.nom ? f.reference : null, filiere, f.cohorte].filter(Boolean).join(' · ');
    rendre(corps, f);
    corps.scrollTop = apresOperation ? corps.scrollTop : 0;
    if (apresOperation && etat.surChangement) etat.surChangement(id, f);
    if (etat.surSelection) etat.surSelection(id);
  }

  function ouvrir(id, ids, options = {}) {
    etat.ids = ids && ids.length ? ids : [id];
    etat.index = Math.max(0, etat.ids.indexOf(id));
    etat.surChangement = options.surChangement || null;
    etat.surSelection = options.surSelection || null;
    window.Tiroir.ouvrir('', '');
    window.Tiroir.surFermeture = options.surFermeture || null;
    charger();
  }

  function aller(pas) {
    const i = etat.index + pas;
    if (i < 0 || i >= etat.ids.length) return false;
    etat.index = i; charger(); return true;
  }
  document.getElementById('tiroir-prec').addEventListener('click', () => aller(-1));
  document.getElementById('tiroir-suiv').addEventListener('click', () => aller(1));
  document.addEventListener('keydown', (e) => {
    if (!window.Tiroir.estOuvert() || e.target.closest('input, textarea, select')) return;
    const pas = { ArrowDown: 1, ArrowUp: -1 }[e.key];
    if (pas && aller(pas)) e.preventDefault();
  });

  window.Apercu = { ouvrir };
})();
