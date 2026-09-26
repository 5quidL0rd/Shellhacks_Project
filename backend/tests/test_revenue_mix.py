"""Tests for the revenue mix: who pays a company, read from its filing.

A wrong number here is drawn as a slice of a pie and read as fact, so:
  1. Every way filings state a share is found ("22%", "91 percent").
  2. A floor ("10% or more") is never charted as an exact share.
  3. A number or name the quote does not contain never reaches the screen.
  4. Only one direct customer's share of revenue becomes a slice: groups,
     indirect customers, receivables and older years would double-count.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.research import concentration as conc  # noqa: E402
from app.sources.filing import CONCENTRATION_TERMS  # noqa: E402


def fact(**kw):
    base = {"kind": "customer_concentration", "subject": "one direct customer",
            "counterparty_name": None, "percent": 22.0, "at_least": False,
            "scope": "single", "basis": "direct", "metric": "total revenue",
            "period": "fiscal year 2026", "threshold": None,
            "evidence": "Sales to one direct customer accounted for 22% of total revenue.",
            "confidence": "high"}
    return {**base, **kw}


def result(*facts):
    return {"available": True, "form": "10-K", "filing_date": "2026-02-25",
            "url": "https://sec.gov/x", "facts": list(facts), "dropped_unverified": 0}


# --- 1. finding the passages ------------------------------------------------

def test_percent_spelled_out_is_found():
    # Cirrus Logic's 10-K; matching only "%" missed its 91% customer entirely.
    assert CONCENTRATION_TERMS.search(
        "we had one end customer, Apple Inc., who purchased through multiple contract "
        "manufacturers and represented approximately 91 percent of net sales")


def test_floor_wording_is_found():
    assert CONCENTRATION_TERMS.search(
        "Apple, Samsung and Xiaomi each accounted for 10% or more of consolidated revenues")


def test_unrelated_percentages_are_not():
    assert not CONCENTRATION_TERMS.search("Our effective tax rate was 12% this year.")


# --- 2 and 3. checking a fact against its own quote --------------------------

def model_fact(**kw):
    return conc.Fact(**{k: v for k, v in fact(**kw).items()})


def test_floor_is_flagged_even_if_the_model_missed_it():
    f = model_fact(counterparty_name="Samsung", percent=10.0, at_least=False,
                   evidence="Apple, Samsung and Xiaomi each accounted for 10% or more "
                            "of consolidated revenues")
    assert conc._check(f)["at_least"] is True


def test_exact_share_is_not_flagged():
    assert conc._check(model_fact())["at_least"] is False


def test_percent_not_in_quote_is_dropped():
    assert conc._check(model_fact(percent=25.0)) is None


def test_spelled_out_percent_verifies():
    f = model_fact(counterparty_name="Apple Inc.", percent=91.0,
                   evidence="one end customer, Apple Inc., who purchased through multiple "
                            "contract manufacturers and represented approximately 91 percent")
    assert conc._check(f)["percent"] == 91.0


def test_name_not_in_quote_is_removed_not_guessed():
    checked = conc._check(model_fact(counterparty_name="Microsoft"))
    assert checked is not None and checked["counterparty_name"] is None


# --- 4. what becomes a slice -------------------------------------------------

def test_slices_and_remainder():
    mix = conc.revenue_mix(result(
        fact(),
        fact(subject="another direct customer", percent=14.0,
             evidence="another direct customer accounted for 14% of total revenue")))
    assert mix["status"] == "disclosed"
    assert [(s["label"], s["percent"]) for s in mix["slices"]] == [
        ("Customer A", 22.0), ("Customer B", 14.0)]
    assert mix["other"]["percent"] == 64.0 and not mix["other"]["at_most"]


def test_unnamed_customer_keeps_the_filings_description():
    s = conc.revenue_mix(result(fact()))["slices"][0]
    assert s["named"] is False and s["described_as"] == "one direct customer"


def test_floor_makes_the_remainder_an_upper_bound():
    mix = conc.revenue_mix(result(fact(counterparty_name="Apple", percent=10.0, at_least=True)))
    assert mix["slices"][0]["label"] == "Apple"
    assert mix["other"]["at_most"] is True


def test_groups_indirect_receivables_and_old_years_are_not_slices():
    mix = conc.revenue_mix(result(
        fact(),
        fact(subject="our ten largest customers", percent=96.0, scope="group"),
        fact(subject="an indirect customer", percent=10.0, basis="indirect"),
        fact(percent=25.0, metric="accounts receivable balance"),
        fact(percent=18.0, period="fiscal year 2023")))
    assert [s["percent"] for s in mix["slices"]] == [22.0]
    # The group and the indirect customer are still shown, as context.
    assert {c["percent"] for c in mix["context"]} == {96.0, 10.0}


def test_no_big_customer_is_a_finding():
    mix = conc.revenue_mix(result(fact(kind="none_above_threshold", percent=None,
                                       subject="customer", metric="revenue", threshold=10.0)))
    assert mix["status"] == "none_above_threshold"
    assert mix["other"]["percent"] == 100.0 and mix["slices"] == []


def test_shares_over_100_are_not_drawn():
    mix = conc.revenue_mix(result(fact(percent=70.0), fact(subject="a second customer", percent=60.0)))
    assert mix["status"] == "overlapping" and mix["other"] is None


def test_nothing_disclosed():
    mix = conc.revenue_mix(result(fact(kind="single_source", percent=None, subject="wafers")))
    assert mix["status"] == "not_disclosed"
    assert mix["suppliers"][0]["text"] == "wafers"


def test_receivables_are_not_supplier_dependence():
    # Apple: "two vendors ... 46% of total vendor non-trade receivables"
    mix = conc.revenue_mix(result(fact(kind="supplier_concentration", subject="two vendors",
                                       percent=46.0, metric="total vendor non-trade receivables")))
    assert mix["suppliers"] == []


def test_listing_cutoff_is_not_a_country_share():
    # Apple: "countries that individually accounted for 10% or more ... U.S."
    mix = conc.revenue_mix(result(fact(kind="geographic_concentration", subject="U.S.",
                                       percent=10.0, at_least=True, metric="net sales")))
    assert mix["geography"] == []


def test_indirect_customer_is_the_slice_when_nothing_direct_is_disclosed():
    # Cirrus Logic: Apple buys through contract manufacturers, 91% of sales.
    mix = conc.revenue_mix(result(
        fact(subject="one end customer", counterparty_name="Apple Inc.", percent=91.0,
             basis="indirect", metric="total net sales"),
        fact(kind="none_above_threshold", subject="other customer", percent=None,
             metric="net sales", threshold=10.0)))
    assert [(s["label"], s["percent"]) for s in mix["slices"]] == [("Apple Inc.", 91.0)]
    assert mix["other"]["percent"] == 9.0


def test_named_floors_beside_exact_unnamed_shares_are_not_drawn_twice():
    # Qualcomm: (x) 21%, (y) 20%, (z) 13%, and "Apple, Samsung and Xiaomi each
    # comprised 10% or more". Same customers; which is which is not stated.
    floor = "revenues from Apple, Samsung and Xiaomi each comprised 10% or more"
    mix = conc.revenue_mix(result(
        fact(subject="Customer/licensee (x)", percent=21.0),
        fact(subject="Customer/licensee (y)", percent=20.0),
        fact(subject="Customer/licensee (z)", percent=13.0),
        *[fact(subject=n, counterparty_name=n, percent=10.0, at_least=True, evidence=floor)
          for n in ("Apple", "Samsung", "Xiaomi")]))
    assert [s["percent"] for s in mix["slices"]] == [21.0, 20.0, 13.0]
    assert all(not s["named"] for s in mix["slices"])
    assert [n["name"] for n in mix["named_without_share"]] == ["Apple", "Samsung", "Xiaomi"]
    assert mix["other"]["percent"] == 46.0 and mix["context"] == []


def test_table_row_number_verifies_under_a_percent_heading():
    f = model_fact(subject="Customer/licensee (y)", percent=20.0,
                   evidence="Revenues from each customer/licensee that were 10% or greater of "
                            "total revenues were as follows: 2025 2024 2023 Customer/licensee (y) 20 19 21")
    assert conc._check(f) is not None


def test_bare_number_without_a_percent_heading_is_rejected():
    f = model_fact(percent=20.0, evidence="We shipped to 20 customers in 2025 across many regions.")
    assert conc._check(f) is None


def test_earlier_years_from_the_same_quote_make_a_trend():
    # TSMC: "Our largest customer in 2023, 2024 and 2025 accounted for 25%, 22% and 19%"
    quote = ("Our largest customer in 2023 , 2024 and 2025 accounted for 25% , 22% and 19% "
             "of our net revenue")
    f = conc._check(model_fact(subject="Our largest customer", percent=19.0, period="2025",
                               metric="net revenue", evidence=quote,
                               earlier=[{"period": "2023", "percent": 25.0},
                                        {"period": "2024", "percent": 22.0},
                                        {"period": "2022", "percent": 31.0}]))  # not in quote
    s = conc.revenue_mix(result(f))["slices"][0]
    assert [(p["period"], p["percent"]) for p in s["history"]] == [
        ("2023", 25.0), ("2024", 22.0), ("2025", 19.0)]


def test_customers_named_in_filings_exclude_hand_added_edges():
    named = conc.named_in_filings("TSM")
    ids = {c["id"] for c in named}
    assert {"NVDA", "AMD", "QCOM"} <= ids
    assert "AAPL" not in ids  # TSMC -> Apple is a manual edge, not from a filing
    assert all(c["evidence"] and c["source"] in conc.FILED_SOURCES for c in named)


def test_table_row_quoted_alone_verifies_against_the_heading_before_it():
    heading = "Revenues from each customer/licensee that were 10% or greater of total revenues were as follows: "
    f = model_fact(subject="Customer/licensee (y)", percent=20.0,
                   evidence="Customer/licensee (y) 20 19 21")
    assert conc._check(f) is None                  # no heading, no proof it is a percent
    assert conc._check(f, before=heading) is not None


def test_same_unnamed_customer_in_a_sentence_and_a_table_is_one_slice():
    # TSMC: "Our largest customer ... 19%" and a table row "Customer A 19%".
    mix = conc.revenue_mix(result(
        fact(subject="Our largest customer", percent=19.0, period="2025",
             evidence="Our largest customer in 2025 accounted for 19% of our net revenue"),
        fact(subject="Customer A", percent=19.0, period="2025",
             evidence="Customer A 19% 22% 25%")))
    assert [(s["described_as"], s["percent"]) for s in mix["slices"]] == [("Our largest customer", 19.0)]


def test_two_customers_at_the_same_share_in_one_passage_stay_two():
    quote = "two customers each accounted for 12% of total revenue"
    mix = conc.revenue_mix(result(fact(subject="a customer", percent=12.0, evidence=quote),
                                  fact(subject="another customer", percent=12.0, evidence=quote)))
    assert len(mix["slices"]) == 2
