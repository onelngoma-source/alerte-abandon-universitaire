"""Fabrique le carton QR a projeter pendant la demonstration.

Usage :
    python3 qr_soutenance.py "https://adresse-de-mon-application"
    python3 qr_soutenance.py "https://..." --identifiant jury --motdepasse soutenance2026
"""
import argparse
import pathlib

import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.constants import ERROR_CORRECT_H

SERIF = "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"
SANS = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
SANS_G = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
VIOLET, ORANGE, LILAS, GRIS = (75, 46, 131), (232, 112, 26), (201, 184, 232), (120, 125, 140)


def carton(url, identifiant, motdepasse, sortie="QR_application.png"):
    larg, haut = 1600, 900
    im = Image.new("RGB", (larg, haut), "white")
    d = ImageDraw.Draw(im)

    qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_H, box_size=12, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color=VIOLET, back_color="white").convert("RGB")
    img = img.resize((520, 520), Image.NEAREST)
    im.paste(img, (120, 190))

    f_titre = ImageFont.truetype(SERIF, 46)
    f_sous = ImageFont.truetype(SANS, 24)
    f_eti = ImageFont.truetype(SANS_G, 18)
    f_val = ImageFont.truetype(SANS, 26)
    f_url = ImageFont.truetype(SANS, 19)

    x = 740
    d.text((x, 210), "Testez l'application", font=f_titre, fill=VIOLET)
    d.text((x, 280), "Scannez ce code pour l'ouvrir sur votre telephone.", font=f_sous, fill=GRIS)

    y = 380
    for etiquette, valeur in (("IDENTIFIANT", identifiant), ("MOT DE PASSE", motdepasse)):
        if not valeur:
            continue
        d.rounded_rectangle([x, y, x + 700, y + 92], radius=12, fill=(243, 241, 248))
        d.text((x + 26, y + 16), etiquette, font=f_eti, fill=ORANGE)
        d.text((x + 26, y + 44), valeur, font=f_val, fill=(26, 26, 46))
        y += 108

    affiche = url if len(url) <= 62 else url[:59] + "..."
    d.text((x, y + 14), affiche, font=f_url, fill=GRIS)

    d.text((120, 760), "Dispositif d'alerte precoce du risque d'abandon universitaire",
           font=ImageFont.truetype(SANS, 22), fill=GRIS)
    d.text((120, 796), "NGOMA NGOMA Onel Melvy  ·  Licence professionnelle IABD  ·  Session d'Octobre 2026",
           font=ImageFont.truetype(SANS, 20), fill=LILAS)

    p = pathlib.Path(sortie)
    im.save(p)

    seul = qrcode.QRCode(error_correction=ERROR_CORRECT_H, box_size=16, border=3)
    seul.add_data(url)
    seul.make(fit=True)
    seul.make_image(fill_color="black", back_color="white").save(p.with_name("QR_seul.png"))
    return p


if __name__ == "__main__":
    a = argparse.ArgumentParser()
    a.add_argument("url")
    a.add_argument("--identifiant", default="jury")
    a.add_argument("--motdepasse", default="soutenance2026")
    a.add_argument("--sortie", default="QR_application.png")
    o = a.parse_args()
    print("carton ecrit :", carton(o.url, o.identifiant, o.motdepasse, o.sortie))
