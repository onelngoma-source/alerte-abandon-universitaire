/* Evaluer un etudiant : saisie guidee, estimation recalculee par le serveur a chaque modification. */
(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const form = $('formulaire');
  const sortie = $('resultat');
  const ATTENTE = sortie.innerHTML;

  const S = (s, e, v, a, n) => ({ [`Curricular units ${s} sem (enrolled)`]: e, [`Curricular units ${s} sem (evaluations)`]: v,
    [`Curricular units ${s} sem (approved)`]: a, [`Curricular units ${s} sem (grade)`]: n });
  const EXEMPLES = {
    inscription: { semestres: [], valeurs: { Course: 9991, 'Age at enrollment': 27, 'Scholarship holder': 0, 'Tuition fees up to date': 0, Debtor: 1 } },
    difficulte: { semestres: ['1st', '2nd'], valeurs: { Course: 9119, 'Age at enrollment': 21, 'Scholarship holder': 0, 'Tuition fees up to date': 1, Debtor: 0,
      ...S('1st', 6, 8, 3, 10.5), ...S('2nd', 6, 7, 2, 10.2) } },
    solide: { semestres: ['1st', '2nd'], valeurs: { Course: 9500, 'Age at enrollment': 18, 'Scholarship holder': 1, 'Tuition fees up to date': 1, Debtor: 0,
      ...S('1st', 7, 8, 7, 14.2), ...S('2nd', 7, 7, 7, 13.8) } },
  };

  function semestreActif(s) { return form.querySelector(`[data-bascule="${s}"]`).checked; }

  function majEtapes() {
    const s1 = semestreActif('1st');
    const b2 = form.querySelector('[data-bascule="2nd"]');
    if (!s1 && b2.checked) b2.checked = false;
    b2.disabled = !s1;
    form.querySelectorAll('[data-semestre]').forEach((sec) => sec.classList.toggle('inactive', !semestreActif(sec.dataset.semestre)));
  }

  function donnees() {
    const d = {};
    new FormData(form).forEach((v, k) => {
      if (String(v).trim() === '') return;
      if (k.includes(' sem ') && !semestreActif(k.includes('1st') ? '1st' : '2nd')) return;
      d[k] = v;
    });
    return d;
  }

  let minuterie = null, compteur = 0;
  async function estimer() {
    const d = donnees();
    if (!Object.keys(d).length) { sortie.innerHTML = ATTENTE; return; }
    const numero = ++compteur;
    const res = await fetch('/api/predict', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) });
    const json = await res.json();
    if (numero !== compteur) return; // une saisie plus recente est deja en cours
    if (!res.ok) {
      sortie.innerHTML = `<div class="erreur-saisie" role="alert">${Commun.echapper(json.erreur || 'Erreur du serveur')}</div>`;
      return;
    }
    Fiche.rendre(sortie, json, { compact: true });
  }
  const planifier = () => { clearTimeout(minuterie); minuterie = setTimeout(estimer, 250); };

  form.addEventListener('input', planifier);
  form.addEventListener('change', (e) => { if (e.target.dataset.bascule) majEtapes(); planifier(); });

  function remplir(exemple) {
    form.reset();
    form.querySelectorAll('[data-bascule]').forEach((b) => { b.checked = exemple.semestres.includes(b.dataset.bascule); });
    Object.entries(exemple.valeurs).forEach(([k, v]) => {
      const champs = form.querySelectorAll(`[name="${CSS.escape(k)}"]`);
      champs.forEach((c) => { if (c.type === 'radio') c.checked = String(c.value) === String(v); else c.value = v; });
    });
    majEtapes(); estimer();
  }
  document.querySelectorAll('[data-exemple]').forEach((b) => b.addEventListener('click', () => remplir(EXEMPLES[b.dataset.exemple])));
  $('effacer').addEventListener('click', () => { form.reset(); majEtapes(); sortie.innerHTML = ATTENTE; });
  majEtapes();
})();
