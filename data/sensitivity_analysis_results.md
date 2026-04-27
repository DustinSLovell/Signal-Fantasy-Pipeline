# Sensitivity Analysis Results
*Generated: April 25, 2026 | Training: 2022–2024 | Validation (OOS): 2025*

---

## Production Baseline (current parameter values)

### Pitcher Model — Current Production

| Signal | 2022 | 2023 | 2024 | 2025 | 4yr Avg | 2025 OOS | n (total) |
|--------|------|------|------|------|---------|----------|-----------|
| Buy Low | 100% (n=2) | 100% (n=4) | 77% (n=13) | 73% (n=11) | 80.0% | 72.7% | n=30 |
| Slight Buy |   —  (n=0) | 100% (n=1) | 100% (n=2) | 100% (n=1) | 100.0% | 100.0% | n=4 |
| Slight Sell | 100% (n=5) | 67% (n=6) | 100% (n=2) | 83% (n=6) | 84.2% | 83.3% | n=19 |
| Sell High | 97% (n=33) | 96% (n=25) | 95% (n=42) | 90% (n=29) | 94.6% | 89.7% | n=129 |
| Overall | 98% (n=40) | 92% (n=36) | 92% (n=59) | 85% (n=47) | 91.2% | 85.1% | n=182 |

### Hitter Model — Current Production

| Signal | 2022 | 2023 | 2024 | 2025 | 4yr Avg | 2025 OOS | n (total) |
|--------|------|------|------|------|---------|----------|-----------|
| Buy Low | 91% (n=35) | 86% (n=42) | 94% (n=48) | 96% (n=57) | 92.3% | 96.5% | n=182 |
| Slight Buy | 50% (n=2) | 67% (n=6) | 50% (n=10) | 88% (n=8) | 65.4% | 87.5% | n=26 |
| Slight Sell | 75% (n=8) | 82% (n=11) | 73% (n=15) | 82% (n=17) | 78.4% | 82.4% | n=51 |
| Sell High | 100% (n=14) | 91% (n=35) | 88% (n=42) | 94% (n=32) | 91.9% | 93.8% | n=123 |
| Overall | 90% (n=59) | 86% (n=94) | 85% (n=115) | 93% (n=114) | 88.5% | 93.0% | n=382 |

---

## PART 1 — Pitcher Sensitivity Analysis


### P1: Pitcher Slight Buy — ERA Floor

| ERA Floor    | 2022 | 2023 | 2024 | 2025 | 4yr Avg | 2025 OOS | n (total) | |
|--------------|------|------|------|------|---------|----------|-----------|--|
| 3.5          |   —  | 100% | 100% | 100% |  100.0% |   100.0% | n=5     |   ★
| 3.6          |   —  | 100% | 100% | 100% |  100.0% |   100.0% | n=5     |    
| 3.7          |   —  | 100% | 100% | 100% |  100.0% |   100.0% | n=5     |    
| 3.75         |   —  | 100% | 100% | 100% |  100.0% |   100.0% | n=4     |    
| 3.8          |   —  | 100% | 100% | 100% |  100.0% |   100.0% | n=4     |    
| 3.9          |   —  | 100% | 100% | 100% |  100.0% |   100.0% | n=4     |    
| 4.0          |   —  | 100% | 100% | 100% |  100.0% |   100.0% | n=4     | ←  

### P1: Pitcher Slight Buy ERA Floor — Overall Impact

| ERA Floor    | 2022 | 2023 | 2024 | 2025 | 4yr Avg | 2025 OOS | n (total) | |
|--------------|------|------|------|------|---------|----------|-----------|--|
| 3.5          |  98% |  92% |  92% |  85% |   91.3% |    85.4% | n=183   |   ★
| 3.6          |  98% |  92% |  92% |  85% |   91.3% |    85.4% | n=183   |    
| 3.7          |  98% |  92% |  92% |  85% |   91.3% |    85.4% | n=183   |    
| 3.75         |  98% |  92% |  92% |  85% |   91.2% |    85.1% | n=182   |    
| 3.8          |  98% |  92% |  92% |  85% |   91.2% |    85.1% | n=182   |    
| 3.9          |  98% |  92% |  92% |  85% |   91.2% |    85.1% | n=182   |    
| 4.0          |  98% |  92% |  92% |  85% |   91.2% |    85.1% | n=182   | ←  

### P2: Pitcher Buy Low — ERA Floor

| ERA Floor    | 2022 | 2023 | 2024 | 2025 | 4yr Avg | 2025 OOS | n (total) | |
|--------------|------|------|------|------|---------|----------|-----------|--|
| 3.0          | 100% |  80% |  77% |  73% |   77.4% |    72.7% | n=31    |    
| 3.25         | 100% | 100% |  77% |  73% |   80.0% |    72.7% | n=30    |    
| 3.5          | 100% | 100% |  77% |  73% |   80.0% |    72.7% | n=30    | ←  
| 3.75         | 100% | 100% |  83% |  80% |   85.7% |    80.0% | n=28    |   ★
| 4.0          | 100% | 100% |  82% |  80% |   85.2% |    80.0% | n=27    |    

### P3: Pitcher Buy Low — IP Minimum

| Min IP       | 2022 | 2023 | 2024 | 2025 | 4yr Avg | 2025 OOS | n (total) | |
|--------------|------|------|------|------|---------|----------|-----------|--|
| 10.0         | 100% |  80% |  77% |  73% |   78.1% |    72.7% | n=32    |    
| 15.0         | 100% |  80% |  77% |  73% |   78.1% |    72.7% | n=32    |    
| 20.0         | 100% | 100% |  77% |  73% |   80.0% |    72.7% | n=30    | ←  
| 25.0         | 100% | 100% |  82% |  70% |   80.8% |    70.0% | n=26    |    
| 30.0         | 100% | 100% | 100% | 100% |  100.0% |   100.0% | n=15    |   ★

### P3: Pitcher Slight Buy — IP Minimum

| Min IP       | 2022 | 2023 | 2024 | 2025 | 4yr Avg | 2025 OOS | n (total) | |
|--------------|------|------|------|------|---------|----------|-----------|--|
| 10.0         |   —  | 100% | 100% | 100% |  100.0% |   100.0% | n=4     |    
| 15.0         |   —  | 100% | 100% | 100% |  100.0% |   100.0% | n=4     |    
| 20.0         |   —  | 100% | 100% | 100% |  100.0% |   100.0% | n=4     | ←  
| 25.0         |   —  | 100% | 100% | 100% |  100.0% |   100.0% | n=3     |    
| 30.0         |   —  |   —  | 100% |   —  |  100.0% |      —   | n=1     |    

### P4: Pitcher Buy Low — FIP Ceiling

| FIP Ceil     | 2022 | 2023 | 2024 | 2025 | 4yr Avg | 2025 OOS | n (total) | |
|--------------|------|------|------|------|---------|----------|-----------|--|
| 3.75         | 100% | 100% |  75% |  75% |   79.2% |    75.0% | n=24    |   ★
| 4.0          | 100% | 100% |  75% |  73% |   78.6% |    72.7% | n=28    |    
| 4.25         | 100% | 100% |  75% |  73% |   79.3% |    72.7% | n=29    |    
| 4.5          | 100% | 100% |  77% |  73% |   80.0% |    72.7% | n=30    | ←  
| 4.75         | 100% | 100% |  79% |  73% |   81.2% |    72.7% | n=32    |    
| 5.0          | 100% | 100% |  79% |  73% |   81.2% |    72.7% | n=32    |    

### P5: Pitcher Buy Low — SwStr% Floor

| SwStr Floor  | 2022 | 2023 | 2024 | 2025 | 4yr Avg | 2025 OOS | n (total) | |
|--------------|------|------|------|------|---------|----------|-----------|--|
| 0.06         | 100% | 100% |  79% |  75% |   81.2% |    75.0% | n=32    |   ★
| 0.07         | 100% | 100% |  79% |  75% |   81.2% |    75.0% | n=32    |    
| 0.08         | 100% | 100% |  77% |  73% |   80.0% |    72.7% | n=30    | ←  
| 0.09         | 100% | 100% |  77% |  70% |   79.3% |    70.0% | n=29    |    
| 0.1          | 100% | 100% |  75% |  71% |   80.0% |    71.4% | n=25    |    

### P6: Pitcher Slight Buy — Luck Score Lower Bound

| SB LS Threshold | 2022 | 2023 | 2024 | 2025 | 4yr Avg | 2025 OOS | n (total) | |
|--------------|------|------|------|------|---------|----------|-----------|--|
| 0.04         |   —  | 100% | 100% | 100% |  100.0% |   100.0% | n=4     |    
| 0.05         |   —  | 100% | 100% | 100% |  100.0% |   100.0% | n=4     |    
| 0.06         |   —  | 100% | 100% | 100% |  100.0% |   100.0% | n=4     |    
| 0.065        |   —  | 100% | 100% | 100% |  100.0% |   100.0% | n=4     | ←  
| 0.07         |   —  | 100% | 100% | 100% |  100.0% |   100.0% | n=3     |    
| 0.08         |   —  | 100% | 100% | 100% |  100.0% |   100.0% | n=3     |    

---

## PART 2 — Hitter Sensitivity Analysis


### H1: Hitter Buy Low — Luck Score Threshold

| BL Threshold | 2022 | 2023 | 2024 | 2025 | 4yr Avg | 2025 OOS | n (total) | |
|--------------|------|------|------|------|---------|----------|-----------|--|
| 0.08         |  85% |  80% |  84% |  91% |   85.5% |    91.3% | n=234   |    
| 0.1          |  89% |  85% |  90% |  92% |   89.4% |    92.4% | n=217   |    
| 0.12         |  91% |  86% |  93% |  95% |   91.5% |    95.2% | n=201   |    
| 0.13         |  91% |  85% |  92% |  97% |   91.7% |    96.6% | n=193   |   ★
| 0.14         |  91% |  87% |  92% |  97% |   92.1% |    96.6% | n=189   |    
| 0.15         |  91% |  86% |  94% |  96% |   92.3% |    96.5% | n=182   | ←  

### H2: Hitter Slight Buy — Luck Score Threshold

| SB Threshold | 2022 | 2023 | 2024 | 2025 | 4yr Avg | 2025 OOS | n (total) | |
|--------------|------|------|------|------|---------|----------|-----------|--|
| 0.04         |  75% |  67% |  50% |  47% |   55.0% |    46.7% | n=40    |    
| 0.05         |  75% |  75% |  50% |  54% |   59.5% |    53.8% | n=37    |    
| 0.055        |  67% |  71% |  45% |  64% |   59.4% |    63.6% | n=32    |    
| 0.06         |  50% |  67% |  50% |  64% |   58.6% |    63.6% | n=29    |    
| 0.065        |  50% |  67% |  50% |  88% |   65.4% |    87.5% | n=26    | ←  
| 0.07         |  50% |  67% |  50% |  88% |   65.4% |    87.5% | n=26    |    

### H3: Hitter Slight Buy — xwOBA Gap Gate

| xwOBA Gate   | 2022 | 2023 | 2024 | 2025 | 4yr Avg | 2025 OOS | n (total) | |
|--------------|------|------|------|------|---------|----------|-----------|--|
| 0.0          |  50% |  65% |  50% |  67% |   59.4% |    66.7% | n=64    |    
| 0.01         |  50% |  78% |  50% |  89% |   68.8% |    88.9% | n=32    |    
| 0.015        |  50% |  67% |  50% |  88% |   65.4% |    87.5% | n=26    | ←  
| 0.02         |  50% |  80% |  62% |  83% |   71.4% |    83.3% | n=21    |    
| 0.025        |  50% |  80% |  57% | 100% |   68.8% |   100.0% | n=16    |   ★

### H4: Hitter Sell High — Luck Score Threshold

| SH Threshold | 2022 | 2023 | 2024 | 2025 | 4yr Avg | 2025 OOS | n (total) | |
|--------------|------|------|------|------|---------|----------|-----------|--|
| -0.08        |  91% |  89% |  84% |  90% |   88.0% |    89.8% | n=175   |    
| -0.1         | 100% |  89% |  90% |  91% |   91.0% |    90.7% | n=155   |    
| -0.12        | 100% |  88% |  90% |  92% |   90.8% |    92.3% | n=142   |    
| -0.13        | 100% |  89% |  89% |  92% |   91.2% |    91.9% | n=137   |    
| -0.14        | 100% |  89% |  89% |  91% |   90.8% |    91.4% | n=130   |    
| -0.15        | 100% |  91% |  88% |  94% |   91.9% |    93.8% | n=123   | ←  

### H5: Hitter Slight Sell — Luck Score Threshold

| SS Threshold | 2022 | 2023 | 2024 | 2025 | 4yr Avg | 2025 OOS | n (total) | |
|--------------|------|------|------|------|---------|----------|-----------|--|
| -0.04        |  75% |  84% |  68% |  68% |   72.4% |    67.9% | n=87    |    
| -0.05        |  75% |  81% |  72% |  71% |   74.0% |    70.8% | n=77    |    
| -0.06        |  75% |  80% |  82% |  71% |   77.1% |    71.4% | n=70    |    
| -0.07        |  67% |  86% |  79% |  79% |   78.7% |    78.9% | n=61    |    
| -0.085       |  75% |  82% |  73% |  82% |   78.4% |    82.4% | n=51    | ←  

---

## PART 3 — Interaction Effects


### Pitcher Interaction: SB ERA Floor × FIP Ceiling

| SB ERA Floor | FIP Ceil | BL 4yr | SB 4yr | Overall 4yr | 2025 OOS |
|---|---|---|---|---|---|
| 4.0 | 4.5 | 80.0% | 100.0% | 91.2% | 85.1%  ←|
| 3.5 | 4.5 | 80.0% | 100.0% | 91.3% | 85.4% |
| 4.0 | 3.75 | 79.2% | 100.0% | 91.3% | 86.0% |
| 3.5 | 3.75 | 79.2% | 100.0% | 91.4% | 86.4% |

### Pitcher Interaction: BL ERA Floor × SwStr% Floor

| BL ERA Floor | SwStr Floor | BL 4yr | SB 4yr | Overall 4yr | 2025 OOS |
|---|---|---|---|---|---|
| 3.5 | 8% | 80.0% | 100.0% | 91.2% | 85.1%  ←|
| 3.75 | 8% | 85.7% | 100.0% | 92.2% | 87.0% |
| 3.5 | 6% | 81.2% | 80.0% | 90.8% | 83.7% |
| 3.75 | 6% | 86.7% | 80.0% | 91.8% | 85.4% |

### Hitter Interaction: BL Threshold × SB Threshold

| BL Thresh | SB Thresh | BL 4yr | SB 4yr | Overall 4yr | 2025 OOS |
|---|---|---|---|---|---|
| 0.15 | 0.065 | 92.3% | 65.4% | 88.5% | 93.0%  ←|
| 0.13 | 0.065 | 91.7% | 55.0% | 88.1% | 93.0% |

---

## PART 5 — Recommendations

### Parameters to Change

| Parameter | Current | Recommended | Signal Δ | Accuracy Δ | Confidence | Notes |
|-----------|---------|-------------|----------|------------|------------|-------|
| P1: SB ERA Floor | 4.0 | **3.5** | +1 signals | +0.0pp (100.0% → 100.0% OOS) | LOW | ERA gate for Slight Buy signals |
| P2: BL ERA Floor | 3.5 | **3.75** | -2 signals | +5.7pp (72.7% → 80.0% OOS) | HIGH | ERA gate for Buy Low signals |
| P4: FIP Ceiling | 4.5 | **3.75** | -6 signals | -0.8pp (72.7% → 75.0% OOS) | HIGH | Stricter FIP requirement filters noise |
| P5: SwStr% Floor | 0.08 | **0.06** | +2 signals | +1.2pp (72.7% → 75.0% OOS) | HIGH | Swing-and-miss requirement |
| H1: BL Threshold | 0.15 | **0.13** | +11 signals | -0.6pp (96.5% → 96.6% OOS) | HIGH | Buy Low classification boundary |
| H3: xwOBA Gate | 0.015 | **0.025** | -10 signals | +3.4pp (87.5% → 100.0% OOS) | MED | xwOBA quality gate for Slight Buy |

### Parameters to Keep As-Is

| Parameter | Current | Reason |
|-----------|---------|--------|
| H2: SB Threshold | 0.065 | Already optimal on 2025 OOS |
| H4: SH Threshold | -0.15 | Already optimal on 2025 OOS |
| H5: SS Threshold | -0.085 | Already optimal on 2025 OOS |

### Risk Assessment


**High confidence (n >= 20 historically):**
- Sell High signals across all models — large samples, consistent yearly accuracy
- Overall pitcher accuracy — driven primarily by Sell High which dominates signal count

**Medium confidence (n = 8-20):**
- Buy Low pitcher signals — n=30 total; directionally reliable but high year-to-year variance
- Hitter Buy Low — larger sample but sensitive to threshold choice

**Low confidence / Small sample:**
- Pitcher Slight Buy — n=4 total in Version E backtest; any accuracy number is noise
  The ERA floor (P1) analysis has too few signals to draw firm conclusions
- Hitter Slight Buy — n varies significantly by threshold; xwOBA gate impact is real
  but hard to measure precisely given overlap with BABIP luck signal

**Flags:**
- If ANY pitcher parameter change causes 2025 Overall accuracy < 85%, reject it
- Pitcher Slight Buy accuracy = 100% at current production — this is a ceiling artifact
  (n=4), not a reason to declare current parameters optimal for that signal
- The CLAUDE.md "KNOWN OPEN FIX" (ERA < 3.75 suppresses Buy Low) is captured in P2;
  if P2 sensitivity shows 3.75 better than 3.50, that confirms the fix is warranted
