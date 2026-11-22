/* Fiche etudiant : le dossier de suivi (statut, conseiller, echeance, actions, cloture), l'historique des
   estimations, la mise a jour des resultats et le devenir reel. Chaque operation renvoie la fiche a jour. */
(function () {
  'use strict';
  const { echapper, api, date, dateHeure, relatif, statut, notifier, pct } = window.Commun;
  const ORDRE = ['a_contacter', 'contacte', 'entretien', 'accompagnement', 'clos'];
  const SUIVANT = { a_contacter: ['contacte', 'Marquer comme contacté'], contacte: ['entretien', "Entretien réalisé"],
    entretien: ['accompagnement', "Démarrer l'accompagnement"] };
  const SYSTEME = ['ouverture', 'reevaluation', 'statut', 'attribution', 'echeance'];

  function chronologie(d) {
    return `<ol class="chrono">${d.chronologie.map((a) => {
      const humain = !SYSTEME.includes(a.type) || a.type === 'statut';
      let texte = a.texte || '';
      if (a.type === 'statut') texte = `${a.statut_avant} → ${a.statut_apres}` + (a.texte ? `\n${a.texte}` : '');
      return `<li class="${humain ? 'humain' : 'systeme'}"><div class="tete"><b>${echapper(a.libelle)}</b> · ${dateHeure(a.cree_le)}${a.auteur ? ' · ' + echapper(a.auteur) : ' · automatique'}</div>
        ${texte ? `<p>${echapper(texte)}</p>` : ''}</li>`;
    }).join('')}</ol>`;
  }

  function carteDossier(f) {
    const d = f.dossier, droits = f.droits, rang = ORDRE.indexOf(d.statut);
    const etapes = ORDRE.map((s, i) => `<span class="${i <= rang ? 'fait' : ''}"></span>`).join('');
    const libelles = ORDRE.map((s) => `<span>${window.Commun.STATUTS[s]}</span>`).join('');
    let conseiller = d.conseiller ? echapper(d.conseiller) : '<span class="etiquette or">Non attribué</span>';
    if (droits.modifier_dossier && droits.gerer) {
      conseiller = `<select class="champ" data-op="attribuer" style="height:32px"><option value="">Non attribué</option>${f.conseillers.map((c) =>
        `<option value="${c.id}" ${c.id === d.conseiller_id ? 'selected' : ''}>${echapper(c.nom)}</option>`).join('')}</select>`;
    } else if (droits.modifier_dossier && !d.conseiller_id) {
      conseiller += ` <button class="btn btn-petit" data-op="prendre">Me l'attribuer</button>`;
    }
    const echeance = droits.modifier_dossier
      ? `<input class="champ" type="date" data-op="echeance" value="${d.echeance || ''}" style="height:32px">`
      : date(d.echeance);
    const enRetard = d.echeance && new Date(d.echeance + 'T23:59:59') < new Date();
    const suivant = SUIVANT[d.statut];
    const commandes = droits.modifier_dossier ? `
      <div class="actions" style="margin-bottom:16px">
        ${suivant ? `<button class="btn btn-plein" data-op="statut" data-statut="${suivant[0]}">${suivant[1]}</button>` : ''}
        <select class="champ" data-op="statut-choix" style="height:38px" aria-label="Changer de statut">
          <option value="">Autre statut…</option>${ORDRE.slice(0, 4).filter((s) => s !== d.statut).map((s) => `<option value="${s}">${window.Commun.STATUTS[s]}</option>`).join('')}</select>
        <button class="btn" data-op="ouvrir-cloture">Clore le dossier</button>
      </div>
      <form class="pile" data-op="action">
        <div class="sous-titre-bloc" style="margin:0">Consigner une action</div>
        <select class="champ" name="type">${Object.entries(f.types_action).map(([k, v]) => `<option value="${k}">${echapper(v)}</option>`).join('')}</select>
        <textarea class="champ" name="texte" maxlength="4000" placeholder="Ce qui a été fait ou décidé, en quelques mots." required></textarea>
        <div><button class="btn btn-plein" type="submit">Enregistrer l'action</button></div>
      </form>` : `<div class="encart">Ce dossier est suivi par ${echapper(d.conseiller || 'un autre conseiller')} : consultation seule.</div>`;
    return `<section class="carte c12" id="carte-dossier">
      <div class="carte-tete"><h2>Dossier de suivi</h2>${statut(d.statut)}${d.relance ? '<span class="etiquette alerte">Risque en hausse depuis l\'ouverture</span>' : ''}</div>
      <div class="carte-corps">
        <div class="etapes-suivi">${etapes}</div><div class="libelles-suivi">${libelles}</div>
        <div class="deux-colonnes">
          <div>
            <div class="grille-2" style="margin-bottom:16px">
              <div class="info-bloc"><span class="discret petit">Conseiller</span><div>${conseiller}</div></div>
              <div class="info-bloc"><span class="discret petit">Prochaine échéance ${enRetard ? '<span class="retard">· en retard</span>' : d.echeance ? '· ' + relatif(d.echeance) : ''}</span><div>${echeance}</div></div>
              <div class="info-bloc"><span class="discret petit">Ouvert le</span><div>${date(d.ouvert_le)} · risque ${Math.round(100 * d.probabilite_ouverture)} %</div></div>
              <div class="info-bloc"><span class="discret petit">Premier contact</span><div>${d.premier_contact_le ? date(d.premier_contact_le) : '<span class="discret">pas encore</span>'}</div></div>
            </div>
            ${commandes}
          </div>
          <div><div class="sous-titre-bloc">Journal du dossier</div>${chronologie(d)}</div>
        </div>
      </div>
      <dialog class="modale" id="modale-cloture"><form class="carte-corps" data-op="cloture" method="dialog">
        <h2>Clore le dossier</h2>
        <label class="champ-bloc"><span class="lbl">Motif</span><select class="champ" name="motif" required><option value="">Choisir…</option>
          ${Object.entries(f.motifs).map(([k, v]) => `<option value="${k}">${echapper(v)}</option>`).join('')}</select></label>
        <label class="champ-bloc"><span class="lbl">Commentaire (facultatif)</span><textarea class="champ" name="texte" maxlength="4000"></textarea></label>
        <div class="actions" style="justify-content:flex-end"><button class="btn" type="button" data-op="annuler">Annuler</button>
          <button class="btn btn-plein" type="submit">Clore</button></div>
      </form></dialog>
    </section>`;
  }

  function carteSansDossier(f) {
    const p = f.resultat.probabilite_ml;
    const clos = f.dossiers_clos.length ? `<div class="sous-titre-bloc" style="margin-top:16px">Dossiers précédents</div>
      <ul class="limites">${f.dossiers_clos.map((d) => `<li>Du ${date(d.ouvert_le)} au ${date(d.clos_le)} : ${echapper(d.motif || '')}</li>`).join('')}</ul>` : '';
    const message = window.Commun.enAlerte(p)
      ? (f.dossiers_clos.length ? "Le risque reste au-dessus du seuil, mais un dossier a déjà été clos à ce niveau de risque : il ne se rouvre automatiquement que si le risque monte encore de 10 points."
        : "Le risque est au-dessus du seuil d'alerte.")
      : "Le risque est sous le seuil d'alerte : aucun dossier n'est ouvert automatiquement.";
    return `<section class="carte c12" id="carte-dossier"><div class="carte-tete"><h2>Dossier de suivi</h2><span class="statut s-clos">Aucun dossier ouvert</span></div>
      <div class="carte-corps"><p class="texte-court">${message} Vous pouvez en ouvrir un sur signalement (enseignant, demande de l'étudiant…).</p>
        <form class="formulaire-ligne" data-op="ouvrir" style="margin-top:12px">
          <input class="champ" name="texte" maxlength="300" placeholder="Motif de l'ouverture (ex. signalement de l'enseignant de mathématiques)">
          <button class="btn btn-plein" type="submit">Ouvrir un dossier</button></form>${clos}</div></section>`;
  }

  function carteHistorique(f) {
    const lignes = f.historique.slice().reverse().map((h) => `<tr><td>${dateHeure(h.date)}</td><td>${window.Commun.MOMENTS[h.moment]}</td>
      <td class="tnum">${pct(h.probabilite, 1)}</td><td>${h.import ? 'Import' : echapper(h.par || 'Saisie')}</td></tr>`).join('');
    const champs = f.profil.map((p) => {
      const nom = echapper(p.champ);
      if (['Tuition fees up to date', 'Scholarship holder', 'Debtor'].includes(p.champ)) {
        return `<label class="champ-bloc"><span class="lbl">${echapper(p.variable)}</span><select class="champ" name="${nom}">
          <option value="" ${p.brute == null ? 'selected' : ''}>Inconnu</option><option value="1" ${p.brute === 1 ? 'selected' : ''}>Oui</option><option value="0" ${p.brute === 0 ? 'selected' : ''}>Non</option></select></label>`;
      }
      if (p.champ === 'Course') return '';
      return `<label class="champ-bloc"><span class="lbl">${echapper(p.variable)}</span><input class="champ" type="number" step="any" name="${nom}" value="${p.brute ?? ''}"></label>`;
    }).join('');
    const devenir = f.droits.gerer ? `<div class="sous-titre-bloc" style="margin-top:18px">Devenir réel en fin d'année</div>
      <p class="discret petit" style="margin-bottom:8px">Sert à vérifier le modèle sur l'établissement (page Fiabilité). À renseigner une fois connu.</p>
      <div class="formulaire-ligne"><select class="champ" data-op="devenir"><option value="">Pas encore connu</option>
        ${[['Dropout', 'Abandon'], ['Graduate', 'Diplômé'], ['Enrolled', 'Toujours inscrit']].map(([k, v]) => `<option value="${k}" ${f.devenir_reel === k ? 'selected' : ''}>${v}</option>`).join('')}</select></div>
      <div class="sous-titre-bloc" style="margin-top:18px">Conseiller référent</div>
      <p class="discret petit" style="margin-bottom:8px">Les prochains dossiers de cet étudiant lui seront attribués d'office.</p>
      <select class="champ" data-op="referent" style="width:100%"><option value="">Aucun</option>${f.conseillers.map((c) =>
        `<option value="${c.id}" ${f.referent && f.referent.id === c.id ? 'selected' : ''}>${echapper(c.nom)}</option>`).join('')}</select>` : '';
    return `<section class="carte c12"><div class="carte-tete"><h2>Historique et mise à jour</h2></div>
      <div class="carte-corps"><div class="deux-colonnes">
        <div><div class="sous-titre-bloc">Estimations successives</div>
          <div class="tableau-wrap"><table class="simple"><thead><tr><th>Date</th><th>Moment</th><th>Risque</th><th>Origine</th></tr></thead><tbody>${lignes}</tbody></table></div>
          ${devenir}</div>
        <div><div class="sous-titre-bloc">Mettre à jour les résultats</div>
          <p class="discret petit" style="margin-bottom:10px">Par exemple à la fin d'un semestre. Le risque est recalculé, enregistré, et la règle d'alerte s'applique.</p>
          <form data-op="maj"><div class="grille-2">${champs}</div><div style="margin-top:12px"><button class="btn btn-plein" type="submit">Recalculer et enregistrer</button></div></form></div>
      </div></div></section>`;
  }

  const Suivi = {
    rendre(el, f, recharger) {
      el.innerHTML = `<div class="fiche">${f.dossier ? carteDossier(f) : carteSansDossier(f)}</div>`;
      const histo = document.getElementById('historique');
      histo.innerHTML = `<div class="fiche">${carteHistorique(f)}</div>`;
      const base = '/api/dossiers/' + (f.dossier ? f.dossier.id : 0);
      async function faire(url, corps, message) {
        try { await api(url, corps); notifier(message); await recharger(); } catch (e) { notifier(e.message, 'erreur'); }
      }
      const q = (s) => document.querySelector(s);
      if (f.dossier) {
        el.querySelectorAll('[data-op="statut"]').forEach((b) => b.addEventListener('click', () => faire(base + '/statut', { statut: b.dataset.statut }, 'Statut mis à jour.')));
        const choix = q('[data-op="statut-choix"]');
        if (choix) choix.addEventListener('change', () => choix.value && faire(base + '/statut', { statut: choix.value }, 'Statut mis à jour.'));
        const att = q('select[data-op="attribuer"]');
        if (att) att.addEventListener('change', () => faire(base + '/attribution', { conseiller_id: att.value ? Number(att.value) : null }, 'Dossier attribué.'));
        const prendre = q('[data-op="prendre"]');
        if (prendre) prendre.addEventListener('click', () => faire(base + '/attribution', { conseiller_id: window.UTILISATEUR_ID }, 'Dossier pris en charge.'));
        const ech = q('[data-op="echeance"]');
        if (ech) ech.addEventListener('change', () => ech.value && faire(base + '/echeance', { echeance: ech.value }, 'Échéance modifiée.'));
        const form = q('form[data-op="action"]');
        if (form) form.addEventListener('submit', (e) => { e.preventDefault(); faire(base + '/actions', { type: form.type.value, texte: form.texte.value }, 'Action enregistrée.'); });
        const modale = q('#modale-cloture');
        const ouvrir = q('[data-op="ouvrir-cloture"]');
        if (ouvrir) ouvrir.addEventListener('click', () => modale.showModal());
        if (modale) {
          q('[data-op="annuler"]').addEventListener('click', () => modale.close());
          q('form[data-op="cloture"]').addEventListener('submit', (e) => {
            e.preventDefault(); const fo = e.target; modale.close();
            faire(base + '/cloture', { motif: fo.motif.value, texte: fo.texte.value }, 'Dossier clos.');
          });
        }
      } else {
        const fo = q('form[data-op="ouvrir"]');
        fo.addEventListener('submit', (e) => { e.preventDefault(); faire(`/api/etudiants/${f.id}/dossier`, { texte: fo.texte.value }, 'Dossier ouvert.'); });
      }
      const maj = q('form[data-op="maj"]');
      maj.addEventListener('submit', (e) => {
        e.preventDefault(); const corps = {};
        new FormData(maj).forEach((v, k) => { corps[k] = v; });
        faire(`/api/etudiants/${f.id}/evaluations`, corps, 'Résultats enregistrés, risque recalculé.');
      });
      const dev = q('[data-op="devenir"]');
      if (dev) dev.addEventListener('change', () => faire(`/api/etudiants/${f.id}/devenir`, { devenir: dev.value || null }, 'Devenir enregistré.'));
      const ref = q('[data-op="referent"]');
      if (ref) ref.addEventListener('change', () => faire(`/api/etudiants/${f.id}/referent`, { conseiller_id: ref.value ? Number(ref.value) : null }, 'Référent enregistré.'));
    },
  };
  window.Suivi = Suivi;
})();
