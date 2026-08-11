#!/usr/bin/env python3
"""Infos du jour -> image Instagram, puis publication optionnelle.

V1 pensée pour le dépôt GitHub Agenda-data.

Exemples :
    python info_du_jour.py generate --date 2026-08-11
    python info_du_jour.py generate --date 2026-08-11 --latitude 43.60 --longitude 1.44
    python info_du_jour.py publish --file Instagram/2026-08-11.png

La publication Instagram utilise l'Instagram API avec Instagram Login.
Les identifiants/tokens ne sont jamais stockés dans le code : ils viennent des
variables d'environnement.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = ROOT / "Instagram"
DEFAULT_TIMEZONE = os.getenv("TIMEZONE", "Europe/Paris")

MONTHS_FR = [
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
]
WEEKDAYS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

DATA_BASENAMES = {
    "saints": "saints.json",
    "dictons": "dictons-du-jour.json",
    "mondiales": "journees-mondiales.json",
    "insolites": "journees-insolites.json",
}


def normalize_name(name: str) -> str:
    """Tolère les suffixes de copie du type '(1)' dans les fichiers téléchargés."""
    stem = Path(name).stem
    stem = stem.replace("(1)", "").replace(" (1)", "")
    return stem.lower().replace("_", "-")


def find_data_file(expected_name: str) -> Path:
    expected = normalize_name(expected_name)
    candidates = [ROOT, ROOT / "json", ROOT / "JSON", ROOT / "data", ROOT / "Data"]
    for folder in candidates:
        if not folder.exists():
            continue
        for p in folder.glob("*.json"):
            if normalize_name(p.name) == expected:
                return p
    # Dernier recours : recherche récursive, mais on ignore .git
    for p in ROOT.rglob("*.json"):
        if ".git" in p.parts:
            continue
        if normalize_name(p.name) == expected:
            return p
    raise FileNotFoundError(f"Impossible de trouver {expected_name} dans le dépôt.")


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
        # Le fichier journées mondiales peut mettre plusieurs journées dans un label séparé par |.
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
    return f"{WEEKDAYS_FR[d.weekday()]} {d.day} {MONTHS_FR[d.month - 1]} {d.year}"


def parse_target_date(raw: str | None, timezone: str) -> date:
    if raw:
        return date.fromisoformat(raw)
    return datetime.now(ZoneInfo(timezone)).date()


def get_day_data(target: date) -> dict[str, Any]:
    key = target.strftime("%d-%m")
    files = {name: find_data_file(filename) for name, filename in DATA_BASENAMES.items()}
    db = {name: load_json(path) for name, path in files.items()}

    saint_obj = db["saints"].get(key) or {}
    saint = saint_obj.get("label") if isinstance(saint_obj, dict) else None
    saint_type = saint_obj.get("type") if isinstance(saint_obj, dict) else None

    dicton = db["dictons"].get(key)
    if dicton is not None:
        dicton = str(dicton).strip()

    return {
        "key": key,
        "date": target.isoformat(),
        "date_fr": format_date_fr(target),
        "saint": saint,
        "saint_type": saint_type,
        "dicton": dicton,
        "journees_mondiales": labels_from_value(db["mondiales"].get(key)),
        "journees_fun": fun_labels(db["insolites"].get(key)),
        "source_files": {k: str(v.relative_to(ROOT)) for k, v in files.items()},
    }


def compute_sun_times(target: date, latitude: float | None, longitude: float | None,
                      timezone: str) -> tuple[str | None, str | None]:
    """Calcule lever/coucher avec l'algorithme solaire NOAA simplifié.

    Cela évite toute API météo et toute dépendance supplémentaire. Les heures sont
    converties dans le fuseau demandé, y compris heure d'été/hiver via zoneinfo.
    """
    if latitude is None or longitude is None:
        return None, None

    zenith = 90.833  # réfraction atmosphérique + rayon apparent du Soleil
    day_of_year = target.timetuple().tm_yday
    lng_hour = longitude / 15.0
    tz = ZoneInfo(timezone)
    noon = datetime(target.year, target.month, target.day, 12, 0, tzinfo=tz)
    offset_hours = noon.utcoffset().total_seconds() / 3600.0

    def event(is_sunrise: bool) -> str | None:
        approx = day_of_year + (((6 if is_sunrise else 18) - lng_hour) / 24.0)
        mean_anomaly = (0.9856 * approx) - 3.289
        true_long = (
            mean_anomaly
            + 1.916 * math.sin(math.radians(mean_anomaly))
            + 0.020 * math.sin(math.radians(2 * mean_anomaly))
            + 282.634
        ) % 360.0

        right_ascension = math.degrees(
            math.atan(0.91764 * math.tan(math.radians(true_long)))
        ) % 360.0
        l_quadrant = math.floor(true_long / 90.0) * 90.0
        ra_quadrant = math.floor(right_ascension / 90.0) * 90.0
        right_ascension = (right_ascension + l_quadrant - ra_quadrant) / 15.0

        sin_dec = 0.39782 * math.sin(math.radians(true_long))
        cos_dec = math.cos(math.asin(sin_dec))
        cos_h = (
            math.cos(math.radians(zenith))
            - sin_dec * math.sin(math.radians(latitude))
        ) / (cos_dec * math.cos(math.radians(latitude)))

        if cos_h > 1 or cos_h < -1:
            return None

        if is_sunrise:
            hour_angle = 360.0 - math.degrees(math.acos(cos_h))
        else:
            hour_angle = math.degrees(math.acos(cos_h))
        hour_angle /= 15.0

        local_mean = hour_angle + right_ascension - (0.06571 * approx) - 6.622
        utc_hour = (local_mean - lng_hour) % 24.0
        local_hour = (utc_hour + offset_hours) % 24.0
        total_minutes = int(round(local_hour * 60)) % (24 * 60)
        return f"{total_minutes // 60:02d}:{total_minutes % 60:02d}"

    return event(True), event(False)


def find_font(bold: bool, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = []
    if bold:
        candidates += [
            "DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
            "/Library/Fonts/Arial Bold.ttf",
        ]
    else:
        candidates += [
            "DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
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


def text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont,
              max_width: int) -> list[str]:
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


def draw_wrapped(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str,
                 font: ImageFont.ImageFont, fill: str, max_width: int,
                 line_gap: int = 8) -> int:
    x, y = xy
    lines = wrap_text(draw, text, font, max_width)
    if not lines:
        return y
    bbox = draw.textbbox((0, 0), "Ag", font=font)
    line_h = bbox[3] - bbox[1]
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        y += line_h + line_gap
    return y


def fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, start_size: int,
             min_size: int = 24, bold: bool = False) -> ImageFont.ImageFont:
    size = start_size
    while size >= min_size:
        font = find_font(bold, size)
        if text_width(draw, text, font) <= max_width:
            return font
        size -= 2
    return find_font(bold, min_size)


def render_image(data: dict[str, Any], sunrise: str | None, sunset: str | None,
                 location_name: str | None, output: Path) -> None:
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), "#f6efe6")
    draw = ImageDraw.Draw(img)

    # Bandeau supérieur simple, chaleureux et lisible.
    draw.rounded_rectangle((40, 40, W - 40, 230), radius=36, fill="#fff8ef")
    title_font = find_font(True, 72)
    date_font = find_font(False, 40)
    draw.text((80, 70), "Bonjour", font=title_font, fill="#222222")
    draw.text((80, 160), data["date_fr"].capitalize(), font=date_font, fill="#555555")

    y = 275
    left = 80
    max_width = W - 160
    label_font = find_font(True, 30)
    body_font = find_font(False, 34)
    body_small = find_font(False, 30)

    def block(label: str, text: str, body: ImageFont.ImageFont = body_font) -> None:
        nonlocal y
        if not text:
            return
        draw.text((left, y), label.upper(), font=label_font, fill="#8c5c3c")
        y += 43
        y = draw_wrapped(draw, (left, y), text, body, "#222222", max_width, line_gap=7)
        y += 28

    saint_prefix = "Fête" if data.get("saint_type") == "fete" else "Saint du jour"
    block(saint_prefix, data.get("saint") or "")

    if data.get("dicton"):
        block("Dicton", f"« {data['dicton']} »", body_small)

    mondiales = data.get("journees_mondiales") or []
    if mondiales:
        block("Journée mondiale", " • ".join(mondiales), body_small)

    funs = data.get("journees_fun") or []
    if funs:
        block("Journée fun", " • ".join(funs), body_small)

    if sunrise and sunset:
        solar_text = f"Lever {sunrise}   •   Coucher {sunset}"
        if location_name:
            solar_text += f"   —   {location_name}"
        block("Soleil", solar_text, body_small)

    # Si le contenu est trop long, on avertit au lieu de laisser sortir de l'image.
    if y > H - 70:
        # On recrée une version légèrement plus petite de façon simple et déterministe.
        render_image_compact(data, sunrise, sunset, location_name, output)
        return

    draw.text((left, H - 62), "Infos du jour", font=find_font(False, 24), fill="#8a8178")
    output.parent.mkdir(parents=True, exist_ok=True)
    img.save(output, format="PNG", optimize=True)


def render_image_compact(data: dict[str, Any], sunrise: str | None, sunset: str | None,
                         location_name: str | None, output: Path) -> None:
    W, H = 1080, 1080
    img = Image.new("RGB", (W, H), "#f6efe6")
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((40, 40, W - 40, 210), radius=34, fill="#fff8ef")
    draw.text((75, 65), "Bonjour", font=find_font(True, 64), fill="#222222")
    draw.text((75, 145), data["date_fr"].capitalize(), font=find_font(False, 35), fill="#555555")

    left, y, max_width = 75, 245, W - 150
    label_font = find_font(True, 25)
    body_font = find_font(False, 27)
    body_small = find_font(False, 25)

    def block(label: str, text: str, body: ImageFont.ImageFont = body_font) -> None:
        nonlocal y
        if not text:
            return
        draw.text((left, y), label.upper(), font=label_font, fill="#8c5c3c")
        y += 34
        y = draw_wrapped(draw, (left, y), text, body, "#222222", max_width, line_gap=4)
        y += 18

    saint_prefix = "Fête" if data.get("saint_type") == "fete" else "Saint du jour"
    block(saint_prefix, data.get("saint") or "")
    if data.get("dicton"):
        block("Dicton", f"« {data['dicton']} »", body_small)
    if data.get("journees_mondiales"):
        block("Journée mondiale", " • ".join(data["journees_mondiales"]), body_small)
    if data.get("journees_fun"):
        block("Journée fun", " • ".join(data["journees_fun"]), body_small)
    if sunrise and sunset:
        solar_text = f"Lever {sunrise} • Coucher {sunset}"
        if location_name:
            solar_text += f" — {location_name}"
        block("Soleil", solar_text, body_small)

    draw.text((left, H - 55), "Infos du jour", font=find_font(False, 22), fill="#8a8178")
    output.parent.mkdir(parents=True, exist_ok=True)
    img.save(output, format="PNG", optimize=True)


def build_caption(data: dict[str, Any], sunrise: str | None, sunset: str | None) -> str:
    parts = [f"Bonjour — {data['date_fr'].capitalize()}"]
    if data.get("saint"):
        parts.append(f"Saint du jour : {data['saint']}")
    if sunrise and sunset:
        parts.append(f"Lever du soleil : {sunrise} — coucher : {sunset}")
    return "\n".join(parts)


def http_post_form(url: str, token: str, fields: dict[str, str]) -> dict[str, Any]:
    body = urllib.parse.urlencode(fields).encode("utf-8")
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = resp.read().decode("utf-8")
    except Exception as exc:
        raise RuntimeError(f"Erreur HTTP Instagram sur {url}: {exc}") from exc
    data = json.loads(payload)
    if "error" in data:
        raise RuntimeError(f"Erreur Instagram: {data['error']}")
    return data


def wait_until_public(url: str, attempts: int = 12, delay: int = 5) -> None:
    for _ in range(attempts):
        try:
            req = urllib.request.Request(url, method="HEAD")
            req.add_header("Cache-Control", "no-cache")
            with urllib.request.urlopen(req, timeout=20) as resp:
                if 200 <= resp.status < 300:
                    return
        except Exception:
            pass
        time.sleep(delay)
    raise RuntimeError(f"L'image n'est pas encore accessible publiquement : {url}")


def publish_instagram(image_url: str, caption: str) -> str:
    token = os.environ.get("INSTAGRAM_ACCESS_TOKEN", "").strip()
    ig_user_id = os.environ.get("INSTAGRAM_ACCOUNT_ID", "").strip()
    api_version = os.environ.get("INSTAGRAM_API_VERSION", "v23.0").strip()
    if not token or not ig_user_id:
        raise RuntimeError(
            "INSTAGRAM_ACCESS_TOKEN et INSTAGRAM_ACCOUNT_ID doivent être configurés."
        )

    base = f"https://graph.instagram.com/{api_version}/{ig_user_id}"
    container = http_post_form(
        f"{base}/media",
        token,
        {"image_url": image_url, "caption": caption},
    )
    creation_id = str(container.get("id", ""))
    if not creation_id:
        raise RuntimeError(f"Instagram n'a pas renvoyé d'identifiant de conteneur: {container}")

    published = http_post_form(
        f"{base}/media_publish",
        token,
        {"creation_id": creation_id},
    )
    media_id = str(published.get("id", ""))
    if not media_id:
        raise RuntimeError(f"Instagram n'a pas renvoyé d'identifiant de média: {published}")
    return media_id


def raw_url_for_file(file_path: Path) -> str:
    base = os.environ.get("PUBLIC_IMAGE_BASE_URL", "").rstrip("/")
    if not base:
        raise RuntimeError(
            "PUBLIC_IMAGE_BASE_URL doit être configurée, par exemple l'URL raw GitHub du dossier Instagram."
        )
    return f"{base}/{urllib.parse.quote(file_path.name)}"


def cmd_generate(args: argparse.Namespace) -> int:
    target = parse_target_date(args.date, args.timezone)
    lat = args.latitude if args.latitude is not None else _env_float("LATITUDE")
    lon = args.longitude if args.longitude is not None else _env_float("LONGITUDE")
    location_name = args.location or os.getenv("LOCATION_NAME")

    data = get_day_data(target)
    sunrise, sunset = compute_sun_times(target, lat, lon, args.timezone)

    output_dir = Path(args.output_dir) if args.output_dir else DEFAULT_OUTPUT_DIR
    if not output_dir.is_absolute():
        output_dir = ROOT / output_dir
    output = output_dir / f"{target.isoformat()}.png"
    render_image(data, sunrise, sunset, location_name, output)

    metadata = {
        **data,
        "sunrise": sunrise,
        "sunset": sunset,
        "timezone": args.timezone,
        "latitude": lat,
        "longitude": lon,
        "location_name": location_name,
        "image": str(output.relative_to(ROOT)),
    }
    meta_path = output.with_suffix(".json")
    meta_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    print(str(output.relative_to(ROOT)))
    return 0


def cmd_publish(args: argparse.Namespace) -> int:
    file_path = Path(args.file)
    if not file_path.is_absolute():
        file_path = ROOT / file_path
    if not file_path.exists():
        raise FileNotFoundError(file_path)

    meta_path = file_path.with_suffix(".json")
    if meta_path.exists():
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        caption = build_caption(data, data.get("sunrise"), data.get("sunset"))
    else:
        caption = args.caption or "Bonjour !"

    image_url = args.image_url or raw_url_for_file(file_path)
    wait_until_public(image_url)
    media_id = publish_instagram(image_url, caption)
    print(media_id)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    target = parse_target_date(args.date, args.timezone)
    data = get_day_data(target)
    lat = args.latitude if args.latitude is not None else _env_float("LATITUDE")
    lon = args.longitude if args.longitude is not None else _env_float("LONGITUDE")
    sunrise, sunset = compute_sun_times(target, lat, lon, args.timezone)
    data["sunrise"] = sunrise
    data["sunset"] = sunset
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0


def _env_float(name: str) -> float | None:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return None
    return float(raw)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Génère et publie les Infos du jour.")
    sub = p.add_subparsers(dest="command", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--date", help="Date ISO YYYY-MM-DD. Par défaut: aujourd'hui.")
        sp.add_argument("--timezone", default=DEFAULT_TIMEZONE)
        sp.add_argument("--latitude", type=float)
        sp.add_argument("--longitude", type=float)

    g = sub.add_parser("generate", help="Génère le PNG et son JSON de métadonnées.")
    common(g)
    g.add_argument("--location", help="Nom affiché à côté des heures de soleil.")
    g.add_argument("--output-dir", default="Instagram")
    g.set_defaults(func=cmd_generate)

    s = sub.add_parser("show", help="Affiche les données du jour sans générer d'image.")
    common(s)
    s.set_defaults(func=cmd_show)

    pub = sub.add_parser("publish", help="Publie un PNG déjà accessible publiquement.")
    pub.add_argument("--file", required=True, help="PNG local déjà poussé dans GitHub.")
    pub.add_argument("--image-url", help="URL publique à utiliser à la place de PUBLIC_IMAGE_BASE_URL.")
    pub.add_argument("--caption", help="Légende si aucun JSON de métadonnées n'existe.")
    pub.set_defaults(func=cmd_publish)
    return p


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as exc:
        print(f"ERREUR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
