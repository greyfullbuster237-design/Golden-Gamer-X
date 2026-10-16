/* ==========================================================================
   GOLDEN GAMER X - Catalogue : catégories, recherche, pagination numérotée
   - Une page = un petit fichier de 24 jeux (rien d'autre n'est chargé).
   - L'état (catégorie, page, recherche, position de défilement) est gardé
     dans l'historique : le bouton retour du site, du navigateur ou du
     téléphone ramène exactement au même endroit.
   ========================================================================== */
(function () {
    'use strict';

    const containerJeux = document.getElementById('liste-jeux');
    const nav = document.querySelector('.categories');
    const searchInput = document.getElementById('search-input');
    const searchClear = document.getElementById('search-clear');
    const compteur = document.getElementById('search-results-count');
    const zonePagination = document.getElementById('pagination');
    const sectionNouveautes = document.getElementById('nouveautes');
    const trackNouveautes = document.getElementById('carousel-track');

    // true = cache les boutons des catégories qui n'ont encore aucun jeu
    const MASQUER_CATEGORIES_VIDES = false;

    const etat = { cat: 'tous', q: '', page: 1 };
    let meta = null;
    let jeton = 0;                 // invalide les chargements devenus obsolètes
    let minuteurRecherche = null;
    let minuteurScroll = null;
    let indexRecherche = null;
    let derniereRecherche = { cle: '', resultats: [] };
    let nouveautes = null;         // null = pas encore chargé

    if ('scrollRestoration' in history) history.scrollRestoration = 'manual';

    // ----------------------------- Historique -----------------------------
    function urlEtat(e) {
        const p = new URLSearchParams();
        if (e.cat !== 'tous') p.set('cat', e.cat);
        if (e.q.trim()) p.set('q', e.q.trim());
        if (e.page > 1) p.set('page', e.page);
        const qs = p.toString();
        return qs ? '?' + qs : location.pathname;
    }

    /** Mémorise l'état + la position de défilement dans l'entrée d'historique courante. */
    function sauverEtat() {
        try {
            history.replaceState({ gg: { ...etat, scroll: window.scrollY } }, '');
        } catch (_) { /* navigateur restrictif : sans gravité */ }
    }

    /** Crée une nouvelle entrée d'historique avec l'état courant. */
    function pousserEtat() {
        const nouveau = { gg: { ...etat, scroll: 0 } };
        try {
            history.pushState(nouveau, '', urlEtat(etat));
        } catch (_) {
            try { history.pushState(nouveau, ''); } catch (__) { /* ignore */ }   // ex. file://
        }
    }

    /** Met à jour l'URL sans créer d'entrée (frappe dans la recherche). */
    function remplacerEtat() {
        const e = { gg: { ...etat, scroll: window.scrollY } };
        try {
            history.replaceState(e, '', urlEtat(etat));
        } catch (_) {
            try { history.replaceState(e, ''); } catch (__) { /* ignore */ }
        }
    }

    /** Navigation utilisateur : l'entrée quittée garde son état et sa position, puis on en crée une nouvelle. */
    function aller(changements) {
        sauverEtat();                      // AVANT de modifier l'état
        Object.assign(etat, changements);
        pousserEtat();
        return afficher();
    }

    function lireEtatInitial() {
        const hs = history.state && history.state.gg;
        if (hs) {
            Object.assign(etat, { cat: hs.cat, q: hs.q, page: hs.page });
            return hs.scroll || 0;
        }
        const p = new URLSearchParams(location.search);
        etat.cat = (p.get('cat') || 'tous').toLowerCase();
        etat.q = (p.get('q') || '').slice(0, 100);
        etat.page = Math.max(1, parseInt(p.get('page'), 10) || 1);
        return 0;
    }

    function restaurerScroll(y) {
        if (!y) return;
        const aller = () => window.scrollTo(0, y);
        requestAnimationFrame(aller);
        setTimeout(aller, 150);   // 2e passage si la mise en page a bougé (polices, images)
    }

    // ------------------------------- Rendu -------------------------------
    function highlight(texte, motCle) {
        const propre = GG.esc(texte);
        if (!motCle) return propre;
        const motEchappe = GG.esc(motCle).replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        return propre.replace(new RegExp('(' + motEchappe + ')', 'gi'), '<span class="highlight">$1</span>');
    }

    function htmlTags(jeu) {
        const autres = (jeu.autres || []).map(a =>
            `<span class="tag tag-secondaire ${GG.esc(a.tagClass)}">${GG.esc(a.nom)}</span>`).join('');
        return `<div class="tags-jeu"><span class="tag ${GG.esc(jeu.tagClass)}">${GG.esc(jeu.categorie)}</span>${autres}</div>`;
    }

    function carteDetaillee(jeu, motCle) {
        const lien = GG.urlFiche(jeu.id);
        const taille = jeu.taille && jeu.taille !== 'N/C'
            ? `<span><strong>Taille :</strong> ${GG.esc(jeu.taille)}</span>` : '';
        return `
            <article class="carte-jeu" data-categorie="${GG.esc(jeu.categorie)}">
                <a href="${lien}" class="lien-image">
                    <img src="${GG.esc(jeu.image)}" alt="${GG.esc(jeu.nom)}" width="250" height="350" loading="lazy" decoding="async">
                </a>
                <div class="infos">
                    <h2>${highlight(jeu.nom, motCle)}</h2>
                    ${htmlTags(jeu)}
                    <div class="description"><p>${GG.esc(jeu.descriptionCourte)}</p></div>
                    <div class="details-jeu">
                        ${taille}
                        <span><strong>Sortie :</strong> ${GG.esc(jeu.sortie)}</span>
                    </div>
                    <a href="${lien}" class="btn-telecharger">Voir la fiche</a>
                </div>
            </article>`;
    }

    function carteGrille(jeu, motCle) {
        const lien = GG.urlFiche(jeu.id);
        return `
            <article class="game-card ${GG.esc(jeu.tagClass)}">
                <a href="${lien}" class="game-card-lien">
                    <img src="${GG.esc(jeu.image)}" alt="${GG.esc(jeu.nom)}" width="300" height="300" loading="lazy" decoding="async">
                    <h3 class="game-card-titre">${highlight(jeu.nom, motCle)}</h3>
                </a>
                ${htmlTags(jeu).replace('class="tags-jeu"', 'class="tags-jeu tags-compact"')}
                <a href="${lien}" class="btn-telecharger">Voir la fiche</a>
            </article>`;
    }

    function messageVide(html) {
        containerJeux.className = 'games-grid';
        containerJeux.innerHTML = `<div class="no-results"><span>🎮</span>${html}</div>`;
        zonePagination.innerHTML = '';
    }

    function messageErreur() {
        zonePagination.innerHTML = '';
        containerJeux.className = 'games-grid';
        containerJeux.innerHTML = `
            <div class="no-results"><span>⚠️</span>
                Impossible de charger les jeux.<br>
                <button type="button" class="btn-telecharger" id="btn-reessayer">Réessayer</button>
            </div>`;
        document.getElementById('btn-reessayer').addEventListener('click', () => afficher());
    }

    // ---------------------------- Pagination ------------------------------
    function numerosAffiches(courante, total) {
        const garde = new Set([1, total, courante - 1, courante, courante + 1]);
        const nums = [...garde].filter(n => n >= 1 && n <= total).sort((a, b) => a - b);
        const sortie = [];
        nums.forEach((n, i) => {
            if (i > 0) {
                const ecart = n - nums[i - 1];
                if (ecart === 2) sortie.push(n - 1);
                else if (ecart > 2) sortie.push('…');
            }
            sortie.push(n);
        });
        return sortie;
    }

    function htmlPagination(courante, total) {
        if (total <= 1) return '';
        const lien = (n, classe, texte, extra = '') =>
            `<li><a class="${classe}" href="${GG.esc(urlEtat({ ...etat, page: n }))}" data-page="${n}"${extra}>${texte}</a></li>`;

        let html = '<ul>';
        if (courante > 1) html += lien(courante - 1, 'pg-nav', '← PRÉCÉDENT');
        numerosAffiches(courante, total).forEach(n => {
            if (n === '…') html += '<li><span class="pg-points" aria-hidden="true">…</span></li>';
            else if (n === courante) html += lien(n, 'pg-num actif', n, ' aria-current="page"');
            else html += lien(n, 'pg-num', n, ` aria-label="Page ${n}"`);
        });
        if (courante < total) html += lien(courante + 1, 'pg-nav', 'SUIVANT →');
        return html + '</ul>';
    }

    // ------------------------------ Données -------------------------------
    function infosCategorie(slug) {
        return slug === 'tous' ? { pages: meta.pages, total: meta.total }
            : meta.categories.find(c => c.slug === slug) || { pages: 0, total: 0 };
    }

    async function resultatsRecherche() {
        const cle = etat.cat + '|' + etat.q.trim();
        if (derniereRecherche.cle === cle) return derniereRecherche.resultats;
        if (!indexRecherche) indexRecherche = await GG.charger('recherche');

        const requete = GG.normaliser(etat.q).trim();
        const indexCat = etat.cat === 'tous' ? -1 : meta.categories.findIndex(c => c.slug === etat.cat);
        const debut = [], contient = [];
        for (const ligne of indexRecherche) {
            if (indexCat !== -1 && !ligne[2].includes(indexCat)) continue;
            const pos = GG.normaliser(ligne[1]).indexOf(requete);
            if (pos === 0) debut.push(ligne);
            else if (pos > 0) contient.push(ligne);
        }
        derniereRecherche = { cle, resultats: debut.concat(contient) };
        return derniereRecherche.resultats;
    }

    function ligneVersJeu(l) {
        const cats = l[2].map(i => meta.categories[i]).filter(Boolean);
        const [principale, ...autres] = cats;
        return {
            id: l[0], nom: l[1], sortie: l[3],
            image: GG.imageUrl(l[4], meta.imgPrefix),
            categorie: principale ? principale.nom : '',
            tagClass: principale ? principale.tagClass : '',
            autres: autres.slice(0, 2).map(c => ({ nom: c.nom, tagClass: c.tagClass }))
        };
    }

    // ------------------------------ Affichage -----------------------------
    function majNavActif() {
        nav.querySelectorAll('a').forEach(a => {
            const actif = a.dataset.cat === etat.cat;
            a.classList.toggle('active', actif);
            if (actif) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current');
        });
    }

    function construireNav() {
        const visibles = meta.categories.filter(c => !MASQUER_CATEGORIES_VIDES || c.total > 0);
        const liens = visibles.map(c =>
            `<a href="${GG.esc('?cat=' + c.slug)}" data-cat="${GG.esc(c.slug)}"` +
            (c.total ? '' : ' class="vide" title="Aucun jeu pour le moment"') +
            `>${GG.esc(c.nom)}</a>`);
        nav.innerHTML = '<a href="accueil.html" data-cat="tous">Tous</a>' + liens.join('');
        // Catégorie inconnue dans l'URL (ou vide) : retour sur "Tous"
        if (etat.cat !== 'tous' && !visibles.some(c => c.slug === etat.cat)) {
            etat.cat = 'tous';
            etat.page = 1;
        }
    }

    // ------------------------ Nouvelles sorties --------------------------
    function carteCarousel(j) {
        return `
            <a class="carousel-carte" href="${GG.urlFiche(j.id)}" role="listitem" draggable="false">
                <img src="${GG.esc(j.image)}" alt="${GG.esc(j.nom)}" width="220" height="300"
                     loading="lazy" decoding="async" draggable="false">
                <span class="date-badge">${GG.esc(GG.formaterDate(j.dateSortie))}</span>
                <h3 class="carousel-titre">${GG.esc(j.nom)}</h3>
            </a>`;
    }

    /** Le carrousel ne s'affiche que sur l'accueil (Tous, page 1, sans recherche). */
    function majVisibiliteNouveautes() {
        const accueil = etat.cat === 'tous' && !etat.q.trim() && etat.page === 1;
        sectionNouveautes.hidden = !(accueil && nouveautes && nouveautes.length);
    }

    function brancherCarousel() {
        const track = trackNouveautes;
        let glisse = false, aBouge = false, departX = 0, departScroll = 0;

        // Défilement à la souris (au doigt, le navigateur le fait déjà)
        track.addEventListener('pointerdown', (e) => {
            if (e.pointerType !== 'mouse' || e.button !== 0) return;
            glisse = true; aBouge = false;
            departX = e.clientX; departScroll = track.scrollLeft;
        });
        window.addEventListener('pointermove', (e) => {
            if (!glisse) return;
            const dx = e.clientX - departX;
            if (Math.abs(dx) > 5) { aBouge = true; track.classList.add('en-glissement'); }
            if (aBouge) track.scrollLeft = departScroll - dx;
        });
        const fin = () => { glisse = false; track.classList.remove('en-glissement'); };
        window.addEventListener('pointerup', fin);
        window.addEventListener('pointercancel', fin);
        // Un glissement ne doit pas ouvrir la fiche ; un vrai clic, si
        track.addEventListener('click', (e) => {
            if (aBouge) { e.preventDefault(); e.stopPropagation(); aBouge = false; }
        }, true);

        // Flèches et clavier
        const defiler = (sens) => track.scrollBy({ left: sens * Math.max(240, track.clientWidth * 0.8), behavior: 'smooth' });
        sectionNouveautes.querySelectorAll('.carousel-fleche').forEach(b =>
            b.addEventListener('click', () => defiler(Number(b.dataset.sens))));
        track.addEventListener('keydown', (e) => {
            if (e.key === 'ArrowRight') { e.preventDefault(); defiler(1); }
            else if (e.key === 'ArrowLeft') { e.preventDefault(); defiler(-1); }
        });
    }

    async function chargerNouveautes() {
        try {
            const m = await GG.meta();
            if (m.nouveautes === false) throw new Error('pas de nouveautés');   // fichier absent : aucune requête
            nouveautes = await GG.charger('nouveautes');
        } catch (_) {
            nouveautes = [];          // pas de fichier : la section reste masquée
        }
        if (nouveautes.length) {
            trackNouveautes.innerHTML = nouveautes.map(carteCarousel).join('');
            brancherCarousel();
        }
        majVisibiliteNouveautes();
    }

    /** Affiche la page courante (catégorie + recherche + n° de page). */
    async function afficher() {
        const monJeton = ++jeton;
        majVisibiliteNouveautes();
        try {
            if (!meta) {
                meta = await GG.meta();
                if (monJeton !== jeton) return;
                construireNav();
            }
            majNavActif();
            const rechercheActive = etat.q.trim() !== '';
            let jeux, totalJeux, totalPages, motCle = '';

            if (rechercheActive) {
                const resultats = await resultatsRecherche();
                if (monJeton !== jeton) return;
                totalJeux = resultats.length;
                totalPages = Math.max(1, Math.ceil(totalJeux / meta.taillePage));
                etat.page = Math.min(Math.max(1, etat.page), totalPages);
                const debut = (etat.page - 1) * meta.taillePage;
                jeux = resultats.slice(debut, debut + meta.taillePage).map(ligneVersJeu);
                motCle = etat.q.trim();
            } else {
                const infos = infosCategorie(etat.cat);
                totalJeux = infos.total;
                totalPages = infos.pages;
                etat.page = Math.min(Math.max(1, etat.page), Math.max(1, totalPages));
                jeux = totalJeux ? await GG.charger('pages/' + etat.cat + '-' + etat.page) : [];
                if (monJeton !== jeton) return;
            }

            const n = totalJeux;
            compteur.textContent = n === 0 ? (rechercheActive ? 'Aucun résultat' : '')
                : `${n} jeu${n > 1 ? 'x' : ''}${rechercheActive ? ' trouvé' + (n > 1 ? 's' : '') : ''}` +
                  (totalPages > 1 ? ` · page ${etat.page}/${totalPages}` : '');

            if (jeux.length === 0) {
                messageVide(rechercheActive
                    ? `Aucun jeu trouvé pour "<strong>${GG.esc(motCle)}</strong>"`
                    : 'Aucun jeu dans cette catégorie pour le moment');
                return;
            }

            const detaille = etat.cat === 'tous' && !rechercheActive;
            containerJeux.className = detaille ? 'games-list' : 'games-grid';
            const cartes = jeux.map(j => (detaille ? carteDetaillee : carteGrille)(j, motCle));
            // Publicité "in-feed" après le 6e jeu, seulement s'il y a du contenu avant ET après
            // (jamais sur une page vide ou presque vide, comme l'exige AdSense).
            const pub = window.GGPub ? GGPub.emplacementHtml() : '';
            if (pub && cartes.length > 6) cartes.splice(6, 0, pub);
            containerJeux.innerHTML = cartes.join('');
            // Après l'insertion dans le DOM : demande une annonce pour chaque NOUVEL emplacement
            // (les anciens ont été supprimés avec le contenu précédent : pas de rafraîchissement automatique).
            if (window.GGPub) GGPub.activer(containerJeux);
            zonePagination.innerHTML = htmlPagination(etat.page, totalPages);

            // Précharge la page suivante pour un changement instantané
            if (!rechercheActive && etat.page < totalPages) {
                GG.charger('pages/' + etat.cat + '-' + (etat.page + 1)).catch(() => {});
            }
        } catch (err) {
            if (monJeton === jeton) messageErreur();
        }
    }

    function versHautDeListe() {
        const haut = containerJeux.getBoundingClientRect().top + window.scrollY - 20;
        window.scrollTo({ top: Math.max(0, haut), behavior: 'auto' });
    }

    // ------------------------------ Événements ----------------------------
    nav.addEventListener('click', (e) => {
        const lien = e.target.closest('a[data-cat]');
        if (!lien || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        if (lien.dataset.cat === etat.cat && etat.page === 1 && !etat.q.trim()) return;
        aller({ cat: lien.dataset.cat, page: 1 });
    });

    zonePagination.addEventListener('click', async (e) => {
        const lien = e.target.closest('a[data-page]');
        if (!lien || e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
        e.preventDefault();
        await aller({ page: parseInt(lien.dataset.page, 10) });
        versHautDeListe();
    });

    searchInput.addEventListener('input', () => {
        etat.q = searchInput.value;
        etat.page = 1;
        searchClear.style.display = etat.q ? 'block' : 'none';
        clearTimeout(minuteurRecherche);
        minuteurRecherche = setTimeout(() => { remplacerEtat(); afficher(); }, 200);
    });

    searchClear.addEventListener('click', () => {
        searchInput.value = '';
        etat.q = '';
        etat.page = 1;
        searchClear.style.display = 'none';
        remplacerEtat();
        afficher();
        searchInput.focus();
    });

    // Bouton retour / suivant du navigateur ou du téléphone
    window.addEventListener('popstate', async (e) => {
        const hs = e.state && e.state.gg;
        if (!hs) return;
        Object.assign(etat, { cat: hs.cat, q: hs.q, page: hs.page });
        searchInput.value = etat.q;
        searchClear.style.display = etat.q ? 'block' : 'none';
        await afficher();
        restaurerScroll(hs.scroll || 0);
    });

    // Position de défilement : sauvée en continu et avant de quitter la page
    window.addEventListener('scroll', () => {
        clearTimeout(minuteurScroll);
        minuteurScroll = setTimeout(sauverEtat, 300);
    }, { passive: true });
    document.addEventListener('click', (e) => {
        if (e.target.closest && e.target.closest('a[href*="jeu.html"]')) sauverEtat();
    }, true);
    window.addEventListener('pagehide', sauverEtat);
    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') sauverEtat();
    });

    // ------------------------------- Bandeau ------------------------------
    // Les images du bandeau sont dupliquées par JS pour une boucle sans à-coup.
    function initialiserBandeau() {
        const bandeau = document.querySelector('.marquee-content');
        if (!bandeau) return;

        [...bandeau.children].forEach(el => {
            const copie = el.cloneNode(true);
            copie.setAttribute('aria-hidden', 'true');
            copie.alt = '';
            bandeau.appendChild(copie);
        });

        const gererErreur = (img) => {
            if (img.dataset.alt && img.dataset.essai !== '1') {
                img.dataset.essai = '1';
                img.src = img.dataset.alt;     // 2e extension possible (.jpeg / .png)
            } else {
                img.remove();                  // image absente : on la retire
            }
        };
        bandeau.querySelectorAll('img').forEach(img => {
            img.addEventListener('error', () => gererErreur(img));
            if (img.complete && img.naturalWidth === 0) gererErreur(img);
        });
    }

    // Le visiteur vient d'accepter les cookies : on réaffiche la page avec ses annonces
    document.addEventListener('gg:consentement', () => afficher());

    // ------------------------------- Démarrage ----------------------------
    async function demarrer() {
        initialiserBandeau();
        const scroll = lireEtatInitial();
        searchInput.value = etat.q;
        searchClear.style.display = etat.q ? 'block' : 'none';
        await afficher();
        chargerNouveautes();       // en parallèle : n'attend pas la liste des jeux
        remplacerEtat();           // ancre l'état dans l'entrée d'historique
        restaurerScroll(scroll);
    }

    demarrer();
})();
