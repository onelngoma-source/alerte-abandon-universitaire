/* Effets d'interface partages : onde au clic sur les boutons, voile de chargement en verre depoli.
   Rien ici ne touche au calcul : ce fichier ne fait que de l'affichage. */
(function () {
  'use strict';

  const sobre = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* --- onde au clic, sur tous les boutons --- */
  document.addEventListener('click', (e) => {
    if (sobre) return;
    const bouton = e.target.closest('.btn');
    if (!bouton || bouton.disabled) return;
    const rect = bouton.getBoundingClientRect();
    const taille = Math.max(rect.width, rect.height);
    const onde = document.createElement('span');
    onde.className = 'onde';
    onde.style.width = onde.style.height = taille + 'px';
    onde.style.left = (e.clientX - rect.left - taille / 2) + 'px';
    onde.style.top = (e.clientY - rect.top - taille / 2) + 'px';
    bouton.appendChild(onde);
    setTimeout(() => onde.remove(), 600);
  });

  /* --- voile de chargement --- */
  const Chargement = {
    afficher(texte) {
      const voile = document.querySelector('[data-role="voile"]');
      if (!voile) return;
      const zone = voile.querySelector('[data-role="texte-chargement"]');
      if (zone && texte) zone.textContent = texte;
      voile.dataset.visible = '1';
    },
    masquer() {
      const voile = document.querySelector('[data-role="voile"]');
      if (voile) voile.dataset.visible = '0';
    },
  };
  window.Chargement = Chargement;

  /* --- rail lateral : repli et depli, memorise d'une page a l'autre --- */
  const coque = document.getElementById('coque');
  const replier = document.getElementById('replier');
  if (coque && replier) {
    let ouvert = false;
    try { ouvert = localStorage.getItem('rail-ouvert') === '1'; } catch (e) { ouvert = false; }
    const appliquer = () => {
      coque.classList.toggle('ouvert', ouvert);
      replier.setAttribute('aria-label', ouvert ? 'Replier la navigation' : 'Déplier la navigation');
    };
    appliquer();
    replier.addEventListener('click', () => {
      ouvert = !ouvert;
      appliquer();
      try { localStorage.setItem('rail-ouvert', ouvert ? '1' : '0'); } catch (e) { /* navigation privee */ }
    });
  }
})();
