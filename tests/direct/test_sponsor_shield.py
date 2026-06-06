# =============================================================================
# tests/direct/test_sponsor_shield.py
#
# SponsorShield — Direct-Mode Test Suite
#
# Runs entirely in-process using GenLayer's `gltest` harness.
# No Docker, no simulator, no internet connection required.
#
# Run with:
#   pytest tests/direct/ -v
#
# Each test uses `direct_vm` cheatcodes to mock the web scraper and LLM so
# the evaluation logic can be validated deterministically on any machine.
# =============================================================================

import pytest
from gltest import direct_deploy, direct_vm   # noqa: F401  (fixtures injected by pytest)


# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

SPONSOR   = "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266"   # test account #0
CREATOR   = "0x70997970C51812dc3A010C7d01b50e0d17dc79C8"   # test account #1
THIRD_PTY = "0x3C44CdDdB6a900fa2b585dd299e03d12FA4293BC"   # test account #2

CAMPAIGN_RULES = (
    "Post a tweet mentioning @SponsorShield with the hashtag #Web3Sponsor. "
    "The tweet must have at least 50 likes and be publicly visible."
)
CAMPAIGN_BUDGET  = 1_000  # tokens (smallest unit)

VALID_TWEET_URL   = "https://x.com/creator123/status/1234567890"
INVALID_TWEET_URL = "https://x.com/creator123/status/9999999999"

# Mocked HTML bodies returned by the fake web scraper
VALID_PAGE_HTML = """
<html><body>
  <article>
    <p>Just tried @SponsorShield — absolute game changer for Web3 creators!
       #Web3Sponsor #DeFi</p>
    <span class="likes">142 Likes</span>
  </article>
</body></html>
"""

INVALID_PAGE_HTML = """
<html><body>
  <article>
    <p>GM everyone! Just had coffee ☕</p>
    <span class="likes">3 Likes</span>
  </article>
</body></html>
"""


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def contract(direct_deploy, direct_vm):
    """
    Deploy a fresh SponsorShield instance for each test.
    `direct_deploy` compiles and instantiates the contract in-memory via the
    GenLayer direct-mode VM — no network call needed.
    """
    # Set the deployer / initial sender
    direct_vm.set_account(SPONSOR)
    return direct_deploy("contracts/sponsor_shield.py")


# ---------------------------------------------------------------------------
# 1. Campaign lifecycle tests
# ---------------------------------------------------------------------------

class TestCampaignCreation:
    """Verify that sponsors can create and inspect campaigns."""

    def test_create_campaign_returns_id(self, contract, direct_vm):
        direct_vm.set_account(SPONSOR)
        campaign_id = contract.create_campaign(CAMPAIGN_RULES, CAMPAIGN_BUDGET)

        assert campaign_id == "campaign_0", (
            "First campaign should receive ID 'campaign_0'"
        )

    def test_campaign_data_persisted_correctly(self, contract, direct_vm):
        direct_vm.set_account(SPONSOR)
        campaign_id = contract.create_campaign(CAMPAIGN_RULES, CAMPAIGN_BUDGET)

        data = contract.get_campaign(campaign_id)
        assert data["sponsor"] == SPONSOR
        assert data["rules"]   == CAMPAIGN_RULES
        assert data["budget"]  == CAMPAIGN_BUDGET
        assert data["active"]  is True

    def test_multiple_campaigns_get_unique_ids(self, contract, direct_vm):
        direct_vm.set_account(SPONSOR)
        id_0 = contract.create_campaign("Rule A", 100)
        id_1 = contract.create_campaign("Rule B", 200)

        assert id_0 != id_1
        assert contract.get_total_campaigns() == 2

    def test_nonexistent_campaign_raises(self, contract):
        with pytest.raises(Exception, match="does not exist"):
            contract.get_campaign("campaign_999")


class TestCampaignDeactivation:
    """Sponsor can deactivate; other callers cannot."""

    def test_sponsor_can_deactivate(self, contract, direct_vm):
        direct_vm.set_account(SPONSOR)
        cid = contract.create_campaign(CAMPAIGN_RULES, CAMPAIGN_BUDGET)
        contract.deactivate_campaign(cid)

        assert contract.get_campaign(cid)["active"] is False

    def test_non_sponsor_cannot_deactivate(self, contract, direct_vm):
        direct_vm.set_account(SPONSOR)
        cid = contract.create_campaign(CAMPAIGN_RULES, CAMPAIGN_BUDGET)

        # Switch to a different caller
        direct_vm.set_account(THIRD_PTY)
        with pytest.raises(Exception, match="only the campaign sponsor"):
            contract.deactivate_campaign(cid)


# ---------------------------------------------------------------------------
# 2. Proof submission tests
# ---------------------------------------------------------------------------

class TestProofSubmission:
    """Creators submit proof URLs; guard conditions prevent abuse."""

    def _make_campaign(self, contract, direct_vm) -> str:
        direct_vm.set_account(SPONSOR)
        return contract.create_campaign(CAMPAIGN_RULES, CAMPAIGN_BUDGET)

    def test_creator_can_submit_proof(self, contract, direct_vm):
        cid = self._make_campaign(contract, direct_vm)

        direct_vm.set_account(CREATOR)
        contract.submit_proof(cid, VALID_TWEET_URL)

        status = contract.get_proof_status(cid)
        assert status["creator"]   == CREATOR
        assert status["proof_url"] == VALID_TWEET_URL
        assert status["verdict"]   == "PENDING"

    def test_double_proof_submission_rejected(self, contract, direct_vm):
        cid = self._make_campaign(contract, direct_vm)
        direct_vm.set_account(CREATOR)
        contract.submit_proof(cid, VALID_TWEET_URL)

        with pytest.raises(Exception, match="already been submitted"):
            contract.submit_proof(cid, VALID_TWEET_URL)

    def test_proof_rejected_on_inactive_campaign(self, contract, direct_vm):
        cid = self._make_campaign(contract, direct_vm)
        direct_vm.set_account(SPONSOR)
        contract.deactivate_campaign(cid)

        direct_vm.set_account(CREATOR)
        with pytest.raises(Exception, match="no longer accepting proofs"):
            contract.submit_proof(cid, VALID_TWEET_URL)


# ---------------------------------------------------------------------------
# 3. LLM Consensus Evaluation tests (the core nondet block)
#
# direct_vm.mock_web  — intercepts gl.nondet.web.render() calls
# direct_vm.mock_llm  — intercepts gl.nondet.exec_prompt() calls
#
# Both mocks use regex patterns matched against the URL / prompt text.
# This lets us simulate exactly what every validator would independently see.
# ---------------------------------------------------------------------------

class TestProofEvaluation:
    """
    The most important tests: verify that the Equivalence Principle block
    correctly translates mocked web + LLM responses into verdicts.
    """

    def _setup_campaign_and_proof(self, contract, direct_vm, proof_url: str) -> str:
        """Helper: deploy campaign → submit proof → return campaign_id."""
        direct_vm.set_account(SPONSOR)
        cid = contract.create_campaign(CAMPAIGN_RULES, CAMPAIGN_BUDGET)

        direct_vm.set_account(CREATOR)
        contract.submit_proof(cid, proof_url)
        return cid

    # ------------------------------------------------------------------
    # 3a. Happy path — compliant tweet, LLM says APPROVED
    # ------------------------------------------------------------------

    def test_evaluate_approves_compliant_proof(self, contract, direct_vm):
        """
        Mock flow:
          web.render -> returns HTML with @SponsorShield, #Web3Sponsor, 142 likes
          exec_prompt -> LLM deems compliant: {"compliant": true, "reason": "..."}
          Expected verdict: APPROVED
        """
        # 1. Mock the web scraper to return a valid tweet page
        direct_vm.mock_web(
            r"x\.com/creator123/status/1234567890",
            VALID_PAGE_HTML,
        )

        # 2. Mock the LLM — pattern matches any prompt that mentions "compliant"
        direct_vm.mock_llm(
            r".*compliance auditor.*",
            {"compliant": True, "reason": "Tweet mentions @SponsorShield with #Web3Sponsor and 142 likes."},
        )

        cid = self._setup_campaign_and_proof(contract, direct_vm, VALID_TWEET_URL)

        # 3. Trigger evaluation
        direct_vm.set_account(THIRD_PTY)   # Anyone can evaluate
        contract.evaluate_proof(cid)

        status = contract.get_proof_status(cid)
        assert status["verdict"] == "APPROVED"

    def test_approved_campaign_becomes_inactive(self, contract, direct_vm):
        """After approval the campaign should close to prevent re-evaluation."""
        direct_vm.mock_web(r"x\.com/creator123/status/1234567890", VALID_PAGE_HTML)
        direct_vm.mock_llm(
            r".*compliance auditor.*",
            {"compliant": True, "reason": "All conditions met."},
        )

        cid = self._setup_campaign_and_proof(contract, direct_vm, VALID_TWEET_URL)
        contract.evaluate_proof(cid)

        assert contract.get_campaign(cid)["active"] is False

    # ------------------------------------------------------------------
    # 3b. Rejection path — tweet does not satisfy the rules
    # ------------------------------------------------------------------

    def test_evaluate_rejects_non_compliant_proof(self, contract, direct_vm):
        """
        Mock flow:
          web.render -> returns an unrelated tweet (no mention of SponsorShield)
          exec_prompt -> LLM deems non-compliant: {"compliant": false, "reason": "..."}
          Expected verdict: REJECTED
        """
        direct_vm.mock_web(
            r"x\.com/creator123/status/9999999999",
            INVALID_PAGE_HTML,
        )
        direct_vm.mock_llm(
            r".*compliance auditor.*",
            {"compliant": False, "reason": "Tweet does not mention @SponsorShield or #Web3Sponsor."},
        )

        cid = self._setup_campaign_and_proof(contract, direct_vm, INVALID_TWEET_URL)
        contract.evaluate_proof(cid)

        assert contract.get_proof_status(cid)["verdict"] == "REJECTED"

    def test_rejected_campaign_stays_pending_for_re_submission(self, contract, direct_vm):
        """
        A REJECTED verdict locks the *current proof* (cannot re-evaluate).
        The campaign design is first-come-first-served so after rejection
        the verdict is simply stored; a new campaign must be created.
        """
        direct_vm.mock_web(r"x\.com.*", INVALID_PAGE_HTML)
        direct_vm.mock_llm(r".*compliance auditor.*", {"compliant": False, "reason": "Not compliant."})

        cid = self._setup_campaign_and_proof(contract, direct_vm, INVALID_TWEET_URL)
        contract.evaluate_proof(cid)

        # Trying to evaluate again should raise
        with pytest.raises(Exception, match="already been evaluated"):
            contract.evaluate_proof(cid)

    # ------------------------------------------------------------------
    # 3c. Malformed LLM response — fallback to REJECTED
    # ------------------------------------------------------------------

    def test_malformed_llm_response_defaults_to_rejected(self, contract, direct_vm):
        """
        If the LLM returns something unexpected (not a dict), the contract
        should defensively mark the proof as REJECTED.
        """
        direct_vm.mock_web(r"x\.com.*", VALID_PAGE_HTML)
        # Simulate a hallucination / non-JSON response
        direct_vm.mock_llm(r".*compliance auditor.*", "Sure, looks fine!")  # plain string

        cid = self._setup_campaign_and_proof(contract, direct_vm, VALID_TWEET_URL)
        contract.evaluate_proof(cid)

        assert contract.get_proof_status(cid)["verdict"] == "REJECTED"

    # ------------------------------------------------------------------
    # 3d. Guard conditions for evaluate_proof
    # ------------------------------------------------------------------

    def test_evaluate_without_proof_raises(self, contract, direct_vm):
        """evaluate_proof must fail if no proof URL has been submitted."""
        direct_vm.set_account(SPONSOR)
        cid = contract.create_campaign(CAMPAIGN_RULES, CAMPAIGN_BUDGET)

        with pytest.raises(Exception, match="no proof has been submitted"):
            contract.evaluate_proof(cid)
