const fs = require("fs");
const path = require("path");

const FICHIER_SORTIE = path.join(
    __dirname,
    "..",
    "json",
    "evenements-live.json"
);

const DUREE_MAX_HEURES = 48;
const NOMBRE_MAX = 8;

// ==================================================
// OUTILS
// ==================================================

function nettoyerTexte(texte) {
    return String(texte || "")
        .replace(/<!\[CDATA\[|\]\]>/g, "")
        .replace(/<[^>]+>/g, "")
        .replace(/&amp;/g, "&")
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'")
        .replace(/&lt;/g, "<")
        .replace(/&gt;/g, ">")
        .replace(/\s+/g, " ")
        .trim();
}

function extraireBalise(bloc, balise) {
    const regex = new RegExp(
        `<${balise}[^>]*>([\\s\\S]*?)<\\/${balise}>`,
        "i"
    );

    const resultat = bloc.match(regex);

    return resultat
        ? nettoyerTexte(resultat[1])
        : "";
}

function dateRecente(date) {
    const limite =
        Date.now()
        -
        DUREE_MAX_HEURES
        * 60
        * 60
        * 1000;

    return date.getTime() >= limite;
}

// ==================================================
// ESA
// ==================================================

async function lireESA() {

    const sources = [
        {
            nom: "ESA",
            icone: "🚀",
            url: "https://www.esa.int/rssfeed/Our_Activities/Space_News"
        },
        {
            nom: "ESA Science",
            icone: "🔭",
            url: "https://www.esa.int/rssfeed/Our_Activities/Space_Science"
        }
    ];

    let resultats = [];

    for (const source of sources) {

        try {

            console.log(`Lecture : ${source.nom}`);

            const reponse =
                await fetch(source.url);

            if (!reponse.ok) {
                throw new Error(
                    `HTTP ${reponse.status}`
                );
            }

            const xml =
                await reponse.text();

            const blocs =
                xml.match(
                    /<item[\s\S]*?<\/item>/gi
                ) || [];

            for (const bloc of blocs) {

                const titre =
                    extraireBalise(
                        bloc,
                        "title"
                    );

                const dateTexte =
                    extraireBalise(
                        bloc,
                        "pubDate"
                    );

                const date =
                    new Date(dateTexte);

                if (
                    !titre
                    ||
                    Number.isNaN(date.getTime())
                    ||
                    !dateRecente(date)
                ) {
                    continue;
                }

                // Petits contenus peu intéressants
                const titreMin =
                    titre.toLowerCase();

                if (
                    titreMin.includes("week in images")
                    ||
                    titreMin.includes("implementation")
                ) {
                    continue;
                }

                resultats.push({
                    date:
                        date.toISOString(),

                    icone:
                        source.icone,

                    texte:
                        `${source.nom} : ${titre}`,

                    source:
                        source.nom
                });
            }

        } catch (erreur) {

            console.error(
                `Erreur ${source.nom} :`,
                erreur.message
            );
        }
    }

    return resultats;
}

// ==================================================
// SÉISMES USGS
// ==================================================

async function lireSeismesUSGS() {

    console.log("Lecture : USGS séismes");

    try {

        const url =
            "https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/4.5_day.geojson";

        const reponse =
            await fetch(url);

        if (!reponse.ok) {
            throw new Error(
                `HTTP ${reponse.status}`
            );
        }

        const donnees =
            await reponse.json();

        return donnees.features
            .filter(feature => {

                const magnitude =
                    feature.properties.mag;

                const date =
                    new Date(
                        feature.properties.time
                    );

                return (
                    magnitude >= 6
                    &&
                    dateRecente(date)
                );
            })
            .map(feature => {

                const magnitude =
                    feature.properties.mag;

                const lieu =
                    feature.properties.place
                    ||
                    "région non précisée";

                const date =
                    new Date(
                        feature.properties.time
                    );

                return {
                    date:
                        date.toISOString(),

                    icone:
                        "🌍",

                    texte:
                        `Séisme de magnitude ${magnitude.toFixed(1)} — ${lieu}`,

                    source:
                        "USGS"
                };
            });

    } catch (erreur) {

        console.error(
            "Erreur USGS séismes :",
            erreur.message
        );

        return [];
    }
}

// ==================================================
// VOLCANS SMITHSONIAN / USGS
// Priorité : France (outre-mer compris), puis Europe
// Maximum : 3 volcans
// ==================================================

async function lireVolcans() {

    console.log(
        "Lecture : Smithsonian volcans"
    );

    try {

        const url =
            "https://volcano.si.edu/reports_weekly.cfm";

        const reponse =
            await fetch(
                url,
                {
                    headers: {
                        "User-Agent":
                            "Agenda-du-jour/1.0"
                    }
                }
            );

        if (!reponse.ok) {
            throw new Error(
                `HTTP ${reponse.status}`
            );
        }

        const html =
            await reponse.text();

        const volcans = [];

        // ------------------------------------------
        // PAYS EUROPÉENS VOLCANIQUES
        // France inclut aussi les territoires
        // français classés "France" par Smithsonian
        // ------------------------------------------

        const PAYS_EUROPE = [
            "France",
            "Italy",
            "Iceland",
            "Greece",
            "Spain",
            "Portugal",
            "Norway"
        ];

        // Traduction pour affichage
        const NOMS_PAYS = {
            France: "France",
            Italy: "Italie",
            Iceland: "Islande",
            Greece: "Grèce",
            Spain: "Espagne",
            Portugal: "Portugal",
            Norway: "Norvège"
        };

        // ------------------------------------------
        // EXTRACTION DES LIGNES DU TABLEAU
        // ------------------------------------------

        const lignes =
            html.match(
                /<tr[\s\S]*?<\/tr>/gi
            ) || [];

        for (const ligne of lignes) {

            const cellules = [
                ...ligne.matchAll(
                    /<td[^>]*>([\s\S]*?)<\/td>/gi
                )
            ].map(
                correspondance =>
                    nettoyerTexte(
                        correspondance[1]
                    )
            );

            // Tableau Smithsonian :
            // 0 = nom
            // 1 = pays
            // 2 = région volcanique
            // 3 = début éruption
            // 4 = type de rapport

            if (cellules.length < 5) {
                continue;
            }

            const nom =
                cellules[0];

            const pays =
                cellules[1];

            const region =
                cellules[2];

            const type =
                cellules[4];

            if (
                !nom
                ||
                !pays
                ||
                !type
            ) {
                continue;
            }

            // --------------------------------------
            // On ne garde que les nouveautés
            // significatives
            // --------------------------------------

            const typeMin =
                type.toLowerCase();

            const estNouveau =
                typeMin.includes(
                    "new eruptive activity"
                )
                ||
                typeMin.includes(
                    "new unrest"
                );

            if (!estNouveau) {
                continue;
            }

            volcans.push({
                nom,
                pays,
                region,
                type
            });
        }

        // ------------------------------------------
        // ÉVITER LES DOUBLONS
        // ------------------------------------------

        const uniques = [];

        const nomsVus =
            new Set();

        for (const volcan of volcans) {

            const cle =
                volcan.nom
                    .toLowerCase();

            if (nomsVus.has(cle)) {
                continue;
            }

            nomsVus.add(cle);

            uniques.push(volcan);
        }

        // ------------------------------------------
        // PRIORITÉS
        //
        // 1 - France, outre-mer compris
        // 2 - reste de l'Europe
        // 3 - si rien en Europe :
        //     un seul volcan ailleurs
        // ------------------------------------------

        const france =
            uniques.filter(
                volcan =>
                    volcan.pays === "France"
            );

        const europe =
            uniques.filter(
                volcan =>
                    volcan.pays !== "France"
                    &&
                    PAYS_EUROPE.includes(
                        volcan.pays
                    )
            );

        const monde =
            uniques.filter(
                volcan =>
                    !PAYS_EUROPE.includes(
                        volcan.pays
                    )
            );

        let retenus = [];

        if (
            france.length > 0
            ||
            europe.length > 0
        ) {

            retenus = [
                ...france,
                ...europe
            ].slice(
                0,
                3
            );

        } else {

            // Pas d'activité nouvelle en Europe :
            // seulement UNE info volcanique mondiale.

            retenus =
                monde.slice(
                    0,
                    1
                );
        }

        // ------------------------------------------
        // CONSTRUCTION DES MESSAGES
        // ------------------------------------------

        return retenus.map(
            volcan => {

                const paysAffiche =
                    NOMS_PAYS[volcan.pays]
                    ||
                    volcan.pays;

                let typeAffiche =
                    "activité volcanique notable";

                if (
                    volcan.type
                        .toLowerCase()
                        .includes(
                            "new eruptive activity"
                        )
                ) {
                    typeAffiche =
                        "nouvelle activité éruptive";
                }

                if (
                    volcan.type
                        .toLowerCase()
                        .includes(
                            "new unrest"
                        )
                ) {
                    typeAffiche =
                        "nouvelle agitation volcanique";
                }

                const localisation =
                    volcan.region
                        ? `${paysAffiche} — ${volcan.region}`
                        : paysAffiche;

                return {

                    date:
                        new Date()
                            .toISOString(),

                    icone:
                        "🌋",

                    texte:
                        `${volcan.nom} — ${localisation} : ${typeAffiche}`,

                    source:
                        "Smithsonian / USGS"
                };
            }
        );

    } catch (erreur) {

        console.error(
            "Erreur Smithsonian volcans :",
            erreur.message
        );

        return [];
    }
}

// ==================================================
// PROGRAMME PRINCIPAL
// ==================================================

async function principal() {

    let evenements = [];

    const [
        esa,
        seismes,
        volcans
    ] = await Promise.all([
        lireESA(),
        lireSeismesUSGS(),
        lireVolcans()
    ]);

    evenements.push(
        ...esa,
        ...seismes,
        ...volcans
    );

    // Doublons
    const vus = new Set();

    evenements =
        evenements.filter(
            evenement => {

                const cle =
                    evenement.texte
                        .toLowerCase();

                if (vus.has(cle)) {
                    return false;
                }

                vus.add(cle);

                return true;
            }
        );

    // Plus récent en premier
    evenements.sort(
        (a, b) =>
            new Date(b.date)
            -
            new Date(a.date)
    );

    // Limite pour le bandeau
    evenements =
        evenements.slice(
            0,
            NOMBRE_MAX
        );

    fs.writeFileSync(
        FICHIER_SORTIE,
        JSON.stringify(
            evenements,
            null,
            2
        )
        +
        "\n",
        "utf8"
    );

    console.log(
        `${evenements.length} événement(s) live enregistré(s)`
    );
}

principal();