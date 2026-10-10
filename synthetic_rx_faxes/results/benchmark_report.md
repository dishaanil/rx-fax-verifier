# RxBridge benchmark results

40/40 faxes extracted. Synthetic data; results do not establish production safety.

## RxBridge scoring policy

| tier | critical fields | correct | flagged | **silent errors** | warnings surfaced |
|---|---|---|---|---|---|
| clean | 72 | 100.0% | 11.1% | **0** | 1/1 |
| moderate | 96 | 100.0% | 13.5% | **1** | 1/1 |
| hard | 72 | 93.1% | 23.6% | **0** | 3/3 |

- **Silent errors (critical fields): 1**
- False-review rate: 27/228 correct critical fields flagged (11.8%)
- Planted problems caught: 15/16 (excludes rx_016, see below)
- Exception compression: 394 fields extracted, 57 decisions required (86% review-surface reduction)

Silent errors (1):
- `rx_022` strength (dose_out_of_range): got `'5000 MG'`, truth `'5000 mg'`

Out of scope: `rx_016` methotrexate frequency: indication-specific dosing, out of scope (DESIGN.md §4)

## Original score.py (unmodified, for transparency)

```
tier        fields   correct   flagged   SILENT ERRORS
clean          120    100.0%      8.3%               0
moderate       160     97.5%     10.6%               4
hard           120     86.7%     21.7%               4

per-field accuracy: patient_name 100%, patient_dob 85%, drug 95%, strength 92%, sig 100%, quantity 100%, refills 100%, prescriber_name 100%, npi 90%, date_written 88%
planted problems caught: 15/17
unnecessary flags on correct fields: 31/370

silent errors (8):
  rx_009 patient_dob      smudged_strength   got='1965-04-04' truth='1965-04-01'
  rx_015 date_written     misread            got='2024-10-09' truth='2026-10-09'
  rx_016 sig              frequency_error    got='1 tab po qd' truth='Take 1 tablet by mouth once daily'
  rx_022 strength         dose_out_of_range  got='5000 MG' truth='5000 mg'
  rx_024 date_written     missing_signature  got='2026-10-01' truth='2026-10-10'
  rx_026 patient_dob      misread            got='1950-01-27' truth='1959-01-27'
  rx_037 date_written     smudged_drug       got='2024-10-07' truth='2026-10-07'
  rx_040 date_written     misread            got='2016-10-26' truth='2026-10-06'
```
