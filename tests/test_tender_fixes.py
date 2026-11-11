"""Forms from the table of contents, and the Bid Data Sheet always being offered."""
from core.tender_index import TenderIndex, page_label, toc_entries

FOOT = "e-Pak Acquisition and Disposal System (EPADS) generated document | \u00a9 2026 Page {n} of 97"


def big_tender():
    pages = {i: f"filler text on page {i}" for i in range(1, 101)}
    pages[2] = ("Table of Contents\nREQUEST FOR BIDS 1\nInstructions to Bidders 3\nBid Data Sheet 31\n"
                "Eligibility Criteria 37\nSpecial Conditions of Contract 78\nBid Securing Declaration 83\n"
                "Contract Form 85\nIntegrity Pact 88\nPerformance Guarantee Form 90\nAnnexure 93\n"
                "Procurement Forms 95\nPast Construction Experiences 1")
    pages[3] = "REQUEST FOR BIDS\n1. The Procuring Agency invites sealed bids."
    pages[86] = "Bid Securing Declaration\nForm 9: Bid Securing Declaration\nI declare that I will not withdraw."
    pages[88] = "Contract Form\nAgreement text."
    pages[91] = "Integrity Pact\nThe bidder promises not to bribe."
    pages[93] = "Performance Guarantee Form\nBank guarantee text."
    pages[98] = "Procurement Forms\nList of forms."
    pages[99] = "Past Construction Experiences\nTable of past works."
    out = []
    for i in range(1, 101):
        body = pages[i]
        if i >= 4:
            body += "\n" + FOOT.format(n=i - 3)
        out.append(body)
    return out


def test_toc_entries_stop_where_the_body_starts():
    entries = toc_entries(big_tender())
    titles = [t for t, _ in entries]
    assert titles[0] == "REQUEST FOR BIDS" and "Integrity Pact" in titles and "Past Construction Experiences" in titles
    assert not any("invites" in t for t in titles)
    assert dict(entries)["Bid Securing Declaration"] == 83


def test_forms_come_from_the_table_of_contents():
    t = TenderIndex(big_tender())
    by = {f["title"] or f["label"]: f for f in t.forms}
    assert "Annexure" not in by and "Special Conditions of Contract" not in by
    assert by["Bid Securing Declaration"]["label"] == "Form 9"               # heading and contents merged
    assert sum(1 for f in t.forms if "securing" in (f["title"] + f["label"]).lower()) == 1
    assert by["Bid Securing Declaration"]["pdf_page"] == 86 and by["Bid Securing Declaration"]["printed_page"] == 83
    assert by["Contract Form"]["pdf_page"] == 88
    assert by["Integrity Pact"]["pdf_page"] == 91
    assert by["Performance Guarantee Form"]["pdf_page"] == 93
    assert by["Procurement Forms"]["pdf_page"] == 98
    assert by["Past Construction Experiences"]["pdf_page"] == 99             # the contents says page 1: found by title
    assert [f["pdf_page"] for f in t.forms] == sorted(f["pdf_page"] for f in t.forms)


def test_page_not_located_label():
    assert page_label(None, None) == "page not located"


def test_bid_data_sheet_passage_is_always_offered():
    flood = "Instructions to Bidders\n" + ("Bids shall remain valid. Bid validity period: the bids remain valid, "
                                           "validity of bids and valid bids. " * 4)
    pages = [f"{flood}\nvariant {i}" for i in range(10)]
    pages.append("Bid Data Sheet\n16.1 The Bids/Bid Validity period shall be: 182 Days")
    t = TenderIndex(pages)
    found = [p.pdf_page for p in t.search("How long must bids remain valid?", 6)]
    assert 11 in found
    assert len(found) <= 6
