# Synthetic faxed prescriptions

40 invented prescriptions rendered as fax images, with exact ground truth. Nothing here is real:
patients, prescribers, clinics and phone numbers are made up, and every page is stamped
"SYNTHETIC TEST DATA - NOT A VALID PRESCRIPTION". No controlled substances are included.

## Contents

| Path | What it is |
|---|---|
| `faxes/rx_NNN.png` | The degraded fax image (1700x2200, 16 grey levels, blurred after the 1-bit pass like a fax that was printed and rescanned). Feed these to your pipeline. |
| `clean/rx_NNN.png` | The same page before the fax trip, for debugging and for side-by-side demos. |
| `truth.json` | Full ground truth per prescription, including field bounding boxes on the fax image. |
| `truth.csv` | The same values flattened, for a quick look in a spreadsheet. |
| `generate.py` | The generator. `python3 generate.py --n 40 --seed 7 --out dataset`. Add `--blur 1.5` for blurrier, `--blur 0.6` for sharper. |
| `score.py` | Scores your predictions. `python3 score.py truth.json predictions.json` |
| `fonts/` | Open-licensed handwriting fonts the generator needs. |

## Templates (10 of each)

- `pad`: classic prescription pad, everything filled in by hand.
- `ehr`: typed EHR printout that was faxed. Tests blur and skew, not handwriting.
- `faxform`: clinic fax order form with typed labels, handwritten fills and circled refills.
- `ltc`: long-term care physician order sheet with a typed resident label and a handwritten order row.

## Fax quality tiers

- `clean` (12): light blur and noise, almost no skew.
- `moderate` (16): half resolution, clear blur, up to 2 degrees of skew, speckle, streaks.
- `hard` (12): about 70 dpi effective, heavy blur, up to 3.2 degrees of skew, streaks and lost scan lines.

## Planted problems (20 of the 40)

`challenge` names the problem and `expected_flags` lists the fields a safe system should send to
a pharmacist instead of accepting.

| Challenge | Count | Should flag |
|---|---|---|
| `smudged_strength`, `smudged_dob`, `smudged_drug` | 5 | the obscured field (it cannot be read from the image) |
| `missing_quantity`, `missing_refills`, `missing_dob`, `missing_signature` | 6 | the blank field |
| `dose_out_of_range`, `dose_unit_error` | 3 | strength (for example metformin 5000 mg, levothyroxine 25 mg) |
| `frequency_error` | 1 | sig (methotrexate written as daily) |
| `correction` | 2 | strength (one value crossed out, another written) |
| `lookalike_risk` | 3 | nothing required; the name is legible but easily confused |

For clinical-error cases the truth records what is written on the page, not what the prescriber
probably meant. For smudged cases the truth holds the original value and `unreadable_in_image`
lists the field, so a confident answer there counts as a guess even if it happens to be right.

## Limits

- Handwriting comes from fonts with per-word jitter, so it is tidier than real prescriber handwriting.
- One medication per page.
- NPIs are random but pass the NPI check-digit test, so you can demo checksum validation. They are not
  assigned to these fictional prescribers.
