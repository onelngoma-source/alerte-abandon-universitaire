/* Page de connexion : aurore WebGL, carte inclinable, carrousel de presentation
   et morphose du bouton. Tout est decoratif ; la connexion elle-meme reste un
   envoi de formulaire classique. */
(() => {
  'use strict';
  const sobre = matchMedia('(prefers-reduced-motion: reduce)').matches;

  /* ============ 1. Aurore WebGL ============ */
  const toile = document.getElementById('aurore');
  const gl = toile.getContext('webgl', { antialias:false, alpha:false, powerPreference:'low-power' });

  const VERT = `attribute vec2 p; void main(){ gl_Position = vec4(p, 0.0, 1.0); }`;
  const FRAG = `
precision highp float;
uniform vec2 taille; uniform float temps; uniform vec2 souris;

vec3 permute(vec3 x){ return mod(((x*34.0)+1.0)*x, 289.0); }
float bruit(vec2 v){
  const vec4 C = vec4(0.211324865, 0.366025403, -0.577350269, 0.024390243);
  vec2 i = floor(v + dot(v, C.yy)); vec2 x0 = v - i + dot(i, C.xx);
  vec2 i1 = (x0.x > x0.y) ? vec2(1.0,0.0) : vec2(0.0,1.0);
  vec4 x12 = x0.xyxy + C.xxzz; x12.xy -= i1;
  i = mod(i, 289.0);
  vec3 p = permute(permute(i.y + vec3(0.0, i1.y, 1.0)) + i.x + vec3(0.0, i1.x, 1.0));
  vec3 m = max(0.5 - vec3(dot(x0,x0), dot(x12.xy,x12.xy), dot(x12.zw,x12.zw)), 0.0);
  m = m*m; m = m*m;
  vec3 x = 2.0 * fract(p * C.www) - 1.0; vec3 h = abs(x) - 0.5;
  vec3 ox = floor(x + 0.5); vec3 a0 = x - ox;
  m *= 1.79284291400159 - 0.85373472095314 * (a0*a0 + h*h);
  vec3 g; g.x = a0.x * x0.x + h.x * x0.y;
  g.yz = a0.yz * x12.xz + h.yz * x12.yw;
  return 130.0 * dot(m, g);
}
float fbm(vec2 v){
  float s = 0.0, amp = 0.5;
  for(int i = 0; i < 3; i++){ s += amp * bruit(v); v *= 2.0; amp *= 0.5; }
  return s;
}
void main(){
  vec2 uv = gl_FragCoord.xy / taille.xy;
  vec2 q = uv; q.x *= taille.x / taille.y;
  q *= 0.62;                       // formes larges : une aurore, pas du marbre
  float t = temps * 0.035;

  // deformation du domaine : c'est elle qui donne le mouvement liquide
  vec2 d1 = vec2(fbm(q + vec2(0.0, t)), fbm(q + vec2(5.2, -t*0.8)));
  vec2 d2 = vec2(fbm(q + 1.5*d1 + vec2(1.7, 9.2) + t*0.6),
                 fbm(q + 1.5*d1 + vec2(8.3, 2.8) - t*0.5));
  float f = fbm(q + 1.2*d2);

  float halo = smoothstep(0.62, 0.0, distance(uv, souris));   // la lumiere suit le curseur

  vec3 nuit   = vec3(0.016, 0.071, 0.153);
  vec3 profond= vec3(0.051, 0.220, 0.388);
  vec3 vif    = vec3(0.196, 0.506, 0.878);
  vec3 ciel   = vec3(0.373, 0.659, 1.000);
  vec3 dore   = vec3(0.847, 0.722, 0.361);

  float m = clamp(f * 0.45 + 0.5, 0.0, 1.0);
  vec3 c = mix(nuit, profond, smoothstep(0.30, 0.86, m));
  c = mix(c, vif, smoothstep(0.66, 1.02, m) * 0.52);
  c = mix(c, ciel, smoothstep(0.88, 1.12, m) * 0.26);
  c = mix(c, dore, smoothstep(0.62, 1.15, length(d2)) * 0.13);
  c += vif * halo * 0.12;
  c += dore * halo * 0.04;

  // vignette : on garde le centre lumineux et les bords profonds
  float vig = smoothstep(1.25, 0.25, length(uv - 0.5) * 1.35);
  c *= mix(0.62, 1.0, vig);

  gl_FragColor = vec4(c, 1.0);
}`;

  let programme = null, uTaille, uTemps, uSouris;
  let largeurFond = 400;      // l'aurore est floue : inutile de la calculer en pleine definition
  let periode = 33;           // 30 images par seconde suffisent pour un mouvement aussi lent

  function compiler(type, source){
    const s = gl.createShader(type); gl.shaderSource(s, source); gl.compileShader(s);
    if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) { console.warn(gl.getShaderInfoLog(s)); return null; }
    return s;
  }
  function demarrerAurore(){
    if (!gl) {   // pas de WebGL : un degrade ordinaire fait l'affaire
      document.getElementById('fond').style.background =
        'linear-gradient(142deg,#04172C 0%,#0D3863 46%,#2a6fc4 100%)';
      toile.remove();
      return false;
    }
    const vs = compiler(gl.VERTEX_SHADER, VERT), fs = compiler(gl.FRAGMENT_SHADER, FRAG);
    if (!vs || !fs) return false;
    programme = gl.createProgram();
    gl.attachShader(programme, vs); gl.attachShader(programme, fs); gl.linkProgram(programme);
    if (!gl.getProgramParameter(programme, gl.LINK_STATUS)) { console.warn(gl.getProgramInfoLog(programme)); return false; }
    gl.useProgram(programme);
    const tampon = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, tampon);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 3,-1, -1,3]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(programme, 'p');
    gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    uTaille = gl.getUniformLocation(programme, 'taille');
    uTemps  = gl.getUniformLocation(programme, 'temps');
    uSouris = gl.getUniformLocation(programme, 'souris');
    return true;
  }
  function ajusterToile(){
    const r = Math.max(0.5, Math.min(2.2, innerWidth / Math.max(innerHeight, 1)));
    toile.width = largeurFond;
    toile.height = Math.round(largeurFond / r);
    gl.viewport(0, 0, toile.width, toile.height);
  }
  const visee = { x:0.62, y:0.45 }, suivi = { x:0.62, y:0.45 };
  let dernierRendu = 0, depart = performance.now(), fondVivant = false;

  function peindre(t){
    requestAnimationFrame(peindre);
    if (!programme || document.hidden) return;
    if (econome || sobre) {                 // une seule image, puis plus rien
      if (fondVivant) return;
      fondVivant = true;
    } else {
      if (t - dernierRendu < periode) return;
      dernierRendu = t;
    }
    suivi.x += (visee.x - suivi.x) * 0.05;
    suivi.y += (visee.y - suivi.y) * 0.05;
    gl.uniform2f(uTaille, toile.width, toile.height);
    gl.uniform1f(uTemps, (econome || sobre) ? 11 : (t - depart) / 1000);
    gl.uniform2f(uSouris, suivi.x, suivi.y);
    gl.drawArrays(gl.TRIANGLES, 0, 3);
  }

  if (demarrerAurore()) {
    ajusterToile();
    let attente = null;
    addEventListener('resize', () => { clearTimeout(attente); attente = setTimeout(ajusterToile, 250); });
    requestAnimationFrame(peindre);
  }

  /* ============ 2. Carte qui s'incline en 3D ============ */
  const carte = document.getElementById('carte');
  const volet = document.getElementById('volet');
  let inclinaison = true, econome = false, pointeur = null, enAttente = false;
  const lueurGauche = document.getElementById('lueur-gauche');
  const voletGauche = document.querySelector('.volet-gauche');
  function appliquerPointeur(){
    enAttente = false;
    const e = pointeur; if (!e) return;
    if (lueurGauche && voletGauche && !econome) {
      const g = voletGauche.getBoundingClientRect();
      lueurGauche.style.transform =
        `translate3d(${(e.x - g.left).toFixed(1)}px, ${(e.y - g.top).toFixed(1)}px, 0)`;
    }
    visee.x = e.x / innerWidth; visee.y = 1 - e.y / innerHeight;
    if (volet) {
      const r = volet.getBoundingClientRect();
      volet.style.setProperty('--mx', ((e.x - r.left) / r.width * 100) + '%');
      volet.style.setProperty('--my', ((e.y - r.top) / r.height * 100) + '%');
    }
    if (!inclinaison || sobre || econome) return;
    const x = (e.x / innerWidth - 0.5), y = (e.y / innerHeight - 0.5);
    carte.style.transform = `rotateY(${x * 7}deg) rotateX(${-y * 5}deg)`;
  }
  addEventListener('pointermove', (e) => {
    pointeur = { x:e.clientX, y:e.clientY };
    if (!enAttente) { enAttente = true; requestAnimationFrame(appliquerPointeur); }
  }, { passive:true });
  addEventListener('pointerleave', () => { if (inclinaison) carte.style.transform = ''; });

  /* ============ 3. Les bulles de donnees ============ */
  const PANNEAUX = [
    { titre:"Repérer le décrochage avant qu'il arrive",
      texte:"Chaque étudiant reçoit une estimation de son risque d'abandon, dès la fin du premier semestre.",
      bulles:[
        { c:'b1', z:46, h:`<div class="ligne"><span>Risque estimé</span><span class="etiq chaud">Élevé</span></div>
             <div class="nombre">0,867</div><div class="jauge"><i style="width:87%"></i></div>
             <div class="note">Approche à noyau · étudiant E-1718</div>` },
        { c:'b2', z:24, h:`<div class="ligne" style="gap:6px"><span class="etiq chaud">Élevé</span>
             <span class="etiq">Moyen</span><span class="etiq">Faible</span></div>
             <div class="note">Trois niveaux, aux seuils de 0,30 et 0,60</div>` },
        { c:'b3', z:62, h:`<span class="puce"></span><div><div class="nombre petit">1 328</div>
             <div class="note">étudiants suivis, dont 427 abandons observés</div></div>` } ] },
    { titre:"Comprendre, pas seulement prédire",
      texte:"Le score se lit à travers les étudiants qui ressemblent le plus à celui que vous suivez.",
      bulles:[
        { c:'b1', z:52, h:`<div class="ligne" style="margin-bottom:8px"><strong style="font-size:.86rem">Profils les plus proches</strong></div>
             <div class="ligne" style="padding:3px 0"><span>6 unités · 12,5</span><span class="etiq chaud">a abandonné</span></div>
             <div class="ligne" style="padding:3px 0"><span>4 unités · 10,5</span><span class="etiq chaud">a abandonné</span></div>
             <div class="ligne" style="padding:3px 0"><span>6 unités · 12,7</span><span class="etiq">diplômé</span></div>` },
        { c:'b2', z:28, h:`<div class="ligne" style="margin-bottom:6px"><strong style="font-size:.84rem">Ce qui pèse le plus</strong></div>
             <div class="note" style="color:#FF9A9A">▲ Frais de scolarité en retard</div>
             <div class="note" style="color:#8FE6A6">▼ Unités validées au second semestre</div>` },
        { c:'b3', z:66, h:`<span class="puce or"></span><div><span class="etiq or">Synthétique</span>
             <div class="note">Les profils créés pour équilibrer les données sont signalés</div></div>` } ] },
    { titre:"Deux approches, côte à côte",
      texte:"Une méthode statistique traçable et un modèle d'apprentissage, comparés sur les mêmes étudiants.",
      bulles:[
        { c:'b1', z:50, h:`<div class="duo"><div><div class="mini">Approche à noyau</div>
             <div class="nombre petit">0,875</div><div class="jauge froide"><i style="width:87.5%"></i></div></div>
             <div><div class="mini">Random Forest</div><div class="nombre petit">0,934</div>
             <div class="jauge"><i style="width:93.4%;background:linear-gradient(90deg,#F6E7B4,#D8B85C)"></i></div></div></div>
             <div class="note">AUC mesurée sur 1 328 étudiants jamais vus à l'entraînement</div>` },
        { c:'b2', z:30, h:`<div class="nombre petit">349</div>
             <div class="note">étudiants pour lesquels les deux modèles ne disent pas la même chose</div>` },
        { c:'b3', z:64, h:`<span class="puce or"></span><div>Le noyau s'explique par ses voisins
             <div class="note">sans outil d'explication ajouté</div></div>` } ] },
    { titre:"Agir avant le second semestre",
      texte:"Les résultats du premier semestre suffisent à repérer l'essentiel du risque.",
      bulles:[
        { c:'b1', z:48, h:`<div class="ligne"><span>Fin du 1<sup>er</sup> semestre</span>
             <span class="etiq or">Mode précoce</span></div><div class="nombre">0,912</div>
             <div class="note">AUC sans aucune donnée du second semestre, contre 0,934 avec l'année complète</div>` },
        { c:'b2', z:26, h:`<div class="note" style="color:#F6E7B4">✓ Unités inscrites &nbsp; ✓ Unités validées</div>
             <div class="note" style="opacity:.55">◻ Second semestre</div>` },
        { c:'b3', z:68, h:`<span class="puce"></span><div>Bascule automatique
             <div class="note">30 variables sur 36 suffisent</div></div>` } ] },
  ];

  const pile = document.getElementById('pile');
  const recit = document.getElementById('recit');
  const rail = document.getElementById('rail');
  let indice = 0, minuterie = null, arret = false, survol = false;

  PANNEAUX.forEach((_, i) => {
    const b = document.createElement('button');
    b.className = 'tiret' + (i === 0 ? ' actif' : '');
    b.innerHTML = '<i></i>';
    b.setAttribute('aria-label', 'Panneau ' + (i + 1));
    b.addEventListener('click', () => { montrer(i); relancer(); });
    rail.appendChild(b);
  });
  const pause = document.createElement('button');
  pause.className = 'pause';
  pause.setAttribute('aria-label', 'Mettre le défilement en pause');
  pause.innerHTML = '<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>';
  pause.addEventListener('click', () => {
    arret = !arret;
    pause.innerHTML = arret
      ? '<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><path d="M8 5l11 7-11 7z"/></svg>'
      : '<svg width="11" height="11" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="5" width="4" height="14" rx="1"/><rect x="14" y="5" width="4" height="14" rx="1"/></svg>';
    pause.setAttribute('aria-label', arret ? 'Reprendre le défilement' : 'Mettre le défilement en pause');
    figer(); relancer();
  });
  rail.appendChild(pause);

  function figer(){
    rail.querySelectorAll('.tiret.actif i').forEach(i => {
      i.style.animationPlayState = (arret || survol) ? 'paused' : 'running';
    });
  }

  function montrer(i){
    const p = PANNEAUX[i];
    recit.classList.add('sort');
    pile.querySelectorAll('.bulle').forEach(b => {
      b.classList.remove('vue');
      b.style.transform = 'translateZ(0) scale(.94)';
    });
    setTimeout(() => {
      pile.innerHTML = '';
      p.bulles.forEach((b, k) => {
        const el = document.createElement('div');
        el.className = 'bulle ' + b.c;
        el.innerHTML = b.h;
        pile.appendChild(el);
        requestAnimationFrame(() => setTimeout(() => {
          el.classList.add('vue');
          el.style.transform = `translateZ(${b.z}px) scale(1)`;
        }, 80 * k));
      });
      recit.querySelector('h2').textContent = p.titre;
      recit.querySelector('p').textContent = p.texte;
      recit.classList.remove('sort');
    }, 320);
    rail.querySelectorAll('.tiret').forEach((t, k) => {
      const neuf = t.cloneNode(true);
      neuf.classList.toggle('actif', k === i);
      neuf.addEventListener('click', () => { montrer(k); relancer(); });
      t.replaceWith(neuf);
    });
    indice = i;
    figer();
  }
  function relancer(){
    clearInterval(minuterie);
    if (!sobre && !arret && !survol) minuterie = setInterval(() => montrer((indice + 1) % PANNEAUX.length), 6000);
  }
  if (volet) {
    volet.addEventListener('pointerenter', () => { survol = true; figer(); relancer(); });
    volet.addEventListener('pointerleave', () => { survol = false; figer(); relancer(); });
  }
  montrer(0); relancer();

  /* ============ 4. Chiffres qui derivent ============ */
  const CHIFFRES = ['0,934','0,875','1 328','427','4 424','75 voisins','0,816','32,2 %','89,6 %',
                    '3 096','0,867','0,30','0,60','70 / 30','0,747','345','382','0,912','36 variables'];
  const champ = document.getElementById('particules');
  function semer(){
    if (sobre || econome || !champ || document.hidden) return;
    const e = document.createElement('span');
    e.className = 'flottant' + (Math.random() < .3 ? ' dore' : '');
    e.textContent = CHIFFRES[(Math.random() * CHIFFRES.length) | 0];
    e.style.left = (6 + Math.random() * 80) + '%';
    e.style.top = (30 + Math.random() * 60) + '%';
    e.style.fontSize = (0.78 + Math.random() * 0.75).toFixed(2) + 'rem';
    e.style.animationDuration = (3.4 + Math.random() * 2.4).toFixed(2) + 's';
    champ.appendChild(e);
    setTimeout(() => e.remove(), 6200);
  }
  setInterval(semer, 1500);

  /* ============ 5. Morphose du bouton, puis retournement ============ */
  const form = document.getElementById('formulaire-connexion');
  const valider = document.getElementById('valider');
  const oeil = document.getElementById('oeil');

  oeil.addEventListener('click', () => {
    const champMdp = document.getElementById('mot_de_passe');
    const visible = champMdp.type === 'text';
    champMdp.type = visible ? 'password' : 'text';
    document.getElementById('oeil-ouvert').hidden = !visible;
    document.getElementById('oeil-ferme').hidden = visible;
    oeil.setAttribute('aria-label', visible ? 'Afficher le mot de passe' : 'Masquer le mot de passe');
  });

  /* Le formulaire part normalement vers le serveur. Le bouton se contracte en
     anneau pendant l'attente ; la page suivante prend le relais. */
  form.addEventListener('submit', () => {
    if (valider.classList.contains('charge')) return;
    valider.classList.add('charge');
    inclinaison = false;
    carte.style.transform = '';
  });

  /* Effets reduits : plus de flou sur les bulles, plus de mouvement de fond,
     plus d'inclinaison. La page reste la meme, elle ne demande plus rien au GPU. */
  const avis = document.getElementById('avis-perf');
  function annoncer(texte){
    if (!avis) return;
    avis.innerHTML = '';
    avis.append(texte);
    const b = document.createElement('button');
    b.type = 'button'; b.textContent = 'Rétablir';
    b.addEventListener('click', retablir);
    avis.appendChild(b);
    avis.hidden = false;
  }
  function retablir(){
    econome = false; allege = false;
    document.body.classList.remove('econome');
    periode = 33; largeurFond = 400;
    fondVivant = false; depart = performance.now() - 11000;
    if (programme) ajusterToile();
    if (avis) avis.hidden = true;
  }

  document.addEventListener('visibilitychange', () => { document.hidden ? clearInterval(minuterie) : relancer(); });

  /* ============ 6. Garde-fou : la page surveille sa propre fluidite ============
     Apres un temps de chauffe, on compte les images affichees. S'il en manque
     vraiment (moins de 20 par seconde, quatre secondes d'affilee, fenetre au
     premier plan), on bascule seul en effets reduits plutot que de laisser la
     machine s'etouffer. Le compteur s'arrete ensuite et ne revient plus. */
  /* Premier palier : l'aurore continue d'onduler, simplement moins souvent et
     sur une toile plus petite. On ne coupe rien tant qu'on peut alleger. */
  let allege = false;
  function allegerFond(){
    if (allege) return;
    allege = true;
    periode = 66;            // 15 images par seconde
    largeurFond = 260;
    if (programme) ajusterToile();
    if (champ) champ.innerHTML = '';
    annoncer("Le fond a été allégé : il continue d'onduler, un peu moins vite. ");
  }

  function basculerEconome(auto){
    if (econome) return;
    econome = true;
    document.body.classList.add('econome');
    carte.style.transform = '';
    if (champ) champ.innerHTML = '';
    if (auto) annoncer("Les animations ont été réduites : votre machine peinait à suivre. ");
  }
  if (!sobre) {
    setTimeout(() => {
      let images = 0, depart = performance.now(), lents = 0, fin = depart + 16000;
      const compter = (t) => {
        if (document.hidden || !document.hasFocus()) {   // une fenetre en arriere-plan
          images = 0; depart = t; lents = 0;             // est ralentie par le navigateur
          if (t < fin) requestAnimationFrame(compter);
          return;
        }
        images++;
        const ecoule = t - depart;
        if (ecoule >= 1000) {
          if (images * 1000 / ecoule < 20) lents++; else lents = 0;
          images = 0; depart = t;
          if (lents >= 4) {
            if (!allege) { allegerFond(); lents = 0; }   // on allege d'abord
            else { basculerEconome(true); return; }      // et seulement ensuite on coupe
          }
        }
        if (t < fin) requestAnimationFrame(compter);
      };
      requestAnimationFrame(compter);
    }, 1800);
  }
})();
