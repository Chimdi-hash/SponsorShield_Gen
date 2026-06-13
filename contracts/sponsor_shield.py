# v0.2.17
# { "Depends": "py-genlayer:1jb45aa8ynh2a9c9xn3b7qqh8sm5q93hwfp7jqmwsfhh8jpz09h6" }

from genlayer import *


@gl.evm.contract_interface
class _Recipient:
    class View:
        pass

    class Write:
        pass


class SponsorShield(gl.Contract):
    # Class-level storage declarations for the persistent state.
    # Note: GenLayer Studio handles initialization of these structures internally.
    campaign_rules: TreeMap[u256, str]
    campaign_funds: TreeMap[u256, u256]
    campaign_sponsors: TreeMap[u256, Address]
    campaign_completed: TreeMap[u256, bool]

    def __init__(self):
        # The constructor must be kept empty/private for standard initialization
        pass

    @gl.public.write.payable
    def create_campaign(self, campaign_id: u256, rules: str) -> None:
        deposit_value = gl.message.value
        if deposit_value == u256(0):
            raise gl.vm.UserError("You must lock up funds to create a campaign")
            
        # Ensure duplicate campaign IDs are not overwritten
        if self.campaign_funds.get(campaign_id, u256(0)) > u256(0):
            raise gl.vm.UserError("Campaign ID already exists")

        # Directly store information into state
        self.campaign_rules[campaign_id] = rules
        self.campaign_funds[campaign_id] = deposit_value
        self.campaign_sponsors[campaign_id] = gl.message.sender_address
        self.campaign_completed[campaign_id] = False

    @gl.public.write
    def verify_and_pay(self, campaign_id: u256, proof_url: str, creator_address: str) -> None:
        if self.campaign_completed.get(campaign_id, False):
            raise gl.vm.UserError("Campaign already completed or paid out")
            
        rules = self.campaign_rules.get(campaign_id, "")
        funds_to_pay = self.campaign_funds.get(campaign_id, u256(0))
        
        if funds_to_pay == u256(0):
            raise gl.vm.UserError("Campaign does not exist or has no funds")

        # Define the non-deterministic web text retrieval function
        def fetch_tweet_content():
            return gl.nondet.web.render(proof_url, mode='text')

        # Using non-comparative consensus validation for AI evaluation
        task_desc = f"Determine if the web content satisfies these sponsor requirements: {rules}."
        validation_criteria = "The content must match the rules specified. Respond with exactly 'YES' or 'NO'."

        ai_decision = gl.eq_principle.prompt_non_comparative(
            fetch_tweet_content,
            task=task_desc,
            criteria=validation_criteria
        )

        if ai_decision != "YES":
            raise gl.vm.UserError("GenLayer LLM nodes rejected the proof submission")

        # Prevent re-entrancy by resetting the state BEFORE making the external EVM transfer
        self.campaign_completed[campaign_id] = True
        self.campaign_funds[campaign_id] = u256(0)

        # Release the locked up value to the creator using the example interface format
        _Recipient(Address(creator_address)).emit_transfer(value=funds_to_pay)