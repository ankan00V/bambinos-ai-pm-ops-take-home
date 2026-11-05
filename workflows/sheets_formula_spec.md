# Google Sheets version

For an ops team that wants this running before engineering ships anything. It mirrors the engine's decisions except for one rule, stated at the end. Built in about 40 minutes on a copy of the four tables.

## Sheet layout

Create a spreadsheet with six tabs:

1. `invoices` (paste CSV, row 1 headers)
2. `forms` (paste CSV)
3. `bookings` (paste CSV)
4. `reference` (paste CSV)
5. `recon` (the working tab, one row per form)
6. `dashboard` (counts)

## Step 1: helper columns on `forms`

Put these in columns X onward. Row 2 is the first data row, and each formula is dragged down.

| Cell | Header | Formula |
| --- | --- | --- |
| X1 | clean_ref | `=IFERROR(REGEXEXTRACT(TO_TEXT($K2), "\d+$"), "")` |
| Y1 | phone_norm | `=REGEXREPLACE(REGEXREPLACE(TO_TEXT($G2), "[^0-9X]", ""), "^91", "")` |
| Z1 | invoice_row | `=IFERROR(MATCH($K2, invoices!$A:$A, 0), IFERROR(MATCH($X2, invoices!$A:$A, 0), ""))` |
| AA1 | inv_status | `=IF($Z2="", "unmatched", INDEX(invoices!$U:$U, $Z2))` |
| AB1 | inv_net | `=IF($Z2="", 0, INDEX(invoices!$N:$N, $Z2))` |
| AC1 | inv_gross | `=IF($Z2="", 0, INDEX(invoices!$L:$L, $Z2))` |
| AD1 | inv_discount | `=IF($Z2="", 0, INDEX(invoices!$M:$M, $Z2))` |
| AE1 | inv_type | `=IF($Z2="", "", INDEX(invoices!$O:$O, $Z2))` |
| AF1 | ref_row | `=IFERROR(MATCH($D2, reference!$A:$A, 0), "")` |
| AG1 | seat_used | `=IF($AF2="", 0, INDEX(reference!$R:$R, $AF2))` |
| AH1 | seat_max | `=IF($AF2="", 0, INDEX(reference!$S:$S, $AF2))` |
| AI1 | seats_left | `=$AH2-$AG2` |
| AJ1 | invoice_qty | `=COUNTIF(forms!$K:$K, $K2)` |
| AK1 | first_form | `=MINIFS(forms!$T:$T, forms!$K:$K, $K2)` |
| AL1 | is_duplicate | `=IF(AND($AJ2>1, $T2>$AK2), "Yes", "No")` |

`MATCH` on the raw `invoice_id` covers the exact case and the link case, because the link ends in the same number. The typo case falls through to the fuzzy rule in step 3.

## Step 2: the decision column

Put this in `AM2` and drag down. It reads top to bottom, first match wins, which is exactly how the Python engine orders its rules.

```
=IFS(
 $AL2="Yes","R04 duplicate form",
 $Z2="","R02 invoice not found",
 NOT(OR($AA2="Paid",$AA2="Partially_Paid")),"R07 payment not settled",
 OR($AE2<>"Full", $AB2+MAX(1,$AC2*0.005) < $AC2-$AD2),"R06 part payment",
 ABS($J2-$AB2)>1,"R05 amount mismatch",
 $AF2="","R10 student not in reference",
 $Q2<>INDEX(invoices!$F:$F,$Z2),"R11 student mismatch",
 AND(REGEXREPLACE(TO_TEXT($G2),"[^0-9X]","")<>REGEXREPLACE(TO_TEXT(INDEX(invoices!$I:$I,$Z2)),"[^0-9X]",""), REGEXREPLACE(TO_TEXT(INDEX(invoices!$H:$I,$Z2,1)),"[^0-9X]",""))=FALSE,"R12 payer contact",
 $P2="No","R09 batch change",
 $AI2<=0,"R08 batch full",
 $N2<=0,"R16 no sessions",
 $U2="Approved","R17 already processed",
 TRUE,"R00 ready"
)
```

The `R12` test compares the form's `parent_mobile` against the invoice `mobile` after stripping punctuation. In the current data it fires for form 3304, which is the right answer: the form carries the number that appears on the parent record, not the number the payment came from.

## Step 3: the typo repair

The engine uses edit distance, which Sheets does not have natively. Use this instead, in `AN2`:

```
=IF($Z2<>"","",
 IFERROR(
  IF(COUNTIFS(invoices!$D:$D,$D2,invoices!$N:$N,$J2)=1,
   INDEX(invoices!$A:$A,MATCH(1,(invoices!$D:$D=$D2)*(invoices!$N:$N=$J2),0)),
   "ambiguous"),
  "unmatched"))
```

It accepts a repair only when exactly one invoice exists for that student with exactly that net amount. That is the same safety condition as the engine, minus the digit similarity score. It catches 84931 to 84913, because student 68113 has one invoice worth 11,500. It refuses when two candidates exist, which is the behaviour I want.

For a full mirror, add a column that compares the last two digits with `RIGHT()` and requires a match on the first three digits, but the single candidate rule is enough in practice and is much easier to explain to an ops person.

## Step 4: owner and SLA

```
AO2 owner  =IFS(LEFT($AM2,3)="R02","teacher", LEFT($AM2,3)="R04","teacher", LEFT($AM2,3)="R05","finance", LEFT($AM2,3)="R06","finance", LEFT($AM2,3)="R07","parent", LEFT($AM2,3)="R09","parent", LEFT($AM2,3)="R00","system", TRUE,"ops_agent")
AP2 sla    =IFS(LEFT($AM2,3)="R07",24, LEFT($AM2,3)="R09",8, LEFT($AM2,3)="R04",24, LEFT($AM2,3)="R00",0, TRUE,4)
AQ2 age_h  =(NOW()-IF($Z2="",$T2,INDEX(invoices!$W:$W,$Z2)))*24
AR2 breach =IF(AND($AQ2>$AP2,$AM2<>"R00"),"BREACH","")
```

## Step 5: the dashboard tab

| Metric | Formula |
| --- | --- |
| Cases | `=COUNTA(recon!$AM$2:$AM)` |
| Auto approved | `=COUNTIF(recon!$AM$2:$AM,"R00*")` |
| Auto approval rate | `=B2/B1` |
| Blocking exceptions | `=COUNTIFS(recon!$AM$2:$AM,"<>R00*",recon!$AM$2:$AM,"<>R17*",recon!$AM$2:$AM,"<>R04*")` |
| Orphaned invoices | `=COUNTIFS(invoices!$U:$U,"Paid")-COUNTIF(forms!$K:$K,"<>")` |
| Stuck over 12h | `=SUMPRODUCT((invoices!$U:$U="Paid")*(NOW()-invoices!$W:$W>0.5)*(COUNTIF(forms!$K:$K,invoices!$A:$A)=0))` |
| Breaches | `=COUNTIF(recon!$AR$2:$AR,"BREACH")` |

The stuck formula is the one to sanity check on your own data, because `SUMPRODUCT` with a `COUNTIF` array is the least readable formula in the sheet. If it disagrees with the exception list, trust the exception list.

## What this version cannot do

- Seat ledger across several renewals in the same batch. It checks each row against the reference count, so two renewals into the last free seat will both pass. The Python engine handles this because it processes rows in invoice order and decrements a ledger.
- Message drafting. Use the `prompts/draft_message.md` prompt in a Slack workflow or paste the row into your LLM of choice. The templates in `outputs/messages.md` are the fallback.
- Idempotency. Running it twice does not create duplicate rows because it only writes decisions to `recon`, but nothing stops a human from re-sending a message.

Use this version for the shadow-mode pilot with two teachers. Move to the Python engine or the n8n workflow before the full rollout.
