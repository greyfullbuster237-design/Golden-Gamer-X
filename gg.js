/* ==========================================================================
   GOLDEN GAMER X - Noyau commun : chargement des données + utilitaires
   Les fichiers data/*.js appellent GG.recevoir(cle, donnees).
   Fonctionne en double-cliquant sur les pages (file://) comme sur un hébergeur.
   ========================================================================== */
(function () {
    'use strict';

    const cache = new Map();     // clé -> données
    const enCours = new Map();   // clé -> Promise
    let versionDonnees = '';
    let promesseMeta = null;

    const PLACEHOLDER = 'data:image/svg+xml;utf8,' + encodeURIComponent(
        '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="560" viewBox="0 0 400 560">' +
        '<rect width="400" height="560" fill="#1a1a2e"/>' +
        '<text x="200" y="285" fill="#00ffff" font-family="Arial" font-size="22" text-anchor="middle">' +
        'Image indisponible</text></svg>');

    const GG = window.GG = {
        recevoir(cle, donnees) { cache.set(cle, donnees); },

        /** Charge data/<cle>.js et retourne les données (mises en cache). */
        charger(cle) {
            if (cache.has(cle)) return Promise.resolve(cache.get(cle));
            if (enCours.has(cle)) return enCours.get(cle);

            const promesse = new Promise((resolve, reject) => {
                const script = document.createElement('script');
                const suffixe = cle === 'meta' ? '?t=' + Date.now()
                    : (versionDonnees ? '?v=' + versionDonnees : '');
                script.src = 'data/' + cle + '.js' + suffixe;
                script.async = true;
                script.onload = () => {
                    script.remove();
                    cache.has(cle) ? resolve(cache.get(cle)) : reject(new Error('Données invalides : ' + cle));
                };
                script.onerror = () => {
                    script.remove();
                    reject(new Error('Fichier introuvable : ' + cle));
                };
                document.head.appendChild(script);
            });
            const nettoyer = () => enCours.delete(cle);
            promesse.then(nettoyer, nettoyer);
            enCours.set(cle, promesse);
            return promesse;
        },

        /** Métadonnées du catalogue (totaux, catégories). Toujours rechargées à neuf. */
        meta() {
            if (!promesseMeta) {
                promesseMeta = GG.charger('meta').then(meta => {
                    versionDonnees = meta.version || '';
                    return meta;
                });
                promesseMeta.catch(() => { promesseMeta = null; });
            }
            return promesseMeta;
        },

        /** Échappe le HTML (à utiliser pour tout texte inséré avec innerHTML). */
        esc(texte) {
            return String(texte ?? '').replace(/[&<>"']/g, c => ({
                '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
            }[c]));
        },

        /** Minuscules sans accents, pour une recherche tolérante. */
        normaliser(texte) {
            return String(texte ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
        },

        /** Reconstruit l'URL complète d'une image de l'index de recherche. */
        imageUrl(chemin, prefixe) {
            return /^https?:/i.test(chemin) ? chemin : (prefixe || '') + chemin;
        },

        /** URL d'origine d'une image RAWG redimensionnée. */
        originale(url) {
            return String(url).replace(/\/media\/resize\/\d+\/-\//, '/media/');
        },

        /** Miniature légère d'une image RAWG (les autres URL restent inchangées). */
        miniature(url, largeur) {
            const m = /^https:\/\/media\.rawg\.io\/media\/(games|screenshots)\/(.+)$/.exec(url);
            return m ? 'https://media.rawg.io/media/resize/' + largeur + '/-/' + m[1] + '/' + m[2] : url;
        },

        /** Id de jeu valide (évite de charger un fichier arbitraire). */
        idValide(id) { return /^[a-z0-9][a-z0-9_-]*$/i.test(id || ''); },

        urlFiche(id) { return 'jeu.html?id=' + encodeURIComponent(id); },

        /** "2026-03-12" -> "12 mars 2026" (une année seule reste telle quelle). */
        formaterDate(iso) {
            if (/^\d{4}$/.test(iso || '')) return iso;
            const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || '');
            if (!m) return '';
            return new Date(Date.UTC(+m[1], +m[2] - 1, +m[3])).toLocaleDateString('fr-FR',
                { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
        },


        PLACEHOLDER
    };

    // Image cassée : on tente l'original, puis une image de remplacement.
    document.addEventListener('error', (e) => {
        const img = e.target;
        if (!(img instanceof HTMLImageElement) || img.dataset.repli === '2') return;
        if (img.closest('[data-sans-repli]')) return;   // ex. bandeau : géré à part
        if (img.dataset.repli !== '1' && GG.originale(img.src) !== img.src) {
            img.dataset.repli = '1';
            img.src = GG.originale(img.src);
        } else {
            img.dataset.repli = '2';
            img.src = PLACEHOLDER;
        }
    }, true);
})();
