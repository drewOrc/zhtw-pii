# Test set v0 label audit

A manual check of the gold labels in `data/testset/v0/test.jsonl` (issue #4) on 30 of
its 300 rows. `make audit-sample` generated this file with every question
blank; every answer in it is written by hand.

- Test set SHA-256: `84025f8e7fd50c905258864c3a93349f565e17a75b208f98ad29f431656d69f6`
- Sample: 30 rows, seed 42, drawn as described at the end of this file

## How to answer

Each row shows its text, one question per labeled span, and a last question about
anything left unlabeled. Labeled characters are wrapped in ⟦ ⟧ inside the original
text, so a boundary that is one character off shows as a bracket in the wrong place.

- **Span**: `agree` if you would annotate exactly the characters inside ⟦ ⟧, no more
  and no fewer, with that label. Otherwise `disagree`, and write in the note what
  the span or label should be.
- **Unlabeled entities**: `yes` if the text holds a PERSON, ADDRESS, or ORG that is
  not inside ⟦ ⟧, and write it and its label in the note. Otherwise `no`.
- Labels: PERSON is a person's name, ADDRESS is an address, ORG is an
  organization's name. Format-defined identifiers such as ID or phone numbers are
  out of scope (`docs/adr/0002-exclude-format-defined-entities.md`).
- Judge each row the way you would annotate its text yourself, not by how the
  generator is known to build rows.
- Mark exactly one box per question by typing `x` between its brackets. A note is
  required after `disagree` or `yes` and optional otherwise; it may run several
  lines. Leave every other line as it is.

Record the verdict at the end once every question is answered. A PASS is what
freezes the test set (`docs/OPERATIONS.md`). `make audit-check`, which CI runs,
fails a PASS that leaves a question unanswered or a `disagree` or `yes` without a
note, and fails if any line other than a box mark or field text is edited.

---

## Row 1 of 30: hard_061

Tier `hard`, template `ad_01`, labeled spans: 1.

Text: `申請人邱先生`

### Span 1 of 1: PERSON, start=3, end=6

`申請人⟦邱先生⟧`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`申請人⟦邱先生⟧`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 2 of 30: medium_072

Tier `medium`, template `ad_03`, labeled spans: 2.

Text: `曾小的戶籍地址登記為台南市東區信義路3段87號特此公告`

### Span 1 of 2: PERSON, start=0, end=2

`⟦曾小⟧的戶籍地址登記為台南市東區信義路3段87號特此公告`

- [ ] agree
- [ ] disagree

Note:

### Span 2 of 2: ADDRESS, start=10, end=23

`曾小的戶籍地址登記為⟦台南市東區信義路3段87號⟧特此公告`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`⟦曾小⟧的戶籍地址登記為⟦台南市東區信義路3段87號⟧特此公告`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 3 of 30: medium_015

Tier `medium`, template `rc_01`, labeled spans: 2.

Text: `應徵者朱智投遞了集賢工作室的職缺`

### Span 1 of 2: PERSON, start=3, end=5

`應徵者⟦朱智⟧投遞了集賢工作室的職缺`

- [ ] agree
- [ ] disagree

Note:

### Span 2 of 2: ORG, start=8, end=13

`應徵者朱智投遞了⟦集賢工作室⟧的職缺`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`應徵者⟦朱智⟧投遞了⟦集賢工作室⟧的職缺`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 4 of 30: negative_012

Tier `negative`, template `neg_01`, labeled spans: 0.

Text: `訂單編號B596115163已出貨，預計2024年03月04日送達，金額NT$1,667。`

### Unlabeled entities

`訂單編號B596115163已出貨，預計2024年03月04日送達，金額NT$1,667。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 5 of 30: medium_055

Tier `medium`, template `rc_03`, labeled spans: 3.

Text: `昇陽診所人資部門將聯繫王淑安排面試，地點：基隆市仁愛區民生路１段２３１號。`

### Span 1 of 3: ORG, start=0, end=4

`⟦昇陽診所⟧人資部門將聯繫王淑安排面試，地點：基隆市仁愛區民生路１段２３１號。`

- [ ] agree
- [ ] disagree

Note:

### Span 2 of 3: PERSON, start=11, end=13

`昇陽診所人資部門將聯繫⟦王淑⟧安排面試，地點：基隆市仁愛區民生路１段２３１號。`

- [ ] agree
- [ ] disagree

Note:

### Span 3 of 3: ADDRESS, start=21, end=36

`昇陽診所人資部門將聯繫王淑安排面試，地點：⟦基隆市仁愛區民生路１段２３１號⟧。`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`⟦昇陽診所⟧人資部門將聯繫⟦王淑⟧安排面試，地點：⟦基隆市仁愛區民生路１段２３１號⟧。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 6 of 30: hard_029

Tier `hard`, template `cs_02`, labeled spans: 2.

Text: `客戶徐婷來電反映，居住地址為桃園市八德區，請盡快處理。`

### Span 1 of 2: PERSON, start=2, end=4

`客戶⟦徐婷⟧來電反映，居住地址為桃園市八德區，請盡快處理。`

- [ ] agree
- [ ] disagree

Note:

### Span 2 of 2: ADDRESS, start=14, end=20

`客戶徐婷來電反映，居住地址為⟦桃園市八德區⟧，請盡快處理。`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`客戶⟦徐婷⟧來電反映，居住地址為⟦桃園市八德區⟧，請盡快處理。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 7 of 30: negative_009

Tier `negative`, template `neg_01`, labeled spans: 0.

Text: `訂單編號F927142786已出貨，預計2024年08月10日送達，金額NT$60,831。`

### Unlabeled entities

`訂單編號F927142786已出貨，預計2024年08月10日送達，金額NT$60,831。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 8 of 30: medium_031

Tier `medium`, template `md_02`, labeled spans: 2.

Text: `張女士的聯絡地址為新北市新莊區建國街３段５６號，看診科別為家醫科。`

### Span 1 of 2: PERSON, start=0, end=3

`⟦張女士⟧的聯絡地址為新北市新莊區建國街３段５６號，看診科別為家醫科。`

- [ ] agree
- [ ] disagree

Note:

### Span 2 of 2: ADDRESS, start=9, end=23

`張女士的聯絡地址為⟦新北市新莊區建國街３段５６號⟧，看診科別為家醫科。`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`⟦張女士⟧的聯絡地址為⟦新北市新莊區建國街３段５６號⟧，看診科別為家醫科。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 9 of 30: medium_081

Tier `medium`, template `rc_03`, labeled spans: 3.

Text: `昇陽事務所人資部門將聯繫宋女士安排面試，地點：台中市南屯區中山街1段269號。`

### Span 1 of 3: ORG, start=0, end=5

`⟦昇陽事務所⟧人資部門將聯繫宋女士安排面試，地點：台中市南屯區中山街1段269號。`

- [ ] agree
- [ ] disagree

Note:

### Span 2 of 3: PERSON, start=12, end=15

`昇陽事務所人資部門將聯繫⟦宋女士⟧安排面試，地點：台中市南屯區中山街1段269號。`

- [ ] agree
- [ ] disagree

Note:

### Span 3 of 3: ADDRESS, start=23, end=38

`昇陽事務所人資部門將聯繫宋女士安排面試，地點：⟦台中市南屯區中山街1段269號⟧。`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`⟦昇陽事務所⟧人資部門將聯繫⟦宋女士⟧安排面試，地點：⟦台中市南屯區中山街1段269號⟧。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 10 of 30: medium_029

Tier `medium`, template `fi_02`, labeled spans: 3.

Text: `華夏基金會已將款項匯至歐小姐的帳戶地址核對為桃園市八德區仁愛路3段107號`

### Span 1 of 3: ORG, start=0, end=5

`⟦華夏基金會⟧已將款項匯至歐小姐的帳戶地址核對為桃園市八德區仁愛路3段107號`

- [ ] agree
- [ ] disagree

Note:

### Span 2 of 3: PERSON, start=11, end=14

`華夏基金會已將款項匯至⟦歐小姐⟧的帳戶地址核對為桃園市八德區仁愛路3段107號`

- [ ] agree
- [ ] disagree

Note:

### Span 3 of 3: ADDRESS, start=22, end=37

`華夏基金會已將款項匯至歐小姐的帳戶地址核對為⟦桃園市八德區仁愛路3段107號⟧`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`⟦華夏基金會⟧已將款項匯至⟦歐小姐⟧的帳戶地址核對為⟦桃園市八德區仁愛路3段107號⟧`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 11 of 30: negative_022

Tier `negative`, template `neg_03`, labeled spans: 0.

Text: `產品編號P6761-C，庫存數量289件，到貨日2024年08月18日。`

### Unlabeled entities

`產品編號P6761-C，庫存數量289件，到貨日2024年08月18日。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 12 of 30: hard_037

Tier `hard`, template `ad_02`, labeled spans: 2.

Text: `本案由集賢有限公司承辦聯絡人為莊翊品`

### Span 1 of 2: ORG, start=3, end=9

`本案由⟦集賢有限公司⟧承辦聯絡人為莊翊品`

- [ ] agree
- [ ] disagree

Note:

### Span 2 of 2: PERSON, start=15, end=18

`本案由集賢有限公司承辦聯絡人為⟦莊翊品⟧`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`本案由⟦集賢有限公司⟧承辦聯絡人為⟦莊翊品⟧`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 13 of 30: easy_049

Tier `easy`, template `md_01`, labeled spans: 1.

Text: `病患蕭筠預約於明日回診。`

### Span 1 of 1: PERSON, start=2, end=4

`病患⟦蕭筠⟧預約於明日回診。`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`病患⟦蕭筠⟧預約於明日回診。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 14 of 30: hard_009

Tier `hard`, template `cs_03`, labeled spans: 3.

Text: `賴小姐的包裹已送達台中市北屯區復興街２段２５１號如有疑問請聯繫廣益事務所客服`

### Span 1 of 3: PERSON, start=0, end=3

`⟦賴小姐⟧的包裹已送達台中市北屯區復興街２段２５１號如有疑問請聯繫廣益事務所客服`

- [ ] agree
- [ ] disagree

Note:

### Span 2 of 3: ADDRESS, start=9, end=24

`賴小姐的包裹已送達⟦台中市北屯區復興街２段２５１號⟧如有疑問請聯繫廣益事務所客服`

- [ ] agree
- [ ] disagree

Note:

### Span 3 of 3: ORG, start=31, end=36

`賴小姐的包裹已送達台中市北屯區復興街２段２５１號如有疑問請聯繫⟦廣益事務所⟧客服`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`⟦賴小姐⟧的包裹已送達⟦台中市北屯區復興街２段２５１號⟧如有疑問請聯繫⟦廣益事務所⟧客服`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 15 of 30: medium_099

Tier `medium`, template `rc_03`, labeled spans: 3.

Text: `華夏事務所人資部門將聯繫蘇淑安排面試，地點：台中市南屯區中正路3段215號。`

### Span 1 of 3: ORG, start=0, end=5

`⟦華夏事務所⟧人資部門將聯繫蘇淑安排面試，地點：台中市南屯區中正路3段215號。`

- [ ] agree
- [ ] disagree

Note:

### Span 2 of 3: PERSON, start=12, end=14

`華夏事務所人資部門將聯繫⟦蘇淑⟧安排面試，地點：台中市南屯區中正路3段215號。`

- [ ] agree
- [ ] disagree

Note:

### Span 3 of 3: ADDRESS, start=22, end=37

`華夏事務所人資部門將聯繫蘇淑安排面試，地點：⟦台中市南屯區中正路3段215號⟧。`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`⟦華夏事務所⟧人資部門將聯繫⟦蘇淑⟧安排面試，地點：⟦台中市南屯區中正路3段215號⟧。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 16 of 30: easy_011

Tier `easy`, template `fi_03`, labeled spans: 1.

Text: `本月請款單位：集賢工作室。`

### Span 1 of 1: ORG, start=7, end=12

`本月請款單位：⟦集賢工作室⟧。`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`本月請款單位：⟦集賢工作室⟧。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 17 of 30: hard_039

Tier `hard`, template `rc_03`, labeled spans: 3.

Text: `啟明診所人資部門將聯繫劉玲安排面試地點新北市三重區`

### Span 1 of 3: ORG, start=0, end=4

`⟦啟明診所⟧人資部門將聯繫劉玲安排面試地點新北市三重區`

- [ ] agree
- [ ] disagree

Note:

### Span 2 of 3: PERSON, start=11, end=13

`啟明診所人資部門將聯繫⟦劉玲⟧安排面試地點新北市三重區`

- [ ] agree
- [ ] disagree

Note:

### Span 3 of 3: ADDRESS, start=19, end=25

`啟明診所人資部門將聯繫劉玲安排面試地點⟦新北市三重區⟧`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`⟦啟明診所⟧人資部門將聯繫⟦劉玲⟧安排面試地點⟦新北市三重區⟧`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 18 of 30: easy_028

Tier `easy`, template `fi_03`, labeled spans: 1.

Text: `本月請款單位：協和股份有限公司。`

### Span 1 of 1: ORG, start=7, end=15

`本月請款單位：⟦協和股份有限公司⟧。`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`本月請款單位：⟦協和股份有限公司⟧。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 19 of 30: easy_022

Tier `easy`, template `cs_01`, labeled spans: 1.

Text: `您好，我是葉睿，想詢問訂單狀態。`

### Span 1 of 1: PERSON, start=5, end=7

`您好，我是⟦葉睿⟧，想詢問訂單狀態。`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`您好，我是⟦葉睿⟧，想詢問訂單狀態。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 20 of 30: negative_030

Tier `negative`, template `neg_01`, labeled spans: 0.

Text: `訂單編號F579565240已出貨，預計2024年05月07日送達，金額NT$32,807。`

### Unlabeled entities

`訂單編號F579565240已出貨，預計2024年05月07日送達，金額NT$32,807。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 21 of 30: easy_041

Tier `easy`, template `md_01`, labeled spans: 1.

Text: `病患黃佳雅預約於明日回診。`

### Span 1 of 1: PERSON, start=2, end=5

`病患⟦黃佳雅⟧預約於明日回診。`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`病患⟦黃佳雅⟧預約於明日回診。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 22 of 30: hard_020

Tier `hard`, template `fi_01`, labeled spans: 1.

Text: `匯款人賴先生請確認收款帳戶無誤`

### Span 1 of 1: PERSON, start=3, end=6

`匯款人⟦賴先生⟧請確認收款帳戶無誤`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`匯款人⟦賴先生⟧請確認收款帳戶無誤`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 23 of 30: easy_023

Tier `easy`, template `ad_01`, labeled spans: 1.

Text: `申請人：曹雅恩。`

### Span 1 of 1: PERSON, start=4, end=7

`申請人：⟦曹雅恩⟧。`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`申請人：⟦曹雅恩⟧。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 24 of 30: medium_004

Tier `medium`, template `cs_03`, labeled spans: 3.

Text: `郭承承小姐的包裹已送達新竹市北區羅斯福路3段51號，如有疑問請聯繫華夏基金會客服。`

### Span 1 of 3: PERSON, start=0, end=5

`⟦郭承承小姐⟧的包裹已送達新竹市北區羅斯福路3段51號，如有疑問請聯繫華夏基金會客服。`

- [ ] agree
- [ ] disagree

Note:

### Span 2 of 3: ADDRESS, start=11, end=25

`郭承承小姐的包裹已送達⟦新竹市北區羅斯福路3段51號⟧，如有疑問請聯繫華夏基金會客服。`

- [ ] agree
- [ ] disagree

Note:

### Span 3 of 3: ORG, start=33, end=38

`郭承承小姐的包裹已送達新竹市北區羅斯福路3段51號，如有疑問請聯繫⟦華夏基金會⟧客服。`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`⟦郭承承小姐⟧的包裹已送達⟦新竹市北區羅斯福路3段51號⟧，如有疑問請聯繫⟦華夏基金會⟧客服。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 25 of 30: easy_009

Tier `easy`, template `rc_02`, labeled spans: 1.

Text: `姓名：彭靜。`

### Span 1 of 1: PERSON, start=3, end=5

`姓名：⟦彭靜⟧。`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`姓名：⟦彭靜⟧。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 26 of 30: medium_025

Tier `medium`, template `cs_02`, labeled spans: 2.

Text: `客戶曾先生來電反映居住地址為基隆市仁愛區羅斯福街３段１１４號請盡快處理`

### Span 1 of 2: PERSON, start=2, end=5

`客戶⟦曾先生⟧來電反映居住地址為基隆市仁愛區羅斯福街３段１１４號請盡快處理`

- [ ] agree
- [ ] disagree

Note:

### Span 2 of 2: ADDRESS, start=14, end=30

`客戶曾先生來電反映居住地址為⟦基隆市仁愛區羅斯福街３段１１４號⟧請盡快處理`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`客戶⟦曾先生⟧來電反映居住地址為⟦基隆市仁愛區羅斯福街３段１１４號⟧請盡快處理`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 27 of 30: hard_010

Tier `hard`, template `cs_03`, labeled spans: 3.

Text: `鄭芸先生的包裹已送達新北市板橋區如有疑問請聯繫誠信事務所客服`

### Span 1 of 3: PERSON, start=0, end=4

`⟦鄭芸先生⟧的包裹已送達新北市板橋區如有疑問請聯繫誠信事務所客服`

- [ ] agree
- [ ] disagree

Note:

### Span 2 of 3: ADDRESS, start=10, end=16

`鄭芸先生的包裹已送達⟦新北市板橋區⟧如有疑問請聯繫誠信事務所客服`

- [ ] agree
- [ ] disagree

Note:

### Span 3 of 3: ORG, start=23, end=28

`鄭芸先生的包裹已送達新北市板橋區如有疑問請聯繫⟦誠信事務所⟧客服`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`⟦鄭芸先生⟧的包裹已送達⟦新北市板橋區⟧如有疑問請聯繫⟦誠信事務所⟧客服`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 28 of 30: hard_004

Tier `hard`, template `cs_03`, labeled spans: 3.

Text: `彭昀的包裹已送達台中市北屯區仁愛街３段４１號，如有疑問請聯繫廣益協會客服。`

### Span 1 of 3: PERSON, start=0, end=2

`⟦彭昀⟧的包裹已送達台中市北屯區仁愛街３段４１號，如有疑問請聯繫廣益協會客服。`

- [ ] agree
- [ ] disagree

Note:

### Span 2 of 3: ADDRESS, start=8, end=22

`彭昀的包裹已送達⟦台中市北屯區仁愛街３段４１號⟧，如有疑問請聯繫廣益協會客服。`

- [ ] agree
- [ ] disagree

Note:

### Span 3 of 3: ORG, start=30, end=34

`彭昀的包裹已送達台中市北屯區仁愛街３段４１號，如有疑問請聯繫⟦廣益協會⟧客服。`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`⟦彭昀⟧的包裹已送達⟦台中市北屯區仁愛街３段４１號⟧，如有疑問請聯繫⟦廣益協會⟧客服。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 29 of 30: negative_046

Tier `negative`, template `neg_02`, labeled spans: 0.

Text: `本次活動日期為2026年08月19日，報名人數上限312人，費用NT$62,103。`

### Unlabeled entities

`本次活動日期為2026年08月19日，報名人數上限312人，費用NT$62,103。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Row 30 of 30: medium_007

Tier `medium`, template `fi_02`, labeled spans: 3.

Text: `匯通工作室已將款項匯至沈承豪的帳戶，地址核對為台北市士林區和平街１段４７號。`

### Span 1 of 3: ORG, start=0, end=5

`⟦匯通工作室⟧已將款項匯至沈承豪的帳戶，地址核對為台北市士林區和平街１段４７號。`

- [ ] agree
- [ ] disagree

Note:

### Span 2 of 3: PERSON, start=11, end=14

`匯通工作室已將款項匯至⟦沈承豪⟧的帳戶，地址核對為台北市士林區和平街１段４７號。`

- [ ] agree
- [ ] disagree

Note:

### Span 3 of 3: ADDRESS, start=23, end=37

`匯通工作室已將款項匯至沈承豪的帳戶，地址核對為⟦台北市士林區和平街１段４７號⟧。`

- [ ] agree
- [ ] disagree

Note:

### Unlabeled entities

`⟦匯通工作室⟧已將款項匯至⟦沈承豪⟧的帳戶，地址核對為⟦台北市士林區和平街１段４７號⟧。`

Is there a PERSON, ADDRESS, or ORG in the text that is not inside ⟦ ⟧?

- [ ] no
- [ ] yes

Note:

---

## Verdict

Record this once every question above is answered. In the summary, describe any
pattern across the `disagree` and `yes` answers, or say there were none.

- [ ] PASS: no systematic labeling error; freeze the test set as it is
- [ ] FAIL: systematic labeling error found; fix and regenerate before freezing

Reviewer:

Date (YYYY-MM-DD):

Summary:

---

## How the sample was drawn

This audit looks for systematic labeling errors. An error tied to one template, one
surface form of an entity, or one noise transform repeats on every row that shares
it, so the draw makes sure each of those appears at least once. It is not an error
rate estimate. Zero errors in 30 rows would still allow a rate as high as 9.5%
(one-sided 95 percent upper bound), and the draw is not uniform, so do not quote an
error rate from this file.

Each row belongs to a few cells: its tier, its template, the form of each labeled
span, and, for rows with spans, whether punctuation was removed (the text has no
`。`, which every template ends with). Using `random.Random(42)`, cells are
visited from fewest rows to most, and each cell that no chosen row covers yet gets
one row drawn uniformly from its unchosen rows. The remaining slots are drawn
uniformly from all unchosen rows, and the chosen rows are shuffled into the order
above. `make audit-check` repeats the draw and fails if the rows above differ.

| Cell | Rows in test set | Rows in this sample |
|---|---|---|
| ADDRESS: city and district only | 22 | 3 |
| ADDRESS: street, ASCII digits | 50 | 5 |
| ADDRESS: street, fullwidth digits | 44 | 6 |
| ORG | 99 | 14 |
| PERSON: 2-character name | 89 | 10 |
| PERSON: 3-character name | 68 | 4 |
| PERSON: full name + honorific | 21 | 2 |
| PERSON: surname + honorific | 60 | 7 |
| template: ad_01 | 19 | 2 |
| template: ad_02 | 12 | 1 |
| template: ad_03 | 16 | 1 |
| template: cs_01 | 17 | 1 |
| template: cs_02 | 21 | 2 |
| template: cs_03 | 20 | 4 |
| template: fi_01 | 22 | 1 |
| template: fi_02 | 20 | 2 |
| template: fi_03 | 12 | 2 |
| template: md_01 | 21 | 2 |
| template: md_02 | 17 | 1 |
| template: neg_01 | 16 | 3 |
| template: neg_02 | 18 | 1 |
| template: neg_03 | 16 | 1 |
| template: rc_01 | 13 | 1 |
| template: rc_02 | 18 | 1 |
| template: rc_03 | 22 | 4 |
| text: punctuation removed | 98 | 10 |
| tier: easy | 80 | 7 |
| tier: hard | 70 | 8 |
| tier: medium | 100 | 10 |
| tier: negative | 50 | 5 |
