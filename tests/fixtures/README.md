# Test files

These PDFs are small excerpts (only the BOQ pages, cover pages removed) of public
government tender documents downloaded from EPADS. They are used only to test
the BOQ parser. They contain no contact details.

| File | Source tender | Pages kept | Column layout |
|---|---|---|---|
| tender_a_nust_boq.pdf | Restructuring and Renovation of C3A Offices, NUST H-12 | 25 (original pages 43-67) | Sr. No, Ref No., Description, Unit, Quantity, Rate, Amount (rates filled) |
| tender_b_jiap_boq.pdf | Improvement works, public address rooms, JIAP Karachi | 3 (original pages 44-46) | Sr. No, S. No, Description, Unit, Quantity ("432 Sft"), Rate, Amount (rates blank) |
| tender_c_pidcl_boq.pdf | 50 kW hybrid solar system, PIDCL Islamabad | 4 (original pages 43-45 and 80) | Sr., S.No., Description, Unit, Qty, Rate, Amount, plus a second BOQ with different labels |

Keep your full tender PDFs in a folder called `private_tenders/` on your own
computer. That folder is ignored by git, so it is never uploaded.
