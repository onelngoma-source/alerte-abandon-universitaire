/* Administration des comptes. */
(function () {
  'use strict';
  const { echapper, api, dateHeure, notifier } = window.Commun;
  const $ = (id) => document.getElementById(id);
  let comptes = [], edition = null;

  async function charger() {
    comptes = await api('/api/admin/utilisateurs');
    $('comptes').querySelector('tbody').innerHTML = comptes.map((u) => `<tr data-id="${u.id}">
      <td class="etudiant"><b>${echapper(u.nom)}</b><span>${echapper(u.email || '')}</span></td>
      <td>${echapper(u.identifiant)}</td><td>${echapper(u.libelle_role)}</td>
      <td class="petit">${u.derniere_connexion ? dateHeure(u.derniere_connexion) : '<span class="discret">jamais</span>'}</td>
      <td>${u.actif ? (u.doit_changer_mdp ? '<span class="etiquette or">Mot de passe provisoire</span>' : '<span class="badge faible">Actif</span>') : '<span class="etiquette">Désactivé</span>'}</td>
      <td style="text-align:right;white-space:nowrap">${window.DEMO ? '' : `<button class="btn btn-petit" data-op="modifier">Modifier</button>
        <button class="btn btn-petit" data-op="mdp">Nouveau mot de passe</button>
        ${u.id === window.MOI ? '' : `<button class="btn btn-petit ${u.actif ? 'btn-danger' : ''}" data-op="actif">${u.actif ? 'Désactiver' : 'Réactiver'}</button>`}`}</td></tr>`).join('');
  }

  function montrerMdp(nom, mdp) { $('mdp-pour').textContent = nom; $('mdp').textContent = mdp; $('modale-mdp').showModal(); }

  function ouvrir(u) {
    edition = u || null;
    const f = $('form-compte'); f.reset();
    $('titre-modale').textContent = u ? 'Modifier le compte' : 'Nouveau compte';
    $('bloc-identifiant').hidden = Boolean(u); f.identifiant.required = !u;
    if (u) { f.nom.value = u.nom; f.email.value = u.email || ''; f.role.value = u.role; }
    $('erreur-compte').hidden = true; $('modale-compte').showModal();
  }

  $('nouveau').addEventListener('click', () => ouvrir());
  $('annuler').addEventListener('click', () => $('modale-compte').close());
  $('fermer-mdp').addEventListener('click', () => $('modale-mdp').close());
  $('form-compte').addEventListener('submit', async (e) => {
    e.preventDefault(); const f = e.target;
    try {
      if (edition) {
        await api('/api/admin/utilisateurs/' + edition.id, { nom: f.nom.value, email: f.email.value, role: f.role.value });
        $('modale-compte').close(); notifier('Compte modifié.');
      } else {
        const r = await api('/api/admin/utilisateurs', { nom: f.nom.value, identifiant: f.identifiant.value, email: f.email.value, role: f.role.value });
        $('modale-compte').close(); montrerMdp(f.nom.value, r.mot_de_passe_provisoire);
      }
      charger();
    } catch (x) { $('erreur-compte').textContent = x.message; $('erreur-compte').hidden = false; }
  });
  $('comptes').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-op]'); if (!b) return;
    const u = comptes.find((x) => x.id === Number(b.closest('tr').dataset.id));
    try {
      if (b.dataset.op === 'modifier') ouvrir(u);
      if (b.dataset.op === 'mdp' && confirm(`Générer un nouveau mot de passe provisoire pour ${u.nom} ?`)) {
        const r = await api(`/api/admin/utilisateurs/${u.id}/reinitialiser`, {}); montrerMdp(u.nom, r.mot_de_passe_provisoire); charger();
      }
      if (b.dataset.op === 'actif') {
        if (u.actif && !confirm(`Désactiver le compte de ${u.nom} ? Ses dossiers ouverts redeviendront non attribués.`)) return;
        await api('/api/admin/utilisateurs/' + u.id, { actif: !u.actif }); notifier(u.actif ? 'Compte désactivé.' : 'Compte réactivé.'); charger();
      }
    } catch (x) { notifier(x.message, 'erreur'); }
  });
  charger();
})();
