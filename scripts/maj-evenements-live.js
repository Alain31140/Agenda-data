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

        const resultats = [];

        // Cherche les lignes marquées
        // "New Eruptive Activity"
        const regex =
            />([^<>]{2,80})<\/a>[\s\S]{0,500}?New Eruptive Activity/gi;

        let correspondance;

        while (
            (
                correspondance =
                    regex.exec(html)
            ) !== null
        ) {

            const nom =
                nettoyerTexte(
                    correspondance[1]
                );

            if (!nom) {
                continue;
            }

            resultats.push({
                date:
                    new Date()
                        .toISOString(),

                icone:
                    "🌋",

                texte:
                    `Activité volcanique nouvelle ou notable : ${nom}`,

                source:
                    "Smithsonian / USGS"
            });
        }

        return resultats;

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