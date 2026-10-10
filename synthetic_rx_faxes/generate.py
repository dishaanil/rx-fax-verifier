#!/usr/bin/env python3
"""Synthetic faxed-prescription generator.

Makes N fake prescriptions across 4 templates and 3 fax-quality tiers, plus exact
ground truth (values, field bounding boxes, and the fields a safe system should flag).

    python3 generate.py --n 40 --seed 7 --out dataset

Everything is invented. Every page carries a "SYNTHETIC TEST DATA" footer.
Requires: pillow, numpy. Handwriting fonts are read from ./fonts (OFL/Apache licensed).
"""
import argparse, csv, datetime as dt, json, os, random
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
W, H = 1700, 2200  # US letter at 200 dpi (standard fax resolution)
LIB = "/usr/share/fonts/truetype/liberation/"
TYPED = {"R": "LiberationSans-Regular.ttf", "B": "LiberationSans-Bold.ttf",
         "S": "LiberationSerif-BoldItalic.ttf", "M": "LiberationMono-Regular.ttf",
         "MB": "LiberationMono-Bold.ttf"}
# handwriting font -> size multiplier (their natural sizes differ a lot)
HAND = {"Kalam": 1.0, "ReenieBeanie": 1.35, "IndieFlower": 1.0, "NothingYouCouldDo": 0.95,
        "Caveat": 1.2, "Cedarville": 0.9, "ShadowsIntoLight": 1.1, "Covered": 1.15,
        "Gloria": 0.8, "HomemadeApple": 0.7}
THIN = {"NothingYouCouldDo", "ReenieBeanie", "Cedarville", "ShadowsIntoLight", "HomemadeApple"}  # get 1px extra stroke
_fc = {}


def font(name, size):
    k = (name, size)
    if k not in _fc:
        path = LIB + TYPED[name] if name in TYPED else os.path.join(HERE, "fonts", name + ".ttf")
        try:
            _fc[k] = ImageFont.truetype(path, size)
        except OSError:  # typed fonts missing on this machine: fall back to PIL's default
            _fc[k] = ImageFont.load_default(size)
    return _fc[k]


R = lambda s: font("R", s)
B = lambda s: font("B", s)
M = lambda s: font("M", s)

# ----------------------------------------------------------------------------- data
FIRST = ["Marisol", "Devon", "Priya", "Tobias", "Anneliese", "Kwame", "Lucinda", "Rafael", "Ingrid",
         "Malcolm", "Yasmin", "Dmitri", "Beatrix", "Osvaldo", "Noor", "Clement", "Saoirse", "Jun",
         "Thaddeus", "Imani", "Greta", "Cormac", "Leilani", "Anselm", "Farah", "Hollis", "Mireille",
         "Ezekiel", "Odalys", "Bram", "Winifred", "Kofi", "Sunniva", "Lazaro", "Petra", "Ambrose",
         "Zainab", "Hartley", "Calista", "Evander"]
LAST = ["Quintanilla", "Ashgrove", "Raghunathan", "Vandermeer", "Holloway", "Boateng", "Featherstone",
        "Echeverria", "Lindqvist", "Okonkwo", "Darwish", "Volkonsky", "Pemberton", "Zaragoza",
        "Haddadin", "Thistlewood", "Gallagher", "Nakashima", "Birdwhistle", "Adebayo", "Sorensen",
        "Fitzwilliam", "Kahananui", "Drummond", "Sabbagh", "Wetherby", "Charpentier", "Mbeki",
        "Villaverde", "Oosterhuis", "Larkspur", "Asante", "Hjelmstad", "Montenegro", "Wojcik",
        "Castellane", "Rahimzadeh", "Underhill", "Marchetti", "Stavros"]
STREETS = ["Quarry Bend Rd", "Tallow St", "Wren Hollow Ln", "Old Ferry Rd", "Marlpit Ave", "Sedge Ct"]
CLINICS = {
    "Tamsin Ridge Family Medicine": ("118 Copperleaf Lane, Suite 2, Tamsin Ridge, NY 10099", "(212) 555-0143", "(212) 555-0144"),
    "Orrin Vale Internal Medicine": ("4070 Lantern Mill Rd, Orrin Vale, NJ 07099", "(201) 555-0118", "(201) 555-0119"),
    "Pellham Marsh Primary Care": ("22 Saltgrass Way, Pellham Marsh, CT 06099", "(203) 555-0162", "(203) 555-0163"),
    "Kestrel Row Medical Group": ("901 Kestrel Row, 4th Floor, Dunmere, NY 10098", "(718) 555-0177", "(718) 555-0178"),
}
PRESCRIBERS = [  # name, credential, clinic, handwriting font
    ("Renata Okafor-Lindh", "MD", "Tamsin Ridge Family Medicine", "Kalam"),
    ("Gideon Praetorius", "DO", "Orrin Vale Internal Medicine", "ReenieBeanie"),
    ("Shirin Talebpour", "NP", "Pellham Marsh Primary Care", "IndieFlower"),
    ("Augustin Belrose", "MD", "Kestrel Row Medical Group", "NothingYouCouldDo"),
    ("Mei-Lin Castellanos", "PA-C", "Tamsin Ridge Family Medicine", "Caveat"),
    ("Bartholomew Nkemelu", "MD", "Orrin Vale Internal Medicine", "Cedarville"),
    ("Linnea Hargreave", "MD", "Kestrel Row Medical Group", "ShadowsIntoLight"),
    ("Dorian Vasquez-Thorne", "DO", "Pellham Marsh Primary Care", "Covered"),
]
FACILITIES = [("Alderwick Care Center", "(914) 555-0131", "(914) 555-0132"),
              ("Fennimore Glen Nursing & Rehab", "(516) 555-0156", "(516) 555-0157")]
NURSES = [("T. Brannigan RN", "Gloria"), ("O. Achterberg LPN", "IndieFlower"), ("S. Dellacroce RN", "Kalam")]
PHARMACY = ("Corner Test Pharmacy", "(212) 555-0199")

QD = ("1 tab po qd", "Take 1 tablet by mouth once daily")
# drug, strengths, unit, form, form abbrev, (sig as written, sig normalized), quantities, refills
MEDS = [
    ("Lisinopril", [10, 20, 40], "mg", "tablet", "tab", QD, [30, 90], [0, 1, 3, 5]),
    ("Metformin", [500, 1000], "mg", "tablet", "tab", ("1 tab po bid w/ meals", "Take 1 tablet by mouth twice daily with meals"), [60, 180], [1, 3, 5]),
    ("Atorvastatin", [10, 20, 40, 80], "mg", "tablet", "tab", ("1 tab po qhs", "Take 1 tablet by mouth at bedtime"), [30, 90], [1, 3]),
    ("Amlodipine", [5, 10], "mg", "tablet", "tab", ("1 tab po daily", "Take 1 tablet by mouth once daily"), [30, 90], [2, 5]),
    ("Levothyroxine", [50, 75, 100, 125], "mcg", "tablet", "tab", ("1 tab po qam on empty stomach", "Take 1 tablet by mouth every morning on an empty stomach"), [30, 90], [1, 3]),
    ("Omeprazole", [20, 40], "mg", "capsule", "cap", ("1 cap po qam ac", "Take 1 capsule by mouth every morning before breakfast"), [30], [0, 2]),
    ("Sertraline", [25, 50, 100], "mg", "tablet", "tab", QD, [30], [1, 2]),
    ("Losartan", [25, 50, 100], "mg", "tablet", "tab", QD, [30, 90], [3]),
    ("Hydrochlorothiazide", [12.5, 25], "mg", "tablet", "tab", ("1 tab po qam", "Take 1 tablet by mouth every morning"), [30], [3, 5]),
    ("Amoxicillin", [500], "mg", "capsule", "cap", ("1 cap po tid x 10 days", "Take 1 capsule by mouth three times daily for 10 days"), [30], [0]),
    ("Azithromycin", [250], "mg", "tablet", "tab", ("2 tabs po day 1, then 1 tab qd x 4 days", "Take 2 tablets by mouth on day 1, then 1 tablet once daily for 4 days"), [6], [0]),
    ("Prednisone", [10, 20], "mg", "tablet", "tab", ("2 tabs po qd x 5 days", "Take 2 tablets by mouth once daily for 5 days"), [10], [0]),
    ("Albuterol HFA", [90], "mcg", "inhaler", "inh", ("2 puffs q4-6h prn wheezing", "Inhale 2 puffs every 4 to 6 hours as needed for wheezing"), [1], [1, 2]),
    ("Metoprolol succinate ER", [25, 50, 100], "mg", "tablet", "tab", QD, [30, 90], [3]),
    ("Montelukast", [10], "mg", "tablet", "tab", ("1 tab po qhs", "Take 1 tablet by mouth at bedtime"), [30], [5]),
    ("Hydroxyzine", [25, 50], "mg", "tablet", "tab", ("1 tab po tid prn itching", "Take 1 tablet by mouth three times daily as needed for itching"), [30], [0, 1]),
    ("Hydralazine", [25, 50], "mg", "tablet", "tab", ("1 tab po tid", "Take 1 tablet by mouth three times daily"), [90], [2]),
    ("Lamotrigine", [25, 100], "mg", "tablet", "tab", ("1 tab po bid", "Take 1 tablet by mouth twice daily"), [60], [2]),
    ("Metronidazole", [500], "mg", "tablet", "tab", ("1 tab po bid x 7 days", "Take 1 tablet by mouth twice daily for 7 days"), [14], [0]),
    ("Furosemide", [20, 40], "mg", "tablet", "tab", ("1 tab po qam", "Take 1 tablet by mouth every morning"), [30], [2]),
    ("Cephalexin", [500], "mg", "capsule", "cap", ("1 cap po qid x 7 days", "Take 1 capsule by mouth four times daily for 7 days"), [28], [0]),
    ("Glipizide", [5, 10], "mg", "tablet", "tab", ("1 tab po qam ac", "Take 1 tablet by mouth every morning before breakfast"), [30], [3]),
    ("Warfarin", [2.5, 5], "mg", "tablet", "tab", ("1 tab po qpm", "Take 1 tablet by mouth every evening"), [30], [1]),
    ("Methotrexate", [2.5], "mg", "tablet", "tab", ("3 tabs po once weekly", "Take 3 tablets by mouth once weekly"), [12], [2]),
]
MED = {m[0]: m for m in MEDS}
LOOKALIKE = {"Hydroxyzine": "Hydralazine", "Hydralazine": "Hydroxyzine", "Metformin": "Metronidazole",
             "Metronidazole": "Metformin", "Lamotrigine": "Lamivudine", "Prednisone": "Prednisolone",
             "Glipizide": "Glyburide"}

# record index (0-based) -> (challenge, forced drug or None). Spread over templates and tiers.
CHALLENGES = {
    2: ("lookalike_risk", "Hydralazine"), 13: ("lookalike_risk", "Metronidazole"), 28: ("lookalike_risk", "Lamotrigine"),
    4: ("missing_quantity", None), 18: ("missing_quantity", None),
    9: ("missing_signature", None), 23: ("missing_signature", None),
    12: ("dose_unit_error", "Levothyroxine"),
    21: ("dose_out_of_range", "Metformin"), 30: ("dose_out_of_range", "Lisinopril"),
    15: ("frequency_error", "Methotrexate"),
    8: ("smudged_strength", None), 26: ("smudged_strength", None), 37: ("smudged_strength", None),
    11: ("smudged_dob", None), 27: ("missing_dob", None),
    36: ("smudged_drug", "Hydroxyzine"),
    16: ("correction", "Atorvastatin"), 34: ("correction", "Sertraline"),
    33: ("missing_refills", None),
}
EXPECTED_FLAGS = {
    "lookalike_risk": [], "missing_quantity": ["quantity"], "missing_signature": ["signature"],
    "dose_unit_error": ["strength"], "dose_out_of_range": ["strength"], "frequency_error": ["sig"],
    "smudged_strength": ["strength"], "smudged_dob": ["patient_dob"], "missing_dob": ["patient_dob"],
    "smudged_drug": ["drug"], "correction": ["strength"], "missing_refills": ["refills"],
}
NOTES = {
    "lookalike_risk": "Drug name is easily confused with {alt}. Legible here; a good system still double-checks.",
    "missing_quantity": "Quantity was left blank by the prescriber.",
    "missing_signature": "Prescription is not signed.",
    "dose_unit_error": "Written as 25 mg; levothyroxine is dosed in mcg. Truth records what is on the page.",
    "dose_out_of_range": "Strength as written is far above any marketed strength. Truth records what is on the page.",
    "frequency_error": "Methotrexate written as daily; it is normally weekly. Truth records what is on the page.",
    "smudged_strength": "Strength digits are physically obscured. Truth holds the original value, but it cannot be read from the image.",
    "smudged_dob": "Date of birth is physically obscured. Truth holds the original value, but it cannot be read from the image.",
    "missing_dob": "Date of birth was left blank.",
    "smudged_drug": "Middle of the drug name is obscured, leaving Hydr___ine: Hydroxyzine or Hydralazine. It cannot be resolved from the image.",
    "correction": "Prescriber crossed out one strength and wrote another. Truth is the corrected value; alterations should be verified.",
    "missing_refills": "Refills field was left blank.",
}
TEMPLATES = ["pad", "ehr", "faxform", "ltc"]
TIER_BY_GROUP = ["clean", "moderate", "hard", "moderate", "clean", "moderate", "hard", "moderate", "clean", "hard"]
FIELDS = ["patient_name", "patient_dob", "drug", "strength", "sig", "quantity", "refills",
          "prescriber_name", "npi", "date_written", "signature"]


def npi(rng):
    """Random 10-digit NPI with a valid Luhn check digit (prefix 80840), so checksum validation can be demoed."""
    body = "1" + "".join(str(rng.randint(0, 9)) for _ in range(8))
    digits = [int(c) for c in "80840" + body]
    tot = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        tot += d
    return body + str((10 - tot % 10) % 10)


def num(x):
    return str(int(x)) if float(x).is_integer() else str(x)


def build_records(n, seed):
    rng = random.Random(seed)
    firsts, lasts = FIRST[:], LAST[:]
    rng.shuffle(firsts); rng.shuffle(lasts)
    pool = []
    prescribers = {}
    for name, cred, clinic, hand in PRESCRIBERS:
        addr, tel, fax = CLINICS[clinic]
        prescribers[name] = dict(name=name, credential=cred, clinic=clinic, address=addr, phone=tel, fax=fax,
                                 npi=npi(rng), lic=f"{rng.randint(100000, 999999)}", _hand=hand)
    recs = []
    for i in range(n):
        template = TEMPLATES[i % 4]
        tier = TIER_BY_GROUP[(i // 4) % len(TIER_BY_GROUP)]
        ch, forced = CHALLENGES.get(i, (None, None)) if n >= 40 or i in CHALLENGES else (None, None)
        if template in ("ehr",) and ch == "correction":
            ch, forced = None, None
        if not pool:
            pool = [m[0] for m in MEDS]; rng.shuffle(pool)
        drug = forced or pool.pop()
        _, strengths, unit, form, fabbr, (sig_w, sig_n), qtys, rfs = MED[drug]
        strength = f"{num(rng.choice(strengths))} {unit}"
        qty, refills = rng.choice(qtys), rng.choice(rfs)
        wrong = None
        if ch == "dose_unit_error":
            strength = "25 mg"
        elif ch == "dose_out_of_range":
            strength = {"Metformin": "5000 mg", "Lisinopril": "400 mg"}[drug]
        elif ch == "frequency_error":
            sig_w, sig_n, qty = "1 tab po qd", "Take 1 tablet by mouth once daily", 30
        elif ch == "correction":
            others = [s for s in strengths if f"{num(s)} {unit}" != strength]
            wrong = num(rng.choice(others))
        pr = dict(rng.choice(list(prescribers.values())))
        written = dt.date(2026, 10, 10) - dt.timedelta(days=rng.randint(0, 4))
        old = template == "ltc"
        dob = dt.date(rng.randint(1932, 1950) if old else rng.randint(1941, 2008), rng.randint(1, 12), rng.randint(1, 28))
        hand = pr.pop("_hand")
        rec = dict(
            id=f"rx_{i + 1:03d}", template=template, tier=tier,
            patient=dict(name=f"{firsts[i % 40]} {lasts[i % 40]}",
                         dob=None if ch == "missing_dob" else dob.isoformat(),
                         address=f"{rng.randint(11, 989)} {rng.choice(STREETS)}",
                         phone=f"(646) 555-01{rng.randint(10, 99)}"),
            medication=dict(drug=drug, strength=strength, form=form),
            sig_as_written=sig_w, sig_normalized=sig_n,
            quantity=None if ch == "missing_quantity" else qty,
            refills=None if ch == "missing_refills" else refills,
            prescriber={k: pr[k] for k in ("name", "credential", "npi", "clinic", "phone", "fax")},
            date_written=written.isoformat(),
            signed=ch != "missing_signature",
            challenge=ch, expected_flags=EXPECTED_FLAGS.get(ch, []),
            unreadable_in_image=EXPECTED_FLAGS[ch] if ch and ch.startswith("smudged") else [],
            notes=NOTES[ch].format(alt=LOOKALIKE.get(drug, "")) if ch else "",
        )
        if ch == "lookalike_risk" or drug in LOOKALIKE:
            rec["lookalike_of"] = LOOKALIKE.get(drug)
        if template == "ltc":
            fac = rng.choice(FACILITIES); nurse = rng.choice(NURSES)
            rec["facility"] = dict(name=fac[0], phone=fac[1], fax=fac[2], room=f"{rng.randint(101, 348)}-{rng.choice('AB')}")
            rec["_nurse"] = nurse[0]; hand = nurse[1]
        # private rendering hints (stripped before truth is written)
        rec["_p"] = pr; rec["_hand"] = hand; rec["_sigfont"] = rng.choice(["HomemadeApple", "Cedarville", "NothingYouCouldDo"])
        rec["_wrong"] = wrong; rec["_fabbr"] = fabbr; rec["_seed"] = rng.randint(0, 10**9)
        y2 = rng.random() < 0.5
        rec["_date_w"] = f"{written.month}/{written.day}/{str(written.year)[2:] if y2 else written.year}"
        rec["_dob_w"] = f"{dob.month}/{dob.day}/{dob.year}" if rng.random() < 0.6 else dob.strftime("%m-%d-%Y")
        recs.append(rec)
    return recs


# ----------------------------------------------------------------------------- drawing
class Page:
    def __init__(self, rec):
        self.rec = rec
        self.rng = random.Random(rec["_seed"])
        self.img = Image.new("L", (W, H), 255)
        self.d = ImageDraw.Draw(self.img)
        self.boxes = {}
        self.hf = rec["_hand"]
        self.ink = self.rng.randint(0, 45)

    def mark(self, field, b):
        if not field:
            return
        o = self.boxes.get(field)
        self.boxes[field] = list(b) if not o else [min(o[0], b[0]), min(o[1], b[1]), max(o[2], b[2]), max(o[3], b[3])]

    def t(self, x, y, txt, f, field=None, anchor="la"):
        """Typed text. Returns the right edge."""
        self.d.text((x, y), txt, font=f, fill=0, anchor=anchor)
        b = self.d.textbbox((x, y), txt, font=f, anchor=anchor)
        self.mark(field, b)
        return b[2]

    def hand(self, x, y, txt, size=46, field=None, fnt=None):
        """Handwritten text, one word at a time with jitter. Returns the right edge."""
        name = fnt or self.hf
        f = font(name, int(size * HAND[name]))
        cx = x
        for w in txt.split(" "):
            if not w:
                continue
            l, tp, r, bt = f.getbbox(w)
            pad = 14
            m = Image.new("L", (r - l + 2 * pad, bt - tp + 2 * pad), 0)
            ImageDraw.Draw(m).text((pad - l, pad - tp), w, font=f, fill=255, stroke_width=1 if name in THIN else 0, stroke_fill=255)
            m = m.rotate(self.rng.uniform(-2.5, 2.5), expand=True, resample=Image.BICUBIC)
            px, py = int(cx - pad), int(y + tp - pad + self.rng.randint(-4, 4))
            self.img.paste(self.ink, (px, py), m)
            bb = m.getbbox()
            if bb:
                self.mark(field, (px + bb[0], py + bb[1], px + bb[2], py + bb[3]))
            cx += (r - l) + int(f.getlength(" ") * self.rng.uniform(0.9, 1.4))
        return cx

    def hand_wrap(self, x, y, txt, maxw, size=46, field=None, lh=62):
        f = font(self.hf, int(size * HAND[self.hf]))
        line, lines = "", []
        for w in txt.split(" "):
            trial = (line + " " + w).strip()
            if f.getlength(trial) * 1.12 > maxw and line:
                lines.append(line); line = w
            else:
                line = trial
        lines.append(line)
        for ln in lines:
            self.hand(x, y, ln, size, field); y += lh
        return y

    def hline(self, x0, y, x1, w=2):
        self.d.line((x0, y, x1, y), fill=0, width=w)

    def strike_last(self, key="_strike"):
        b = self.boxes.pop(key)
        cy = (b[1] + b[3]) // 2
        self.d.line((b[0] - 10, cy + 6, b[2] + 10, cy - 6), fill=self.ink, width=5)

    def signature(self, x, y, size=64):
        if not self.rec["signed"]:
            return
        n = self.rec["prescriber"]["name"].split()
        self.hand(x, y, f"{n[0][0]}. {n[-1]}", size, "signature", fnt=self.rec["_sigfont"])

    def chrome(self, sender, sender_fax):
        tm = f"{self.rng.randint(7, 17):02d}:{self.rng.randint(0, 59):02d}"
        d = dt.date.fromisoformat(self.rec["date_written"]).strftime("%b-%d-%Y").upper()
        self.t(36, 14, f"{d} {tm}  FROM: {sender.upper()[:26]}  {sender_fax}   TO: {PHARMACY[1]}   P.001/001", M(24))
        self.t(W // 2, H - 44, "SYNTHETIC TEST DATA - NOT A VALID PRESCRIPTION", R(20), None, "ma")


def strength_written(rec, compact):
    s = rec["medication"]["strength"]
    return s.replace(" ", "") if compact else s


def hand_med_line(p, x, y, size=50):
    r = p.rec
    x = p.hand(x, y, r["medication"]["drug"], size, "drug")
    if r["_wrong"]:
        x = p.hand(x + 14, y, r["_wrong"], size, "_strike"); p.strike_last()
    x = p.hand(x + 14, y, strength_written(r, p.rng.random() < 0.4), size, "strength")
    p.hand(x + 14, y, r["_fabbr"], size)


def refills_written(p):
    rf = p.rec["refills"]
    if rf is None:
        return None
    return p.rng.choice(["0", "NR", "none"]) if rf == 0 else str(rf)


def tpl_pad(p):
    """Classic pre-printed prescription pad, filled in by hand."""
    r, d, pr, full = p.rec, p.d, p.rec["prescriber"], p.rec["_p"]
    x0, y0, x1, y1 = 300, 220, 1400, 1700
    d.rectangle((x0, y0, x1, y1), outline=0, width=3)
    cx = (x0 + x1) // 2
    p.t(cx, y0 + 36, f'{pr["name"]}, {pr["credential"]}', B(44), "prescriber_name", "ma")
    p.t(cx, y0 + 94, pr["clinic"], R(32), None, "ma")
    p.t(cx, y0 + 138, full["address"], R(25), None, "ma")
    p.t(cx, y0 + 172, f'Tel {pr["phone"]}    Fax {pr["fax"]}', R(25), None, "ma")
    xx = p.t(x0 + 40, y0 + 222, "NPI ", R(26)); p.t(xx, y0 + 222, pr["npi"], R(26), "npi")
    p.t(x1 - 40, y0 + 222, f'State Lic. {full["lic"]}', R(26), None, "ra")
    d.line((x0, y0 + 270, x1, y0 + 270), fill=0, width=3)
    y = y0 + 312
    xx = p.t(x0 + 40, y, "Name", R(28)); p.hline(xx + 10, y + 34, x0 + 690)
    p.hand(xx + 28, y - 20, r["patient"]["name"], 46, "patient_name")
    xx = p.t(x0 + 710, y, "DOB", R(28)); p.hline(xx + 10, y + 34, x1 - 40)
    if r["patient"]["dob"]:
        p.hand(xx + 24, y - 20, r["_dob_w"], 44, "patient_dob")
    y += 86
    xx = p.t(x0 + 40, y, "Address", R(28)); p.hline(xx + 10, y + 34, x0 + 690)
    p.hand(xx + 28, y - 20, r["patient"]["address"], 42)
    xx = p.t(x0 + 710, y, "Date", R(28)); p.hline(xx + 10, y + 34, x1 - 40)
    p.hand(xx + 24, y - 20, r["_date_w"], 44, "date_written")
    y += 110
    p.t(x0 + 40, y, "Rx", font("S", 130))
    hx = x0 + 215
    y += 150
    hand_med_line(p, hx, y, 52)
    y += 120
    xe = p.hand(hx, y, "Sig:", 48)
    y = p.hand_wrap(xe + 12, y, r["sig_as_written"], x1 - 60 - xe, 48, "sig", 74)
    y += 46
    xe = p.hand(hx, y, "Disp:", 48)
    if r["quantity"] is not None:
        q = r["quantity"]  # a string (e.g. "50 mL") is drawn as written; counts get the usual "#"
        p.hand(xe + 14, y, q if isinstance(q, str) else f'#{q}', 50, "quantity")
    yb = y1 - 250
    xx = p.t(x0 + 40, yb, "Refills", R(28)); p.hline(xx + 10, yb + 34, x0 + 330)
    rw = refills_written(p)
    if rw:
        p.hand(xx + 40, yb - 20, rw, 48, "refills")
    p.hline(x0 + 520, yb + 110, x1 - 40)
    p.signature(x0 + 570, yb + 30)
    p.t(x0 + 520, yb + 120, "Prescriber signature", R(22))
    d.rectangle((x0 + 40, y1 - 90, x0 + 66, y1 - 64), outline=0, width=2); p.t(x0 + 78, y1 - 92, "Dispense as written", R(24))
    d.rectangle((x0 + 420, y1 - 90, x0 + 446, y1 - 64), outline=0, width=2); p.t(x0 + 458, y1 - 92, "Substitution permissible", R(24))
    p.chrome(pr["clinic"], pr["fax"])


def tpl_ehr(p):
    """Typed EHR printout that was printed and faxed instead of e-prescribed."""
    r, d, pr, full = p.rec, p.d, p.rec["prescriber"], p.rec["_p"]
    L, Rr = 110, 1590
    p.t(L, 130, pr["clinic"], B(46))
    p.t(L, 190, full["address"], R(27))
    p.t(L, 226, f'Phone {pr["phone"]}   Fax {pr["fax"]}', R(27))
    p.t(Rr, 130, "PRESCRIPTION", B(44), None, "ra")
    p.t(Rr, 190, f'Rx ref: {p.rng.randint(1000000, 9999999)}', M(26), None, "ra")
    wd = dt.date.fromisoformat(r["date_written"])
    xx = p.t(Rr - 330, 226, "Written: ", R(27)); p.t(xx, 226, wd.strftime("%m/%d/%Y"), B(27), "date_written")
    d.line((L, 280, Rr, 280), fill=0, width=4)

    def box(y, h, title):
        d.rectangle((L, y, Rr, y + h), outline=0, width=2)
        d.rectangle((L, y, Rr, y + 46), fill=0)
        d.text((L + 16, y + 8), title, font=B(28), fill=255)
        return y + 70

    def kv(x, y, k, v, field=None, vf=None):
        p.t(x, y, k, R(24))
        if v is not None:
            p.t(x, y + 32, v, vf or B(32), field)

    y = box(330, 290, "PATIENT")
    kv(L + 24, y, "Name", r["patient"]["name"], "patient_name")
    dob = r["patient"]["dob"]
    kv(L + 780, y, "Date of birth", dt.date.fromisoformat(dob).strftime("%m/%d/%Y") if dob else None, "patient_dob")
    kv(L + 1150, y, "Phone", r["patient"]["phone"])
    kv(L + 24, y + 110, "Address", r["patient"]["address"])
    kv(L + 780, y + 110, "Allergies", "NKDA")
    y = box(660, 560, "MEDICATION")
    p.t(L + 24, y, "Drug / strength / form", R(24))
    xx = p.t(L + 24, y + 34, r["medication"]["drug"].upper(), font("MB", 40), "drug")
    xx = p.t(xx + 24, y + 34, r["medication"]["strength"].upper(), font("MB", 40), "strength")
    p.t(xx + 24, y + 34, r["medication"]["form"].upper(), font("MB", 40))
    p.t(L + 24, y + 120, "Directions (Sig)", R(24))
    p.t(L + 24, y + 154, r["sig_normalized"], B(32), "sig")
    q = r["quantity"]
    kv(L + 24, y + 240, "Quantity", str(q) if q is not None else None, "quantity", font("MB", 36))
    rf = r["refills"]
    kv(L + 420, y + 240, "Refills", str(rf) if rf is not None else None, "refills", font("MB", 36))
    kv(L + 780, y + 240, "Substitution", "Permitted")
    kv(L + 1150, y + 240, "Days supply", "--")
    p.t(L + 24, y + 360, "Pharmacy", R(24)); p.t(L + 24, y + 392, f"{PHARMACY[0]}   Fax {PHARMACY[1]}", R(30))
    y = box(1260, 380, "PRESCRIBER")
    kv(L + 24, y, "Name", f'{pr["name"]}, {pr["credential"]}', "prescriber_name")
    kv(L + 780, y, "NPI", pr["npi"], "npi", font("MB", 34))
    kv(L + 1150, y, "License", full["lic"])
    if r["signed"]:
        if p.rng.random() < 0.5:
            tm = f"{p.rng.randint(8, 17):02d}:{p.rng.randint(0, 59):02d}"
            p.t(L + 24, y + 160, f'Electronically signed by {pr["name"]}, {pr["credential"]} on {wd.strftime("%m/%d/%Y")} {tm}', R(28), "signature")
        else:
            p.signature(L + 220, y + 110)
    p.t(L + 24, y + 216, "Signature", R(24)); p.hline(L + 150, y + 240, L + 900)
    p.t(L, 1700, "This prescription was generated from the electronic health record and transmitted by facsimile.", R(22))
    p.t(L, 1730, "If you received it in error, notify the sender and destroy all copies.", R(22))
    p.chrome(pr["clinic"], pr["fax"])


def tpl_faxform(p):
    """Generic clinic fax order form: typed labels, handwritten fills, circled refills."""
    r, d, pr = p.rec, p.d, p.rec["prescriber"]
    L, Rr = 130, 1570
    d.rectangle((L, 110, Rr, 196), outline=0, width=4)
    p.t(W // 2, 126, "PRESCRIPTION FAX ORDER FORM", B(50), None, "ma")
    y = 230
    p.t(L, y, "TO:", B(28)); p.t(L + 90, y, PHARMACY[0], R(30)); p.t(L + 90, y + 40, f"Fax {PHARMACY[1]}", R(28))
    p.t(L + 760, y, "FROM:", B(28)); p.t(L + 880, y, pr["clinic"], R(30))
    p.t(L + 880, y + 40, f'Tel {pr["phone"]}  Fax {pr["fax"]}', R(28))
    xx = p.t(L, y + 100, "Date:", B(28)); p.hline(xx + 10, y + 134, L + 420)
    p.hand(xx + 30, y + 82, r["_date_w"], 46, "date_written")
    p.t(L + 760, y + 100, "Pages (incl. cover): 1", R(28))

    def section(y, title):
        d.rectangle((L, y, Rr, y + 44), fill=0)
        d.text((L + 14, y + 7), title, font=B(28), fill=255)
        return y + 80

    def line(y, label, val, field=None, x=L, xend=Rr, size=48):
        xx = p.t(x, y, label, R(28)); p.hline(xx + 10, y + 34, xend)
        if val:
            p.hand(xx + 30, y - 22, val, size, field)
        return xx

    y = section(410, "PATIENT INFORMATION")
    line(y, "Patient name:", r["patient"]["name"], "patient_name", xend=L + 860)
    line(y, "Date of birth:", r["_dob_w"] if r["patient"]["dob"] else None, "patient_dob", x=L + 890)
    y += 90
    line(y, "Phone:", r["patient"]["phone"], None, xend=L + 620, size=44)
    line(y, "Allergies:", "NKDA", None, x=L + 650)
    y = section(y + 90, "MEDICATION ORDER")
    xx = p.t(L, y, "Drug name:", R(28)); p.hline(xx + 10, y + 34, L + 900)
    p.hand(xx + 30, y - 24, r["medication"]["drug"], 52, "drug")
    xx = p.t(L + 930, y, "Strength:", R(28)); p.hline(xx + 10, y + 34, Rr)
    hx = xx + 26
    if r["_wrong"]:
        hx = p.hand(hx, y - 24, r["_wrong"], 50, "_strike") + 12; p.strike_last()
    p.hand(hx, y - 24, strength_written(r, p.rng.random() < 0.4), 50, "strength")
    y += 96
    line(y, "Dosage form:", r["medication"]["form"], None, xend=L + 700)
    xx = p.t(L + 730, y, "Quantity:", R(28)); p.hline(xx + 10, y + 34, Rr)
    if r["quantity"] is not None:
        p.hand(xx + 40, y - 24, str(r["quantity"]), 52, "quantity")
    y += 96
    xx = p.t(L, y, "Directions (Sig):", R(28)); p.hline(xx + 10, y + 34, Rr); p.hline(L, y + 124, Rr)
    sig = r["sig_as_written"] if p.rng.random() < 0.65 else r["sig_normalized"]
    r["_sig_drawn"] = sig
    f = font(p.hf, int(48 * HAND[p.hf]))
    if f.getlength(sig) * 1.15 < Rr - xx - 40:
        p.hand(xx + 30, y - 24, sig, 48, "sig")
    else:
        words = sig.split(" "); k = len(words) * 3 // 5
        p.hand(xx + 30, y - 24, " ".join(words[:k]), 48, "sig"); p.hand(L + 20, y + 66, " ".join(words[k:]), 48, "sig")
    y += 200
    xx = p.t(L, y, "Refills (circle one):", R(28))
    opts = ["0", "1", "2", "3", "4", "5", "PRN"]
    ox = xx + 60
    for o in opts:
        b = d.textbbox((ox, y - 4), o, font=B(34)); d.text((ox, y - 4), o, font=B(34), fill=0)
        if r["refills"] is not None and o == str(r["refills"]):
            e = (b[0] - 22 + p.rng.randint(-4, 4), b[1] - 16 + p.rng.randint(-4, 4), b[2] + 22, b[3] + 16)
            d.ellipse(e, outline=p.ink, width=4); p.mark("refills", e)
        ox = b[2] + 86
    y = section(y + 90, "PRESCRIBER")
    xx = p.t(L, y, "Name (print):", R(28)); p.hline(xx + 10, y + 34, L + 860)
    p.t(xx + 30, y - 6, f'{pr["name"]}, {pr["credential"]}', B(32), "prescriber_name")
    xx = p.t(L + 890, y, "NPI:", R(28)); p.hline(xx + 10, y + 34, Rr)
    p.hand(xx + 30, y - 22, pr["npi"], 46, "npi")
    y += 130
    xx = p.t(L, y, "Signature:", R(28)); p.hline(xx + 10, y + 34, L + 900)
    p.signature(xx + 60, y - 50)
    p.t(L, 1780, "CONFIDENTIALITY NOTICE: This facsimile contains protected health information intended only for the", R(21))
    p.t(L, 1808, "addressee. If you are not the intended recipient, any disclosure or copying is prohibited. Please notify", R(21))
    p.t(L, 1836, "the sender by telephone and destroy this document.", R(21))
    p.chrome(pr["clinic"], pr["fax"])


def tpl_ltc(p):
    """Long-term care facility physician order sheet: typed resident label, handwritten order row."""
    r, d, pr, fac = p.rec, p.d, p.rec["prescriber"], p.rec["facility"]
    L, Rr = 100, 1600
    p.t(L, 110, fac["name"], B(44))
    p.t(L, 166, f'Tel {fac["phone"]}   Fax {fac["fax"]}', R(27))
    p.t(Rr, 110, "PHYSICIAN ORDER FORM", B(40), None, "ra")
    p.t(Rr, 164, f"Send to: {PHARMACY[0]}  {PHARMACY[1]}", R(25), None, "ra")
    d.rectangle((L, 230, Rr, 430), outline=0, width=3)
    xx = p.t(L + 20, 250, "RESIDENT: ", M(28)); p.t(xx, 246, r["patient"]["name"].upper(), font("MB", 36), "patient_name")
    xx = p.t(L + 20, 310, "DOB: ", M(28))
    dob = r["patient"]["dob"]
    if dob:
        p.t(xx, 308, dt.date.fromisoformat(dob).strftime("%m/%d/%Y"), font("MB", 32), "patient_dob")
    p.t(L + 520, 310, f'ROOM/BED: {fac["room"]}', M(28))
    p.t(L + 980, 310, f"MRN: {p.rng.randint(100000, 999999)}", M(28))
    p.t(L + 20, 370, "ALLERGIES: NKDA", M(28))
    xx = p.t(L + 520, 370, "ATTENDING: ", M(28))
    p.t(xx, 370, f'{pr["name"].upper()}, {pr["credential"]}', M(28), "prescriber_name")
    cols = [L, 290, 840, 1300, 1450, Rr]
    heads = ["Date", "Medication / strength / form", "Dose, route, frequency", "Qty", "Refills"]
    top, hh, rh, nrows = 480, 56, 210, 4
    d.rectangle((L, top, Rr, top + hh), fill=0)
    for i, h in enumerate(heads):
        d.text((cols[i] + 12, top + 13), h, font=B(26), fill=255)
    for k in range(nrows + 1):
        yy = top + hh + k * rh
        d.line((L, yy, Rr, yy), fill=0, width=2)
    for c in cols:
        d.line((c, top, c, top + hh + nrows * rh), fill=0, width=2)
    y = top + hh + 26
    p.hand(cols[0] + 12, y, r["_date_w"], 40, "date_written")
    p.hand(cols[1] + 14, y, r["medication"]["drug"], 46, "drug")
    hx = cols[1] + 14
    if r["_wrong"]:
        hx = p.hand(hx, y + 76, r["_wrong"], 46, "_strike") + 12; p.strike_last()
    hx = p.hand(hx, y + 76, strength_written(r, p.rng.random() < 0.4), 46, "strength")
    p.hand(hx + 14, y + 76, r["_fabbr"], 46)
    p.hand_wrap(cols[2] + 14, y, r["sig_as_written"], cols[3] - cols[2] - 24, 42, "sig", 60)
    if r["quantity"] is not None:
        p.hand(cols[3] + 24, y + 30, str(r["quantity"]), 48, "quantity")
    rw = refills_written(p)
    if rw:
        p.hand(cols[4] + 26, y + 30, rw, 46, "refills")
    yb = top + hh + nrows * rh + 60
    for i, lab in enumerate(["Telephone order", "Verbal order", "Written order"]):
        bx = L + i * 380
        d.rectangle((bx, yb, bx + 28, yb + 28), outline=0, width=2); p.t(bx + 42, yb - 2, lab, R(27))
    d.line((L + 760 + 4, yb + 4, L + 760 + 24, yb + 24), fill=p.ink, width=4); d.line((L + 760 + 24, yb + 4, L + 760 + 4, yb + 24), fill=p.ink, width=4)
    yb += 110
    xx = p.t(L, yb, "Noted by (nurse):", R(27)); p.hline(xx + 10, yb + 34, L + 820)
    p.hand(xx + 30, yb - 22, r["_nurse"], 44)
    yb += 120
    xx = p.t(L, yb, "Physician signature:", R(27)); p.hline(xx + 10, yb + 34, L + 900)
    p.signature(xx + 50, yb - 50)
    xx = p.t(L + 940, yb, "NPI:", R(27)); p.t(xx + 16, yb - 2, pr["npi"], font("MB", 30), "npi")
    p.t(L, 1830, "Orders must be signed by the attending physician within the period required by facility policy.", R(21))
    p.chrome(fac["name"], fac["fax"])


RENDER = {"pad": tpl_pad, "ehr": tpl_ehr, "faxform": tpl_faxform, "ltc": tpl_ltc}


# ----------------------------------------------------------------------------- damage
def smudge(img, b, frac, rng, kind="ink"):
    """Physically destroy part of a field (toner blot or scanner dropout) so it cannot be read."""
    x0, y0, x1, y1 = b
    w = x1 - x0
    sx0, sx1 = x0 + int(w * frac[0]) - 10, x0 + int(w * frac[1]) + 10
    lay = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((sx0, y0 - 6, sx1, y1 + 6), radius=14, fill=255)
    for _ in range(16):
        cx, cy = rng.uniform(sx0, sx1), rng.uniform(y0 - 8, y1 + 8)
        rx, ry = rng.uniform(16, 34), rng.uniform(12, 26)
        d.ellipse((cx - rx, cy - ry, cx + rx, cy + ry), fill=255)
    lay = lay.filter(ImageFilter.GaussianBlur(3))
    img.paste(0 if kind == "ink" else 255, (0, 0), lay)


TIERS = {
    "clean": dict(rot=0.6, scale=0.8, blur=0.7, noise=9, thr=(145, 175), speck=0.0008, streaks=(0, 0), drops=(0, 1), grad=6, post=0.7),
    "moderate": dict(rot=2.0, scale=0.5, blur=1.2, noise=18, thr=(140, 188), speck=0.004, streaks=(0, 2), drops=(1, 3), grad=18, post=1.5),
    "hard": dict(rot=3.2, scale=0.36, blur=1.7, noise=26, thr=(150, 198), speck=0.009, streaks=(1, 3), drops=(2, 5), grad=26, post=2.3),
}
BLUR = 1.0  # set by --blur; multiplies every blur radius


def degrade(img, boxes, tier, rng):
    """Simulate a fax trip: skew, resolution loss, blur, noise, 1-bit threshold, streaks, dropouts."""
    c = TIERS[tier]
    nrng = np.random.default_rng(rng.randint(0, 2**31))
    ang = rng.uniform(-c["rot"], c["rot"])
    tr = (rng.randint(-14, 14), rng.randint(-18, 18))
    geo = lambda im, fill, rs: im.rotate(ang, resample=rs, translate=tr, fillcolor=fill)
    im = geo(img, 255, Image.BICUBIC)
    if c["scale"] < 1:
        im = im.resize((int(W * c["scale"]), int(H * c["scale"])), Image.LANCZOS).resize((W, H), Image.BILINEAR)
    im = im.filter(ImageFilter.GaussianBlur(c["blur"] * BLUR))
    a = np.asarray(im, dtype=np.float32)
    a = a + nrng.normal(0, c["noise"], a.shape)
    a = a + np.linspace(-1, 1, W, dtype=np.float32)[None, :] * rng.uniform(-c["grad"], c["grad"])
    white = a > rng.uniform(*c["thr"])
    flip = nrng.random(white.shape) < c["speck"]
    white[flip] = ~white[flip]
    for _ in range(rng.randint(*c["streaks"])):  # dirty scanner glass: vertical black lines
        x = rng.randint(60, W - 60); white[:, x:x + rng.randint(1, 3)] = False
    for _ in range(rng.randint(*c["drops"])):  # lost scan lines: horizontal white gaps
        y = rng.randint(80, H - 80); white[y:y + rng.randint(1, 4), :] = True
    # re-blur after the 1-bit pass (a fax that was printed and scanned again), keep 16 grey levels
    out = Image.fromarray((white * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(c["post"] * BLUR))
    out = out.point(lambda v: (v // 17) * 17)
    newb = {}
    for k, b in boxes.items():
        m = Image.new("L", (W, H), 0)
        ImageDraw.Draw(m).rectangle(tuple(b), fill=255)
        bb = geo(m, 0, Image.NEAREST).getbbox()
        if bb:
            newb[k] = [max(0, bb[0] - 6), max(0, bb[1] - 6), min(W, bb[2] + 6), min(H, bb[3] + 6)]
    return out, newb


# ----------------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="dataset")
    ap.add_argument("--blur", type=float, default=1.0, help="blur multiplier; 1.5 is noticeably worse, 0.6 is closer to a clean fax")
    a = ap.parse_args()
    global BLUR
    BLUR = a.blur
    for sub in ("faxes", "clean"):
        os.makedirs(os.path.join(a.out, sub), exist_ok=True)
    truth = []
    for rec in build_records(a.n, a.seed):
        p = Page(rec)
        RENDER[rec["template"]](p)
        p.img.save(os.path.join(a.out, "clean", rec["id"] + ".png"), optimize=True)
        ch = rec["challenge"]
        if ch == "smudged_strength" and "strength" in p.boxes:
            smudge(p.img, p.boxes["strength"], (0.0, 0.62), p.rng, "ink" if rec["template"] != "faxform" else "dropout")
        elif ch == "smudged_dob" and "patient_dob" in p.boxes:
            smudge(p.img, p.boxes["patient_dob"], (0.25, 1.0), p.rng, "ink")
        elif ch == "smudged_drug" and "drug" in p.boxes:
            smudge(p.img, p.boxes["drug"], (0.36, 0.74), p.rng, "ink")
        fax, boxes = degrade(p.img, p.boxes, rec["tier"], p.rng)
        fax.save(os.path.join(a.out, "faxes", rec["id"] + ".png"), optimize=True)
        if rec["template"] == "faxform":
            rec["sig_as_written"] = rec.pop("_sig_drawn")
        elif rec["template"] == "ehr":
            rec["sig_as_written"] = rec["sig_normalized"]
        t = {k: v for k, v in rec.items() if not k.startswith("_")}
        t["file"] = f'faxes/{rec["id"]}.png'
        t["clean_file"] = f'clean/{rec["id"]}.png'
        t["boxes"] = {k: boxes[k] for k in FIELDS if k in boxes}
        truth.append(t)
    with open(os.path.join(a.out, "truth.json"), "w") as f:
        json.dump(truth, f, indent=1)
    with open(os.path.join(a.out, "truth.csv"), "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id", "file", "template", "tier", "patient_name", "patient_dob", "drug", "strength", "form",
                    "sig_as_written", "sig_normalized", "quantity", "refills", "prescriber_name", "npi",
                    "date_written", "signed", "challenge", "expected_flags", "unreadable_in_image"])
        for t in truth:
            w.writerow([t["id"], t["file"], t["template"], t["tier"], t["patient"]["name"], t["patient"]["dob"],
                        t["medication"]["drug"], t["medication"]["strength"], t["medication"]["form"],
                        t["sig_as_written"], t["sig_normalized"], t["quantity"], t["refills"],
                        t["prescriber"]["name"], t["prescriber"]["npi"], t["date_written"], t["signed"],
                        t["challenge"] or "", "|".join(t["expected_flags"]), "|".join(t["unreadable_in_image"])])
    print(f"wrote {len(truth)} prescriptions to {a.out}/")


if __name__ == "__main__":
    main()
