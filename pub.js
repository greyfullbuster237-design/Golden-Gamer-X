/* ==========================================================================
   GOLDEN GAMER X - Consentement aux cookies (RGPD) + publicités Google AdSense
   - AUCUN script publicitaire n'est chargé avant que le visiteur ait accepté.
   - Refuser est aussi simple qu'accepter : le site reste entièrement accessible.
   - Sans identifiants AdSense renseignés (ci-dessous), aucune publicité ni boîte vide.
   ========================================================================== */
(function () {
    'use strict';

    // ======================== À MODIFIER (voir LISEZMOI.txt) ========================
    const CONFIG = {
        idEditeur: 'ca-pub-XXXXXXXXXXXXXXXX',    // votre ID éditeur AdSense
        emplacement: 'XXXXXXXXXX',               // data-ad-slot de votre unité "in-feed"
        cleMiseEnPage: 'XXXXXXXXXXXXXXXX',       // data-ad-layout-key de cette unité
        apercu: false                            // true = encadré de test pour vérifier la mise en page
    };
    // ===============================================================================

    const CLE = 'gg_cookies';        // 'accepte' | 'refuse'
    let scriptCharge = false;

    function lire() {
        try { return localStorage.getItem(CLE); } catch (_) { return null; }
    }
    function ecrire(valeur) {
        try { localStorage.setItem(CLE, valeur); } catch (_) { /* navigation privée : choix valable pour la page */ }
    }

    const configure = () => !/X{6,}/.test(CONFIG.idEditeur + CONFIG.emplacement + CONFIG.cleMiseEnPage);
    const adsActives = () => lire() === 'accepte' && configure();

    function chargerAdsense() {
        if (scriptCharge || !configure()) return;
        scriptCharge = true;
        const s = document.createElement('script');
        s.async = true;
        s.crossOrigin = 'anonymous';
        s.src = 'https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=' +
                encodeURIComponent(CONFIG.idEditeur);
        document.head.appendChild(s);
    }

    // ------------------------------- Bandeau -------------------------------
    function fermerBandeau() {
        const b = document.getElementById('bandeau-cookies');
        if (b) b.remove();
        document.body.classList.remove('avec-bandeau');
    }

    function choisir(valeur) {
        const avant = lire();
        ecrire(valeur);
        fermerBandeau();
        if (valeur === 'accepte') {
            chargerAdsense();
            document.dispatchEvent(new Event('gg:consentement'));   // le catalogue se réaffiche avec ses annonces
        } else if (avant === 'accepte') {
            location.reload();    // retire proprement les scripts publicitaires déjà chargés
        }
    }

    function afficherBandeau() {
        if (document.getElementById('bandeau-cookies')) return;
        const b = document.createElement('section');
        b.id = 'bandeau-cookies';
        b.className = 'bandeau-cookies';
        b.setAttribute('role', 'dialog');
        b.setAttribute('aria-label', 'Gestion des cookies');
        b.innerHTML = `
            <div class="bandeau-cookies-texte">
                <strong>🍪 Vos choix sur les cookies</strong>
                <p>Ce site est financé par la publicité. Google AdSense et ses partenaires peuvent déposer des cookies
                pour afficher des annonces personnalisées et mesurer leur efficacité, <b>uniquement avec votre accord</b>.
                Vous pouvez refuser : le site reste entièrement accessible.
                <a href="confidentialite.html">Politique de confidentialité</a></p>
            </div>
            <div class="bandeau-cookies-actions">
                <button type="button" class="btn-cookies" data-choix="refuse">Refuser</button>
                <button type="button" class="btn-cookies" data-choix="accepte">Accepter</button>
            </div>`;
        b.addEventListener('click', (e) => {
            const bouton = e.target.closest('[data-choix]');
            if (bouton) choisir(bouton.dataset.choix);
        });
        document.body.appendChild(b);
        document.body.classList.add('avec-bandeau');
    }

    // ------------------------------ Annonces -------------------------------
    /** HTML de l'emplacement "in-feed" (vide si pas de consentement ou pas configuré). */
    function emplacementHtml() {
        if (CONFIG.apercu) {
            return `<aside class="pub-container-infeed" aria-label="Publicité">
                        <span class="pub-label">Publicité</span>
                        <div class="pub-apercu">Espace publicitaire (aperçu)</div>
                    </aside>`;
        }
        if (!adsActives()) return '';
        return `<aside class="pub-container-infeed" aria-label="Publicité">
                    <span class="pub-label">Publicité</span>
                    <ins class="adsbygoogle" style="display:block"
                         data-ad-format="fluid"
                         data-ad-layout-key="${CONFIG.cleMiseEnPage}"
                         data-ad-client="${CONFIG.idEditeur}"
                         data-ad-slot="${CONFIG.emplacement}"></ins>
                </aside>`;
    }

    /** À appeler APRÈS l'insertion dans le DOM : demande une annonce pour chaque nouvel emplacement. */
    function activer(racine) {
        if (CONFIG.apercu || !adsActives()) return;
        racine.querySelectorAll('ins.adsbygoogle').forEach((ins) => {
            if (ins.dataset.gg === '1') return;     // un emplacement ne se demande qu'une seule fois
            ins.dataset.gg = '1';
            try { (window.adsbygoogle = window.adsbygoogle || []).push({}); } catch (_) { /* bloqueur de pub, etc. */ }
        });
    }

    window.GGPub = { emplacementHtml, activer, rouvrir: afficherBandeau };

    // ------------------------------ Démarrage ------------------------------
    document.addEventListener('click', (e) => {
        if (e.target.closest && e.target.closest('[data-gerer-cookies]')) {
            e.preventDefault();
            afficherBandeau();
        }
    });

    const etat = lire();
    if (etat === null) afficherBandeau();
    else if (etat === 'accepte') chargerAdsense();
})();
