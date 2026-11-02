#!/usr/bin/env python3
"""Build the photography site from original photos kept OUTSIDE this repo.

Originals are only read, never modified or copied. Every subfolder of the originals folder is one
work: a single photo or a series. For each photo the script reads the date and camera settings,
then writes two watermarked WebP files with all metadata removed (a thumbnail for the grid, and a
large image for the work page and the lightbox), and renders the pages.

    python3 scripts/build.py                     # originals folder from config.local.yaml
    python3 scripts/build.py --originals PATH    # or give it explicitly
"""
import argparse
import datetime
import hashlib
import io
import json
import math
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image, ImageCms, ImageDraw, ImageFilter, ImageFont, ImageOps

REPO = Path(__file__).resolve().parent.parent
IMAGE_EXTS = {'.jpg', '.jpeg', '.png', '.tif', '.tiff', '.heic', '.heif'}
# Changing anything here (or the watermark text) regenerates every image.
SETTINGS = {
    'version': 1,
    'large': {'max_w': 2048, 'max_h': 2048, 'quality': 84},
    'small': {'max_w': 1600, 'max_h': 640, 'quality': 80},
}
FONTS = [
    ('/System/Library/Fonts/HelveticaNeue.ttc', 0),
    ('/System/Library/Fonts/Helvetica.ttc', 0),
    ('/System/Library/Fonts/Supplemental/Arial.ttf', 0),
]
MAKES = {
    'NIKON CORPORATION': 'Nikon', 'NIKON': 'Nikon', 'CANON': 'Canon', 'SONY': 'Sony',
    'FUJIFILM': 'Fujifilm', 'PANASONIC': 'Panasonic', 'OLYMPUS CORPORATION': 'Olympus',
    'OM DIGITAL SOLUTIONS': 'OM System', 'LEICA CAMERA AG': 'Leica',
    'RICOH IMAGING COMPANY, LTD.': 'Ricoh', 'APPLE': 'Apple', 'DJI': 'DJI',
    'HASSELBLAD': 'Hasselblad', 'GOOGLE': 'Google', 'SAMSUNG': 'Samsung', 'XIAOMI': 'Xiaomi',
    'HUAWEI': 'Huawei',
}
# EXIF model codes shown under their product names.
MODELS = {'Canon EOS R6m2': 'Canon EOS R6 Mark II', 'ILCE-7CM2': 'Sony α7C II'}
EXIF_FIELDS = ('camera', 'lens', 'focal', 'aperture', 'shutter', 'iso')

Image.MAX_IMAGE_PIXELS = None  # originals are the user's own files; allow very large ones


def die(message):
    sys.exit(f'error: {message}')


def load_yaml(path):
    with open(path, encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def slugify(text):
    return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')


def resolve_paths(args):
    data = Path(args.data).expanduser().resolve()
    if not data.is_file():
        die(f'gallery data not found: {data}')
    out = Path(args.out).expanduser().resolve()
    originals = args.originals
    local = REPO / 'config.local.yaml'
    if not originals and local.is_file():
        originals = load_yaml(local).get('originals')
    if not originals:
        die('no originals folder: pass --originals PATH or set "originals:" in config.local.yaml')
    originals = Path(originals).expanduser().resolve()
    if not originals.is_dir():
        die(f'originals folder not found: {originals}')
    # Originals must never live inside the repo, and nothing may ever be written into them.
    if originals == REPO or REPO in originals.parents:
        die(f'the originals folder {originals} is inside the repo; move it outside {REPO}')
    if out == originals or originals in out.parents:
        die(f'the output folder {out} is inside the originals folder')
    return data, originals, out


def collect(data, originals):
    """Return the works and every photo, keyed by '<folder name>/<file name>'.

    Each subfolder of the originals folder is a work and its image files are the photos.
    gallery.yaml only adds information, keyed by folder name and then by file name.
    """
    config = data.get('works') or {}
    folders = sorted((p for p in originals.iterdir() if p.is_dir() and not p.name.startswith(('.', '_'))),
                     key=lambda p: p.name.lower())
    for name in config:
        if not (originals / name).is_dir():
            die(f'works: "{name}" in gallery.yaml has no folder in {originals}')
    works, photos, ids = [], {}, set()
    for folder in folders:
        meta = config.get(folder.name) or {}
        wid = str(meta.get('id') or slugify(folder.name) or 'work-' + hashlib.sha1(folder.name.encode()).hexdigest()[:6])
        if not re.fullmatch(r'[a-z0-9]+(-[a-z0-9]+)*', wid):
            die(f'works: id "{wid}" for "{folder.name}" must be lowercase letters, digits and hyphens')
        if wid in ids:
            die(f'works: two folders share the id "{wid}"; give one of them its own id in gallery.yaml')
        ids.add(wid)
        files = {p.name: p for p in sorted(folder.iterdir(), key=lambda p: p.name.lower())
                 if p.is_file() and p.suffix.lower() in IMAGE_EXTS and not p.name.startswith('.')}
        photo_config = meta.get('photos') or {}
        for name in photo_config:
            if name not in files:
                die(f'works: "{folder.name}/{name}" is in gallery.yaml but not in the folder')
        keys = []
        for name, path in files.items():
            entry = dict(photo_config.get(name) or {})
            if entry.get('hidden'):
                continue
            key = f'{folder.name}/{name}'
            pid = 'p-' + (slugify(path.stem) or hashlib.sha1(name.encode()).hexdigest()[:8])
            photos[key] = {'key': key, 'work': wid, 'path': path, 'entry': entry, 'pid': pid}
            keys.append(key)
        works.append({'id': wid, 'folder': folder.name, 'meta': meta, 'keys': keys,
                      'title': str(meta.get('title') or folder.name),
                      'location': str(meta.get('location') or folder.name)})
    return works, photos


def open_original(path, raw, tmp):
    """Open an original lazily. HEIC goes through macOS sips into a temp JPEG outside the repo."""
    if path.suffix.lower() in ('.heic', '.heif'):
        converted = Path(tmp) / (hashlib.sha1(raw).hexdigest() + '.jpg')
        if not converted.exists():
            subprocess.run(['sips', '-s', 'format', 'jpeg', '-s', 'formatOptions', '100',
                            str(path), '--out', str(converted)], check=True, capture_output=True)
        return Image.open(converted)
    return Image.open(io.BytesIO(raw))


def read_exif(im):
    """Return the camera settings that are present, and the capture time (or None)."""
    exif = im.getexif()
    sub = exif.get_ifd(0x8769)

    def text(value):
        if isinstance(value, bytes):
            value = value.decode('utf-8', 'ignore')
        return str(value or '').replace('\x00', '').strip()

    def number(value):
        if isinstance(value, (tuple, list)):
            value = value[0] if value else None
        try:
            value = float(value)
        except (TypeError, ValueError, ZeroDivisionError):
            return None
        return value if math.isfinite(value) and value > 0 else None

    make, model, lens = text(exif.get(0x010F)), text(exif.get(0x0110)), text(sub.get(0xA434))
    brand = MAKES.get(make.upper(), make)
    if model in MODELS:
        camera = MODELS[model]
    elif brand == 'Apple' or (model and brand and brand.split()[0].lower() in model.lower()):
        camera = model or brand
    else:
        camera = f'{brand} {model}'.strip()
    # Drop empty lens names and generic ones like "6.7 mm f/1.7" that only repeat focal length and aperture.
    if re.fullmatch(r'[-\s]*', lens) or ' f/0' in lens or re.fullmatch(r'[\d.]+\s*mm\s*f/[\d.]+', lens):
        lens = ''
    focal, fnum, expo, iso, focal35 = (number(sub.get(tag)) for tag in (0x920A, 0x829D, 0x829A, 0x8827, 0xA405))
    result = {'camera': camera, 'lens': lens}
    if focal:
        result['focal'] = f'{round(focal, 1):g}mm'
        if focal35 and focal35 / focal > 1.6:  # small sensors (phones, drones): add the 35mm equivalent
            result['focal'] += f' ({round(focal35):g}mm equiv.)'
    if fnum:
        result['aperture'] = f'f/{round(fnum, 1):g}'
    if expo:
        inverse = 1 / expo
        if expo < 1 and abs(inverse - round(inverse)) < 0.05 * inverse:
            result['shutter'] = f'1/{round(inverse)}s'
        else:
            result['shutter'] = f'{round(expo, 1):g}s'
    if iso:
        result['iso'] = f'ISO {int(iso)}'
    stamp = text(sub.get(0x9003)) or text(sub.get(0x9004))
    try:
        taken = datetime.datetime.strptime(stamp[:19], '%Y:%m:%d %H:%M:%S') if stamp else None
    except ValueError:
        taken = None
    return result, taken


def normalize(field, value):
    """Tidy a camera setting typed into gallery.yaml, e.g. aperture 4 -> f/4, iso 400 -> ISO 400."""
    text = str(value).strip()
    is_number = re.fullmatch(r'\d+(\.\d+)?', text)
    if field == 'iso' and is_number:
        return f'ISO {text}'
    if field == 'aperture' and is_number:
        return f'f/{text}'
    if field == 'focal' and is_number:
        return f'{text}mm'
    if field == 'shutter' and re.fullmatch(r'(1/)?\d+(\.\d+)?', text):
        return f'{text}s'
    return text


def exif_line(info, work_meta):
    """Camera settings shown under a photo: read from the file, filled in or overridden by gallery.yaml."""
    entry = info['entry']
    if entry.get('show_exif') is False:
        return ''
    values = dict(info['exif'])
    for field in EXIF_FIELDS:
        if not values.get(field) and work_meta.get(field) not in (None, ''):
            values[field] = normalize(field, work_meta[field])
        if entry.get(field) not in (None, ''):
            values[field] = normalize(field, entry[field])
    return ' · '.join(values[f] for f in EXIF_FIELDS if values.get(f))


def to_srgb(im):
    icc = im.info.get('icc_profile')
    if icc:
        try:
            if im.mode not in ('RGB', 'CMYK', 'L'):
                im = im.convert('RGB')
            im = ImageCms.profileToProfile(im, ImageCms.ImageCmsProfile(io.BytesIO(icc)),
                                           ImageCms.createProfile('sRGB'), outputMode='RGB')
        except (ImageCms.PyCMSError, OSError, ValueError):
            pass  # unusable profile: treat the pixels as sRGB
    return im.convert('RGB')


def fit(im, cfg):
    scale = min(cfg['max_w'] / im.width, cfg['max_h'] / im.height, 1.0)
    if scale < 1:
        size = (max(1, round(im.width * scale)), max(1, round(im.height * scale)))
        im = im.resize(size, Image.LANCZOS).filter(ImageFilter.UnsharpMask(radius=0.8, percent=40, threshold=2))
    return im


def find_font():
    return next((spec for spec in FONTS if Path(spec[0]).is_file()), None)


def add_watermark(im, text, font_spec):
    if not text:
        return im
    short = min(im.size)
    size = max(11, round(short * 0.022))
    font = ImageFont.truetype(font_spec[0], size, index=font_spec[1]) if font_spec else ImageFont.load_default(size)
    layer = Image.new('RGBA', im.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(layer)
    _, _, right, bottom = draw.textbbox((0, 0), text, font=font)
    margin = max(8, round(short * 0.025))
    x, y = im.width - margin - right, im.height - margin - bottom
    offset = max(1, round(size / 16))
    draw.text((x + offset, y + offset), text, font=font, fill=(0, 0, 0, 70))
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 170))
    return Image.alpha_composite(im.convert('RGBA'), layer).convert('RGB')


def save_clean(im, dest, quality):
    """Write pixels only: a fresh image carries no EXIF, GPS, XMP or ICC data."""
    clean = Image.new('RGB', im.size)
    clean.paste(im)
    dest.parent.mkdir(parents=True, exist_ok=True)
    clean.save(dest, 'WEBP', quality=quality, method=6)


def is_clean(path):
    """True if a WebP file holds image data only (no EXIF, XMP or ICC chunks)."""
    data = path.read_bytes()
    if data[:4] != b'RIFF' or data[8:12] != b'WEBP':
        return False
    i = 12
    while i + 8 <= len(data):
        fourcc, size = data[i:i + 4], struct.unpack('<I', data[i + 4:i + 8])[0]
        if fourcc not in (b'VP8 ', b'VP8L', b'VP8X', b'ALPH'):
            return False
        if fourcc == b'VP8X' and data[i + 8] & 0x2C:  # ICC, EXIF or XMP flag set
            return False
        i += 8 + size + (size & 1)
    return True


def process_all(photos, out, watermark):
    font = find_font()
    settings_tag = json.dumps([SETTINGS, watermark], sort_keys=True).encode()
    keep, made, reused = set(), 0, 0
    with tempfile.TemporaryDirectory() as tmp:
        for info in photos.values():
            raw = info['path'].read_bytes()
            digest = hashlib.sha1(raw + settings_tag).hexdigest()[:12]
            small = f'photos/{info["work"]}/{digest}-s.webp'
            large = f'photos/{info["work"]}/{digest}-l.webp'
            im = open_original(info['path'], raw, tmp)
            info['exif'], info['taken'] = read_exif(im)
            if (out / small).exists() and (out / large).exists():
                reused += 1
            else:
                upright = to_srgb(ImageOps.exif_transpose(im))
                for rel, cfg in ((large, SETTINGS['large']), (small, SETTINGS['small'])):
                    save_clean(add_watermark(fit(upright, cfg), watermark, font), out / rel, cfg['quality'])
                made += 1
            im.close()
            keep.update((small, large))
            with Image.open(out / small) as s, Image.open(out / large) as l:
                color = '#%02x%02x%02x' % s.convert('RGB').resize((1, 1), Image.BOX).getpixel((0, 0))
                info.update(small=small, large=large, w=s.width, h=s.height, lw=l.width, lh=l.height, color=color)
    return keep, made, reused


def parse_date(value):
    if value in (None, ''):
        return None
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date):
        return datetime.datetime(value.year, value.month, value.day)
    text = str(value).strip()
    for pattern in ('%Y-%m-%d', '%Y-%m', '%Y'):
        try:
            return datetime.datetime.strptime(text, pattern)
        except ValueError:
            pass
    die(f'cannot read the date "{text}"; write it like 2025-11-27')


def fmt_day(when):
    return when.strftime('%B %-d, %Y')


def fmt_range(dates):
    lo, hi = min(dates), max(dates)
    if (lo.year, lo.month) == (hi.year, hi.month):
        return lo.strftime('%B %Y')
    if lo.year == hi.year:
        return f'{lo.strftime("%B")} – {hi.strftime("%B %Y")}'
    return f'{lo.strftime("%B %Y")} – {hi.strftime("%B %Y")}'


def arrange(data, works, photos, selected):
    """Sort each work's photos by time and build the two home page orders."""
    newest = str((data.get('site') or {}).get('timeline') or 'newest').lower() != 'oldest'
    for info in photos.values():
        info['when'] = parse_date(info['entry'].get('date')) or info['taken']
    for work in works:
        known = [photos[k]['when'] for k in work['keys'] if photos[k]['when']]
        fallback = parse_date(work['meta'].get('date')) or (min(known) if known else None)
        for key in work['keys']:
            photos[key]['sort'] = photos[key]['when'] or fallback  # undated photos sort with their work
        work['keys'].sort(key=lambda k: (photos[k]['sort'] is None, photos[k]['sort'] or datetime.datetime.min, k))
        work['dates'] = known or ([fallback] if fallback else [])

    def by_time(keys):
        dated = sorted((k for k in keys if photos[k]['sort']), key=lambda k: (photos[k]['sort'], k), reverse=newest)
        return dated + sorted(k for k in keys if not photos[k]['sort'])

    chosen = set(selected)
    everything = [k for work in works for k in work['keys']]
    return {'selected': selected, 'rest': by_time([k for k in everything if k not in chosen]),
            'timeline': by_time(everything)}


def render(out, data, works, photos, orders):
    env = Environment(loader=FileSystemLoader(str(REPO / 'templates')),
                      autoescape=select_autoescape(['html']), trim_blocks=True, lstrip_blocks=True)
    site = data.get('site') or {}
    common = {'site': site, 'year': datetime.date.today().year}
    works = [work for work in works if work['keys']]
    by_id = {work['id']: work for work in works}
    chosen = set(orders['selected'])

    def month(info):
        if info['when']:
            return info['when'].strftime('%B %Y')
        work = by_id[info['work']]
        return fmt_range(work['dates']) if work['dates'] else ''

    def tile(key, root, eager=False):
        info = photos[key]
        work = by_id[info['work']]
        caption = str(info['entry'].get('caption') or '').strip()
        return {'href': f'{root}w/{work["id"]}/#{info["pid"]}', 'small': root + info['small'], 'large': root + info['large'],
                'w': info['w'], 'h': info['h'], 'lw': info['lw'], 'lh': info['lh'], 'ar': f'{info["w"] / info["h"]:.4f}',
                'color': info['color'], 'title': work['title'], 'date': month(info), 'alt': caption or work['title'],
                'eager': eager}

    selected = orders['selected']
    home = env.get_template('home.html').render(
        root='', **common,
        feature=tile(selected[0], '') if selected else None,
        selected=[tile(k, '', 0 < i < 7) for i, k in enumerate(selected)],
        rest=[tile(k, '', not selected and i < 6) for i, k in enumerate(orders['rest'])],
        timeline=[tile(k, '') for k in orders['timeline']])
    (out / 'index.html').write_text(home, encoding='utf-8')

    # Previous / next work, newest first like the chronological view; the cover is a selected photo if there is one.
    def latest(work):
        dates = [photos[k]['sort'] for k in work['keys'] if photos[k]['sort']]
        return max(dates) if dates else datetime.datetime.min
    ordered = sorted(works, key=latest, reverse=True)
    root = '../../'

    def neighbour(work):
        cover = photos[next((k for k in work['keys'] if k in chosen), work['keys'][0])]
        return {'title': work['title'], 'href': f'{root}w/{work["id"]}/', 'thumb': root + cover['small'],
                'ar': f'{cover["w"] / cover["h"]:.4f}', 'color': cover['color']}

    page = env.get_template('work.html')
    for index, work in enumerate(ordered):
        meta = work['meta']
        count = len(work['keys'])
        parts = [work['location'] if work['location'] != work['title'] else '',
                 fmt_range(work['dates']) if work['dates'] else '',
                 f'{count} photographs' if count > 1 else '']
        shots = []
        for key in work['keys']:
            info = photos[key]
            entry = info['entry']
            caption = str(entry.get('caption') or '').strip()
            detail = [str(entry.get('location') or '').strip(), fmt_day(info['when']) if info['when'] else '']
            shots.append({'pid': info['pid'], 'src': root + info['large'], 'lw': info['lw'], 'lh': info['lh'],
                          'ar': f'{info["lw"] / info["lh"]:.4f}', 'color': info['color'], 'caption': caption,
                          'detail': ' · '.join(d for d in detail if d), 'exif': exif_line(info, meta),
                          'alt': caption or work['title']})
        many = len(ordered) > 1
        html = page.render(root=root, **common, shots=shots,
                           prev=neighbour(ordered[index - 1]) if many else None,
                           next=neighbour(ordered[(index + 1) % len(ordered)]) if many else None,
                           work={'title': work['title'], 'meta': ' · '.join(p for p in parts if p),
                                 'note': str(meta.get('note') or '').strip()})
        target = out / 'w' / work['id'] / 'index.html'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding='utf-8')
    return 1 + len(works)


def clean_stale(out, keep, work_ids):
    """Delete images and work pages that the current build no longer produces."""
    removed = 0
    photos_dir = out / 'photos'
    if photos_dir.is_dir():
        for path in sorted(photos_dir.rglob('*'), reverse=True):
            if path.is_file() and path.relative_to(out).as_posix() not in keep:
                path.unlink()
                removed += 1
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()
    pages_dir = out / 'w'
    if pages_dir.is_dir():
        for folder in pages_dir.iterdir():
            if folder.is_dir() and folder.name not in work_ids:
                (folder / 'index.html').unlink(missing_ok=True)
                if not any(folder.iterdir()):
                    folder.rmdir()
    return removed


def main():
    parser = argparse.ArgumentParser(description='Build the photography site.')
    parser.add_argument('--originals', help='folder with the original photos (must be outside this repo)')
    parser.add_argument('--data', default=str(REPO / 'gallery.yaml'), help='gallery data (default: gallery.yaml)')
    parser.add_argument('--out', default=str(REPO), help='where to write the site (default: this repo)')
    args = parser.parse_args()

    data_path, originals, out = resolve_paths(args)
    data = load_yaml(data_path)
    works, photos = collect(data, originals)
    selected = []
    for key in data.get('selected') or []:
        if key not in photos:
            die(f'selected: "{key}" not found; write it as "<folder name>/<file name>"')
        if key in selected:
            die(f'selected: "{key}" is listed twice')
        selected.append(key)

    watermark = str((data.get('site') or {}).get('watermark') or '')
    keep, made, reused = process_all(photos, out, watermark)
    dirty = [rel for rel in sorted(keep) if not is_clean(out / rel)]
    if dirty:
        die('metadata found in: ' + ', '.join(dirty))
    orders = arrange(data, works, photos, selected)
    if out != REPO:
        shutil.copytree(REPO / 'assets', out / 'assets', dirs_exist_ok=True)
    page_count = render(out, data, works, photos, orders)
    removed = clean_stale(out, keep, {work['id'] for work in works})

    print(f'{len(works)} works, {len(photos)} photos ({made} processed, {reused} unchanged), '
          f'{len(selected)} selected, {page_count} pages, {removed} stale files removed.')
    print(f'All {len(keep)} images checked: no metadata.')
    undated = [key for key, info in photos.items() if not info['when']]
    if undated:
        print('No capture date (sorted with their work; add "date:" in gallery.yaml to set one):')
        for key in undated:
            print(f'  {key}')


if __name__ == '__main__':
    main()
