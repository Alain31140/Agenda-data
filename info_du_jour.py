#!/usr/bin/env python3
"""Infos du jour -> image Instagram style cahier Seyès, puis publication optionnelle.

V2 pour le dépôt GitHub Agenda-data.

Exemples :
    python info_du_jour.py generate --date 2026-08-17
    python info_du_jour.py show --date 2026-08-17
    python info_du_jour.py publish --file Instagram/2026-08-17.png

La page Seyès est dessinée directement par le programme :
aucune image de fond n'est nécessaire.

La publication Instagram utilise l'Instagram API avec Instagram Login.
Les identifiants/tokens ne sont jamais stockés dans le code : ils viennent
des variables d'environnement.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
import unicodedata
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont


# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = ROOT / "Instagram"

DEFAULT_TIMEZONE = os.getenv("TIMEZONE", "Europe/Paris")

# On conserve Paris comme référence pour le Soleil.
DEFAULT_LATITUDE = 48.8566
DEFAULT_LONGITUDE = 2.3522
DEFAULT_LOCATION_NAME = "Paris"

MOON_DIR = ROOT / "Instagram" / "lune"
SYNODIC_MONTH_DAYS = 29.53058867

MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]

WEEKDAYS_FR = [
    "lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"
]


ZODIAC_FUN = {
    "Bélier": "fonce d'abord, réfléchit parfois après 😄",
    "Taureau": "épicurien, fidèle… et peu fan qu'on bouscule ses habitudes",
    "Gémeaux": "curieux, bavard, déjà passé à trois autres idées",
    "Cancer": "sensible, protecteur, avec radar émotionnel intégré",
    "Lion": "solaire, généreux, un brin théâtral",
    "Vierge": "organisée, attentive… même au détail que personne n'avait vu",
    "Balance": "charme, diplomatie… et cinq minutes de plus pour choisir",
    "Scorpion": "intense, mystérieux, rarement tiède",
    "Sagittaire": "optimiste, voyageur, déjà prêt à repartir",
    "Capricorne": "sérieux en façade, humour bien caché",
    "Verseau": "original, indépendant, souvent une idée d'avance",
    "Poissons": "rêveur, intuitif, parfois déjà ailleurs",
}

ZODIAC_SYMBOLS = {
    "Bélier": "♈", "Taureau": "♉", "Gémeaux": "♊", "Cancer": "♋",
    "Lion": "♌", "Vierge": "♍", "Balance": "♎", "Scorpion": "♏",
    "Sagittaire": "♐", "Capricorne": "♑", "Verseau": "♒", "Poissons": "♓",
}

ZODIAC_DIR_CANDIDATES = [
    ROOT / "zodiac",
    ROOT / "Instagram" / "zodiac",
    ROOT / "instagram" / "zodiac",
    ROOT / "assets" / "zodiac",
    ROOT / "images" / "zodiac",
]

ZODIAC_IMAGE_ALIASES = {
    "Bélier": ["belier", "bélier", "bélier_kawaii_au_bandana_rouge"],
    "Taureau": ["taureau", "taureau_kawaii_dans_un_fauteuil_vert"],
    "Gémeaux": ["gemeaux", "gémeaux", "jumeaux_gémeaux_en_sticker_kawaii"],
    "Cancer": ["cancer"],
    "Lion": ["lion", "lion_royal_avec_couronne_dorée"],
    "Vierge": ["vierge"],
    "Balance": ["balance", "balance_dorée_kawaii_avec_cœur_et_plume"],
    "Scorpion": ["scorpion", "scorpion_violet_kawaii_brillant"],
    "Sagittaire": ["sagittaire", "archère_chibi_du_sagittaire_étoilée"],
    "Capricorne": ["capricorne", "capricorne_kawaii_dans_les_montagnes"],
    "Verseau": ["verseau", "verseau_chibi_et_urne_dorée_scintillante"],
    "Poissons": ["poissons"],
}


def slugify_name(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return text


def find_zodiac_image(sign_name: str) -> Path | None:
    aliases = ZODIAC_IMAGE_ALIASES.get(sign_name, [])
    wanted = {slugify_name(a) for a in aliases + [sign_name] if a}

    for folder in ZODIAC_DIR_CANDIDATES:
        if not folder.exists():
            continue
        for ext in ("*.png", "*.webp", "*.jpg", "*.jpeg"):
            for p in folder.glob(ext):
                if slugify_name(p.stem) in wanted:
                    return p
        for ext in ("*.png", "*.webp", "*.jpg", "*.jpeg"):
            for p in folder.glob(ext):
                stem = slugify_name(p.stem)
                if any(token in stem for token in wanted):
                    return p
    # Dernier secours : recherche globale dans le dépôt.
    for p in ROOT.rglob("*.png"):
        if ".git" in p.parts:
            continue
        stem = slugify_name(p.stem)
        if any(token in stem for token in wanted):
            return p
    return None


def zodiac_for_date(target: date) -> dict[str, str]:
    md = (target.month, target.day)
    if (3, 21) <= md <= (4, 19):
        name = "Bélier"
    elif (4, 20) <= md <= (5, 20):
        name = "Taureau"
    elif (5, 21) <= md <= (6, 20):
        name = "Gémeaux"
    elif (6, 21) <= md <= (7, 22):
        name = "Cancer"
    elif (7, 23) <= md <= (8, 22):
        name = "Lion"
    elif (8, 23) <= md <= (9, 22):
        name = "Vierge"
    elif (9, 23) <= md <= (10, 22):
        name = "Balance"
    elif (10, 23) <= md <= (11, 21):
        name = "Scorpion"
    elif (11, 22) <= md <= (12, 21):
        name = "Sagittaire"
    elif md >= (12, 22) or md <= (1, 19):
        name = "Capricorne"
    elif (1, 20) <= md <= (2, 18):
        name = "Verseau"
    else:
        name = "Poissons"
    return {
        "name": name,
        "symbol": ZODIAC_SYMBOLS[name],
        "fun": ZODIAC_FUN[name],
    }


DATA_BASENAMES = {
    "saints": "saints.json",
    "dictons": "dictons-du-jour.json",
    "mondiales": "journees-mondiales.json",
    "insolites": "journees-insolites.json",
}

# Couleur principale selon le jour de la semaine.
DAY_COLORS = {
    0: "#4E7AC7",  # lundi - bleu
    1: "#4D9A68",  # mardi - vert
    2: "#E58B37",  # mercredi - orange
    3: "#7B61A8",  # jeudi - violet
    4: "#D6A51D",  # vendredi - jaune/or
    5: "#2D9FA3",  # samedi - turquoise
    6: "#C77D93",  # dimanche - rose doux
}

# Petite teinte saisonnière.
SEASON_ACCENTS = {
    "hiver": "#DCE8F3",
    "printemps": "#E6F2DE",
    "ete": "#FFF0CF",
    "automne": "#F4E2D3",
}


# ============================================================
# OUTILS DONNÉES
# ============================================================

def normalize_name(name: str) -> str:
    """Tolère les suffixes de copie du type '(1)' dans les fichiers téléchargés."""
    stem = Path(name).stem
    stem = stem.replace("(1)", "").replace(" (1)", "")
    return stem.lower().replace("_", "-")


def find_data_file(expected_name: str) -> Path:
    expected = normalize_name(expected_name)
    candidates = [
        ROOT, ROOT / "json", ROOT / "JSON", ROOT / "data", ROOT / "Data",
        ROOT / "data-save", ROOT / "Data-save", ROOT / "data_save", ROOT / "Data_save"
    ]

    for folder in candidates:
        if not folder.exists():
            continue
        for p in folder.glob("*.json"):
            if normalize_name(p.name) == expected:
                return p

    for p in ROOT.rglob("*.json"):
        if ".git" in p.parts:
            continue
        if normalize_name(p.name) == expected:
            return p

    raise FileNotFoundError(
        f"Impossible de trouver {expected_name} dans le dépôt."
    )


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def normalize_items(value: Any) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, dict):
        return [value]
    if isinstance(value, list):
        return [x for x in value if isinstance(x, dict)]
    return []


def labels_from_value(value: Any) -> list[str]:
    labels: list[str] = []

    for item in normalize_items(value):
        label = str(item.get("label", "")).strip()
        if not label:
            continue

        # Certains fichiers mettent plusieurs journées dans un même label,
        # séparées par "|".
        for piece in label.split("|"):
            piece = piece.strip()
            if piece:
                labels.append(piece)

    return labels


def fun_labels(value: Any) -> list[str]:
    out: list[str] = []

    for item in normalize_items(value):
        label = str(item.get("label", "")).strip()
        emoji = str(item.get("emoji", "")).strip()

        if label:
            out.append(f"{emoji} {label}".strip())

    return out


def format_date_fr(d: date) -> str:
    return (
        f"{WEEKDAYS_FR[d.weekday()]} "
        f"{d.day} "
        f"{MONTHS_FR[d.month - 1]} "
        f"{d.year}"
    )


def parse_target_date(raw: str | None, timezone: str) -> date:
    if raw:
        return date.fromisoformat(raw)
    return datetime.now(ZoneInfo(timezone)).date()


def get_day_data(target: date) -> dict[str, Any]:
    key = target.strftime("%d-%m")

    files: dict[str, Path | None] = {}
    db: dict[str, dict[str, Any]] = {}

    for name, filename in DATA_BASENAMES.items():
        try:
            path = find_data_file(filename)
            files[name] = path
            db[name] = load_json(path)
        except FileNotFoundError:
            if name == "saints":
                raise
            files[name] = None
            db[name] = {}

    saint_obj = db["saints"].get(key) or {}
    saint = saint_obj.get("label") if isinstance(saint_obj, dict) else None
    saint_type = saint_obj.get("type") if isinstance(saint_obj, dict) else None
    saint_info = (
        str(saint_obj.get("info") or "").strip()
        if isinstance(saint_obj, dict)
        else ""
    )
    zodiac = zodiac_for_date(target)
    zodiac_image = find_zodiac_image(zodiac["name"])
    if zodiac_image:
        zodiac["image"] = str(zodiac_image)

    dicton = db["dictons"].get(key)
    if dicton is not None:
        dicton = str(dicton).strip()

    mondiales = labels_from_value(db["mondiales"].get(key))
    insolites = fun_labels(db["insolites"].get(key))

    # Pour l'image, on limite volontairement :
    # 2 journées principales + 1 journée fun.
    mondiales = mondiales[:2]
    insolites = insolites[:1]

    return {
        "key": key,
        "date": target.isoformat(),
        "date_fr": format_date_fr(target),
        "saint": saint,
        "saint_type": saint_type,
        "saint_info": saint_info,
        "zodiac": zodiac,
        "dicton": dicton,
        "journees_mondiales": mondiales,
        "journees_fun": insolites,
        "source_files": {
            k: (str(v.relative_to(ROOT)) if v else "")
            for k, v in files.items()
        },
    }


# ============================================================
# SOLEIL
# ============================================================

def compute_sun_times(
    target: date,
    latitude: float | None,
    longitude: float | None,
    timezone: str,
) -> tuple[str | None, str | None]:
    """Calcule lever/coucher avec l'algorithme solaire NOAA simplifié."""
    if latitude is None or longitude is None:
        return None, None

    zenith = 90.833
    day_of_year = target.timetuple().tm_yday
    lng_hour = longitude / 15.0
    tz = ZoneInfo(timezone)

    noon = datetime(
        target.year,
        target.month,
        target.day,
        12,
        0,
        tzinfo=tz
    )

    offset_hours = noon.utcoffset().total_seconds() / 3600.0

    def event(is_sunrise: bool) -> str | None:
        approx = day_of_year + (
            ((6 if is_sunrise else 18) - lng_hour) / 24.0
        )

        mean_anomaly = (0.9856 * approx) - 3.289

        true_long = (
            mean_anomaly
            + 1.916 * math.sin(math.radians(mean_anomaly))
            + 0.020 * math.sin(math.radians(2 * mean_anomaly))
            + 282.634
        ) % 360.0

        right_ascension = math.degrees(
            math.atan(
                0.91764 * math.tan(math.radians(true_long))
            )
        ) % 360.0

        l_quadrant = math.floor(true_long / 90.0) * 90.0
        ra_quadrant = math.floor(right_ascension / 90.0) * 90.0

        right_ascension = (
            right_ascension
            + l_quadrant
            - ra_quadrant
        ) / 15.0

        sin_dec = 0.39782 * math.sin(math.radians(true_long))
        cos_dec = math.cos(math.asin(sin_dec))

        cos_h = (
            math.cos(math.radians(zenith))
            - sin_dec * math.sin(math.radians(latitude))
        ) / (
            cos_dec * math.cos(math.radians(latitude))
        )

        if cos_h > 1 or cos_h < -1:
            return None

        if is_sunrise:
            hour_angle = 360.0 - math.degrees(math.acos(cos_h))
        else:
            hour_angle = math.degrees(math.acos(cos_h))

        hour_angle /= 15.0

        local_mean = (
            hour_angle
            + right_ascension
            - (0.06571 * approx)
            - 6.622
        )

        utc_hour = (local_mean - lng_hour) % 24.0
        local_hour = (utc_hour + offset_hours) % 24.0

        total_minutes = int(round(local_hour * 60)) % (24 * 60)

        return (
            f"{total_minutes // 60:02d}:"
            f"{total_minutes % 60:02d}"
        )

    return event(True), event(False)


# ============================================================
# LUNE
# ============================================================

def compute_moon_phase(target: date) -> dict[str, Any]:
    """Retourne une des 8 phases lunaires et le PNG associé."""
    reference = datetime(
        2000, 1, 6, 18, 14,
        tzinfo=ZoneInfo("UTC")
    )

    current = datetime(
        target.year,
        target.month,
        target.day,
        12,
        0,
        tzinfo=ZoneInfo("UTC")
    )

    age_days = (
        (current - reference).total_seconds() / 86400.0
    ) % SYNODIC_MONTH_DAYS

    fraction = age_days / SYNODIC_MONTH_DAYS

    index = int(
        math.floor(
            fraction * 8.0 + 0.5
        )
    ) % 8

    phases = [
        ("Nouvelle lune", "nouvelle-lune.png"),
        ("Premier croissant", "premier-croissant.png"),
        ("Premier quartier", "premier-quartier.png"),
        ("Gibbeuse croissante", "gibbeuse-croissante.png"),
        ("Pleine lune", "pleine-lune.png"),
        ("Gibbeuse décroissante", "gibbeuse-decroissante.png"),
        ("Dernier quartier", "dernier-quartier.png"),
        ("Dernier croissant", "dernier-croissant.png"),
    ]

    name, filename = phases[index]

    return {
        "name": name,
        "filename": filename,
        "path": MOON_DIR / filename,
        "index": index,
        "age_days": round(age_days, 2),
        "illumination_percent": round(
            50.0 * (
                1.0 - math.cos(2.0 * math.pi * fraction)
            ),
            1
        ),
    }


# ============================================================
# POLICES ET TEXTE
# ============================================================

FONT_DIR = ROOT / "Instagram" / "fonts"
PATRICK_HAND = FONT_DIR / "PatrickHand-Regular.ttf"


def find_font(
    bold: bool,
    size: int,
    handwritten: bool = False,
) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Utilise Patrick Hand pour tout le visuel."""
    if PATRICK_HAND.exists():
        return ImageFont.truetype(str(PATRICK_HAND), size)

    candidates = [
        "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            pass
    return ImageFont.load_default()

def text_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.ImageFont,
    max_width: int,
) -> list[str]:
    words = text.split()

    if not words:
        return []

    lines: list[str] = []
    current = words[0]

    for word in words[1:]:
        candidate = current + " " + word

        if text_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word

    lines.append(current)
    return lines


def draw_wrapped(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    font: ImageFont.ImageFont,
    fill: str,
    max_width: int,
    line_gap: int = 6,
    bullet: str | None = None,
) -> int:
    x, y = xy
    lines = wrap_text(draw, text, font, max_width)

    if not lines:
        return y

    bbox = draw.textbbox((0, 0), "Ag", font=font)
    line_h = bbox[3] - bbox[1]

    for i, line in enumerate(lines):
        prefix = bullet if (i == 0 and bullet) else ""
        draw.text(
            (x, y),
            f"{prefix}{line}",
            font=font,
            fill=fill
        )
        y += line_h + line_gap

    return y


def fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    max_width: int,
    start_size: int,
    min_size: int = 22,
    bold: bool = False,
    handwritten: bool = False,
) -> ImageFont.ImageFont:
    size = start_size

    while size >= min_size:
        font = find_font(
            bold=bold,
            size=size,
            handwritten=handwritten,
        )

        if text_width(draw, text, font) <= max_width:
            return font

        size -= 2

    return find_font(
        bold=bold,
        size=min_size,
        handwritten=handwritten,
    )


# ============================================================
# STYLE SEYÈS
# ============================================================

def season_for_date(target: date) -> str:
    m = target.month

    if m in (12, 1, 2):
        return "hiver"
    if m in (3, 4, 5):
        return "printemps"
    if m in (6, 7, 8):
        return "ete"

    return "automne"


def draw_seyes_page(
    img: Image.Image,
    target: date,
) -> None:
    """Dessine une vraie feuille Seyès : bord gauche déchiré, perforations,
    légère ombre et coin inférieur droit corné.
    """
    W, H = img.size

    # --------------------------------------------------------
    # FOND EXTÉRIEUR + OMBRE DE LA FEUILLE
    # --------------------------------------------------------
    outer = Image.new("RGB", (W, H), "#D9D2C7")
    img.paste(outer)

    paper_left = 28
    paper_top = 18
    paper_right = W - 22
    paper_bottom = H - 18

    # Bord gauche volontairement irrégulier (effet feuille arrachée).
    tear_points = [
        (paper_left + 14, paper_top),
        (paper_left + 5, 48),
        (paper_left + 19, 78),
        (paper_left + 8, 112),
        (paper_left + 23, 146),
        (paper_left + 7, 184),
        (paper_left + 18, 222),
        (paper_left + 4, 262),
        (paper_left + 20, 300),
        (paper_left + 8, 340),
        (paper_left + 24, 380),
        (paper_left + 5, 420),
        (paper_left + 19, 462),
        (paper_left + 7, 506),
        (paper_left + 23, 550),
        (paper_left + 5, 594),
        (paper_left + 20, 640),
        (paper_left + 8, 686),
        (paper_left + 24, 732),
        (paper_left + 6, 780),
        (paper_left + 19, 828),
        (paper_left + 7, 876),
        (paper_left + 22, 924),
        (paper_left + 5, 972),
        (paper_left + 16, paper_bottom),
    ]

    paper_polygon = (
        tear_points
        + [
            (paper_right - 22, paper_bottom),
            (paper_right, paper_bottom - 22),
            (paper_right, paper_top + 18),
            (paper_right - 18, paper_top),
        ]
    )

    # Ombre décalée.
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_poly = [(x + 8, y + 8) for x, y in paper_polygon]
    shadow_draw.polygon(shadow_poly, fill=(55, 45, 35, 55))
    img_rgba = img.convert("RGBA")
    img_rgba.alpha_composite(shadow)

    # --------------------------------------------------------
    # MASQUE DE LA FEUILLE
    # --------------------------------------------------------
    mask = Image.new("L", (W, H), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.polygon(paper_polygon, fill=255)

    # Perforations sur la gauche.
    hole_x = paper_left + 34
    for cy in range(74, H - 48, 72):
        mask_draw.ellipse(
            (hole_x - 13, cy - 13, hole_x + 13, cy + 13),
            fill=0
        )

    # Papier ivoire avec très légère teinte saisonnière.
    season = season_for_date(target)
    paper = Image.new("RGB", (W, H), SEASON_ACCENTS[season])
    paper_overlay = Image.new("RGBA", (W, H), (251, 248, 239, 226))
    paper_rgba = paper.convert("RGBA")
    paper_rgba.alpha_composite(paper_overlay)
    paper = paper_rgba.convert("RGB")

    img_rgba.paste(paper.convert("RGBA"), (0, 0), mask)
    img.paste(img_rgba.convert("RGB"))

    # --------------------------------------------------------
    # RÉGLURE SEYÈS, CLIPPÉE À LA FEUILLE
    # --------------------------------------------------------
    lines = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    lines_draw = ImageDraw.Draw(lines)

    y_start = 70
    major_step = 32
    minor_step = major_step / 4
    major = "#A9C9E7"
    minor = "#D7E6F4"

    y = y_start
    while y < H:
        for n in range(4):
            yy = y + n * minor_step
            if yy >= H:
                break
            lines_draw.line(
                (0, int(yy), W, int(yy)),
                fill=major if n == 0 else minor,
                width=2 if n == 0 else 1
            )
        y += major_step

    # Marge rouge de cahier.
    margin_x = 108
    lines_draw.line((margin_x, 0, margin_x, H), fill="#D96B6B", width=3)
    lines_draw.line((margin_x + 10, 0, margin_x + 10, H), fill="#E6A0A0", width=1)

    alpha = lines.getchannel("A")
    clipped_alpha = Image.composite(alpha, Image.new("L", (W, H), 0), mask)
    lines.putalpha(clipped_alpha)

    base = img.convert("RGBA")
    base.alpha_composite(lines)
    img.paste(base.convert("RGB"))

    # --------------------------------------------------------
    # COIN INFÉRIEUR DROIT CORNÉ
    # --------------------------------------------------------
    draw = ImageDraw.Draw(img)
    fold = 105
    x2 = paper_right
    y2 = paper_bottom

    # Petite ombre sous le pli.
    draw.polygon(
        [(x2 - fold - 8, y2), (x2, y2 - fold - 8), (x2, y2)],
        fill="#C8BFAF"
    )

    # Face repliée.
    draw.polygon(
        [(x2 - fold, y2), (x2, y2 - fold), (x2 - 10, y2 - 10)],
        fill="#F2E9D8"
    )
    draw.line(
        (x2 - fold, y2, x2, y2 - fold),
        fill="#BFB4A3",
        width=2
    )

    # Marqueur volontairement visible dans GitHub Desktop :
    # STYLE_SEYES_DECHIREE_V2


def underline(
    draw: ImageDraw.ImageDraw,
    x1: int,
    x2: int,
    y: int,
    color: str,
    width: int = 3,
) -> None:
    draw.line(
        (x1, y, x2, y),
        fill=color,
        width=width
    )


def draw_small_sun(
    draw: ImageDraw.ImageDraw,
    cx: int,
    cy: int,
    radius: int = 24,
) -> None:
    draw.ellipse(
        (cx - radius, cy - radius, cx + radius, cy + radius),
        fill="#FFD45A",
        outline="#DAA61C",
        width=3
    )

    for angle in range(0, 360, 45):
        rad = math.radians(angle)

        x1 = cx + int((radius + 6) * math.cos(rad))
        y1 = cy + int((radius + 6) * math.sin(rad))

        x2 = cx + int((radius + 18) * math.cos(rad))
        y2 = cy + int((radius + 18) * math.sin(rad))

        draw.line(
            (x1, y1, x2, y2),
            fill="#DAA61C",
            width=3
        )


WEEKDAY_DECO_FILES = {
    0: "lundi.png",
    1: "mardi.png",
    2: "mercredi.png",
    3: "jeudi.png",
    4: "vendredi.png",
    5: "samedi.png",
    6: "dimanche.png",
}


def paste_weekday_deco(
    img: Image.Image,
    target: date,
    box: tuple[int, int, int, int],
) -> bool:
    """
    Place le petit dessin correspondant au jour de la semaine.

    Fichiers attendus :
      Instagram/deco/lundi.png
      Instagram/deco/mardi.png
      ...
      Instagram/deco/dimanche.png
    """
    filename = WEEKDAY_DECO_FILES[target.weekday()]
    path = ROOT / "Instagram" / "deco" / filename

    if not path.exists():
        print(f"Décoration absente : {path}")
        return False

    deco = Image.open(path).convert("RGBA")

    x1, y1, x2, y2 = box
    max_w = x2 - x1
    max_h = y2 - y1

    deco.thumbnail(
        (max_w, max_h),
        Image.Resampling.LANCZOS
    )

    x = x1 + (max_w - deco.width) // 2
    y = y1 + (max_h - deco.height) // 2

    base = img.convert("RGBA")
    base.alpha_composite(
        deco,
        (x, y)
    )

    img.paste(
        base.convert("RGB")
    )

    return True


def draw_moon_icon_fallback(
    draw: ImageDraw.ImageDraw,
    box: tuple[int, int, int, int],
) -> None:
    x1, y1, x2, y2 = box

    draw.ellipse(
        (x1, y1, x2, y2),
        fill="#D7D7D7",
        outline="#666666",
        width=2
    )


def paste_moon(
    img: Image.Image,
    moon: dict[str, Any],
    box: tuple[int, int, int, int],
) -> bool:
    path = Path(moon["path"])

    if not path.exists():
        return False

    moon_img = Image.open(path).convert("RGBA")

    x1, y1, x2, y2 = box
    max_w = x2 - x1
    max_h = y2 - y1

    moon_img.thumbnail(
        (max_w, max_h),
        Image.Resampling.LANCZOS
    )

    x = x1 + (max_w - moon_img.width) // 2
    y = y1 + (max_h - moon_img.height) // 2

    base = img.convert("RGBA")
    base.alpha_composite(
        moon_img,
        (x, y)
    )

    img.paste(
        base.convert("RGB")
    )

    return True


def paste_asset(
    img: Image.Image,
    asset_path: str | Path | None,
    box: tuple[int, int, int, int],
) -> bool:
    if not asset_path:
        return False

    path = Path(asset_path)
    if not path.exists():
        return False

    asset = Image.open(path).convert("RGBA")
    x1, y1, x2, y2 = box
    max_w = x2 - x1
    max_h = y2 - y1
    asset.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
    x = x1 + (max_w - asset.width) // 2
    y = y1 + (max_h - asset.height) // 2
    base = img.convert("RGBA")
    base.alpha_composite(asset, (x, y))
    img.paste(base.convert("RGB"))
    return True


# ============================================================
# IMAGE INSTAGRAM
# ============================================================

def render_image(
    data: dict[str, Any],
    sunrise: str | None,
    sunset: str | None,
    location_name: str | None,
    moon: dict[str, Any],
    output: Path,
) -> None:
    """
    Génère le visuel carré Instagram style cahier Seyès.
    """
    W, H = 1080, 1080

    img = Image.new(
        "RGB",
        (W, H),
        "#FBF8EF"
    )

    target = date.fromisoformat(data["date"])
    draw_seyes_page(img, target)

    draw = ImageDraw.Draw(img)

    accent = DAY_COLORS[target.weekday()]
    ink = "#173B73"
    black = "#242424"

    # --------------------------------------------------------
    # POLICES
    # --------------------------------------------------------

    date_font = find_font(
        False,
        58,
        handwritten=True
    )

    section_font = find_font(
        False,
        34,
        handwritten=True
    )

    body_font = find_font(
        False,
        30,
        handwritten=True
    )

    body_small = find_font(
        False,
        26,
        handwritten=True
    )

    # --------------------------------------------------------
    # DATE
    # --------------------------------------------------------

    date_text = data["date_fr"].capitalize()

    date_font_fit = fit_font(
        draw,
        date_text,
        max_width=760,
        start_size=58,
        min_size=42,
        handwritten=True,
    )

    draw.text(
        (155, 48),
        date_text,
        font=date_font_fit,
        fill=ink
    )

    date_w = text_width(
        draw,
        date_text,
        date_font_fit
    )

    underline(
        draw,
        155,
        155 + date_w,
        112,
        "#D34848",
        width=3
    )

    # Petit dessin variable selon le jour de la semaine.
    # S'il manque un PNG dans Instagram/deco/, on garde le soleil
    # comme solution de secours.
    if not paste_weekday_deco(
        img,
        target,
        (905, 18, 1050, 138)
    ):
        draw = ImageDraw.Draw(img)
        draw_small_sun(
            draw,
            948,
            76,
            radius=24
        )
    else:
        # alpha_composite remplace l'image : on recrée le contexte draw.
        draw = ImageDraw.Draw(img)

    # --------------------------------------------------------
    # BONNE FÊTE
    # --------------------------------------------------------

    y = 145

    draw.text(
        (155, y),
        "Bonne fête",
        font=section_font,
        fill=ink
    )

    underline(
        draw,
        155,
        335,
        y + 42,
        accent,
        width=3
    )

    y += 47

    saint = data.get("saint") or ""

    if saint:
        saint_text = (
            f"à {saint}"
            if not saint.lower().startswith(("à ", "aux "))
            else saint
        )

        saint_font = fit_font(
            draw,
            saint_text,
            max_width=760,
            start_size=36,
            min_size=28,
            handwritten=True,
        )

        draw.text(
            (185, y),
            saint_text,
            font=saint_font,
            fill=black
        )

    saint_info = data.get("saint_info") or ""
    if saint_info:
        info_font = find_font(False, 21, handwritten=True)
        info_lines = wrap_text(draw, saint_info, info_font, 700)[:2]
        info_y = y + 45
        for line in info_lines:
            draw.text((185, info_y), line, font=info_font, fill="#5E6B76")
            info_y += 25
        y = info_y + 4
    else:
        y += 50

    zodiac = data.get("zodiac") or {}
    zodiac_name = zodiac.get("name") or ""
    zodiac_symbol = zodiac.get("symbol") or ""
    zodiac_fun = zodiac.get("fun") or ""
    zodiac_image = zodiac.get("image")

    if zodiac_name:
        icon_pasted = paste_asset(img, zodiac_image, (145, y - 4, 220, y + 70))
        if icon_pasted:
            draw = ImageDraw.Draw(img)
        text_x = 235 if icon_pasted else 185

        zodiac_title = f"{zodiac_symbol} {zodiac_name}"
        title_font = fit_font(
            draw,
            zodiac_title,
            max_width=660 if icon_pasted else 720,
            start_size=25,
            min_size=20,
            handwritten=True,
        )
        draw.text((text_x, y), zodiac_title, font=title_font, fill=accent)

        if zodiac_fun:
            fun_font = fit_font(
                draw,
                zodiac_fun,
                max_width=650 if icon_pasted else 720,
                start_size=19,
                min_size=16,
                handwritten=True,
            )
            fun_lines = wrap_text(draw, zodiac_fun, fun_font, 650 if icon_pasted else 720)[:2]
            fun_y = y + 28
            for line in fun_lines:
                draw.text((text_x, fun_y), line, font=fun_font, fill="#5E6B76")
                fun_y += 23
            y = max(fun_y, y + (72 if icon_pasted else 52))
        else:
            y += 72 if icon_pasted else 34

    y += 10

    # --------------------------------------------------------
    # DICTON
    # --------------------------------------------------------

    dicton = data.get("dicton") or ""

    if dicton:
        box_top = y
        box_bottom = y + 160

        draw.rounded_rectangle(
            (145, box_top, 955, box_bottom),
            radius=28,
            fill="#F6EAF7",
            outline=accent,
            width=3
        )

        label = "Dicton du jour"

        label_font = find_font(
            False,
            31,
            handwritten=True
        )

        label_w = text_width(
            draw,
            label,
            label_font
        )

        label_x = (W - label_w) // 2

        draw.rounded_rectangle(
            (
                label_x - 26,
                box_top - 20,
                label_x + label_w + 26,
                box_top + 35
            ),
            radius=12,
            fill="#FFF7FC",
            outline=accent,
            width=2
        )

        draw.text(
            (label_x, box_top - 12),
            label,
            font=label_font,
            fill=ink
        )

        dicton_font = find_font(
            False,
            31,
            handwritten=True
        )

        lines = wrap_text(
            draw,
            dicton,
            dicton_font,
            700
        )

        line_h = 39
        text_block_h = len(lines) * line_h

        start_y = box_top + 52 + max(
            0,
            (70 - text_block_h) // 2
        )

        for line in lines[:4]:
            line_w = text_width(
                draw,
                line,
                dicton_font
            )

            draw.text(
                ((W - line_w) // 2, start_y),
                line,
                font=dicton_font,
                fill=black
            )

            start_y += line_h

        y = box_bottom + 30

    # --------------------------------------------------------
    # AUJOURD'HUI ON CÉLÈBRE
    # --------------------------------------------------------

    mondiales = data.get("journees_mondiales") or []

    if mondiales:
        draw.text(
            (155, y),
            "Aujourd'hui on célèbre",
            font=section_font,
            fill=ink
        )

        underline(
            draw,
            155,
            515,
            y + 42,
            accent,
            width=3
        )

        y += 50

        for item in mondiales[:2]:
            y = draw_wrapped(
                draw,
                (185, y),
                item,
                body_small,
                black,
                max_width=760,
                line_gap=4,
                bullet="• "
            )
            y += 4

        y += 15

    # --------------------------------------------------------
    # LA TOUCHE FUN
    # --------------------------------------------------------

    funs = data.get("journees_fun") or []

    if funs:
        draw.text(
            (155, y),
            "La touche fun",
            font=section_font,
            fill=accent
        )

        underline(
            draw,
            155,
            360,
            y + 42,
            accent,
            width=3
        )

        y += 50

        y = draw_wrapped(
            draw,
            (185, y),
            funs[0],
            body_small,
            black,
            max_width=760,
            line_gap=4,
            bullet="• "
        )

        y += 20

    # --------------------------------------------------------
    # CIEL DU JOUR
    # --------------------------------------------------------

    panel_top = min(y, 780)
    panel_bottom = panel_top + 220

    draw.rounded_rectangle(
        (135, panel_top, 965, panel_bottom),
        radius=24,
        fill="#EAF4FC",
        outline="#4D79A6",
        width=3
    )

    draw.text(
        (205, panel_top + 15),
        "Ciel du jour",
        font=section_font,
        fill=ink
    )

    underline(
        draw,
        205,
        395,
        panel_top + 56,
        "#4D79A6",
        width=3
    )

    # Lune
    moon_box = (
        170,
        panel_top + 72,
        255,
        panel_top + 157
    )

    if not paste_moon(
        img,
        moon,
        moon_box
    ):
        draw = ImageDraw.Draw(img)
        draw_moon_icon_fallback(
            draw,
            moon_box
        )

    draw = ImageDraw.Draw(img)

    moon_title_font = find_font(
        True,
        22
    )

    draw.text(
        (280, panel_top + 82),
        "Lune",
        font=moon_title_font,
        fill=ink
    )

    moon_phase_font = fit_font(
        draw,
        moon["name"],
        max_width=260,
        start_size=25,
        min_size=18,
        handwritten=True
    )

    draw.text(
        (280, panel_top + 113),
        moon["name"],
        font=moon_phase_font,
        fill=black
    )

    # Séparateur
    draw.line(
        (
            535,
            panel_top + 70,
            535,
            panel_bottom - 20
        ),
        fill="#7BA4C8",
        width=2
    )

    # Soleil
    draw_small_sun(
        draw,
        615,
        panel_top + 112,
        radius=22
    )

    sun_title_font = find_font(
        True,
        22
    )

    draw.text(
        (665, panel_top + 82),
        "Soleil",
        font=sun_title_font,
        fill=ink
    )

    sun_body = find_font(
        False,
        24,
        handwritten=True
    )

    if sunrise and sunset:
        draw.text(
            (665, panel_top + 115),
            f"lever {sunrise}",
            font=sun_body,
            fill=black
        )

        draw.text(
            (665, panel_top + 145),
            f"coucher {sunset}",
            font=sun_body,
            fill=black
        )

    if location_name:
        loc_font = find_font(
            False,
            18
        )

        draw.text(
            (665, panel_top + 175),
            f"Référence : {location_name}",
            font=loc_font,
            fill="#5E6B76"
        )

    # --------------------------------------------------------
    # FORMULE FINALE
    # --------------------------------------------------------

    footer = "Belle journée à tous !"

    footer_font = find_font(
        False,
        32,
        handwritten=True
    )

    footer_w = text_width(
        draw,
        footer,
        footer_font
    )

    footer_y = min(panel_bottom + 35, 1010)

    draw.text(
        ((W - footer_w) // 2, footer_y),
        footer,
        font=footer_font,
        fill=ink
    )

    underline(
        draw,
        (W - footer_w) // 2,
        (W + footer_w) // 2,
        footer_y + 41,
        "#D34848",
        width=2
    )

    # --------------------------------------------------------
    # SAUVEGARDE
    # --------------------------------------------------------

    output.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    img.save(
        output,
        format="PNG",
        optimize=True
    )


# ============================================================
# LÉGENDE INSTAGRAM
# ============================================================

def build_caption(
    data: dict[str, Any],
    sunrise: str | None,
    sunset: str | None,
    moon_name: str | None = None,
) -> str:
    """Légende courte : l'image contient déjà toutes les informations.

    Cela évite de recopier tout le bulletin en texte lorsque Meta relaie
    automatiquement la publication Instagram vers Facebook.
    """
    return "Belle journée à tous !"


# ============================================================
# INSTAGRAM
# ============================================================

def http_post_form(
    url: str,
    token: str,
    fields: dict[str, str],
) -> dict[str, Any]:
    body = urllib.parse.urlencode(
        fields
    ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        method="POST"
    )

    req.add_header(
        "Authorization",
        f"Bearer {token}"
    )

    req.add_header(
        "Content-Type",
        "application/x-www-form-urlencoded"
    )

    try:
        with urllib.request.urlopen(
            req,
            timeout=60
        ) as resp:
            payload = resp.read().decode(
                "utf-8"
            )
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        raise RuntimeError(
            f"Erreur HTTP Instagram sur {url}: "
            f"HTTP {exc.code} {exc.reason}. "
            f"Détail Meta: {detail}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"Erreur HTTP Instagram sur {url}: {exc}"
        ) from exc

    data = json.loads(payload)

    if "error" in data:
        raise RuntimeError(
            f"Erreur Instagram: {data['error']}"
        )

    return data


def http_get_json(
    url: str,
    token: str,
) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        method="GET"
    )

    req.add_header(
        "Authorization",
        f"Bearer {token}"
    )

    try:
        with urllib.request.urlopen(
            req,
            timeout=60
        ) as resp:
            payload = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        try:
            detail = exc.read().decode("utf-8", errors="replace")
        except Exception:
            detail = ""
        raise RuntimeError(
            f"Erreur HTTP Instagram sur {url}: "
            f"HTTP {exc.code} {exc.reason}. "
            f"Détail Meta: {detail}"
        ) from exc
    except Exception as exc:
        raise RuntimeError(
            f"Erreur HTTP Instagram sur {url}: {exc}"
        ) from exc

    data = json.loads(payload)

    if "error" in data:
        raise RuntimeError(
            f"Erreur Instagram: {data['error']}"
        )

    return data


def wait_for_media_container(
    creation_id: str,
    token: str,
    api_version: str,
    attempts: int = 20,
    delay: int = 3,
) -> None:
    """
    Attend que Meta ait fini de traiter le conteneur média avant
    d'appeler /media_publish. Évite les HTTP 400 quand le conteneur
    vient juste d'être créé.
    """
    status_url = (
        f"https://graph.instagram.com/"
        f"{api_version}/"
        f"{creation_id}"
        f"?fields=status_code,status"
    )

    last_status = "UNKNOWN"

    for _ in range(attempts):
        data = http_get_json(status_url, token)
        status_code = str(data.get("status_code", "")).upper()
        status_text = str(data.get("status", "")).strip()

        if status_code:
            last_status = status_code
        elif status_text:
            last_status = status_text

        print(
            "Statut du conteneur Instagram:",
            status_code or status_text or data
        )

        if status_code == "FINISHED":
            return

        if status_code in {"ERROR", "EXPIRED"}:
            raise RuntimeError(
                "Le traitement du média Instagram a échoué : "
                f"{data}"
            )

        time.sleep(delay)

    raise RuntimeError(
        "Le conteneur Instagram n'est pas prêt après attente. "
        f"Dernier statut : {last_status}"
    )


def wait_until_public(
    url: str,
    attempts: int = 12,
    delay: int = 5,
) -> None:
    for _ in range(attempts):
        try:
            req = urllib.request.Request(
                url,
                method="HEAD"
            )

            req.add_header(
                "Cache-Control",
                "no-cache"
            )

            with urllib.request.urlopen(
                req,
                timeout=20
            ) as resp:
                if 200 <= resp.status < 300:
                    return

        except Exception:
            pass

        time.sleep(delay)

    raise RuntimeError(
        f"L'image n'est pas encore accessible publiquement : {url}"
    )


def publish_instagram(
    image_url: str,
    caption: str,
) -> str:
    token = os.environ.get(
        "INSTAGRAM_ACCESS_TOKEN",
        ""
    ).strip()

    ig_user_id = os.environ.get(
        "INSTAGRAM_ACCOUNT_ID",
        ""
    ).strip()

    api_version = os.environ.get(
        "INSTAGRAM_API_VERSION",
        "v23.0"
    ).strip()

    if not token or not ig_user_id:
        raise RuntimeError(
            "INSTAGRAM_ACCESS_TOKEN et INSTAGRAM_ACCOUNT_ID "
            "doivent être configurés."
        )

    base = (
        f"https://graph.instagram.com/"
        f"{api_version}/"
        f"{ig_user_id}"
    )

    container = http_post_form(
        f"{base}/media",
        token,
        {
            "image_url": image_url,
            "caption": caption,
        },
    )

    creation_id = str(
        container.get("id", "")
    )

    if not creation_id:
        raise RuntimeError(
            "Instagram n'a pas renvoyé "
            f"d'identifiant de conteneur: {container}"
        )

    # La création du conteneur est asynchrone : on attend que Meta
    # ait réellement fini de traiter l'image avant publication.
    wait_for_media_container(
        creation_id,
        token,
        api_version
    )

    published = http_post_form(
        f"{base}/media_publish",
        token,
        {
            "creation_id": creation_id
        },
    )

    media_id = str(
        published.get("id", "")
    )

    if not media_id:
        raise RuntimeError(
            "Instagram n'a pas renvoyé "
            f"d'identifiant de média: {published}"
        )

    return media_id


def raw_url_for_file(
    file_path: Path,
) -> str:
    base = os.environ.get(
        "PUBLIC_IMAGE_BASE_URL",
        ""
    ).rstrip("/")

    if not base:
        raise RuntimeError(
            "PUBLIC_IMAGE_BASE_URL doit être configurée, "
            "par exemple l'URL raw GitHub du dossier Instagram."
        )

    return (
        f"{base}/"
        f"{urllib.parse.quote(file_path.name)}"
    )


# ============================================================
# COMMANDES
# ============================================================

def _env_float(
    name: str,
) -> float | None:
    raw = os.getenv(name)

    if raw is None or not raw.strip():
        return None

    return float(raw)


def cmd_generate(
    args: argparse.Namespace,
) -> int:
    if not PATRICK_HAND.exists():
        raise FileNotFoundError(
            "Police introuvable : Instagram/fonts/PatrickHand-Regular.ttf"
        )
    target = parse_target_date(
        args.date,
        args.timezone
    )

    lat = (
        args.latitude
        if args.latitude is not None
        else (
            _env_float("LATITUDE")
            or DEFAULT_LATITUDE
        )
    )

    lon = (
        args.longitude
        if args.longitude is not None
        else (
            _env_float("LONGITUDE")
            or DEFAULT_LONGITUDE
        )
    )

    location_name = (
        args.location
        or os.getenv("LOCATION_NAME")
        or DEFAULT_LOCATION_NAME
    )

    data = get_day_data(target)

    sunrise, sunset = compute_sun_times(
        target,
        lat,
        lon,
        args.timezone
    )

    moon = compute_moon_phase(
        target
    )

    output_dir = (
        Path(args.output_dir)
        if args.output_dir
        else DEFAULT_OUTPUT_DIR
    )

    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir

    output = (
        output_dir
        / f"{target.isoformat()}.png"
    )

    render_image(
        data,
        sunrise,
        sunset,
        location_name,
        moon,
        output
    )

    metadata = {
        **data,
        "sunrise": sunrise,
        "sunset": sunset,
        "timezone": args.timezone,
        "latitude": lat,
        "longitude": lon,
        "location_name": location_name,
        "moon_phase": moon["name"],
        "moon_phase_index": moon["index"],
        "moon_age_days": moon["age_days"],
        "moon_illumination_percent": moon["illumination_percent"],
        "moon_image": str(
            Path("Instagram")
            / "lune"
            / moon["filename"]
        ),
        "image": str(
            output.relative_to(ROOT)
        ),
    }

    meta_path = output.with_suffix(
        ".json"
    )

    meta_path.write_text(
        json.dumps(
            metadata,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    # Alias toujours à jour.
    current_png = (
        output_dir
        / "info-du-jour.png"
    )

    shutil.copyfile(
        output,
        current_png
    )

    current_json = (
        output_dir
        / "info-du-jour.json"
    )

    shutil.copyfile(
        meta_path,
        current_json
    )

    print(
        str(
            output.relative_to(ROOT)
        )
    )

    return 0


def cmd_publish(
    args: argparse.Namespace,
) -> int:
    file_path = Path(
        args.file
    )

    if not file_path.is_absolute():
        file_path = ROOT / file_path

    if not file_path.exists():
        raise FileNotFoundError(
            file_path
        )

    meta_path = file_path.with_suffix(
        ".json"
    )

    if meta_path.exists():
        data = json.loads(
            meta_path.read_text(
                encoding="utf-8"
            )
        )

        caption = build_caption(
            data,
            data.get("sunrise"),
            data.get("sunset"),
            data.get("moon_phase")
        )
    else:
        caption = (
            args.caption
            or "Bonjour !"
        )

    image_url = (
        args.image_url
        or raw_url_for_file(
            file_path
        )
    )

    wait_until_public(
        image_url
    )

    media_id = publish_instagram(
        image_url,
        caption
    )

    print(
        media_id
    )

    return 0


def cmd_show(
    args: argparse.Namespace,
) -> int:
    target = parse_target_date(
        args.date,
        args.timezone
    )

    data = get_day_data(
        target
    )

    lat = (
        args.latitude
        if args.latitude is not None
        else (
            _env_float("LATITUDE")
            or DEFAULT_LATITUDE
        )
    )

    lon = (
        args.longitude
        if args.longitude is not None
        else (
            _env_float("LONGITUDE")
            or DEFAULT_LONGITUDE
        )
    )

    sunrise, sunset = compute_sun_times(
        target,
        lat,
        lon,
        args.timezone
    )

    moon = compute_moon_phase(
        target
    )

    data["sunrise"] = sunrise
    data["sunset"] = sunset
    data["location_name"] = DEFAULT_LOCATION_NAME
    data["moon_phase"] = moon["name"]
    data["moon_age_days"] = moon["age_days"]
    data["moon_illumination_percent"] = moon["illumination_percent"]

    print(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2
        )
    )

    return 0


# ============================================================
# ARGUMENTS
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Génère et publie "
            "les Infos du jour."
        )
    )

    sub = p.add_subparsers(
        dest="command",
        required=True
    )

    def common(
        sp: argparse.ArgumentParser,
    ) -> None:
        sp.add_argument(
            "--date",
            help=(
                "Date ISO YYYY-MM-DD. "
                "Par défaut: aujourd'hui."
            )
        )

        sp.add_argument(
            "--timezone",
            default=DEFAULT_TIMEZONE
        )

        sp.add_argument(
            "--latitude",
            type=float
        )

        sp.add_argument(
            "--longitude",
            type=float
        )

    g = sub.add_parser(
        "generate",
        help=(
            "Génère le PNG "
            "et son JSON de métadonnées."
        )
    )

    common(g)

    g.add_argument(
        "--location",
        help=(
            "Nom affiché à côté "
            "des heures de soleil."
        )
    )

    g.add_argument(
        "--output-dir",
        default="Instagram"
    )

    g.set_defaults(
        func=cmd_generate
    )

    s = sub.add_parser(
        "show",
        help=(
            "Affiche les données du jour "
            "sans générer d'image."
        )
    )

    common(s)

    s.set_defaults(
        func=cmd_show
    )

    pub = sub.add_parser(
        "publish",
        help=(
            "Publie un PNG "
            "déjà accessible publiquement."
        )
    )

    pub.add_argument(
        "--file",
        required=True,
        help=(
            "PNG local déjà poussé "
            "dans GitHub."
        )
    )

    pub.add_argument(
        "--image-url",
        help=(
            "URL publique à utiliser "
            "à la place de PUBLIC_IMAGE_BASE_URL."
        )
    )

    pub.add_argument(
        "--caption",
        help=(
            "Légende si aucun JSON "
            "de métadonnées n'existe."
        )
    )

    pub.set_defaults(
        func=cmd_publish
    )

    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        return args.func(args)

    except Exception as exc:
        print(
            f"ERREUR: {exc}",
            file=sys.stderr
        )

        return 1


if __name__ == "__main__":
    raise SystemExit(main())