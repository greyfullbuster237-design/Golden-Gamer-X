/* ==========================================================================
   GOLDEN GAMER X - Page "Nouvelles sorties" (data/nouveautes.js)
   ========================================================================== */
(function () {
    'use strict';

    const liste = document.getElementById('nouveautes-liste');

    function carte(j) {
        const lien = GG.urlFiche(j.id);
        return `
            <article class="game-card ${GG.esc(j.tagClass)}">
                <a href="${lien}" class="game-card-lien nouveaute-lien">
                    <img src="${GG.esc(j.image)}" alt="${GG.esc(j.nom)}" width="300" height="300" loading="lazy" decoding="async">
                    <span class="date-badge">${GG.esc(GG.formaterDate(j.dateSortie))}</span>
                    <h3 class="game-card-titre">${GG.esc(j.nom)}</h3>
                </a>
                <div class="tags-jeu tags-compact"><span class="tag ${GG.esc(j.tagClass)}">${GG.esc(j.categorie)}</span></div>
                <a href="${lien}" class="btn-telecharger">Voir la fiche</a>
            </article>`;
    }

    async function demarrer() {
        try {
            const m = await GG.meta();
            if (m.nouveautes === false) throw new Error('pas de nouveautés');
            const jeux = (await GG.charger('nouveautes')).slice()
                .sort((a, b) => String(b.dateSortie).localeCompare(String(a.dateSortie)));   // du plus récent au plus ancien
            if (!jeux.length) throw new Error('vide');
            liste.innerHTML = jeux.map(carte).join('');
        } catch (_) {
            liste.innerHTML = `<div class="no-results"><span>🎮</span>
                Les nouvelles sorties ne sont pas encore disponibles.<br>
                <a href="accueil.html" class="btn-telecharger">Voir le catalogue</a></div>`;
        }
    }

    demarrer();
})();
