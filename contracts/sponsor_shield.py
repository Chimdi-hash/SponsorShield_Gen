# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }
#
# ╔══════════════════════════════════════════════════════════════════╗
# ║              SponsorShield — GenLayer Intelligent Contract       ║
# ║                                                                  ║
# ║  Enables sponsors to define plain-English campaign rules and     ║
# ║  automates creator payout validation via GenLayer's             ║
# ║  decentralised LLM consensus engine.                            ║
# ║                                                                  ║
# ║  Flow:                                                           ║
# ║   1. Sponsor calls `create_campaign` with rules + funds.        ║
# ║   2. Creator calls `submit_proof` with a public URL.            ║
# ║   3. Any validator calls `evaluate_proof` — GenLayer's          ║
# ║      Equivalence Principle fans the call out to N validators,   ║
# ║      each independently scrapes the URL and asks the LLM        ║
# ║      whether the proof satisfies the rules.                     ║
# ║   4. On consensus the contract releases or rejects the payout.  ║
# ╚══════════════════════════════════════════════════════════════════╝

from genlayer import *

# ---------------------------------------------------------------------------
# Helper type aliases (for readability – GenLayer resolves these at runtime)
# ---------------------------------------------------------------------------
Address = str    # Wallet/contract address represented as a hex string
Amount  = int    # Token amount in smallest denomination (e.g. wei / glayer)


class SponsorShield(gl.Contract):
    """
    SponsorShield Intelligent Contract.

    State is stored exclusively in GenLayer-native `TreeMap` structures
    so that the GenVM can persist, snapshot, and roll back state correctly
    across the Optimistic Democracy consensus rounds.
    """

    # -----------------------------------------------------------------------
    # State Variables  (all declared at class scope with type annotations)
    # -----------------------------------------------------------------------

    # campaign_id  →  sponsor address
    campaign_sponsors: TreeMap[str, Address]

    # campaign_id  →  plain-English eligibility rules (e.g. "Post a tweet
    #                 mentioning @BrandX with at least 100 likes")
    campaign_rules: TreeMap[str, str]

    # campaign_id  →  payout amount (in smallest token unit)
    campaign_budgets: TreeMap[str, Amount]

    # campaign_id  →  whether the campaign is still accepting proofs
    campaign_active: TreeMap[str, bool]

    # campaign_id  →  creator address that submitted a proof
    proof_creators: TreeMap[str, Address]

    # campaign_id  →  the public URL used as proof (e.g. a tweet URL)
    proof_urls: TreeMap[str, str]

    # campaign_id  →  verdict after LLM evaluation  ("APPROVED" | "REJECTED" | "PENDING")
    proof_verdicts: TreeMap[str, str]

    # Simple monotonically-increasing counter as a surrogate campaign id key
    next_campaign_id: int

    # -----------------------------------------------------------------------
    # Constructor
    # -----------------------------------------------------------------------

    def __init__(self) -> None:
        """
        Initialise all state stores to empty TreeMaps.
        GenLayer requires every TreeMap to be explicitly constructed here
        before it can be written to.
        """
        self.campaign_sponsors  = TreeMap()
        self.campaign_rules     = TreeMap()
        self.campaign_budgets   = TreeMap()
        self.campaign_active    = TreeMap()
        self.proof_creators     = TreeMap()
        self.proof_urls         = TreeMap()
        self.proof_verdicts     = TreeMap()
        self.next_campaign_id   = 0

    # -----------------------------------------------------------------------
    # Sponsor Actions
    # -----------------------------------------------------------------------

    @gl.public.write
    def create_campaign(self, rules: str, budget: Amount) -> str:
        """
        Sponsor creates a new campaign by supplying plain-English rules
        and depositing a budget that will be paid out to an approved creator.

        :param rules:  Natural-language description of what the creator must
                       do to qualify for the payout, e.g.:
                       "Post a video on YouTube reviewing my product.
                        The video must be at least 3 minutes long and
                        mention the brand name 'BrandX' at least twice."
        :param budget: The payout amount in token units.
        :returns:      The unique campaign_id string for this campaign.

        Note: In a production contract you would pair this with a token
        deposit call (msg.value / ERC-20 transferFrom).  The budget field
        here tracks the promised amount so the validator logic can reference it.
        """
        # Build a deterministic, human-readable campaign key.
        campaign_id = f"campaign_{self.next_campaign_id}"
        self.next_campaign_id += 1

        # Persist all campaign metadata in TreeMap storage.
        self.campaign_sponsors[campaign_id] = gl.message.sender_account
        self.campaign_rules[campaign_id]    = rules
        self.campaign_budgets[campaign_id]  = budget
        self.campaign_active[campaign_id]   = True
        self.proof_verdicts[campaign_id]    = "PENDING"

        return campaign_id

    @gl.public.write
    def deactivate_campaign(self, campaign_id: str) -> None:
        """
        Sponsor closes their campaign, preventing any new proof submissions.

        Only the original sponsor may deactivate the campaign.
        """
        self._assert_campaign_exists(campaign_id)
        assert (
            self.campaign_sponsors[campaign_id] == gl.message.sender_account
        ), "SponsorShield: only the campaign sponsor can deactivate it."

        self.campaign_active[campaign_id] = False

    # -----------------------------------------------------------------------
    # Creator Actions
    # -----------------------------------------------------------------------

    @gl.public.write
    def submit_proof(self, campaign_id: str, proof_url: str) -> None:
        """
        Creator submits a publicly accessible URL (e.g. a tweet, YouTube
        video, or blog post) as evidence that they have fulfilled the
        campaign requirements.

        :param campaign_id: The campaign this proof is for.
        :param proof_url:   A direct, publicly reachable URL to the content.

        Constraint: Only one proof per campaign (first-come, first-served).
        The sponsor should design multi-creator campaigns by deploying
        separate campaign instances.
        """
        self._assert_campaign_exists(campaign_id)
        assert self.campaign_active[campaign_id], \
            "SponsorShield: this campaign is no longer accepting proofs."
        assert campaign_id not in self.proof_creators, \
            "SponsorShield: a proof has already been submitted for this campaign."

        self.proof_creators[campaign_id] = gl.message.sender_account
        self.proof_urls[campaign_id]     = proof_url
        self.proof_verdicts[campaign_id] = "PENDING"

    # -----------------------------------------------------------------------
    # Core Evaluation — GenLayer Equivalence Principle
    # -----------------------------------------------------------------------

    @gl.public.write
    def evaluate_proof(self, campaign_id: str) -> None:
        """
        Triggers the decentralised LLM consensus evaluation for a submitted
        proof.  This can be called by anyone (sponsor, creator, or a third
        party) once a proof URL has been submitted.

        ╔─── GenLayer Consensus Architecture ──────────────────────────────╗
        ║                                                                   ║
        ║  gl.eq_principle.strict_eq(fn)                                   ║
        ║  ├─ GenLayer fans `fn` out to every active validator.            ║
        ║  ├─ Each validator independently:                                ║
        ║  │   1. Calls gl.nondet.web.render() to scrape the proof URL.   ║
        ║  │   2. Calls gl.nondet.exec_prompt() to ask the LLM if the     ║
        ║  │      scraped content satisfies the campaign rules.            ║
        ║  │   3. Returns "APPROVED" or "REJECTED".                        ║
        ║  └─ strict_eq requires ALL validators to return the EXACT SAME  ║
        ║     string.  Validators that deviate are slashed.               ║
        ║                                                                   ║
        ║  Because the result is a short, deterministic label rather than  ║
        ║  a long prose answer, strict_eq is the correct principle here.   ║
        ║  (Use prompt_comparative when comparing longer free-form text.)  ║
        ╚───────────────────────────────────────────────────────────────────╝
        """
        self._assert_campaign_exists(campaign_id)
        assert campaign_id in self.proof_urls, \
            "SponsorShield: no proof has been submitted for this campaign yet."
        assert self.proof_verdicts[campaign_id] == "PENDING", \
            "SponsorShield: this proof has already been evaluated."

        # ── Read all state we need BEFORE entering the nondet block ──────
        # Non-deterministic blocks cannot safely access contract storage
        # directly (the GenVM prohibits it to ensure isolation).
        # We snapshot the values into local variables and close over them.
        rules     = self.campaign_rules[campaign_id]
        proof_url = self.proof_urls[campaign_id]

        # ── Define the non-deterministic evaluation block ─────────────────
        def _evaluate() -> str:
            """
            Each validator executes this function independently.

            Step 1 — Web Scrape
            ───────────────────
            gl.nondet.web.render fetches the proof URL and returns its
            rendered HTML content.  Using 'html' mode ensures we capture
            text even from JavaScript-rendered pages (e.g. Twitter/X).

            Step 2 — LLM Consensus Prompt
            ──────────────────────────────
            We pass the scraped page text and the campaign rules to the
            decentralised LLM.  The prompt is engineered to elicit a strict
            binary JSON response so that strict_eq can compare outputs
            across validators without ambiguity.

            Step 3 — Return Verdict
            ───────────────────────
            The function returns exactly "APPROVED" or "REJECTED" — a short,
            deterministic token that strict_eq can check for equality.
            """

            # ── Step 1: Scrape the proof URL ─────────────────────────────
            # 'html' mode runs the page in a headless browser, executes JS,
            # and returns the full rendered DOM as text.
            page_text = gl.nondet.web.render(proof_url, mode="html")

            # Truncate to avoid exceeding the LLM's context window.
            # 8 000 characters covers the visible text of most social posts.
            page_excerpt = page_text[:8_000]

            # ── Step 2: Build and execute the LLM evaluation prompt ───────
            # The prompt instructs the LLM to act as an impartial auditor
            # and to respond ONLY with a JSON object containing a single
            # boolean field.  This deterministic schema is critical for
            # strict_eq to reach consensus across validators.
            evaluation_prompt = f"""
You are an impartial compliance auditor for a Web3 sponsorship platform.

## Campaign Requirements
The sponsor requires the creator to fulfil ALL of the following conditions:

{rules}

## Creator's Submitted Proof (scraped web content)
The following text was extracted from: {proof_url}

---
{page_excerpt}
---

## Your Task
Carefully read the scraped content above and determine whether it fully
satisfies EVERY condition listed in the Campaign Requirements.

Respond with ONLY the following JSON and nothing else:
{{
  "compliant": true | false,
  "reason": "<one concise sentence explaining your verdict>"
}}

Rules:
- If ALL requirements are met → set compliant to true.
- If ANY requirement is not met or can't be verified → set compliant to false.
- Do NOT add any extra keys, markdown, or explanation outside the JSON.
"""

            # gl.nondet.exec_prompt sends the prompt to the GenLayer LLM
            # consensus engine.  response_format="json" coerces the model
            # to emit valid JSON, which we then parse safely.
            raw_response = gl.nondet.exec_prompt(
                evaluation_prompt,
                response_format="json",
            )

            # ── Step 3: Parse and normalise the verdict ───────────────────
            # raw_response is a Python dict when response_format="json".
            if isinstance(raw_response, dict):
                compliant = raw_response.get("compliant", False)
            else:
                # Fallback: treat any non-dict response as non-compliant
                # to err on the side of protecting the sponsor's funds.
                compliant = False

            # Return a short, exact string — the unit that strict_eq will
            # compare across all validators for consensus.
            return "APPROVED" if compliant else "REJECTED"

        # ── Execute under Equivalence Principle ───────────────────────────
        # gl.eq_principle.strict_eq fans _evaluate() out to every validator.
        # All validators must return the identical string for the transaction
        # to finalise.  Any deviation causes that validator to be slashed.
        verdict: str = gl.eq_principle.strict_eq(_evaluate)

        # ── Post-consensus: update persistent state ───────────────────────
        # (We are back in deterministic territory — storage writes are safe.)
        self.proof_verdicts[campaign_id] = verdict

        if verdict == "APPROVED":
            # Mark the campaign as inactive so it cannot be re-evaluated.
            self.campaign_active[campaign_id] = False

            # ── Release the payout ────────────────────────────────────────
            # In a full production deployment this would trigger an ERC-20
            # transfer or a native token send.  We emit the intent here via
            # a transfer to the creator's recorded address.
            #
            # gl.transfer(
            #     self.proof_creators[campaign_id],
            #     self.campaign_budgets[campaign_id],
            # )
            #
            # Uncomment the above when the GenLayer token-transfer API is
            # available in your target runtime version.  For now, the
            # verified verdict is persisted so an off-chain listener or
            # separate guardian contract can trigger the ERC-20 transfer.
            pass

    # -----------------------------------------------------------------------
    # View / Query Methods
    # -----------------------------------------------------------------------

    @gl.public.view
    def get_campaign(self, campaign_id: str) -> dict:
        """
        Returns a snapshot of a campaign's current state.

        :param campaign_id: The campaign to query.
        :returns:           A dict with sponsor, rules, budget, active flag.
        """
        self._assert_campaign_exists(campaign_id)
        return {
            "campaign_id": campaign_id,
            "sponsor":     self.campaign_sponsors[campaign_id],
            "rules":       self.campaign_rules[campaign_id],
            "budget":      self.campaign_budgets[campaign_id],
            "active":      self.campaign_active[campaign_id],
        }

    @gl.public.view
    def get_proof_status(self, campaign_id: str) -> dict:
        """
        Returns the current evaluation status of a submitted proof.

        :param campaign_id: The campaign whose proof to query.
        :returns:           Dict with creator address, proof URL, and verdict.

        Verdict values:
          "PENDING"  — proof submitted but not yet evaluated, or no proof yet.
          "APPROVED" — LLM validators reached consensus that rules were met.
          "REJECTED" — LLM validators reached consensus that rules were NOT met.
        """
        self._assert_campaign_exists(campaign_id)
        return {
            "campaign_id": campaign_id,
            "creator":     self.proof_creators.get(campaign_id, ""),
            "proof_url":   self.proof_urls.get(campaign_id, ""),
            "verdict":     self.proof_verdicts.get(campaign_id, "PENDING"),
        }

    @gl.public.view
    def get_total_campaigns(self) -> int:
        """
        Returns the total number of campaigns ever created.
        Useful for building a frontend index of all campaigns.
        """
        return self.next_campaign_id

    # -----------------------------------------------------------------------
    # Internal Helpers
    # -----------------------------------------------------------------------

    def _assert_campaign_exists(self, campaign_id: str) -> None:
        """
        Shared guard: reverts the transaction if the given campaign_id has
        never been registered in this contract.
        """
        assert campaign_id in self.campaign_sponsors, \
            f"SponsorShield: campaign '{campaign_id}' does not exist."
