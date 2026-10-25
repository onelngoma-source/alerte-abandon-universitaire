/* Bloc d'analyse d'une cohorte (indicateurs, filtres, graphiques, tableau).
   Un seul script pour le tableau de bord ET pour l'import CSV : le rendu est donc identique. */
(function () {
  const NIVEAUX = { faible: 'Faible', moyen: 'Moyen', eleve: 'Élevé' };
  const COULEURS = { faible: '#2fb344', moyen: '#f59f00', eleve: '#d63939' };
  const COLONNES = [
    { cle: 'reference', titre: 'Référence', type: 'texte' },
    { cle: 'filiere', titre: 'Filière', type: 'texte' },
    { cle: 'genre', titre: 'Genre', type: 'texte' },
    { cle: 'age', titre: 'Âge', type: 'num' },
    { cle: 'boursier', titre: 'Boursier', type: 'ouinon' },
    { cle: 'debiteur', titre: 'Débiteur', type: 'ouinon' },
    { cle: 'frais_a_jour', titre: 'Frais à jour', type: 'ouinon' },
    { cle: 'note_s1', titre: 'Moy. S1', type: 'num' },
    { cle: 'note_s2', titre: 'Moy. S2', type: 'num' },
    { cle: 'devenir', titre: 'Devenir réel', type: 'texte' },
    { cle: 'p_noyau', titre: 'Noyau', type: 'risque', cat: 'c_noyau' },
    { cle: 'p_ml', titre: 'Random Forest', type: 'risque', cat: 'c_ml' },
  ];

  const echapper = (t) => String(t).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const f3 = (x) => (x === null || x === undefined ? '-' : Number(x).toFixed(3).replace('.', ','));
  const pct = (a, b) => (b ? (100 * a / b).toFixed(1).replace('.', ',') + ' %' : '-');
  const nombre = (n) => Number(n).toLocaleString('fr-FR');

  function devenirLibelle(l) {
    if (l.devenir_reel === 'Dropout') return 'Abandon';
    if (l.devenir_reel === 'Graduate') return 'Diplômé';
    if (l.devenir_reel === 'Enrolled') return 'Inscrit';
    if (l.abandon_reel === 1) return 'Abandon';
    if (l.abandon_reel === 0) return 'Pas d\'abandon';
    return null;
  }

  function monter(racine) {
    const $ = (s) => racine.querySelector(s);
    const $$ = (s) => Array.from(racine.querySelectorAll(s));
    const etat = { lignes: [], tri: { cle: 'p_ml', sens: -1 }, page: 1, taille: 20, graph: {}, nom: 'cohorte' };

    $('[data-role="entetes"]').innerHTML = COLONNES.map((c) =>
      `<th data-tri="${c.cle}" class="${c.type === 'num' ? 'num' : ''}">${c.titre}</th>`).join('');

    function lireFiltres() {
      const f = {};
      $$('[data-filtre]').forEach((el) => { f[el.dataset.filtre] = el.type === 'checkbox' ? el.checked : el.value.trim(); });
      return f;
    }

    function filtrer() {
      const f = lireFiltres();
      const q = f.q.toLowerCase();
      return etat.lignes.filter((l) => {
        if (q && !l.reference.toLowerCase().includes(q)) return false;
        if (f.filiere && l.filiere !== f.filiere) return false;
        if (f.genre && l.genre !== f.genre) return false;
        for (const k of ['boursier', 'debiteur', 'frais_a_jour', 'abandon_reel']) {
          if (f[k] !== '' && String(l[k]) !== f[k]) return false;
        }
        if (f.c_noyau && l.c_noyau !== f.c_noyau) return false;
        if (f.c_ml && l.c_ml !== f.c_ml) return false;
        if (f.age_min !== '' && (l.age === null || l.age < Number(f.age_min))) return false;
        if (f.age_max !== '' && (l.age === null || l.age > Number(f.age_max))) return false;
        if (f.desaccord && l.c_noyau === l.c_ml) return false;
        return true;
      });
    }

    function trier(lignes) {
      const { cle, sens } = etat.tri;
      const valeur = (l) => (cle === 'devenir' ? devenirLibelle(l) : l[cle]);
      return lignes.slice().sort((a, b) => {
        const va = valeur(a), vb = valeur(b);
        if (va === null || va === undefined) return 1;
        if (vb === null || vb === undefined) return -1;
        if (typeof va === 'number') return (va - vb) * sens;
        return String(va).localeCompare(String(vb), 'fr', { numeric: true }) * sens;
      });
    }

    function cellule(c, l) {
      if (c.type === 'ouinon') return l[c.cle] === null ? '-' : (l[c.cle] === 1 ? 'Oui' : 'Non');
      if (c.type === 'num') return l[c.cle] === null ? '-' : String(l[c.cle]).replace('.', ',');
      if (c.type === 'risque') {
        const p = Math.round(Math.max(0, Math.min(1, l[c.cle])) * 100);
        const couleur = { eleve: 'var(--risque-eleve)', moyen: 'var(--risque-moyen)', faible: 'var(--risque-faible)' }[l[c.cat]];
        return `<span class="jauge"><i style="width:${p}%;background:${couleur}"></i></span>`
          + `<span class="score">${f3(l[c.cle])}</span><span class="badge badge-risque risque-${l[c.cat]}">${NIVEAUX[l[c.cat]]}</span>`;
      }
      if (c.cle === 'devenir') return devenirLibelle(l) || '-';
      if (c.cle === 'reference') {
        return echapper(l.reference) + (l.mode === 'precoce' ? ' <span class="badge bg-blue-lt ref-precoce" title="Estimation faite sans les résultats du 2e semestre">1er sem.</span>' : '');
      }
      return l[c.cle] === null ? '-' : echapper(l[c.cle]);
    }

    function rendreTableau(lignes) {
      const triees = trier(lignes);
      const nbPages = Math.max(1, Math.ceil(triees.length / etat.taille));
      etat.page = Math.min(etat.page, nbPages);
      const debut = (etat.page - 1) * etat.taille;
      const visibles = triees.slice(debut, debut + etat.taille);
      $('[data-role="corps"]').innerHTML = visibles.length
        ? visibles.map((l) => `<tr data-id="${l.id}" class="ligne-cliquable" tabindex="0" title="Ouvrir la fiche d'explication">` + COLONNES.map((c) => `<td class="${c.type === 'num' ? 'num' : ''}">${cellule(c, l)}</td>`).join('') + '</tr>').join('')
        : `<tr><td colspan="${COLONNES.length}" class="text-center text-secondary py-4">Aucun étudiant ne correspond aux filtres.</td></tr>`;
      $$('th[data-tri]').forEach((th) => {
        th.classList.toggle('tri-asc', th.dataset.tri === etat.tri.cle && etat.tri.sens === 1);
        th.classList.toggle('tri-desc', th.dataset.tri === etat.tri.cle && etat.tri.sens === -1);
      });
      $('[data-role="pagination-info"]').textContent = triees.length
        ? `Étudiants ${nombre(debut + 1)} à ${nombre(debut + visibles.length)} sur ${nombre(triees.length)}` : '';
      const pages = [];
      for (let p = 1; p <= nbPages; p++) if (p === 1 || p === nbPages || Math.abs(p - etat.page) <= 2) pages.push(p);
      let html = `<li class="page-item ${etat.page === 1 ? 'disabled' : ''}"><a class="page-link" href="#" data-page="${etat.page - 1}">Précédent</a></li>`;
      let precedent = 0;
      pages.forEach((p) => {
        if (p - precedent > 1) html += '<li class="page-item disabled"><span class="page-link">…</span></li>';
        html += `<li class="page-item ${p === etat.page ? 'active' : ''}"><a class="page-link" href="#" data-page="${p}">${p}</a></li>`;
        precedent = p;
      });
      html += `<li class="page-item ${etat.page === nbPages ? 'disabled' : ''}"><a class="page-link" href="#" data-page="${etat.page + 1}">Suivant</a></li>`;
      $('[data-role="pagination"]').innerHTML = html;
    }

    const NIV = ['faible', 'moyen', 'eleve'];
    const COULEUR_NIV = { faible: 'var(--risque-faible)', moyen: 'var(--risque-moyen)', eleve: 'var(--risque-eleve)' };

    function rendreIndicateurs(lignes, total) {
      const etiquetees = lignes.filter((l) => l.abandon_reel !== null);
      const abandons = etiquetees.filter((l) => l.abandon_reel === 1).length;
      const set = (cle, v) => { const el = $(`[data-kpi="${cle}"]`); if (el) el.textContent = v; };
      const largeur = (cle, v) => { const el = $(`[data-kpi="${cle}"]`); if (el) el.style.width = v + '%'; };
      const part = (x) => (lignes.length ? 100 * x / lignes.length : 0);

      set('effectif', nombre(lignes.length));
      largeur('effectif-barre', total ? 100 * lignes.length / total : 0);
      set('effectif-sous', lignes.length === total
        ? 'toute la cohorte, aucun filtre actif'
        : `${Math.round(total ? 100 * lignes.length / total : 0)} % de la cohorte`);

      set('abandons', etiquetees.length ? nombre(abandons) : 'n/d');
      largeur('abandons-barre', etiquetees.length ? 100 * abandons / etiquetees.length : 0);
      set('abandons-sous', etiquetees.length
        ? pct(abandons, etiquetees.length) + ' de la sélection'
        : 'devenir réel non fourni');

      [['c_noyau', 'noyau'], ['c_ml', 'ml']].forEach(([cat, nom]) => {
        const compte = {};
        NIV.forEach((n) => { compte[n] = lignes.filter((l) => l[cat] === n).length; });
        set('eleve-' + (nom === 'ml' ? 'ml' : 'noyau'), nombre(compte.eleve));
        const jauge = $(`[data-kpi="${nom}-jauge"]`);
        if (jauge) jauge.innerHTML = NIV.map((n) =>
          `<i style="width:${part(compte[n])}%;background:${COULEUR_NIV[n]}"></i>`).join('');
        const legende = $(`[data-kpi="${nom}-legende"]`);
        if (legende) legende.innerHTML = NIV.map((n) =>
          `<span><i class="pastille" style="background:${COULEUR_NIV[n]}"></i>${nombre(compte[n])}</span>`).join('');
      });
    }

    /* --- modèle de référence : il décide du tri du tableau, du filtre de
       niveau et du graphique par filière. Le second modèle reste visible dans
       sa colonne et garde son propre filtre dans le tiroir. --- */
    const NOM_MODELE = { ml: 'Random Forest', noyau: 'approche à noyau' };
    const modeleChoisi = () => ($('[data-role="modele-filiere"]').value === 'noyau' ? 'noyau' : 'ml');
    const catModele = () => (modeleChoisi() === 'noyau' ? 'c_noyau' : 'c_ml');
    const proModele = () => (modeleChoisi() === 'noyau' ? 'p_noyau' : 'p_ml');

    function appliquerModele() {
      const m = modeleChoisi();
      $('[data-role="niveaux"]').setAttribute('aria-label', 'Niveau de risque, ' + NOM_MODELE[m]);
      $('[data-role="legende-filiere"]').textContent =
        (m === 'ml' ? 'Random Forest' : 'Approche à noyau') + ' · sélection courante';
      $('[data-role="ancre-ml"]').hidden = m !== 'ml';
      $('[data-role="ancre-noyau"]').hidden = m !== 'noyau';
      $('[data-role="ind-ml"]').dataset.reference = m === 'ml' ? 'oui' : 'non';
      $('[data-role="ind-noyau"]').dataset.reference = m === 'noyau' ? 'oui' : 'non';
      // le raccourci de niveau suit le modèle : on déplace la valeur d'un select à l'autre
      const vise = $(`[data-filtre="${catModele()}"]`);
      const autre = $(`[data-filtre="${m === 'noyau' ? 'c_ml' : 'c_noyau'}"]`);
      if (autre.value && !vise.value) { vise.value = autre.value; autre.value = ''; }
      majNiveaux();
    }

    function majNiveaux() {
      const valeur = $(`[data-filtre="${catModele()}"]`).value;
      $$('[data-role="niveaux"] button').forEach((b) =>
        b.setAttribute('aria-pressed', String(b.dataset.n === valeur)));
    }

    /* --- puces des filtres actifs --- */
    const LIBELLES = { q: 'Référence', filiere: 'Filière', genre: 'Genre', abandon_reel: 'Devenir',
      age_min: 'Âge ≥', age_max: 'Âge ≤', boursier: 'Boursier', debiteur: 'Débiteur',
      frais_a_jour: 'Frais à jour', c_noyau: 'Risque · noyau', c_ml: 'Risque · Random Forest' };
    function lisible(cle, v) {
      if (['boursier', 'debiteur', 'frais_a_jour'].includes(cle)) return v === '1' ? 'oui' : 'non';
      if (cle === 'abandon_reel') return v === '1' ? 'abandon' : 'pas d\'abandon';
      if (cle === 'c_noyau' || cle === 'c_ml') return NIVEAUX[v];
      return v;
    }
    function rendrePuces() {
      const zone = $('[data-role="puces"]');
      zone.innerHTML = '';
      let n = 0;
      $$('[data-filtre]').forEach((el) => {
        const cle = el.dataset.filtre;
        const actif = el.type === 'checkbox' ? el.checked : el.value.trim() !== '';
        if (!actif) return;
        n++;
        const texte = cle === 'desaccord' ? 'Estimations divergentes'
          : `${LIBELLES[cle] || cle} : ${lisible(cle, el.value.trim())}`;
        const puce = document.createElement('span');
        puce.className = 'puce';
        puce.append(texte);
        const croix = document.createElement('button');
        croix.type = 'button'; croix.textContent = '×';
        croix.setAttribute('aria-label', 'Retirer le filtre ' + texte);
        croix.addEventListener('click', () => {
          if (el.type === 'checkbox') el.checked = false; else el.value = '';
          etat.page = 1; majNiveaux(); rendreTout();
        });
        puce.append(croix);
        zone.append(puce);
      });
      const compteur = $('[data-role="compteur-filtres"]');
      compteur.hidden = n === 0; compteur.textContent = n;
      $('[data-role="ouvrir-tiroir"]').classList.toggle('charge', n > 0);
      const total = etat.lignes.length;
      const vus = filtrer().length;
      $('[data-role="compte"]').innerHTML = `<b>${nombre(vus)}</b> étudiant${vus > 1 ? 's' : ''} sur ${nombre(total)}`
        + (n ? ` · ${n} filtre${n > 1 ? 's' : ''} actif${n > 1 ? 's' : ''}` : '');
    }

    function rendreGraphiques(lignes) {
      const niveaux = ['faible', 'moyen', 'eleve'];
      const compter = (cat) => niveaux.map((n) => lignes.filter((l) => l[cat] === n).length);
      majGraphique('repartition', {
        labels: niveaux.map((n) => NIVEAUX[n]),
        datasets: [
          { label: 'Noyau', data: compter('c_noyau'), backgroundColor: '#3281E0' },
          { label: 'Random Forest', data: compter('c_ml'), backgroundColor: '#0D3863' },
        ],
      }, { y: { beginAtZero: true, ticks: { precision: 0 } } });
      if (etat.avecDevenir) {
        const taux = (cat) => niveaux.map((n) => {
          const g = lignes.filter((l) => l[cat] === n && l.abandon_reel !== null);
          return g.length ? Math.round(1000 * g.filter((l) => l.abandon_reel === 1).length / g.length) / 10 : null;
        });
        majGraphique('calibration', {
          labels: niveaux.map((n) => NIVEAUX[n]),
          datasets: [
            { label: 'Noyau', data: taux('c_noyau'), backgroundColor: '#3281E0' },
            { label: 'Random Forest', data: taux('c_ml'), backgroundColor: '#0D3863' },
          ],
        }, { y: { beginAtZero: true, max: 100, title: { display: true, text: '% d\'abandons réels' } } });
      }
    }

    function rendreGraphiqueFiliere(lignes) {
      const cat = $('[data-role="modele-filiere"]').value === 'noyau' ? 'c_noyau' : 'c_ml';
      const niveaux = ['faible', 'moyen', 'eleve'];
      const groupes = {};
      lignes.forEach((l) => { const k = l.filiere || 'Non renseignée'; (groupes[k] = groupes[k] || []).push(l); });
      const parts = Object.entries(groupes).map(([nom, g]) => {
        const n = niveaux.map((v) => g.filter((l) => l[cat] === v).length);
        return { nom, total: g.length, n, pct: n.map((x) => 100 * x / g.length) };
      }).sort((a, b) => b.pct[2] - a.pct[2] || b.total - a.total);
      const zone = $('[data-role="zone-filiere"]');
      zone.style.height = Math.max(160, parts.length * 28 + 70) + 'px';
      if (etat.graph.filiere) etat.graph.filiere.destroy();
      const couleurs = { faible: '#2fb344', moyen: '#f59f00', eleve: '#d63939' };
      etat.graph.filiere = new Chart($('[data-role="graphique-filiere"]'), {
        type: 'bar',
        data: {
          labels: parts.map((p) => `${p.nom} (${p.total})`),
          datasets: niveaux.map((v, i) => ({ label: NIVEAUX[v], data: parts.map((p) => Math.round(p.pct[i] * 10) / 10), counts: parts.map((p) => p.n[i]), backgroundColor: couleurs[v] })),
        },
        options: {
          indexAxis: 'y', responsive: true, maintainAspectRatio: false, animation: false,
          scales: { x: { stacked: true, max: 100, title: { display: true, text: '% des étudiants de la filière' } }, y: { stacked: true } },
          plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { label: (c) => `${c.dataset.label} : ${c.dataset.counts[c.dataIndex]} étudiants (${String(c.parsed.x).replace('.', ',')} %)` } } },
        },
      });
    }

    function majGraphique(nom, donnees, echelles) {
      const canvas = $(`[data-role="graphique-${nom}"]`);
      if (etat.graph[nom]) {
        etat.graph[nom].data = donnees; etat.graph[nom].update();
        return;
      }
      etat.graph[nom] = new Chart(canvas, {
        type: 'bar', data: donnees,
        options: { responsive: true, maintainAspectRatio: false, animation: false, scales: echelles,
                   plugins: { legend: { position: 'bottom' } } },
      });
    }

    function rendreTout() {
      const lignes = filtrer();
      rendreIndicateurs(lignes, etat.lignes.length);
      rendreGraphiques(lignes);
      rendreGraphiqueFiliere(lignes);
      rendreTableau(lignes);
      rendrePuces();
    }

    function rendrePerformances(donnees) {
      const m = donnees.metriques || {};
      const bloc = $('[data-role="performances"]');
      bloc.hidden = !m.noyau;
      if (!m.noyau) return;
      $('[data-role="performances-sous"]').textContent = '';
      const ligne = (nom, cle) => {
        const v = m[cle];
        return `<tr><td>${nom}</td><td class="num">${f3(v.auc)}</td><td class="num">${f3(v.exactitude)}</td><td class="num">${f3(v.f1)}</td></tr>`;
      };
      $('[data-role="performances-corps"]').innerHTML = ligne('Approche à noyau', 'noyau') + ligne('Random Forest', 'ml');
    }

    function exporter() {
      const lignes = trier(filtrer());
      const entetes = COLONNES.flatMap((c) => c.type === 'risque' ? [`${c.titre} (probabilité)`, `${c.titre} (niveau)`] : [c.titre]);
      const brut = (l, c) => {
        if (c.type === 'risque') return [String(l[c.cle]).replace('.', ','), NIVEAUX[l[c.cat]]];
        if (c.type === 'ouinon') return [l[c.cle] === null ? '' : (l[c.cle] === 1 ? 'Oui' : 'Non')];
        if (c.cle === 'devenir') return [devenirLibelle(l) || ''];
        return [l[c.cle] === null ? '' : String(l[c.cle]).replace('.', ',')];
      };
      const csv = [entetes.join(';')].concat(lignes.map((l) => COLONNES.flatMap((c) => brut(l, c)).map((v) => `"${v.replace(/"/g, '""')}"`).join(';'))).join('\r\n');
      const lien = document.createElement('a');
      lien.href = URL.createObjectURL(new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8' }));
      lien.download = `${etat.nom.replace(/[^\w-]+/g, '_')}_selection.csv`;
      lien.click();
      URL.revokeObjectURL(lien.href);
    }

    async function ouvrirFiche(id) {
      const erreur = $('[data-role="fiche-erreur"]'), contenu = $('[data-role="fiche-contenu"]');
      erreur.hidden = true; contenu.hidden = true;
      $('[data-role="fiche-titre"]').textContent = 'Fiche étudiant';
      $('[data-role="fiche-sous-titre"]').textContent = 'chargement…';
      $('[data-role="ouvrir-fiche"]').click();
      try {
        const res = await fetch('/api/etudiants/' + id);
        const f = await res.json();
        if (!res.ok) throw new Error(f.erreur || 'Erreur du serveur');
        $('[data-role="fiche-titre"]').textContent = f.reference;
        $('[data-role="fiche-sous-titre"]').textContent = f.cohorte;
        const badge = $('[data-role="fiche-devenir"]');
        badge.textContent = f.devenir || 'non connu';
        badge.className = 'badge ' + (f.abandon_reel === 1 ? 'bg-red-lt' : f.abandon_reel === 0 ? 'bg-green-lt' : 'bg-secondary-lt');
        $('[data-role="fiche-devenir-note"]').textContent = f.devenir ? '' : 'devenir non fourni dans le fichier';
        Resultat.rendre(contenu, Object.assign({}, f.resultat, { conseils: f.conseils, verification: f.verification }));
        $('[data-role="fiche-profil"]').innerHTML = f.profil.map((p) =>
          `<div class="list-group-item d-flex"><span class="flex-fill">${echapper(p.variable)}</span>`
          + (p.fournie ? `<strong>${echapper(String(p.valeur).replace('.', ','))}</strong>` : '<span class="text-secondary">non fournie, estimée</span>') + '</div>').join('');
        contenu.hidden = false;
      } catch (e) { erreur.textContent = e.message; erreur.hidden = false; $('[data-role="fiche-sous-titre"]').textContent = ''; }
    }

    // Evenements
    racine.addEventListener('keydown', (e) => {
      const tr = e.target.closest && e.target.closest('tr[data-id]');
      if (tr && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); ouvrirFiche(tr.dataset.id); }
    });    racine.addEventListener('input', (e) => { if (e.target.matches('[data-filtre]')) { etat.page = 1; majNiveaux(); rendreTout(); } });
    racine.addEventListener('change', (e) => { if (e.target.matches('[data-filtre]')) { etat.page = 1; majNiveaux(); rendreTout(); } });
    $('[data-role="modele-filiere"]').addEventListener('change', () => {
      etat.tri = { cle: proModele(), sens: -1 };   // le tableau se retrie sur le modèle choisi
      etat.page = 1;
      appliquerModele();
      rendreTout();
    });
    $$('[data-role="niveaux"] button').forEach((b) => b.addEventListener('click', () => {
      $(`[data-filtre="${catModele()}"]`).value = b.dataset.n;
      etat.page = 1; majNiveaux(); rendreTout();
    }));

    /* tiroir des filtres détaillés */
    const tiroir = $('[data-role="tiroir"]');
    const ouvrirTiroir = $('[data-role="ouvrir-tiroir"]');
    function placerTiroir() {
      const r = ouvrirTiroir.getBoundingClientRect();
      tiroir.style.left = Math.max(12, Math.min(r.left, innerWidth - tiroir.offsetWidth - 12)) + 'px';
      tiroir.style.top = (r.bottom + 8) + 'px';
    }
    function fermerTiroir() { tiroir.classList.remove('on'); ouvrirTiroir.setAttribute('aria-expanded', 'false'); }
    ouvrirTiroir.addEventListener('click', () => {
      const ouvert = tiroir.classList.toggle('on');
      ouvrirTiroir.setAttribute('aria-expanded', String(ouvert));
      if (ouvert) { placerTiroir(); $('[data-filtre="q"]').focus(); }
    });
    $('[data-action="fermer-tiroir"]').addEventListener('click', fermerTiroir);
    document.addEventListener('click', (e) => {
      if (tiroir.classList.contains('on') && !tiroir.contains(e.target) && !ouvrirTiroir.contains(e.target)) fermerTiroir();
    });
    document.addEventListener('keydown', (e) => { if (e.key === 'Escape') fermerTiroir(); });

    /* onglets Liste / Analyse */
    const segments = $('[data-role="segments"]');
    const curseur = $('[data-role="curseur"]');
    function placerCurseur() {
      const actif = segments.querySelector('[aria-selected="true"]');
      curseur.style.width = actif.offsetWidth + 'px';
      curseur.style.transform = `translateX(${actif.offsetLeft - 3}px)`;
    }
    segments.querySelectorAll('button').forEach((b) => b.addEventListener('click', () => {
      segments.querySelectorAll('button').forEach((x) => x.setAttribute('aria-selected', String(x === b)));
      placerCurseur();
      const liste = b.dataset.vue === 'liste';
      $('[data-role="vue-liste"]').hidden = !liste;
      $('[data-role="vue-analyse"]').hidden = liste;
      const outils = racine.querySelector('.outils');
      if (outils) outils.style.visibility = liste ? '' : 'hidden';
      // les graphiques dessines dans un onglet masque n'ont pas de taille : on les reveille
      if (!liste) Object.values(etat.graph).forEach((g) => g && g.resize());
    }));
    addEventListener('resize', placerCurseur);

    /* densité du tableau */
    $$('[data-densite]').forEach((b) => b.addEventListener('click', () => {
      $$('[data-densite]').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      racine.querySelector('.table-cohorte').classList.toggle('compact', b.dataset.densite === 'compact');
    }));
    $('[data-role="taille-page"]').addEventListener('change', (e) => { etat.taille = Number(e.target.value); etat.page = 1; rendreTout(); });
    $('[data-action="reinitialiser"]').addEventListener('click', () => {
      $$('[data-filtre]').forEach((el) => { if (el.type === 'checkbox') el.checked = false; else el.value = ''; });
      etat.page = 1; majNiveaux(); rendreTout();
    });
    $('[data-action="exporter"]').addEventListener('click', exporter);
    racine.addEventListener('click', (e) => {
      const th = e.target.closest('th[data-tri]');
      if (th) {
        const cle = th.dataset.tri;
        const texte = ['reference', 'filiere', 'genre', 'devenir'].includes(cle);
        etat.tri = { cle, sens: etat.tri.cle === cle ? -etat.tri.sens : (texte ? 1 : -1) };
        rendreTout(); return;
      }
      const ligne = e.target.closest('tr[data-id]');
      if (ligne) { ouvrirFiche(ligne.dataset.id); return; }
      const lien = e.target.closest('a[data-page]');
      if (lien) { e.preventDefault(); etat.page = Number(lien.dataset.page); rendreTableau(filtrer()); }
    });

    return {
      afficher(donnees) {
        etat.lignes = donnees.lignes;
        etat.nom = donnees.cohorte.nom;
        etat.avecDevenir = donnees.lignes.some((l) => l.abandon_reel !== null);
        etat.page = 1;
        // listes dependantes des donnees
        const filieres = Array.from(new Set(donnees.lignes.map((l) => l.filiere).filter(Boolean))).sort((a, b) => a.localeCompare(b, 'fr'));
        $('[data-filtre="filiere"]').innerHTML = '<option value="">Toutes</option>' + filieres.map((f) => `<option>${echapper(f)}</option>`).join('');
        $('[data-role="filtre-devenir"]').hidden = !etat.avecDevenir;
        $('[data-role="bloc-calibration"]').hidden = !etat.avecDevenir;
        $$('[data-filtre]').forEach((el) => { if (el.type === 'checkbox') el.checked = false; else if (el.tagName !== 'SELECT' || el.dataset.filtre !== 'filiere') el.value = ''; });
        racine.hidden = false;
        appliquerModele();
        rendrePerformances(donnees);
        rendreTout();
        placerCurseur();
      },
    };
  }

  window.Cohorte = { monter };
})();
