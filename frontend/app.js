// app.js
import { getGenLayerClient, CONTRACT_ADDRESS } from "./genlayerClient.js";
import { TransactionStatus, ExecutionResult } from "https://esm.sh/genlayer-js/types";

let currentAccount = null;

// UI Toast Notification Helper
function showNotification(message, isError = false) {
    const toast = document.getElementById("toast");
    if (!toast) return;
    toast.textContent = message;
    toast.className = `fixed bottom-5 right-5 px-6 py-3 rounded-lg font-semibold transition-all duration-300 ${isError ? "bg-red-600 text-white" : "bg-[#00FFB2] text-[#121214]"
        }`;
    setTimeout(() => { toast.className = "hidden"; }, 5000);
}

// 🦊 Connect MetaMask Wallet
async function connectWallet() {
    if (typeof window.ethereum !== "undefined") {
        try {
            const accounts = await window.ethereum.request({ method: "eth_requestAccounts" });
            currentAccount = accounts[0];

            const client = getGenLayerClient(currentAccount);
            // Sync MetaMask network configuration with GenLayer Studionet RPC
            await client.connect("studionet");

            document.getElementById("btn-connect").textContent = `Connected: ${currentAccount.substring(0, 6)}...`;
            showNotification("Wallet linked to GenLayer successfully!");
        } catch (error) {
            console.error(error);
            showNotification("Wallet connection rejected.", true);
        }
    } else {
        showNotification("MetaMask not detected! Please open inside a Web3-compatible browser.", true);
    }
}

// 🏢 Sponsor Portal: Create Campaign & Deposit Crypto Funds
async function handleCreateCampaign(event) {
    event.preventDefault();
    if (!currentAccount) return showNotification("Please connect your wallet first!", true);

    const campaignId = document.getElementById("sponsor-campaign-id").value;
    const rulesStr = document.getElementById("sponsor-rules").value;
    const amountEth = document.getElementById("sponsor-amount").value;

    if (!campaignId || !rulesStr || !amountEth) return showNotification("Please fill in all campaign fields.", true);

    const submitBtn = document.getElementById("btn-create-campaign");
    submitBtn.disabled = true;
    submitBtn.textContent = "Deploying Escrow Logic...";

    try {
        const client = getGenLayerClient(currentAccount);

        // GenLayer uses blockchain integers (BigInt). Converting eth/tokens to fundamental values
        const valueWei = BigInt(parseFloat(amountEth) * 1e18);

        const txHash = await client.writeContract({
            address: CONTRACT_ADDRESS,
            functionName: "create_campaign",
            args: [BigInt(campaignId), rulesStr],
            value: valueWei,
        });

        showNotification("Transaction sent! Waiting for block inclusion...");

        // Wait until transaction is finalized into a block
        const receipt = await client.waitForTransactionReceipt({
            hash: txHash,
            status: TransactionStatus.FINALIZED,
        });

        if (receipt.txExecutionResultName === ExecutionResult.SUCCESS) {
            showNotification(`Campaign #${campaignId} live! Funds securely locked.`);
            event.target.reset();
        } else {
            showNotification("Execution reverted. Check contract criteria rules.", true);
        }
    } catch (error) {
        console.error(error);
        showNotification(error.message || "Failed to establish campaign escrow.", true);
    } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Lock Funds & Create Campaign";
    }
}

// 🧑‍💻 Creator Portal: Submit URL Proof for AI Adjudication
async function handleVerifyPayout(event) {
    event.preventDefault();
    if (!currentAccount) return showNotification("Please connect your wallet first!", true);

    const campaignId = document.getElementById("creator-campaign-id").value;
    const proofUrl = document.getElementById("creator-proof-url").value;
    const payoutAddress = document.getElementById("creator-payout-address").value;

    if (!campaignId || !proofUrl || !payoutAddress) return showNotification("All verification fields are required.", true);

    const verifyBtn = document.getElementById("btn-verify-payout");
    verifyBtn.disabled = true;
    verifyBtn.innerHTML = `<span>GenLayer Voting in Progress... 🤖</span>`;

    try {
        const client = getGenLayerClient(currentAccount);

        const txHash = await client.writeContract({
            address: CONTRACT_ADDRESS,
            functionName: "verify_and_pay",
            args: [BigInt(campaignId), proofUrl, payoutAddress],
        });

        showNotification("AI Jury is analyzing proof content...");

        const receipt = await client.waitForTransactionReceipt({
            hash: txHash,
            status: TransactionStatus.FINALIZED,
        });

        if (receipt.txExecutionResultName === ExecutionResult.SUCCESS) {
            showNotification("Success! GenLayer LLM verified the proof. Payout distributed!", false);
            event.target.reset();
        } else {
            showNotification("Verification Failed. Content did not meet the plain-English criteria.", true);
        }
    } catch (error) {
        console.error(error);
        showNotification(error.message || "AI Verification cycle encountered an issue.", true);
    } finally {
        verifyBtn.disabled = false;
        verifyBtn.textContent = "Claim & Verify Payout";
    }
}

// Initialize Frontend DOM Bindings
document.addEventListener("DOMContentLoaded", () => {
    document.getElementById("btn-connect").addEventListener("click", connectWallet);
    document.getElementById("form-sponsor").addEventListener("submit", handleCreateCampaign);
    document.getElementById("form-creator").addEventListener("submit", handleVerifyPayout);
});