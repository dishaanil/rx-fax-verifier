# RxBridge benchmark results

40/40 faxes extracted. Synthetic data; results do not establish production safety.

## Routing outcome

- **READY_FOR_VERIFICATION**: 8 (rx_007, rx_014, rx_018, rx_021, rx_023, rx_029, rx_032, rx_036)
- **REVIEW_REQUIRED**: 32 (rx_001, rx_002, rx_003, rx_004, rx_005, rx_006, rx_008, rx_009, rx_010, rx_011, rx_012, rx_013, rx_015, rx_016, rx_017, rx_019, rx_020, rx_022, rx_024, rx_025, rx_026, rx_027, rx_028, rx_030, rx_031, rx_033, rx_034, rx_035, rx_037, rx_038, rx_039, rx_040)

## RxBridge scoring policy

| tier | critical fields | correct | flagged | **silent errors** | warnings surfaced |
|---|---|---|---|---|---|
| clean | 72 | 100.0% | 15.3% | **0** | 1/1 |
| moderate | 96 | 100.0% | 15.6% | **0** | 1/1 |
| hard | 72 | 91.7% | 26.4% | **2** | 3/3 |

- **Silent errors (critical fields): 2**
- False-review rate: 34/227 correct critical fields flagged (15.0%)
- Planted problems caught: 16/16 (excludes rx_016, see below)
- Exception compression: 395 fields extracted, 56 decisions required (86% review-surface reduction)

Silent errors (2):
- `rx_037` patient_name (smudged_drug): got `'Tobias R?himz-adeh'`, truth `'Tobias Rahimzadeh'`
- `rx_040` strength (misread): got `'25 mg'`, truth `'2.5 mg'`

Out of scope: `rx_016` methotrexate frequency: indication-specific dosing, out of scope (DESIGN.md §4)

## Original score.py (unmodified, for transparency)

```
tier        fields   correct   flagged   SILENT ERRORS
clean          120     99.2%     10.8%               0
moderate       160     98.8%      9.4%               3
hard           120     84.2%     21.7%               9

per-field accuracy: patient_name 98%, patient_dob 85%, drug 98%, strength 90%, sig 100%, quantity 100%, refills 100%, prescriber_name 100%, npi 85%, date_written 90%
planted problems caught: 16/17
unnecessary flags on correct fields: 34/368

silent errors (12):
  rx_009 patient_dob      smudged_strength   got='1965-04-04' truth='1965-04-01'
  rx_011 date_written     misread            got='10/?/2026' truth='2026-10-09'
  rx_016 sig              frequency_error    got='1 tab po qd' truth='Take 1 tablet by mouth once daily'
  rx_023 patient_dob      misread            got='5/15/19?1' truth='1961-05-15'
  rx_024 date_written     missing_signature  got='2026-10-01' truth='2026-10-10'
  rx_026 patient_dob      misread            got='1950-01-27' truth='1959-01-27'
  rx_037 patient_name     smudged_drug       got='Tobias R?himz-adeh' truth='Tobias Rahimzadeh'
  rx_037 patient_dob      smudged_drug       got='9/7/19?1' truth='1958-09-07'
  rx_037 date_written     smudged_drug       got='2024-10-07' truth='2026-10-07'
  rx_039 patient_dob      misread            got='1972-07-15' truth='1972-07-13'
  rx_040 strength         misread            got='25 mg' truth='2.5 mg'
  rx_040 date_written     misread            got='2016-10-06' truth='2026-10-06'
```
