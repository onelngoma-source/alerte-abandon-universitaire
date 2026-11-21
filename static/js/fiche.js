/* Rendu de l'explication d'un etudiant, partage par la fiche et par la saisie.
   Les donnees viennent du serveur (/api/etudiants/<id> ou /api/predict) ; ici, on ne fait qu'afficher. */
(function () {
  'use strict';
  const { echapper, pct, niveau, enAlerte, badge, jauge, NIVEAUX, MOMENTS, MOMENTS_COURTS } = window.Commun;

  const ICONES = {
    academique: '<path d="M22 10L12 5 2 10l10 5 10-5z"/><path d="M6 12v5c3 2 9 2 12 0v-5"/>',
    financier: '<rect x="2" y="6" width="20" height="13" rx="2"/><path d="M2 10h20"/><path d="M6 15h4"/>',
    social: '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0 1 13 0"/><path d="M17 11a3 3 0 1 0 0-6"/><path d="M21.5 20a5.5 5.5 0 0 0-4-5.3"/>',
    aucun: '<path d="M20 6L9 17l-5-5"/>',
  };
  const svg = (contenu, t = 17) => `<svg width="${t}" height="${t}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${contenu}</svg>`;

  function phraseRisque(r) {
    const p = r.probabilite_ml;
    if (!enAlerte(p)) return "Risque sous le seuil d'alerte : aucun accompagnement particulier n'est déclenché.";
    const un_sur = Math.max(1, Math.round(1 / p));
    const proportion = p >= 0.5 ? `plus d'une chance sur deux` : `environ 1 chance sur ${un_sur}`;
    return `<b>En alerte.</b> Parmi les étudiants passés au profil semblable, ${proportion} d'abandonner : un accompagnement est recommandé.`;
  }

  function carteRisque(r) {
    const p = r.probabilite_ml, n = niveau(p);
    const estimees = r.nb_variables_estimees
      ? `<span class="etiquette" title="Valeurs absentes du dossier, remplacées par la valeur la plus courante">${r.nb_variables_estimees} information${r.nb_variables_estimees > 1 ? 's' : ''} complétée${r.nb_variables_estimees > 1 ? 's' : ''}</span>` : '';
    return `<section class="carte c5"><div class="carte-corps">
      <div class="sous-titre-bloc">Risque d'abandon</div>
      <div class="risque-grand"><span class="chiffre tnum">${(100 * p).toLocaleString('fr-FR', { maximumFractionDigits: 1 })}<small> %</small></span>${badge(p)}</div>
      ${jauge(p, true)}
      <div class="seuils-legende"><span style="left:0;transform:none">0</span><span style="left:16.67%">alerte 1/6</span><span style="left:50%">élevé 50 %</span><span style="left:100%;transform:translateX(-100%)">100 %</span></div>
      <p class="phrase-risque">${phraseRisque(r)}</p>
      <div class="meta-risque"><span class="etiquette or">Estimé ${echapper(r.libelle_moment)}</span>${estimees}</div>
    </div></section>`;
  }

  function carteTrajectoire(r) {
    const points = r.trajectoire || [];
    const W = 600, H = 150, L = W - 40, x = (i) => W * (2 * i + 1) / 6, y = (p) => 10 + (1 - p) * (H - 20);
    const bandes = `<rect x="0" y="${y(1)}" width="${L + 40}" height="${y(0.5) - y(1)}" fill="#FCEBEB"/>
      <rect x="0" y="${y(0.5)}" width="${L + 40}" height="${y(1 / 6) - y(0.5)}" fill="#FFF4DB"/>
      <rect x="0" y="${y(1 / 6)}" width="${L + 40}" height="${y(0) - y(1 / 6)}" fill="#E7F6EA"/>`;
    const trace = points.length > 1 ? `<polyline points="${points.map((p, i) => `${x(i)},${y(p.probabilite)}`).join(' ')}" fill="none" stroke="#0D3863" stroke-width="2.5" stroke-linejoin="round"/>` : '';
    const cercles = points.map((p, i) => `<circle cx="${x(i)}" cy="${y(p.probabilite)}" r="6" fill="#fff" stroke="#0D3863" stroke-width="2.5"/>`).join('');
    const futurs = [0, 1, 2].slice(points.length).map((i) => `<line x1="${x(i)}" x2="${x(i)}" y1="${y(0.95)}" y2="${y(0.05)}" stroke="#CED6DF" stroke-dasharray="3 4"/>`).join('');
    const etapes = ['T0', 'T1', 'T2'].map((m, i) => {
      const p = points[i];
      return p ? `<div class="etape-traj"><b class="tnum">${Math.round(100 * p.probabilite)} %</b>${MOMENTS[m]}</div>`
        : `<div class="etape-traj future"><b>à venir</b>${MOMENTS[m]}</div>`;
    }).join('');
    let commentaire = "Seule l'information de l'inscription est connue : le risque sera réévalué à la fin de chaque semestre.";
    if (points.length > 1) {
      const ecart = Math.round(100 * (points[points.length - 1].probabilite - points[0].probabilite));
      commentaire = ecart > 2 ? `Le risque a <b>augmenté de ${ecart} points</b> depuis l'inscription : les résultats de l'année pèsent dans le mauvais sens.`
        : ecart < -2 ? `Le risque a <b>baissé de ${-ecart} points</b> depuis l'inscription : les résultats de l'année rassurent.`
          : "Le risque est resté stable depuis l'inscription.";
    }
    return `<section class="carte c7 trajectoire"><div class="carte-corps">
      <div class="sous-titre-bloc">Évolution au fil de l'année</div>
      <svg viewBox="0 0 ${L + 40} ${H}" role="img" aria-label="Évolution du risque">${bandes}${futurs}${trace}${cercles}</svg>
      <div class="etapes-traj">${etapes}</div>
      <p class="phrase-risque petit">${commentaire}</p>
    </div></section>`;
  }

  function listeFacteurs(liste, sens) {
    if (!liste.length) return `<p class="discret petit">Aucun facteur notable dans ce sens.</p>`;
    return `<ul class="facteurs ${sens}">${liste.map((f) => `<li>
      <span class="texte">${echapper(f.texte)}</span>
      <span class="sous"><span class="etiquette">${echapper(f.libelle_domaine)}</span>${f.levier ? '<span class="levier">Levier d\'action</span>' : ''}</span>
      <span class="force">${f.intensite}<span class="piste"><i style="width:${Math.min(100, Math.abs(f.contribution) / 1.5 * 100)}%"></i></span></span>
    </li>`).join('')}</ul>`;
  }

  function carteFacteurs(r, compact) {
    return `<section class="carte c12"><div class="carte-tete"><h2>Pourquoi ce niveau de risque</h2>
        <span class="discret">comparé à un étudiant moyen des cohortes 2008 à 2014</span></div>
      <div class="carte-corps"><div class="${compact ? '' : 'deux-colonnes'}">
        <div><div class="sous-titre-bloc"><span class="point eleve"></span>Ce qui augmente le risque</div>${listeFacteurs(r.facteurs_hausse || [], 'hausse')}</div>
        <div${compact ? ' style="margin-top:16px"' : ''}><div class="sous-titre-bloc"><span class="point faible"></span>Ce qui le réduit</div>${listeFacteurs(r.facteurs_baisse || [], 'baisse')}</div>
      </div></div></section>`;
  }

  function cartePistes(conseils, classe) {
    return `<section class="carte ${classe}"><div class="carte-tete"><h2>Pistes d'accompagnement</h2></div>
      <div class="carte-corps"><ul class="pistes">${conseils.map((c) => `<li data-type="${c.type}">
        <span class="ico">${svg(ICONES[c.type] || ICONES.aucun)}</span>
        <div><b>${echapper(c.titre || '')}</b><p>${echapper(c.message)}</p></div></li>`).join('')}</ul></div></section>`;
  }

  function carteVoisins(r, classe) {
    const v = r.voisins_noyau; if (!v) return '';
    const k = v.abandons_parmi_plus_proches, n = v.plus_proches.length;
    const lignes = v.plus_proches.map((l) => `<tr><td>${l.rang}</td>${l.valeurs.map((x) => `<td class="tnum">${echapper(typeof x === 'number' ? x.toLocaleString('fr-FR') : x)}</td>`).join('')}
      <td>${l.cohorte}</td><td>${l.abandon ? '<span class="badge eleve">Abandon</span>' : '<span class="badge faible">Poursuite</span>'}</td></tr>`).join('');
    return `<section class="carte ${classe}"><div class="carte-tete"><h2>Étudiants passés au profil proche</h2></div>
      <div class="carte-corps">
        <div class="voisins-resume"><div class="pastilles-voisins">${v.plus_proches.map((l) => `<i class="${l.abandon ? 'abandon' : 'reussite'}" title="${l.abandon ? 'Abandon' : 'Poursuite'}">${l.abandon ? '✕' : '✓'}</i>`).join('')}</div>
          <p><b>${k} sur ${n}</b> ont abandonné.</p></div>
        <p class="discret petit" style="margin-top:10px">Les ${n} étudiants des cohortes 2008 à 2014 dont le dossier, ${echapper(r.libelle_moment)}, ressemble le plus à celui-ci (approche à noyau de Nadaraya-Watson, sujet du mémoire). Un point de comparaison concret, à côté de l'estimation.</p>
        <details class="depli"><summary>Voir leurs dossiers</summary>
          <div class="tableau-wrap"><table class="simple"><thead><tr><th>#</th>${v.colonnes.map((c) => `<th>${echapper(c)}</th>`).join('')}<th>Cohorte</th><th>Devenir</th></tr></thead><tbody>${lignes}</tbody></table></div>
        </details>
      </div></section>`;
  }

  function carteDossier(profil) {
    if (!profil) return '';
    return `<section class="carte c12"><div class="carte-tete"><h2>Dossier de l'étudiant</h2><span class="discret">Informations principales</span></div>
      <div class="carte-corps"><dl class="dossier">${profil.map((p) => `<div><dt>${echapper(p.variable)}</dt>
        <dd class="${p.fournie ? '' : 'absent'}">${p.fournie ? echapper(p.valeur) : 'non renseigné'}</dd></div>`).join('')}</dl></div></section>`;
  }

  function encarts(d) {
    let html = '';
    const r = d.resultat || d;
    if (d.devenir) {
      const alerte = enAlerte(r.probabilite_ml);
      const juste = alerte === (d.abandon_reel === 1);
      html += `<div class="encart c12">${svg('<circle cx="12" cy="12" r="9"/><path d="M12 8h.01"/><path d="M11 12h1v4h1"/>', 18)}
        <div>Cohorte passée : le devenir réel de cet étudiant est connu, <b>${echapper(d.devenir)}</b>.
        ${alerte ? "L'outil l'avait placé en alerte" : "L'outil ne l'avait pas placé en alerte"} : ${juste ? 'estimation conforme au devenir réel.' : 'estimation non conforme au devenir réel.'}</div></div>`;
    }
    (d.avertissements || []).forEach((a) => {
      html += `<div class="encart or c12">${svg('<path d="M12 3l10 18H2z"/><path d="M12 10v4"/><path d="M12 17h.01"/>', 18)}<div>${echapper(a)}</div></div>`;
    });
    return html;
  }

  function rendre(el, d, options = {}) {
    const r = d.resultat || d;
    const compact = !!options.compact;
    if (compact) {
      el.innerHTML = `<div class="fiche">${encarts(d)}${carteRisque(r).replace('c5', 'c12')}${carteTrajectoire(r).replace('c7', 'c12')}
        ${carteFacteurs(r, true)}${cartePistes(d.conseils || [], 'c12')}${carteVoisins(r, 'c12')}</div>`;
    } else {
      el.innerHTML = `<div class="fiche">${encarts(d)}${carteRisque(r)}${carteTrajectoire(r)}${carteFacteurs(r, false)}
        ${cartePistes(d.conseils || [], 'c7')}${carteVoisins(r, 'c5')}${carteDossier(d.profil)}</div>`;
    }
  }

  window.Fiche = { rendre };
})();
