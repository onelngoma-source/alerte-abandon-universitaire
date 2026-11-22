/* Pilotage : indicateurs de suivi des alertes, calcules par le serveur. */
(function () {
  'use strict';
  const { echapper, nombre, pct, api, notifier } = window.Commun;
  const $ = (id) => document.getElementById(id);

  function barres(liste, total) {
    if (!liste.length) return '<p class="discret petit">Rien à afficher pour l\'instant.</p>';
    const max = total || Math.max(...liste.map((x) => x.nombre));
    return liste.map((x) => `<div class="barre-ligne"><span class="nom">${echapper(x.libelle)}</span><span class="val">${nombre(x.nombre)}</span>
      <span class="piste"><i style="width:${100 * x.nombre / Math.max(max, 1)}%"></i></span></div>`).join('');
  }

  async function charger() {
    let d;
    try { d = await api('/api/pilotage' + ($('promotion').value ? '?promotion=' + $('promotion').value : '')); }
    catch (e) { notifier(e.message, 'erreur'); return; }
    const delai = d.delai_median_jours === null ? '–' : String(d.delai_median_jours).replace('.', ',') + ' j';
    $('kpis').innerHTML = `
      <a class="carte indicateur accent" href="/dossiers?vue=ouverts" style="text-decoration:none"><div class="libelle">Dossiers ouverts</div><div class="valeur tnum">${nombre(d.ouverts)}</div><div class="detail">${nombre(d.clos)} clos</div></a>
      <a class="carte indicateur" href="/dossiers?vue=non_attribues" style="text-decoration:none"><div class="libelle"><span class="point moyen"></span>Non attribués</div><div class="valeur tnum">${nombre(d.non_attribues)}</div><div class="detail">à répartir entre les conseillers</div></a>
      <a class="carte indicateur" href="/dossiers?vue=retard" style="text-decoration:none"><div class="libelle"><span class="point eleve"></span>En retard</div><div class="valeur tnum">${nombre(d.en_retard)}</div><div class="detail">échéance dépassée · ${nombre(d.a_revoir)} risque(s) en hausse</div></a>
      <div class="carte indicateur"><div class="libelle">Délai avant premier contact</div><div class="valeur tnum">${delai}</div>
        <div class="detail">médiane · ${d.part_contactes_a_temps === null ? '–' : pct(d.part_contactes_a_temps)} contactés en ${d.delai_cible_jours} jours ou moins</div></div>`;
    $('charge').innerHTML = `<thead><tr><th>Conseiller</th><th>Ouverts</th><th>En retard</th><th>En hausse</th><th>Clos (30 j)</th></tr></thead><tbody>`
      + (d.charge.length ? d.charge.map((c) => `<tr><td>${echapper(c.nom)}${c.actif ? '' : ' <span class="etiquette">désactivé</span>'}</td><td class="tnum">${c.ouverts}</td>
        <td class="tnum ${c.en_retard ? 'faible-detection' : ''}">${c.en_retard}</td><td class="tnum">${c.a_revoir}</td><td class="tnum">${c.clos_30j}</td></tr>`).join('')
        : '<tr><td colspan="5" class="discret">Aucun conseiller : créez des comptes dans « Comptes ».</td></tr>') + '</tbody>';
    $('statuts').innerHTML = barres(d.par_statut);
    $('actions').innerHTML = barres(d.actions_90j);
    $('motifs').innerHTML = barres(d.motifs);
    const a = d.resultats.accompagnes, s = d.resultats.alertes_sans_entretien;
    $('resultats').innerHTML = (a.effectif + s.effectif) === 0
      ? `<p class="texte-court">Le devenir réel des étudiants suivis n'est pas encore connu. Renseignez-le en fin d'année (fichier avec une colonne « devenir », ou sur chaque fiche).</p>`
      : `<p class="texte-court">Taux d'abandon parmi les étudiants alertés dont le devenir est connu :</p>
        <div class="barres" style="margin-top:12px">
          <div class="barre-ligne"><span class="nom">Entretien ou accompagnement (${nombre(a.effectif)})</span><span class="val">${a.taux_abandon === null ? '–' : pct(a.taux_abandon)}</span><span class="piste"><i style="width:${100 * (a.taux_abandon || 0)}%"></i></span></div>
          <div class="barre-ligne"><span class="nom">Sans entretien (${nombre(s.effectif)})</span><span class="val">${s.taux_abandon === null ? '–' : pct(s.taux_abandon)}</span><span class="piste"><i class="or" style="width:${100 * (s.taux_abandon || 0)}%"></i></span></div>
        </div>
        <p class="discret petit" style="margin-top:12px">À lire avec prudence : les deux groupes ne sont pas comparables (les étudiants joignables ou volontaires ne sont pas les autres). Ce n'est pas une mesure de l'effet de l'accompagnement.</p>`;
  }
  $('promotion').addEventListener('change', charger);
  charger();
})();
