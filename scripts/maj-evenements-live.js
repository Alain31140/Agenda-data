const fs = require("fs");
const path = require("path");

const FICHIER_SORTIE = path.join(
    __dirname,
    "..",
    "json",
    "evenements-live.json"
);

// --------------------------------------------------
// RÉGLAGES
// --------------------------------------------------

const DUREE_MAX_HEURES = 48;
const NOMBRE_MAX = 5;

const SOURCES = [
    {
        nom: "ESA",
        icone: "🚀",
        url: "https://www.esa.int/rssfeed/Our_Activities/Space_News"
    },
    {
        nom: "ESA Science",
        icone: "🔭",
        url: "https://www.esa.int/rssfeed/Our_Activities/Space_Science"
    },
    {
        nom: "NASA/JPL",
        icone: "🛰️",
        url: "https://www.jpl.nasa.gov/feeds/news/"
    }
];

// Mots à exclure absolument.
const MOTS_INTERDITS = [
    "politic",
    "election",
    "president",
    "government",
    "minister",
    "war",
    "military",
    "attack",
    "terror",
    "conflict",
    "religion",
    "murder",
    "crime",
    "court",
    "trial"
];


// --------------------------------------------------
// OUTILS
// --------------------------------------------------

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


function contientMotInterdit(texte) {

    const t = texte.toLowerCase();

    return MOTS_INTERDITS.some(
        mot => t.includes(mot)
    );
}


function convertirDate(dateTexte) {

    const date = new Date(dateTexte);

    return Number.isNaN(date.getTime())
        ? null
        : date;
}


// --------------------------------------------------
// LECTURE D'UN FLUX RSS
// --------------------------------------------------

async function lireFlux(source) {

    try {

        console.log(
            `Lecture : ${source.nom}`
        );

        const reponse = await fetch(
            source.url,
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

        const xml =
            await reponse.text();

        const blocs =
            xml.match(
                /<item[\s\S]*?<\/item>/gi
            ) || [];

        const maintenant =
            new Date();

        const limite =
            new Date(
                maintenant.getTime()
                -
                DUREE_MAX_HEURES
                * 60
                * 60
                * 1000
            );

        return blocs
            .map(bloc => {

                const titre =
                    extraireBalise(
                        bloc,
                        "title"
                    );

                const dateTexte =
                    extraireBalise(
                        bloc,
                        "pubDate"
                    )
                    ||
                    extraireBalise(
                        bloc,
                        "date"
                    );

                const date =
                    convertirDate(
                        dateTexte
                    );

                if (
                    !titre
                    ||
                    !date
                    ||
                    date < limite
                ) {
                    return null;
                }

                if (
                    contientMotInterdit(
                        titre
                    )
                ) {
                    return null;
                }

                return {
                    date:
                        date.toISOString(),

                    icone:
                        source.icone,

                    texte:
                        `${source.nom} : ${titre}`,

                    source:
                        source.nom
                };
            })
            .filter(Boolean);

    } catch (erreur) {

        console.error(
            `Erreur ${source.nom} :`,
            erreur.message
        );

        return [];
    }
}


// --------------------------------------------------
// PROGRAMME PRINCIPAL
// --------------------------------------------------

async function principal() {

    let evenements = [];

    for (
        const source
        of SOURCES
    ) {

        const resultats =
            await lireFlux(source);

        evenements.push(
            ...resultats
        );
    }


    // Plus récent en premier.
    evenements.sort(
        (a, b) =>
            new Date(b.date)
            -
            new Date(a.date)
    );


    // Éviter les doublons.
    const titresVus =
        new Set();

    evenements =
        evenements.filter(
            evenement => {

                const cle =
                    evenement.texte
                        .toLowerCase();

                if (
                    titresVus.has(cle)
                ) {
                    return false;
                }

                titresVus.add(cle);

                return true;
            }
        );


    // Éviter de surcharger le bandeau.
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