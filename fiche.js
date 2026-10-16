/* ==========================================================================
   GOLDEN GAMER X - Fiche d'un jeu (chargée à la demande : data/jeux/<id>.js)
   ========================================================================== */
(function () {
    'use strict';

    const conteneur = document.getElementById('fiche-jeu-container');
    const id = new URLSearchParams(location.search).get('id') || '';
    let captures = [];
    let indexLightbox = 0;
    let declencheur = null;

    // ---------------------------- Utilitaires ---------------------------
    /** Retire tout ce qui pourrait exécuter du code dans la description. */
    function assainir(html) {
        const tpl = document.createElement('template');
        tpl.innerHTML = html || '';
        tpl.content.querySelectorAll('script,style,iframe,object,embed,link,meta,form').forEach(n => n.remove());
        tpl.content.querySelectorAll('*').forEach(el => {
            [...el.attributes].forEach(a => {
                const nom = a.name.toLowerCase();
                if (nom.startsWith('on') ||
                    (['href', 'src', 'xlink:href'].includes(nom) && /^\s*(javascript|data|vbscript):/i.test(a.value))) {
                    el.removeAttribute(a.name);
                }
            });
            if (el.tagName === 'A') { el.target = '_blank'; el.rel = 'noopener noreferrer'; }
        });
        return tpl.innerHTML;
    }

    const urlSure = (url) => /^https?:\/\//i.test(url || '') ? url : '#';

    // ----------------------- Boutiques (menu déroulant) ------------------
    function boutiquesDe(jeu) {
        let liste = Array.isArray(jeu.boutiques)
            ? jeu.boutiques.filter(b => b && b.nom && urlSure(b.url) !== '#') : [];
        if (!liste.length && urlSure(jeu.lienBoutique) !== '#') {
            liste = [{ nom: jeu.boutique || 'RAWG', url: jeu.lienBoutique }];
        }
        return liste;
    }

    function libelleBoutique(b) {
        if (b.nom === 'RAWG') return 'Voir sur RAWG';
        return (b.recherche ? 'Chercher sur ' : 'Acheter sur ') + b.nom;
    }

    function htmlAchat(jeu) {
        const liste = boutiquesDe(jeu);
        if (!liste.length) return '<p class="fiche-resume">Aucune boutique référencée pour ce jeu.</p>';

        if (liste.length === 1) {   // une seule boutique : simple bouton
            return `<a href="${GG.esc(urlSure(liste[0].url))}" target="_blank" rel="noopener noreferrer"
                       class="btn-telecharger btn-gros">${GG.esc(libelleBoutique(liste[0]))}</a>`;
        }
        const elements = liste.map(b => `
                <li role="none">
                    <a role="menuitem" href="${GG.esc(urlSure(b.url))}" target="_blank" rel="noopener noreferrer">
                        <span>${GG.esc(b.nom)}</span>
                        <small>${b.recherche ? 'recherche' : 'acheter ↗'}</small>
                    </a>
                </li>`).join('');
        return `
            <div class="achat-menu">
                <button type="button" class="btn-telecharger btn-gros achat-bouton"
                        aria-haspopup="true" aria-expanded="false" aria-controls="achat-liste">
                    Où acheter (${liste.length})
                </button>
                <ul class="achat-liste" id="achat-liste" role="menu" hidden>${elements}
                </ul>
            </div>`;
    }

    function brancherAchat() {
        const menu = conteneur.querySelector('.achat-menu');
        if (!menu) return;
        const bouton = menu.querySelector('.achat-bouton');
        const liste = menu.querySelector('.achat-liste');
        const items = () => [...liste.querySelectorAll('a')];

        const ouvrir = (focusPremier) => {
            liste.hidden = false;
            bouton.setAttribute('aria-expanded', 'true');
            if (focusPremier) items()[0].focus();
        };
        const fermer = (rendreFocus) => {
            liste.hidden = true;
            bouton.setAttribute('aria-expanded', 'false');
            if (rendreFocus) bouton.focus();
        };

        bouton.addEventListener('click', () => (liste.hidden ? ouvrir(false) : fermer(false)));
        bouton.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowDown') { e.preventDefault(); ouvrir(true); }
        });
        liste.addEventListener('keydown', (e) => {
            const els = items();
            const i = els.indexOf(document.activeElement);
            if (e.key === 'Escape') { e.preventDefault(); fermer(true); }
            else if (e.key === 'ArrowDown') { e.preventDefault(); els[(i + 1) % els.length].focus(); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); els[(i - 1 + els.length) % els.length].focus(); }
            else if (e.key === 'Home') { e.preventDefault(); els[0].focus(); }
            else if (e.key === 'End') { e.preventDefault(); els[els.length - 1].focus(); }
        });
        // Clic en dehors ou sortie du menu au clavier : on ferme
        document.addEventListener('click', (e) => { if (!menu.contains(e.target)) fermer(false); });
        menu.addEventListener('focusout', (e) => {
            if (e.relatedTarget && !menu.contains(e.relatedTarget)) fermer(false);
        });
        // Un clic sur une boutique ouvre le lien puis referme le menu
        liste.addEventListener('click', (e) => { if (e.target.closest('a')) fermer(false); });
    }

    function afficherErreur(titre, message) {
        document.title = titre + ' - GOLDEN GAMER X';
        conteneur.innerHTML = `
            <div class="erreur-404">
                <h2>${GG.esc(titre)}</h2>
                <p>${GG.esc(message)}</p>
                <a href="accueil.html" class="btn-telecharger">Retour au catalogue</a>
            </div>`;
    }

    // ------------------------------ Rendu -------------------------------
    function tagsHtml(jeu) {
        const cats = Array.isArray(jeu.categories) && jeu.categories.length
            ? jeu.categories : [{ nom: jeu.categorie, tagClass: jeu.tagClass }];
        return cats.map((c, i) =>
            `<span class="tag ${GG.esc(c.tagClass)}${i ? ' tag-secondaire' : ''}">${GG.esc(c.nom)}</span>`).join('');
    }

    function rendreFiche(jeu) {
        document.title = `${jeu.nom} - GOLDEN GAMER X`;
        const metaDesc = document.querySelector('meta[name="description"]');
        if (metaDesc) metaDesc.content = jeu.descriptionCourte || '';

        captures = Array.isArray(jeu.screenshots) ? jeu.screenshots : [];

        const video = jeu.videoLocale ? `
            <div class="video-locale-container">
                <video autoplay muted loop playsinline controls preload="metadata" poster="${GG.esc(jeu.image)}">
                    <source src="${GG.esc(jeu.videoLocale)}">
                    Votre navigateur ne supporte pas la lecture de vidéos.
                </video>
            </div>` : '';

        const galerie = (captures.length || video) ? `
            <section class="fiche-galerie">
                <h3>${video ? 'Trailer et captures d\'écran' : 'Captures d\'écran'}</h3>
                ${video}
                <div class="galerie-grid">
                    ${captures.map((src, i) => `
                        <button type="button" class="screen-btn" data-index="${i}" aria-label="Agrandir la capture ${i + 1}">
                            <img src="${GG.esc(GG.miniature(src, 420))}" alt="Capture ${i + 1} de ${GG.esc(jeu.nom)}"
                                 class="screen-item" loading="lazy" decoding="async">
                        </button>`).join('')}
                </div>
            </section>` : '';

        const taille = jeu.taille && jeu.taille !== 'N/C'
            ? `<span><strong>Taille :</strong> ${GG.esc(jeu.taille)}</span>` : '';

        conteneur.innerHTML = `
            <article class="fiche-jeu">
                <div class="fiche-header">
                    <a href="accueil.html" class="btn-retour" id="lien-retour">← Retour</a>
                    <img src="${GG.esc(jeu.image)}" alt="${GG.esc(jeu.nom)}" class="jaquette-fiche" width="280" height="400" decoding="async">
                    <div class="fiche-infos-principales">
                        <h1>${GG.esc(jeu.nom)}</h1>
                        <div class="tags-jeu">${tagsHtml(jeu)}</div>
                        <div class="details-jeu">
                            ${taille}
                            <span><strong>Sortie :</strong> ${GG.esc(jeu.sortie)}</span>
                        </div>
                        <p class="fiche-resume">${GG.esc(jeu.descriptionCourte)}</p>
                    </div>
                </div>

                ${galerie}

                <section class="fiche-description">
                    <h3>Description</h3>
                    <div class="description-longue">${assainir(jeu.descriptionLongue || jeu.descriptionCourte)}</div>
                </section>

                <section class="fiche-download">
                    <h3>Où l'acheter</h3>
                    ${htmlAchat(jeu)}
                    <p class="disclaimer">Liens vers les boutiques officielles. Données fournies par RAWG.</p>
                </section>

                <div id="similaires"></div>
            </article>`;

        brancherRetour();
        brancherAchat();
        brancherGalerie(jeu);
        chargerSimilaires(jeu);
    }

    function brancherRetour() {
        // Retour = vraie "page précédente" : le catalogue retrouve sa catégorie,
        // sa page et sa position exacte (voir app.js). Sans historique : accueil.
        const lien = document.getElementById('lien-retour');
        lien.addEventListener('click', (e) => {
            try {
                const ref = new URL(document.referrer);
                if (ref.origin === location.origin && history.length > 1) {
                    e.preventDefault();
                    history.back();
                }
            } catch (_) { /* pas de referrer : lien normal vers accueil.html */ }
        });
    }

    function brancherGalerie(jeu) {
        conteneur.querySelectorAll('.screen-btn').forEach(btn => {
            btn.addEventListener('click', () => ouvrirLightbox(Number(btn.dataset.index), btn));
        });
        const source = conteneur.querySelector('video source');
        if (source) {
            source.addEventListener('error', () => {
                const bloc = conteneur.querySelector('.video-locale-container');
                if (bloc) bloc.remove();   // vidéo indisponible : on la retire proprement
            });
        }
    }

    async function chargerSimilaires(jeu) {
        const slug = jeu.categorieSlug;
        if (!/^[a-z0-9-]+$/.test(slug || '')) return;
        try {
            const lot = await GG.charger('pages/' + slug + '-1');
            const autres = lot.filter(j => j.id !== jeu.id).slice(0, 6);
            if (!autres.length) return;
            document.getElementById('similaires').innerHTML = `
                <section class="fiche-similaires">
                    <h3>Dans la même catégorie</h3>
                    <div class="games-grid">
                        ${autres.map(j => `
                            <article class="game-card ${GG.esc(j.tagClass)}">
                                <a href="${GG.urlFiche(j.id)}" class="game-card-lien">
                                    <img src="${GG.esc(j.image)}" alt="${GG.esc(j.nom)}" width="300" height="300" loading="lazy" decoding="async">
                                    <h3 class="game-card-titre">${GG.esc(j.nom)}</h3>
                                </a>
                            </article>`).join('')}
                    </div>
                </section>`;
        } catch (_) { /* suggestions facultatives */ }
    }

    // ----------------------------- Lightbox -----------------------------
    function creerLightbox() {
        const lb = document.createElement('div');
        lb.id = 'lightbox';
        lb.className = 'lightbox';
        lb.setAttribute('role', 'dialog');
        lb.setAttribute('aria-modal', 'true');
        lb.setAttribute('aria-label', 'Visionneuse d\'images');
        lb.innerHTML = `
            <button type="button" class="fermer-lightbox" aria-label="Fermer">&times;</button>
            <button type="button" class="lightbox-nav lightbox-prev" aria-label="Image précédente">&#10094;</button>
            <img id="lightbox-img" src="" alt="">
            <button type="button" class="lightbox-nav lightbox-next" aria-label="Image suivante">&#10095;</button>
            <span class="lightbox-compteur" id="lightbox-compteur"></span>`;
        document.body.appendChild(lb);

        lb.addEventListener('click', (e) => { if (e.target === lb) fermerLightbox(); });
        lb.querySelector('.fermer-lightbox').addEventListener('click', fermerLightbox);
        lb.querySelector('.lightbox-prev').addEventListener('click', () => naviguer(-1));
        lb.querySelector('.lightbox-next').addEventListener('click', () => naviguer(1));
        document.addEventListener('keydown', (e) => {
            if (!lb.classList.contains('ouvert')) return;
            if (e.key === 'Escape') fermerLightbox();
            else if (e.key === 'ArrowLeft') naviguer(-1);
            else if (e.key === 'ArrowRight') naviguer(1);
        });
        return lb;
    }

    function afficherCapture() {
        const lb = document.getElementById('lightbox');
        const img = lb.querySelector('#lightbox-img');
        delete img.dataset.repli;
        img.src = captures[indexLightbox];
        img.alt = 'Capture ' + (indexLightbox + 1);
        lb.querySelector('#lightbox-compteur').textContent = (indexLightbox + 1) + ' / ' + captures.length;
        const seule = captures.length < 2;
        lb.querySelectorAll('.lightbox-nav').forEach(b => { b.hidden = seule; });
    }

    function ouvrirLightbox(index, bouton) {
        if (!captures.length) return;
        const lb = document.getElementById('lightbox') || creerLightbox();
        declencheur = bouton || null;
        indexLightbox = index;
        afficherCapture();
        lb.classList.add('ouvert');
        document.body.classList.add('lightbox-ouverte');
        lb.querySelector('.fermer-lightbox').focus();
    }

    function fermerLightbox() {
        const lb = document.getElementById('lightbox');
        if (!lb) return;
        lb.classList.remove('ouvert');
        document.body.classList.remove('lightbox-ouverte');
        if (declencheur) declencheur.focus();
    }

    function naviguer(sens) {
        indexLightbox = (indexLightbox + sens + captures.length) % captures.length;
        afficherCapture();
    }

    // ----------------------------- Démarrage ----------------------------
    async function demarrer() {
        if (!GG.idValide(id)) {
            afficherErreur('Jeu introuvable', 'Aucun jeu n\'est indiqué dans ce lien.');
            return;
        }
        try {
            await GG.meta();                         // récupère la version des données
            const jeu = await GG.charger('jeux/' + id);
            rendreFiche(jeu);
        } catch (err) {
            afficherErreur('Jeu introuvable', 'Ce jeu n\'existe pas dans notre catalogue ou n\'est pas disponible pour le moment.');
        }
    }

    demarrer();
})();
