const fs = require("fs");
const path = require("path");

const sortie = path.join(
    __dirname,
    "..",
    "json",
    "evenements-live.json"
);

// Pour l'instant, aucune source automatique.
// On prépare simplement la mécanique.
const evenements = [];

// Écriture propre du JSON.
fs.writeFileSync(
    sortie,
    JSON.stringify(evenements, null, 2) + "\n",
    "utf8"
);

console.log("evenements-live.json mis à jour");