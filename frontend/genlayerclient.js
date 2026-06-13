// genlayerclient.js
// Real GenLayer SDK client — reads & writes directly to the deployed contract.

import { createClient } from "https://esm.sh/genlayer-js@latest";
import { studionet }    from "https://esm.sh/genlayer-js@latest/chains";

// ── Deployed contract address on GenLayer Studionet ──────────────────────────
export const CONTRACT_ADDRESS = "0xE91b2670D14d047B24D198944FfcF72DC061C043";

// ── Singleton client cache ────────────────────────────────────────────────────
let _readClient  = null;
let _writeClient = null;

/**
 * Returns a read-only (no-account) GenLayer client.
 * Safe to call even before the user has connected a wallet.
 */
export function getReadClient() {
    if (!_readClient) {
        _readClient = createClient({ chain: studionet });
    }
    return _readClient;
}

/**
 * Returns a write-capable client bound to a MetaMask-provided account address.
 * @param {string} accountAddress  — EIP-55 checksummed address from MetaMask
 */
export function getWriteClient(accountAddress) {
    if (!accountAddress) throw new Error("No wallet address supplied to getWriteClient().");
    // Always create a fresh write client when the account changes.
    if (!_writeClient || _writeClient._account !== accountAddress) {
        _writeClient = createClient({
            chain:   studionet,
            account: accountAddress,
        });
        _writeClient._account = accountAddress; // tag for change detection
    }
    return _writeClient;
}

// ── MetaMask Wallet Connection ────────────────────────────────────────────────

/**
 * Requests MetaMask wallet access.
 * Returns the first connected account address, or throws if denied / unavailable.
 */
export async function connectMetaMask() {
    if (typeof window.ethereum === "undefined") {
        throw new Error(
            "MetaMask not detected. Please install MetaMask and reload this page."
        );
    }

    // Ask the user to approve account access
    const accounts = await window.ethereum.request({
        method: "eth_requestAccounts",
    });

    if (!accounts || accounts.length === 0) {
        throw new Error("No accounts returned from MetaMask.");
    }

    // Optionally add the GenLayer Studionet chain to MetaMask
    try {
        await addStudionetToMetaMask();
    } catch (_) {
        // Non-fatal — user may be using a different RPC config
    }

    return accounts[0];
}

/**
 * Returns the currently selected MetaMask account (if already authorised),
 * without triggering a connection popup.
 */
export async function getMetaMaskAccount() {
    if (typeof window.ethereum === "undefined") return null;
    const accounts = await window.ethereum.request({ method: "eth_accounts" });
    return accounts && accounts.length > 0 ? accounts[0] : null;
}

/**
 * Attempts to add GenLayer Studionet as a custom network in MetaMask.
 */
async function addStudionetToMetaMask() {
    await window.ethereum.request({
        method: "wallet_addEthereumChain",
        params: [
            {
                chainId:           "0xC7C7", // 51143 decimal — GenLayer Studionet
                chainName:         "GenLayer Studionet",
                nativeCurrency:    { name: "GL", symbol: "GL", decimals: 18 },
                rpcUrls:           ["http://127.0.0.1:4000/api"],
                blockExplorerUrls: [],
            },
        ],
    });
}

// ── Contract Read Helpers ─────────────────────────────────────────────────────

/**
 * Reads a campaign from the contract by its ID.
 * @param {string} campaignId
 * @returns {Promise<object>}
 */
export async function getCampaign(campaignId) {
    const client = getReadClient();
    return await client.readContract({
        address:      CONTRACT_ADDRESS,
        functionName: "get_campaign",
        args:         [campaignId],
    });
}

/**
 * Reads the proof/verdict status for a campaign.
 * @param {string} campaignId
 * @returns {Promise<object>}
 */
export async function getProofStatus(campaignId) {
    const client = getReadClient();
    return await client.readContract({
        address:      CONTRACT_ADDRESS,
        functionName: "get_proof_status",
        args:         [campaignId],
    });
}

// ── Contract Write Helpers ────────────────────────────────────────────────────

/**
 * Creates a new sponsorship campaign on-chain.
 * @param {string} accountAddress   Connected wallet address
 * @param {string} rules            Plain-English validation rules
 * @param {number} budget           GL token budget
 * @returns {Promise<string>}       Transaction hash
 */
export async function createCampaign(accountAddress, rules, budget) {
    const client = getWriteClient(accountAddress);
    return await client.writeContract({
        address:      CONTRACT_ADDRESS,
        functionName: "create_campaign",
        args:         [rules, budget],
        account:      accountAddress,
    });
}

/**
 * Submits creator proof URL to the contract and triggers LLM evaluation.
 * @param {string} accountAddress   Connected wallet address
 * @param {string} campaignId       Target campaign ID
 * @param {string} proofUrl         Publicly-accessible URL
 * @returns {Promise<string>}       Transaction hash
 */
export async function verifyAndPay(accountAddress, campaignId, proofUrl) {
    const client = getWriteClient(accountAddress);
    return await client.writeContract({
        address:      CONTRACT_ADDRESS,
        functionName: "verify_and_pay",
        args:         [campaignId, proofUrl, accountAddress],
        account:      accountAddress,
    });
}