// ════════════════════════════════════════════════════════════════
//  AIMS Gateway Console v2 — Core Business Logic
//  Extracted from monolithic console.html for modular maintainability
//  ════════════════════════════════════════════════════════════════

// ── Auth Guard ─────────────────────────────────────────────────
(function() {
  const jwt = localStorage.getItem("aims_jwt");
  if (!jwt) { window.location.href = "/login"; }
})();

// ── Configuration ──────────────────────────────────────────────
const API_BASE = localStorage.getItem("aims_api_base") || "";
const CONTRACT_ADDRESS = localStorage.getItem("aims_contract_addr") || "0x5FbDB2315678afecb367f032d93F642f64180aa3";

let signer = null;
let provider = null;
let walletAddress = "";
let currentRole = "consumer";
let workerInterval = null;
let workerStartTime = null;
let workerTaskCount = 0;
let workerEarnedUsdc = 0;
let devRevenueUsdc = 0;
let consumerTaskCount = 0;
let consumerDepositedUsdc = 0;
let skillsCache = [];
let usedTrials = {};  // {skill_id: true} — tracks trial consumption

// ── Toast system ───────────────────────────────────────────────
function toast(msg, type = "info") {
  try {
    const container = document.getElementById("toastContainer");
    if (!container) { console.warn("toast:", type, msg); return; }
    const el = document.createElement("div");
    el.className = `toast ${type}`;
    el.textContent = msg;
    container.appendChild(el);
    setTimeout(() => el.remove(), 4000);
  } catch (e) { console.warn("toast error:", e.message, "msg:", msg); }
}

// ── Pipeline progress — 6 steps ────────────────────────────────
function resetPipeline() {
  document.querySelectorAll(".pipeline-step").forEach(s => { s.classList.remove("done", "active", "trial"); });
  const ps = document.getElementById("pipelineStatus");
  if (ps) { ps.textContent = "Idle"; ps.style.color = ""; }
}

function setTrialStep() {
  const steps = document.querySelectorAll(".pipeline-step");
  if (steps[1]) steps[1].classList.add("trial");
}

function advancePipeline(step) {
  const steps = document.querySelectorAll(".pipeline-step");
  steps.forEach((s, i) => {
    s.classList.remove("active");
    if (i < step) s.classList.add("done");
  });
  if (step < steps.length) {
    steps[step].classList.add("active");
    const labels = [
      "Authenticating…", "Checking free trial eligibility…",
      "Verifying on-chain balance…", "Executing skill task…",
      "Generating Proof-of-Task…", "Settling 70/25/5 split…",
    ];
    const ps = document.getElementById("pipelineStatus");
    if (ps) {
      ps.textContent = labels[step] || `Step ${step + 1}/6`;
      ps.style.color = "";
    }
  } else {
    completePipeline();
  }
}

function completePipeline() {
  document.querySelectorAll(".pipeline-step").forEach(s => { s.classList.remove("active"); s.classList.add("done"); });
  const ps = document.getElementById("pipelineStatus");
  if (ps) { ps.textContent = "✅ Complete"; ps.style.color = "var(--neon)"; }
}

// ── Wallet connection ──────────────────────────────────────────
async function connectWallet() {
  resetPipeline();
  if (typeof window.ethereum === "undefined") {
    toast("MetaMask not found — install from metamask.io", "error");
    return;
  }
  try {
    advancePipeline(0);
    provider = new ethers.BrowserProvider(window.ethereum);
    const accounts = await provider.send("eth_requestAccounts", []);
    signer = await provider.getSigner();
    walletAddress = accounts[0].toLowerCase();

    const btn = document.getElementById("connectBtn");
    if (btn) {
      btn.textContent = `● ${walletAddress.slice(0,6)}…${walletAddress.slice(-4)}`;
      btn.classList.add("connected");
    }
    const addrEl = document.getElementById("walletAddress");
    if (addrEl) addrEl.textContent = walletAddress;
    const cfgWallet = document.getElementById("cfgWallet");
    if (cfgWallet) { cfgWallet.textContent = walletAddress; cfgWallet.style.color = "var(--neon)"; }

    const trialBadge = document.getElementById("trialBadge");
    if (trialBadge) trialBadge.style.display = "inline-flex";

    const net = await provider.getNetwork();
    const netBadge = document.getElementById("networkBadge");
    if (netBadge) {
      if (net.chainId === 31337n) { netBadge.textContent = "● Anvil (31337)"; netBadge.className = "network-badge warn"; }
      else if (net.chainId === 8453n) { netBadge.textContent = "● Base Mainnet"; netBadge.className = "network-badge ok"; }
      else if (net.chainId === 84532n) { netBadge.textContent = "● Base Sepolia"; netBadge.className = "network-badge warn"; }
      else { netBadge.textContent = `● Chain ${net.chainId}`; netBadge.className = "network-badge warn"; }
    }
    const cfgNet = document.getElementById("cfgNetwork");
    if (cfgNet) cfgNet.textContent = net.name || `Chain ${net.chainId}`;

    toast(`Wallet connected: ${walletAddress}`, "success");
    await refreshBalance();
    await fetchDiscovery();
    await fetchCreditScore();
    await fetchHealth();
    await fetchHistory('');

    const currentNet = await provider.getNetwork();
    if (currentNet.chainId !== 84532n && currentNet.chainId !== 8453n) {
      if (confirm("Switch to Base Sepolia (testnet) for on-chain settlement?")) {
        try {
          await provider.send("wallet_switchEthereumChain", [{ chainId: "0x14a34" }]);
          toast("Switched to Base Sepolia", "success");
        } catch (switchErr) {
          if (switchErr.code === 4902) {
            try {
              await provider.send("wallet_addEthereumChain", [{
                chainId: "0x14a34", chainName: "Base Sepolia",
                nativeCurrency: { name: "ETH", symbol: "ETH", decimals: 18 },
                rpcUrls: ["https://sepolia.base.org"],
                blockExplorerUrls: ["https://sepolia.basescan.org"],
              }]);
              toast("Added & switched to Base Sepolia", "success");
            } catch (addErr) {
              toast("Could not add Base Sepolia: " + addErr.message, "warn");
            }
          } else { toast("Could not switch network: " + switchErr.message, "warn"); }
        }
      }
    }
    await signAuthBeacon("system");
    return true;
  } catch (err) {
    toast(`Wallet connection failed: ${err.message}`, "error");
    return false;
  }
}

// ── EIP-191 signing ────────────────────────────────────────────
async function eip191SignBody(bodyBytes) {
  return await signer.signMessage(new Uint8Array(bodyBytes));
}

function getAuthHeaders(bodyBytes, signature) {
  const sigHex = signature.startsWith("0x") ? signature.slice(2) : signature;
  const headers = {
    "X-Wallet-Address": walletAddress,
    "X-Signature": sigHex,
    "X-Timestamp": Math.floor(Date.now() / 1000).toString(),
    "Content-Type": "application/json",
  };
  const jwt = localStorage.getItem("aims_jwt");
  if (jwt) headers["Authorization"] = "Bearer " + jwt;
  return headers;
}

function jwtHeaders() {
  const jwt = localStorage.getItem("aims_jwt");
  return jwt ? { "Authorization": "Bearer " + jwt, "Content-Type": "application/json" } : { "Content-Type": "application/json" };
}

async function smartHeaders(body) {
  const bodyBytes = body ? new TextEncoder().encode(body) : null;
  if (walletAddress && signer) {
    try {
      const sig = await eip191SignBody(bodyBytes || new TextEncoder().encode("{}"));
      return getAuthHeaders(bodyBytes || new TextEncoder().encode("{}"), sig);
    } catch (e) { console.warn("EIP-191 signing unavailable, falling back to JWT:", e.message); }
  }
  const jwt = localStorage.getItem("aims_jwt");
  return jwt ? { "Authorization": "Bearer " + jwt, "Content-Type": "application/json" } : { "Content-Type": "application/json" };
}

// ── AIMS_GATEWAY_AUTH Beacon ──────────────────────────────────
async function signAuthBeacon(skillId) {
  if (!walletAddress || !signer) return null;
  const message = `AIMS_GATEWAY_AUTH:${walletAddress}:${skillId}`;
  try {
    const sig = await signer.signMessage(message);
    const sigHex = sig.startsWith("0x") ? sig.slice(2) : sig;
    const resp = await fetch(`${API_BASE}/api/auth/pre-check`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, signature: sigHex }),
    });
    if (resp.ok) {
      const data = await resp.json();
      if (data.verified) {
        consumerLog("success", `🔐 Auth beacon verified — wallet=${walletAddress.slice(0,10)}… skill=${skillId}`);
        return true;
      }
    }
    consumerLog("error", `⚠️ Auth beacon rejected for skill=${skillId}`);
    return false;
  } catch (err) { console.warn("Auth beacon failed:", err.message); return false; }
}

// ── Balance & Deposit ──────────────────────────────────────────
async function refreshBalance() {
  if (!walletAddress) return;
  try {
    const resp = await fetch(`${API_BASE}/api/wallet/balance?user_id=${walletAddress}`);
    if (resp.ok) {
      const data = await resp.json();
      const balance = data.credits || 0;
      const cb = document.getElementById("consumerBalance");
      if (cb) cb.innerHTML = `${balance.toFixed(2)} <span class="unit">USDC</span>`;
      const bd = document.getElementById("balanceDisplay");
      if (bd) bd.style.display = "flex";
      const wb = document.getElementById("walletBalance");
      if (wb) wb.textContent = balance.toFixed(2);
    } else {
      const cb = document.getElementById("consumerBalance");
      if (cb) cb.innerHTML = `— <span class="unit">USDC</span>`;
    }
  } catch (err) {
    const cb = document.getElementById("consumerBalance");
    if (cb) cb.innerHTML = `⚠️ <span class="unit">offline</span>`;
  }
}

function showDepositModal(balanceUsdc, isTrialEligible) {
  const mb = document.getElementById("modalBody");
  if (mb) {
    mb.innerHTML = `Each skill invocation requires a minimum of <strong>0.05 USDC</strong>. Your current available balance is <strong>${balanceUsdc.toFixed(2)} USDC</strong>.`;
  }
  const mca = document.getElementById("modalContractAddr");
  if (mca) mca.textContent = CONTRACT_ADDRESS;
  const tn = document.getElementById("modalTrialNotice");
  if (tn) tn.style.display = isTrialEligible ? "block" : "none";
  const dm = document.getElementById("depositModal");
  if (dm) dm.classList.add("open");
}

function closeDepositModal() {
  const dm = document.getElementById("depositModal");
  if (dm) dm.classList.remove("open");
}

async function handleDeposit() {
  if (!walletAddress) { toast("Connect wallet first", "error"); return; }
  closeDepositModal();
  toast("Depositing 50 USDC…", "info");
  try {
    const body = JSON.stringify({ user_id: walletAddress, amount: 50.0 });
    const headers = await smartHeaders(body);
    const resp = await fetch(`${API_BASE}/api/wallet/deposit`, { method: "POST", headers, body });
    if (resp.ok) {
      const data = await resp.json();
      consumerDepositedUsdc += 50;
      const cd = document.getElementById("consumerDeposited");
      if (cd) cd.innerHTML = `${consumerDepositedUsdc.toFixed(2)} <span class="unit">USDC</span>`;
      toast("Deposit successful! New balance: " + data.new_balance.toFixed(2) + " USDC", "success");
      consumerLog("success", "Deposit 50 USDC → new balance " + data.new_balance.toFixed(2) + " USDC");
      await refreshBalance();
    } else {
      const err = await resp.json();
      toast("Deposit failed: " + (err.detail || resp.statusText), "error");
    }
  } catch (err) { toast("Deposit error: " + err.message, "error"); }
}

// ── Skills Discovery ───────────────────────────────────────────
async function fetchDiscovery() {
  try {
    const resp = await fetch(`${API_BASE}/api/discovery`);
    if (!resp.ok) {
      const sc = document.getElementById("skillsContent");
      if (sc) sc.innerHTML = '<div class="empty-state">API unreachable</div>';
      return;
    }
    const data = await resp.json();
    skillsCache = data.skills || [];

    // Populate skill select
    const sel = document.getElementById("skillSelect");
    if (sel) {
      sel.innerHTML = '<option value="">— Select a skill —</option>';
      skillsCache.forEach(s => {
        const opt = document.createElement("option");
        opt.value = s.id;
        opt.textContent = `${s.id} — ${(s.description || "").slice(0,40)}`;
        sel.appendChild(opt);
      });
    }

    // Populate Publish Task skill select
    const pubSel = document.getElementById("pubSkillSelect");
    if (pubSel) {
      pubSel.innerHTML = '<option value="">— Select skill —</option>';
      skillsCache.forEach(s => {
        const opt = document.createElement("option");
        opt.value = s.id;
        opt.textContent = `${s.id} — ${(s.description || "").slice(0,40)}`;
        pubSel.appendChild(opt);
      });
    }

    // Populate skills panel
    const container = document.getElementById("skillsContent");
    if (container) {
      if (skillsCache.length === 0) {
        container.innerHTML = '<div class="empty-state">No skills registered</div>';
      } else {
        container.innerHTML = skillsCache.map(s => `
          <div class="skill-card" style="margin-bottom:0.4rem">
            <div>
              <div class="name">${s.id}</div>
              <div class="desc">${(s.description || "").slice(0,60)}</div>
              <div class="caps">${(s.capabilities||[]).map(c => `<span class="cap-tag">${c}</span>`).join("")}</div>
            </div>
          </div>
        `).join("");
      }
    }

    // Update dev skill count
    const dsc = document.getElementById("devSkillCount");
    if (dsc) dsc.textContent = skillsCache.length;
    const dsl = document.getElementById("devSkillList");
    if (dsl) {
      dsl.innerHTML = skillsCache.map(s =>
        `<div style="display:flex;justify-content:space-between;padding:0.3rem 0;font-size:0.75rem;border-bottom:1px solid rgba(255,255,255,0.03)">
          <span style="color:#fff">${s.id}</span>
          <span style="color:var(--text-dim)">v${s.manifest?.version || "—"}</span>
        </div>`
      ).join("");
    }

    // Dev settlements
    const settlementsEl = document.getElementById("devSettlements");
    if (settlementsEl && skillsCache.length > 0) {
      settlementsEl.innerHTML = `<div style="font-size:0.75rem;color:var(--text-dim)">${skillsCache.length} skills registered on network.<br/>Revenue will appear here after tasks are executed and settled.</div>`;
    }

    toast(`Discovered ${skillsCache.length} skills`, "info");
  } catch (err) {
    const sc = document.getElementById("skillsContent");
    if (sc) sc.innerHTML = '<div class="empty-state">⚠️ ' + err.message + '</div>';
  }
}

// ── Invoke Skill ───────────────────────────────────────────────
async function invokeSkill(event) {
  event.preventDefault();
  if (!walletAddress) { toast("Connect your wallet first", "error"); return; }

  const skillId = document.getElementById("skillSelect")?.value;
  if (!skillId) { toast("Select a skill", "error"); return; }

  let params = {};
  try { params = JSON.parse(document.getElementById("skillParams")?.value || "{}"); } catch(e) {
    toast("Invalid params JSON", "error"); return;
  }

  const billingMode = document.getElementById("billingMode")?.value || "pay_per_task";
  const isTrial = billingMode === "trial";

  if (isTrial && usedTrials[skillId]) {
    toast(`Free trial already used for "${skillId}". Select a billing mode.`, "warn");
    const bm = document.getElementById("billingMode");
    if (bm) bm.value = "pay_per_task";
    return;
  }

  const worker = document.getElementById("workerAddr")?.value.trim() || "0x70997970C51812dc3A010C7d01b50e0d17dc79C8";
  const developer = document.getElementById("devAddr")?.value.trim() || "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266";

  const invokeBtn = document.getElementById("invokeBtn");
  if (invokeBtn) { invokeBtn.disabled = true; invokeBtn.textContent = "⏳ Executing…"; }

  resetPipeline();

  try {
    advancePipeline(0);
    const bodyPayload = {
      skill_id: skillId, params, user_id: walletAddress,
      developer_premium: 0.01, max_budget: 2.0, compute_tier: 1,
      billing_mode: billingMode,
    };
    const bodyStr = JSON.stringify(bodyPayload);
    const bodyBytes = new TextEncoder().encode(bodyStr);

    const beaconOk = await signAuthBeacon(skillId);
    if (!beaconOk) consumerLog("warn", "Auth beacon not confirmed — continuing with EIP-191 only");

    advancePipeline(1);
    if (isTrial) {
      setTrialStep();
      consumerLog("trial", `🎁 Free trial: skill=${skillId} (1st invocation, 0 USDC)`);
      toast(`Using free trial for "${skillId}" — zero cost`, "trial");
    }
    const sig = await eip191SignBody(bodyBytes);
    const headers = getAuthHeaders(bodyBytes, sig);

    advancePipeline(2);
    advancePipeline(3);
    consumerLog("info", `POST /api/run → skill=${skillId} mode=${billingMode} address=${walletAddress.slice(0,10)}…`);

    const resp = await fetch(`${API_BASE}/api/run`, { method: "POST", headers, body: bodyStr });

    if (resp.status === 402) {
      const errData = await resp.json().catch(() => ({}));
      const balanceMatch = errData.detail ? errData.detail.match(/balance:\s*([\d.]+)/) : null;
      const bal = balanceMatch ? parseFloat(balanceMatch[1]) : 0;
      consumerLog("error", `402 Insufficient balance: ${bal} USDC`);
      resetPipeline();
      showDepositModal(bal, isTrial && !usedTrials[skillId]);
      if (invokeBtn) { invokeBtn.disabled = false; invokeBtn.textContent = "▶ Execute & Settle"; }
      return;
    }
    if (resp.status === 403) {
      const errData = await resp.json().catch(() => ({}));
      consumerLog("error", `403 Auth failed: ${errData.detail || "signature mismatch"}`);
      toast("Auth failed — signature rejected by gateway", "error");
      resetPipeline();
      if (invokeBtn) { invokeBtn.disabled = false; invokeBtn.textContent = "▶ Execute & Settle"; }
      return;
    }
    if (!resp.ok) {
      const errData = await resp.json().catch(() => ({}));
      consumerLog("error", `HTTP ${resp.status}: ${errData.detail || resp.statusText}`);
      toast(`API error: ${errData.detail || resp.statusText}`, "error");
      resetPipeline();
      if (invokeBtn) { invokeBtn.disabled = false; invokeBtn.textContent = "▶ Execute & Settle"; }
      return;
    }

    const data = await resp.json();
    const taskId = data.task_id;
    if (isTrial) {
      usedTrials[skillId] = true;
      updateTrialDisplay();
      consumerLog("trial", `🎁 Free trial consumed for "${skillId}". Task: ${taskId}`);
    }
    consumerLog("success", `Task created: ${taskId}`);

    advancePipeline(4);
    let settled = false;
    for (let i = 0; i < 30; i++) {
      await new Promise(r => setTimeout(r, 1000));
      try {
        const statusResp = await fetch(`${API_BASE}/api/tasks/${taskId}/status`);
        if (statusResp.ok) {
          const statusData = await statusResp.json();
          if (statusData.status === "SUCCESS" || statusData.pot) {
            consumerLog("success", `Task completed — Pot: ${statusData.pot ? statusData.pot.slice(0,20) + "…" : "N/A"}`);
            settled = true;
            break;
          }
          if (statusData.status === "FAILED") {
            consumerLog("error", `Task failed: ${statusData.outcome || "unknown"}`);
            if (isTrial) { delete usedTrials[skillId]; updateTrialDisplay(); consumerLog("trial", "🎁 Free trial restored — failure doesn't count"); }
            break;
          }
        }
      } catch(e) { console.warn("invokeSkill — status poll:", e.message); }
    }

    if (settled) {
      advancePipeline(5);
      await new Promise(r => setTimeout(r, 600));
      completePipeline();
      consumerTaskCount++;
      const ct = document.getElementById("consumerTasks");
      if (ct) ct.textContent = consumerTaskCount;

      devRevenueUsdc += 0.035; workerEarnedUsdc += 0.0125;
      const dr = document.getElementById("devRevenue");
      if (dr) dr.innerHTML = `${devRevenueUsdc.toFixed(4)} <span class="unit">USDC</span>`;
      const drm = document.getElementById("devRevenueMeter");
      if (drm) drm.style.width = Math.min(devRevenueUsdc * 20, 100) + "%";
      const we = document.getElementById("workerEarnings");
      if (we) we.innerHTML = `${workerEarnedUsdc.toFixed(4)} <span class="unit">USDC</span>`;
      const wem = document.getElementById("workerEarningsMeter");
      if (wem) wem.style.width = Math.min(workerEarnedUsdc * 20, 100) + "%";

      consumerLog("success", `🎉 Task ${taskId} settled — 70/25/5 on-chain split complete`);
      toast("Task settled on-chain! 70/25/5 split executed.", "success");
    } else {
      consumerLog("warn", `Task ${taskId} created but not yet settled (still PENDING)`);
      toast("Task submitted, waiting for Worker to pick it up…", "warn");
    }
    await refreshBalance();
  } catch (err) {
    consumerLog("error", `Error: ${err.message}`);
    toast("Execution error: " + err.message, "error");
  }
  if (invokeBtn) { invokeBtn.disabled = false; invokeBtn.textContent = "▶ Execute & Settle"; }
}

// ── Credit Score & Level ───────────────────────────────────────
function getCreditLevel(score) {
  if (score >= 95) return { level: "AAA", color: "#22c55e", label: "Elite" };
  if (score >= 85) return { level: "AA", color: "#34d399", label: "Excellent" };
  if (score >= 70) return { level: "A", color: "var(--neon)", label: "Good" };
  if (score >= 50) return { level: "B", color: "var(--amber)", label: "Fair" };
  return { level: "C", color: "var(--red)", label: "Poor" };
}

const fetchCreditScore = async function() {
  if (!walletAddress) return;
  try {
    const resp = await fetch(`${API_BASE}/api/worker/credit-score/${walletAddress}`);
    if (!resp.ok) return;
    const data = await resp.json();
    const score = data.score || 0;
    const level = getCreditLevel(score);

    const se = document.getElementById("creditScoreDisplay");
    if (se) se.textContent = score;
    const sbar = document.getElementById("creditScoreBar");
    if (sbar) sbar.style.width = score + "%";
    const badge = document.getElementById("creditLevelBadge");
    if (badge) {
      badge.textContent = `${level.level} — ${level.label}`;
      badge.style.background = score >= 70 ? "rgba(34,197,94,0.1)" : score >= 50 ? "rgba(251,191,36,0.1)" : "rgba(255,107,107,0.1)";
      badge.style.color = score >= 70 ? "#22c55e" : score >= 50 ? "var(--amber)" : "var(--red)";
      badge.style.border = `1px solid ${level.color}`;
    }
    const dcs = document.getElementById("devCreditScore");
    if (dcs) dcs.textContent = score;
    const dcb = document.getElementById("devCreditScoreBar");
    if (dcb) dcb.style.width = score + "%";
    const dl = document.getElementById("devCreditLevel");
    if (dl) dl.textContent = `${level.level} — ${level.label}`;
  } catch (e) { console.warn("fetchCreditScore:", e.message); }
};

function updateTrialDisplay() {
  const used = Object.keys(usedTrials).length;
  const total = skillsCache.length || 1;
  const remaining = Math.max(0, total - used);
  const tl = document.getElementById("trialsLeft");
  if (tl) tl.innerHTML = `${remaining} <span class="unit">/ ${total} Skills</span>`;
  const te = document.getElementById("trialsLeftEnhanced");
  if (te) te.textContent = remaining === 0 ? "0 — Purchase a plan" : `${remaining} / ${total}`;
  const pt = document.getElementById("trialProgressText");
  if (pt) pt.textContent = `${used} / ${total} Skills used`;
  const pb = document.getElementById("trialProgressBar");
  if (pb) { const pct = total > 0 ? (used / total) * 100 : 0; pb.style.width = Math.min(pct, 100) + "%"; }
}

// ── Commerce / Billing Mode ───────────────────────────────────
function switchBillingMode(mode) {
  const bm = document.getElementById("billingMode");
  if (bm) bm.value = mode;
  const display = document.getElementById("currentBillingModeDisplay");
  const desc = document.getElementById("commerceModeDesc");
  const labels = { "pay_per_task": "Metered", "subscription": "Subscription", "buyout": "Buyout", "trial": "Free Trial" };
  const descs = {
    "pay_per_task": "Pay per successful invocation. No commitments, no expiration.",
    "subscription": "Monthly pass with guaranteed rate limits, cancel anytime.",
    "buyout": "One-time perpetual license. No recurring fees, unlimited usage.",
    "trial": "First invocation free per Skill. Zero USDC required.",
  };
  if (display) {
    display.textContent = labels[mode] || "Metered";
    display.style.color = mode === "trial" ? "#34d399" : "var(--neon)";
  }
  if (desc) desc.textContent = descs[mode] || "";
  document.querySelectorAll("#commercePanel .btn-outline").forEach(b => {
    b.classList.toggle("active", b.dataset.mode === mode);
  });
  toast(`Switched to ${labels[mode] || mode}`, "info");
}

// ── Buyout Perpetual License ───────────────────────────────────
function openBuyoutModal() {
  if (!walletAddress) { toast("Connect your wallet first", "error"); return; }
  const skillId = document.getElementById("skillSelect")?.value || "—";
  const bsn = document.getElementById("buyoutSkillName");
  if (bsn) bsn.textContent = skillId;
  if (!document.getElementById("skillSelect")?.value) toast("Select a skill first to see buyout pricing", "warn");
  const bm = document.getElementById("buyoutModal");
  if (bm) bm.classList.add("open");
}

function closeBuyoutModal() {
  const bm = document.getElementById("buyoutModal");
  if (bm) bm.classList.remove("open");
}

async function confirmBuyout() {
  if (!walletAddress) { toast("Connect wallet first", "error"); return; }
  const skillId = document.getElementById("skillSelect")?.value;
  if (!skillId) { toast("Select a skill first", "error"); return; }
  closeBuyoutModal();
  toast(`Processing buyout for "${skillId}"…`, "info");
  try {
    const body = JSON.stringify({ skill_id: skillId, user_id: walletAddress, license_type: "buyout", price_usdc: 25.0 });
    const headers = await smartHeaders(body);
    const resp = await fetch(`${API_BASE}/api/licensing/request-key`, { method: "POST", headers, body });
    if (resp.ok) {
      toast(`✅ Buyout license acquired for "${skillId}" — perpetual access granted`, "success");
      consumerLog("success", `🔒 Buyout perpetual license purchased for skill=${skillId} (25.0 USDC)`);
      switchBillingMode("buyout");
    } else {
      const err = await resp.json().catch(() => ({}));
      toast("Buyout failed: " + (err.detail || resp.statusText), "error");
    }
  } catch (err) { toast("Buyout error: " + err.message, "error"); }
}

// ── Publish Task ───────────────────────────────────────────────
function toggleCreditReq() {
  const group = document.getElementById("creditReqGroup");
  if (group) group.style.display = document.getElementById("pubIsCustom")?.checked ? "flex" : "none";
}

const publishTask = async function(event) {
  event.preventDefault();
  if (!walletAddress) { toast("Connect your wallet first", "error"); return; }

  const skillId = document.getElementById("pubSkillSelect")?.value;
  if (!skillId) { toast("Select a skill", "error"); return; }

  const taskName = document.getElementById("pubTaskName")?.value.trim();
  if (!taskName) { toast("Enter a task name", "error"); return; }

  const budget = parseFloat(document.getElementById("pubBudget")?.value);
  if (!budget || budget < 0.05) { toast("Minimum budget is 0.05 USDC", "error"); return; }

  const isCustom = document.getElementById("pubIsCustom")?.checked || false;
  const creditReq = isCustom ? parseInt(document.getElementById("pubCreditReq")?.value) || 90 : 0;
  const description = document.getElementById("pubDescription")?.value.trim() || "";
  const resultEl = document.getElementById("publishResult");
  const btn = document.getElementById("publishBtn");

  if (btn) { btn.disabled = true; btn.textContent = "⏳ Publishing…"; }
  if (resultEl) resultEl.innerHTML = "";

  try {
    const body = JSON.stringify({
      skill_id: skillId, params: {}, user_id: walletAddress,
      developer_premium: 0.01, max_budget: budget, compute_tier: 1,
      task_name: taskName, description, is_custom: isCustom,
      credit_score_required: creditReq,
    });
    const headers = await smartHeaders(body);
    const resp = await fetch(`${API_BASE}/api/tasks/publish`, { method: "POST", headers, body });

    if (resp.ok) {
      const data = await resp.json();
      if (resultEl) resultEl.innerHTML = `<span class="pub-success">✅ Published: ${data.task_id} (escrow frozen: ${budget.toFixed(2)} USDC)</span>`;
      consumerLog("success", `📤 Publish Task: ${data.task_id} name="${taskName}" budget=${budget} custom=${isCustom}`);
      toast(`Task published: ${data.task_id}`, "success");
      if (data.vault_address) showVaultPanel(data.task_id, data.vault_address, data.vault_status);
      const ptn = document.getElementById("pubTaskName");
      if (ptn) ptn.value = "";
      const pd = document.getElementById("pubDescription");
      if (pd) pd.value = "";
      const pic = document.getElementById("pubIsCustom");
      if (pic) pic.checked = false;
      toggleCreditReq();
    } else {
      const err = await resp.json().catch(() => ({}));
      if (resultEl) resultEl.innerHTML = `<span class="pub-error">❌ Publish failed: ${err.detail || resp.statusText}</span>`;
      toast("Publish failed: " + (err.detail || resp.statusText), "error");
    }
  } catch (err) {
    if (resultEl) resultEl.innerHTML = `<span class="pub-error">❌ Error: ${err.message}</span>`;
    toast("Publish error: " + err.message, "error");
  }
  if (btn) { btn.disabled = false; btn.textContent = "📤 Publish to Task Market"; }
};

// ── Task Market ────────────────────────────────────────────────
const fetchPendingTasks = async function() {
  const container = document.getElementById("taskMarketBody");
  if (!container) return;
  try {
    const resp = await fetch(`${API_BASE}/api/tasks/pending`);
    if (!resp.ok) {
      container.innerHTML = '<div class="empty-state"><div class="big-icon">⚠️</div>Market API unavailable</div>';
      return;
    }
    const data = await resp.json();
    const tasks = data.tasks || [];
    const mpc = document.getElementById("mkPendingCount");
    if (mpc) mpc.textContent = `Pending: ${data.count || 0}`;

    if (tasks.length === 0) {
      container.innerHTML = '<div class="empty-state"><div class="big-icon">🛒</div>No pending tasks yet. Publish one from the Consumer tab!</div>';
      return;
    }

    container.innerHTML = tasks.map(t => {
      const isCustom = t.is_custom;
      const creditReq = t.credit_score_required || 0;
      const creditLabel = isCustom ? `<span class="mt-credit block">🔒 ≥${creditReq}</span>` : `<span class="mt-credit ok">✓ Open</span>`;
      return `<div class="mt-row">
        <span class="mt-id">${(t.task_id || "").slice(0,12)}</span>
        <span class="mt-name">${t.task_name || t.skill_id}<span class="boost-badge" id="boostBadge-${t.task_id}" style="display:none"></span></span>
        <span class="mt-skill">${t.skill_id || "—"}</span>
        <span class="mt-budget">$${(t.max_budget || 0).toFixed(2)}</span>
        ${creditLabel}
        <span class="mt-action" style="display:flex;gap:.25rem;align-items:center;min-width:140px;justify-content:flex-end">
          <button class="btn btn-sm boost-btn" onclick="boostFromMarket('${t.task_id}')" title="Boost Reward" style="padding:.25rem .5rem;font-size:.6rem">⚡</button>
          <button class="btn btn-sm ${isCustom ? 'btn-plg' : 'btn-outline'}" onclick="claimTask('${t.task_id}', ${creditReq}, ${isCustom})" style="font-size:.6rem;padding:.25rem .5rem;white-space:nowrap">Claim</button>
        </span>
      </div>`;
    }).join("");
  } catch (err) {
    container.innerHTML = '<div class="empty-state"><div class="big-icon">⚠️</div>Error: ' + err.message + '</div>';
  }
};

const claimTask = async function(taskId, creditReq, isCustom) {
  if (!walletAddress) { toast("Connect your wallet first", "error"); return; }
  let creditScore = 0;
  try {
    const csResp = await fetch(`${API_BASE}/api/worker/credit-score/${walletAddress}`);
    if (csResp.ok) { const csData = await csResp.json(); creditScore = csData.score || 0; }
  } catch(e) { console.warn("claimTask — credit score fetch:", e.message); }

  if (isCustom && creditScore < creditReq) { showCreditBlockModal(creditScore, creditReq, taskId); return; }

  toast(`Claiming ${taskId}…`, "info");
  try {
    const body = JSON.stringify({ task_id: taskId, worker_id: walletAddress, credit_score: creditScore });
    const headers = await smartHeaders(body);
    const resp = await fetch(`${API_BASE}/api/tasks/claim-specific`, { method: "POST", headers, body });
    if (resp.ok) {
      toast(`✅ Claimed ${taskId} successfully!`, "success");
      consumerLog("success", `🛒 Claimed task: ${taskId} credit=${creditScore}`);
      await fetchPendingTasks();
    } else if (resp.status === 403) {
      const err = await resp.json().catch(() => ({}));
      showCreditBlockModal(creditScore, err.credit_score_required || creditReq, taskId);
    } else {
      const err = await resp.json().catch(() => ({}));
      toast("Claim failed: " + (err.detail || resp.statusText), "error");
    }
  } catch (err) { toast("Claim error: " + err.message, "error"); }
};

function showCreditBlockModal(creditScore, required, taskId) {
  const body = document.getElementById("modalBody");
  const title = document.querySelector(".modal h3");
  if (title) title.textContent = "🔒 Credit Score Insufficient";
  if (body) {
    body.innerHTML =
      `<p><strong style="color:#fbbf24">Credit score too low</strong></p>` +
      `<p>Your credit score is <strong style="color:var(--red)">${creditScore}</strong>, ` +
      `but this task requires <strong style="color:#fbbf24">≥ ${required}</strong>.</p>` +
      `<p style="font-size:0.75rem;color:var(--text-dim)">` +
      `Complete open tasks (no credit gate) to build your reputation, or ask an admin to ` +
      `<code style="color:var(--neon)">POST /api/worker/credit-score</code> to raise your score.</p>` +
      `<p style="font-size:0.7rem;color:var(--text-dim)">Task: <code>${taskId}</code></p>`;
  }
  const dm = document.getElementById("depositModal");
  if (dm) dm.classList.add("open");
}

// ── One-Click Integration ──────────────────────────────────────
const oneClickIntegrate = async function(event) {
  event.preventDefault();
  if (!walletAddress) { toast("Connect your wallet first", "error"); return; }
  const input = document.getElementById("integrateInput")?.value.trim();
  if (!input) { toast("Enter a skill name or API URL", "error"); return; }
  const wallet = document.getElementById("integrateWallet")?.value.trim() || walletAddress;
  if (!wallet.startsWith("0x") || wallet.length !== 42) { toast("Enter a valid EVM wallet address (0x + 40 hex)", "error"); return; }

  const btn = document.getElementById("integrateBtn");
  if (btn) { btn.disabled = true; btn.textContent = "⏳ Integrating…"; }

  try {
    const contribRows = document.querySelectorAll("#coContribList .contributor-row");
    const coContributors = [];
    contribRows.forEach(r => {
      const inputs = r.querySelectorAll("input");
      if (inputs.length >= 2) {
        const w = inputs[0].value.trim();
        const p = parseFloat(inputs[1].value);
        if (w && w.startsWith("0x") && w.length === 42 && p > 0 && p <= 100) coContributors.push({ wallet: w, share_pct: p });
      }
    });
    const body = JSON.stringify({ skill_name_or_url: input, wallet_address: wallet, co_contributors: coContributors.length > 0 ? coContributors : undefined });
    const headers = await smartHeaders(body);
    const resp = await fetch(`${API_BASE}/api/developer/integrate`, { method: "POST", headers, body });
    const result = document.getElementById("integrateResult");
    if (resp.ok) {
      const data = await resp.json();
      const typeLabel = data.type === "url_proxy" ? "URL Proxy" : "Skill Mapping";
      if (result) result.innerHTML = `<div class="integrate-status success">✅ Mapped "${input}" → ${wallet.slice(0,10)}… (${typeLabel})</div>`;
      toast(`Integrated: ${input} → revenue to wallet`, "success");
      consumerLog("success", `🔗 One-Click Integrate: ${input} → ${wallet} (${typeLabel})`);
      const ii = document.getElementById("integrateInput");
      if (ii) ii.value = "";
      await fetchIntegrationStatus();
    } else {
      const err = await resp.json().catch(() => ({}));
      if (result) result.innerHTML = `<div class="integrate-status error">❌ Integration failed: ${err.detail || resp.statusText}</div>`;
      toast("Integration failed: " + (err.detail || resp.statusText), "error");
    }
  } catch (err) {
    const result = document.getElementById("integrateResult");
    if (result) result.innerHTML = `<div class="integrate-status error">❌ Error: ${err.message}</div>`;
    toast("Integration error: " + err.message, "error");
  }
  if (btn) { btn.disabled = false; btn.textContent = "🔗 One-Click Integrate"; }
};

const fetchIntegrationStatus = async function() {
  if (!walletAddress) return;
  try {
    const resp = await fetch(`${API_BASE}/api/developer/integration/${walletAddress}`);
    if (resp.ok) { const data = await resp.json(); const el = document.getElementById("integrateCount"); if (el) el.textContent = `Mapped: ${data.count || 0}`; }
  } catch(e) { console.warn("fetchIntegrationStatus:", e.message); }
};

// ── Vault Panel ────────────────────────────────────────────────
let _currentVaultTaskId = null;

function showVaultPanel(taskId, vaultAddress, vaultStatus) {
  _currentVaultTaskId = taskId;
  const panel = document.getElementById("vaultPanel");
  if (!panel) return;
  panel.style.display = "block";
  const vad = document.getElementById("vaultAddressDisplay");
  if (vad) vad.textContent = vaultAddress;
  const vti = document.getElementById("vaultTaskIdDisplay");
  if (vti) vti.textContent = taskId;
  const vbd = document.getElementById("vaultBalanceDisplay");
  if (vbd) vbd.textContent = "0.00 USDC";
  const badge = document.getElementById("vaultStatusBadge");
  if (badge) {
    badge.textContent = (vaultStatus || "unfunded").toUpperCase();
    badge.style.background = "rgba(148,163,184,0.1)";
    badge.style.color = "var(--text-dim)";
    badge.style.borderColor = "var(--border)";
  }
  const vpb = document.getElementById("vaultPayBtn");
  if (vpb) vpb.disabled = false;
  const vpr = document.getElementById("vaultPollResult");
  if (vpr) vpr.textContent = "";
  const qr = document.getElementById("qrMockPanel");
  if (qr) qr.style.display = "flex";
  const btd = document.getElementById("boostTotalDisplay");
  if (btd) btd.textContent = "Total boosted: 0.00 USDC";
  const br = document.getElementById("boostResult");
  if (br) br.textContent = "";
  const ba = document.getElementById("boostAmount");
  if (ba) ba.value = "0.5";
  const status = (vaultStatus || "unfunded").toLowerCase();
  const bb = document.getElementById("boostBtn");
  if (bb) bb.disabled = status !== "funded";
  const bs = document.getElementById("boostSection");
  if (bs) bs.style.opacity = status === "funded" ? "1" : "0.4";
}

const simulateVaultPayment = async function() {
  const taskId = _currentVaultTaskId;
  if (!taskId) { toast("No active vault task", "error"); return; }
  if (!walletAddress) { toast("Connect your wallet first", "error"); return; }

  const btn = document.getElementById("vaultPayBtn");
  if (btn) { btn.disabled = true; btn.textContent = "⏳ Processing payment…"; }
  const vpr = document.getElementById("vaultPollResult");
  if (vpr) vpr.textContent = "";

  try {
    const body = JSON.stringify({});
    const headers = await smartHeaders(body);
    const resp = await fetch(`${API_BASE}/api/tasks/${taskId}/simulate-fiat-payment`, { method: "POST", headers, body });

    if (resp.ok) {
      const data = await resp.json();
      const vbd = document.getElementById("vaultBalanceDisplay");
      if (vbd) vbd.textContent = data.balance.toFixed(2) + " USDC";
      const badge = document.getElementById("vaultStatusBadge");
      if (badge) {
        badge.textContent = "FUNDED";
        badge.style.background = "rgba(34,197,94,0.1)";
        badge.style.color = "#22c55e";
        badge.style.borderColor = "rgba(34,197,94,0.15)";
      }
      const qr = document.getElementById("qrMockPanel");
      if (qr) qr.style.display = "none";
      if (vpr) vpr.innerHTML = `<span style="color:#22c55e">✅ Vault funded! ${data.balance.toFixed(2)} USDC locked — task now in market</span>`;
      const bb = document.getElementById("boostBtn");
      if (bb) bb.disabled = false;
      const bs = document.getElementById("boostSection");
      if (bs) bs.style.opacity = "1";
      if (data.total_boosted) { const btd = document.getElementById("boostTotalDisplay"); if (btd) btd.textContent = `Total boosted: ${data.total_boosted.toFixed(2)} USDC`; }
      toast(`✅ Vault funded: ${data.balance.toFixed(2)} USDC — task is live`, "success");
      consumerLog("success", `📱 Vault funded: task=${taskId} amount=${data.balance} USDC (fiat simulation)`);
    } else {
      const err = await resp.json().catch(() => ({}));
      if (vpr) vpr.innerHTML = `<span style="color:var(--red)">❌ Payment failed: ${err.detail || resp.statusText}</span>`;
      toast("Payment simulation failed: " + (err.detail || resp.statusText), "error");
    }
  } catch (err) {
    if (vpr) vpr.innerHTML = `<span style="color:var(--red)">❌ Error: ${err.message}</span>`;
    toast("Payment error: " + err.message, "error");
  }
  if (btn) { btn.disabled = false; btn.textContent = "💳 Simulate Fiat Payment (扫码付款)"; }
};

// ── Boost Reward ───────────────────────────────────────────────
const boostReward = async function() {
  const taskId = _currentVaultTaskId;
  if (!taskId) { toast("No active vault task", "error"); return; }
  if (!walletAddress) { toast("Connect your wallet first", "error"); return; }

  const amount = parseFloat(document.getElementById("boostAmount")?.value);
  if (!amount || amount <= 0) { toast("Enter a valid boost amount", "error"); return; }

  const btn = document.getElementById("boostBtn");
  if (btn) { btn.disabled = true; btn.textContent = "⏳ Boosting…"; }
  const br = document.getElementById("boostResult");
  if (br) br.textContent = "";

  try {
    const body = JSON.stringify({ amount });
    const headers = await smartHeaders(body);
    const resp = await fetch(`${API_BASE}/api/tasks/${taskId}/boost-reward`, { method: "POST", headers, body });

    if (resp.ok) {
      const data = await resp.json();
      const btd = document.getElementById("boostTotalDisplay");
      if (btd) btd.textContent = `Total boosted: ${data.total_boosted.toFixed(2)} USDC`;
      if (br) br.innerHTML = `<span style="color:var(--amber)">⚡ +${data.boost_amount.toFixed(2)} USDC boosted!</span>`;
      toast(`⚡ Boosted! +${data.boost_amount.toFixed(2)} USDC — total reward: ${data.balance.toFixed(2)} USDC`, "success");
      consumerLog("success", `⚡ Boost reward: task=${taskId} +${data.boost_amount} USDC total_boosted=${data.total_boosted} USDC`);
      const vbd = document.getElementById("vaultBalanceDisplay");
      if (vbd) vbd.textContent = data.balance.toFixed(2) + " USDC";
    } else {
      const err = await resp.json().catch(() => ({}));
      if (br) br.innerHTML = `<span style="color:var(--red)">❌ ${err.detail || resp.statusText}</span>`;
      toast("Boost failed: " + (err.detail || resp.statusText), "error");
    }
  } catch (err) {
    if (br) br.innerHTML = `<span style="color:var(--red)">❌ ${err.message}</span>`;
    toast("Boost error: " + err.message, "error");
  }
  if (btn) { btn.disabled = false; btn.textContent = "⚡ Boost Reward"; }
};

// ── Co-Contributors Split ─────────────────────────────────────
let contributorRowCount = 0;

const addContributorRow = function(wallet, pct) {
  const list = document.getElementById("coContribList");
  if (!list) return;
  const idx = contributorRowCount++;
  const row = document.createElement("div");
  row.className = "contributor-row";
  row.id = "contrib-row-" + idx;
  row.style.cssText = "display:flex;gap:.5rem;align-items:center;margin-bottom:.35rem";
  row.innerHTML = `
    <input class="input" id="contrib-wallet-${idx}" placeholder="Co-contributor wallet (0x...)" style="flex:1;min-width:200px" value="${wallet || ''}">
    <input class="input" id="contrib-pct-${idx}" type="number" step="0.1" min="0" max="100" placeholder="%" style="width:70px;flex-shrink:0" value="${pct || ''}">
    <span style="font-size:.65rem;color:var(--text-dim);min-width:40px">%</span>
    <button class="btn btn-sm btn-ghost" onclick="removeContributorRow(${idx})" style="color:var(--red)">✕</button>
  `;
  list.appendChild(row);
  updateContribTotalPct();
};

const removeContributorRow = function(idx) {
  const row = document.getElementById("contrib-row-" + idx);
  if (row) row.remove();
  updateContribTotalPct();
};

function updateContribTotalPct() {
  const rows = document.querySelectorAll("#coContribList .contributor-row");
  let total = 0;
  rows.forEach(r => {
    const pctInput = r.querySelector("input[type=number]");
    if (pctInput) total += parseFloat(pctInput.value) || 0;
  });
  const ctp = document.getElementById("contribTotalPct");
  if (ctp) ctp.textContent = `Total: ${total.toFixed(1)}%`;
}

document.addEventListener("input", function(e) {
  if (e.target.closest("#coContribList") && e.target.type === "number") updateContribTotalPct();
});

const saveContributors = async function() {
  if (!walletAddress) { toast("Connect your wallet first", "error"); return; }
  const skillName = document.getElementById("integrateInput")?.value.trim();
  if (!skillName) { toast("Enter a skill name first", "error"); return; }
  const wallet = document.getElementById("integrateWallet")?.value.trim() || walletAddress;
  if (!wallet.startsWith("0x") || wallet.length !== 42) { toast("Enter a valid EVM wallet address", "error"); return; }

  const rows = document.querySelectorAll("#coContribList .contributor-row");
  const coContributors = [];
  rows.forEach(r => {
    const inputs = r.querySelectorAll("input");
    if (inputs.length >= 2) {
      const w = inputs[0].value.trim();
      const p = parseFloat(inputs[1].value);
      if (w && w.startsWith("0x") && w.length === 42 && p > 0 && p <= 100) coContributors.push({ wallet: w, share_pct: p });
    }
  });
  if (coContributors.length === 0) { toast("Add at least one valid co-contributor (wallet + share %)", "error"); return; }

  const csr = document.getElementById("contribSaveResult");
  if (csr) csr.textContent = "⏳ Saving…";
  try {
    const body = JSON.stringify({ skill_name: skillName, wallet_address: wallet, co_contributors: coContributors });
    const headers = await smartHeaders(body);
    const resp = await fetch(`${API_BASE}/api/developer/set-contributors`, { method: "POST", headers, body });
    if (resp.ok) {
      const data = await resp.json();
      if (csr) csr.innerHTML = `<span style="color:#22c55e">✅ ${data.message}</span>`;
      toast("✅ Co-contributors saved: " + data.message, "success");
      consumerLog("success", `👥 Co-contributors set: skill=${skillName} count=${coContributors.length} total_pct=${data.total_share_pct}%`);
    } else {
      const err = await resp.json().catch(() => ({}));
      if (csr) csr.innerHTML = `<span style="color:var(--red)">❌ ${err.detail || resp.statusText}</span>`;
      toast("Save failed: " + (err.detail || resp.statusText), "error");
    }
  } catch (err) {
    if (csr) csr.innerHTML = `<span style="color:var(--red)">❌ ${err.message}</span>`;
    toast("Save error: " + err.message, "error");
  }
};

// ── Poll Vault Status ──────────────────────────────────────────
const pollVaultStatus = async function() {
  const taskId = _currentVaultTaskId;
  if (!taskId) { toast("No active vault task", "error"); return; }
  try {
    const resp = await fetch(`${API_BASE}/api/tasks/${taskId}/vault-status`);
    if (resp.ok) {
      const data = await resp.json();
      const vbd = document.getElementById("vaultBalanceDisplay");
      if (vbd) vbd.textContent = data.balance.toFixed(2) + " USDC";
      const badge = document.getElementById("vaultStatusBadge");
      if (badge) {
        badge.textContent = data.status.toUpperCase();
        if (data.status === "funded") {
          badge.style.background = "rgba(34,197,94,0.1)"; badge.style.color = "#22c55e"; badge.style.borderColor = "rgba(34,197,94,0.15)";
        } else if (data.status === "released") {
          badge.style.background = "rgba(222,255,154,0.1)"; badge.style.color = "var(--neon)"; badge.style.borderColor = "var(--neon-glow)";
        }
      }
      const boosted = data.total_boosted || 0;
      const btd = document.getElementById("boostTotalDisplay");
      if (btd) btd.textContent = `Total boosted: ${boosted.toFixed(2)} USDC`;
      const qr = document.getElementById("qrMockPanel");
      if (qr && (data.status === "funded" || data.status === "released")) qr.style.display = "none";
      const bb = document.getElementById("boostBtn");
      const bs = document.getElementById("boostSection");
      if (data.status === "released") {
        if (bb) bb.disabled = true;
        if (bs) bs.style.opacity = "0.4";
        const vpb = document.getElementById("vaultPayBtn");
        if (vpb) vpb.disabled = true;
      } else if (data.status === "funded") {
        if (bb) bb.disabled = false;
        if (bs) bs.style.opacity = "1";
      }
      const vpr = document.getElementById("vaultPollResult");
      if (vpr) vpr.textContent = `Status: ${data.status} | Balance: ${data.balance.toFixed(2)} USDC | Boosted: ${boosted.toFixed(2)} USDC | Vault: ${(data.vault_address || "").slice(0,14)}…`;
    } else {
      const vpr = document.getElementById("vaultPollResult");
      if (vpr) vpr.textContent = "⚠️ Vault not found";
    }
  } catch (err) {
    const vpr = document.getElementById("vaultPollResult");
    if (vpr) vpr.textContent = "⚠️ " + err.message;
  }
};

// ── Consumer Log ───────────────────────────────────────────────
function consumerLog(type, msg) {
  const log = document.getElementById("consumerLog");
  if (!log) return;
  const entry = document.createElement("div");
  entry.className = `log-entry ${type}`;
  const now = new Date();
  entry.innerHTML = `<span class="time">${now.toLocaleTimeString()}</span><span class="msg">${msg}</span>`;
  log.appendChild(entry);
  log.scrollTop = log.scrollHeight;
}

function clearLog() {
  const log = document.getElementById("consumerLog");
  if (log) log.innerHTML = "";
}

// ── Worker Simulation ──────────────────────────────────────────
function startWorkerSim() {
  const btn = document.getElementById("workerStartBtn");
  if (workerInterval) {
    clearInterval(workerInterval);
    if (workerInterval._hbInterval) clearInterval(workerInterval._hbInterval);
    workerInterval = null;
    if (btn) { btn.textContent = "▶ Start Node"; btn.className = "btn btn-sm btn-neon"; }
    const wsd = document.getElementById("workerStatusDot");
    if (wsd) wsd.className = "status-dot offline";
    const wst = document.getElementById("workerStatusText");
    if (wst) wst.textContent = "Offline";
    const wni = document.getElementById("workerNodeId");
    if (wni) wni.textContent = "—";
    updateCanaryStatus(false);
    toast("Worker node stopped", "info");
    return;
  }

  workerStartTime = Date.now();
  const nodeId = "node-" + Math.random().toString(36).slice(2, 8);
  const wni = document.getElementById("workerNodeId");
  if (wni) wni.textContent = nodeId;
  const wsd = document.getElementById("workerStatusDot");
  if (wsd) wsd.className = "status-dot idle";
  const wst = document.getElementById("workerStatusText");
  if (wst) wst.textContent = "Online (Idle)";
  updateCanaryStatus(true);
  if (btn) { btn.textContent = "⏹ Stop Node"; btn.className = "btn btn-sm btn-outline"; }

  if (workerInterval) clearInterval(workerInterval);
  workerInterval = setInterval(() => {
    const uptime = Math.floor((Date.now() - workerStartTime) / 1000);
    const wu = document.getElementById("workerUptime");
    if (wu) wu.textContent = `${uptime}s`;
  }, 1000);

  const hbInterval = setInterval(() => sendHeartbeat(), 15000);
  workerInterval._hbInterval = hbInterval;
  sendHeartbeat();
  toast("Worker node started — heartbeating every 15s", "success");
}

async function sendHeartbeat() {
  if (!walletAddress) { toast("Connect wallet first", "error"); return; }
  try {
    const body = JSON.stringify({ worker_id: walletAddress });
    const headers = await smartHeaders(body);
    const resp = await fetch(`${API_BASE}/api/workers/heartbeat`, { method: "POST", headers, body });
    if (resp.ok) {
      const wsd = document.getElementById("workerStatusDot");
      if (wsd) wsd.className = "status-dot online";
      const wst = document.getElementById("workerStatusText");
      if (wst) wst.textContent = "Online (Active)";
    }
  } catch(err) { console.warn("sendHeartbeat:", err.message); }
}

// ── Canary Watermark Status ────────────────────────────────────
function updateCanaryStatus(active) {
  const dot = document.getElementById("canaryStatusDot");
  const text = document.getElementById("canaryStatusText");
  const badge = document.getElementById("canaryStatusBadge");
  const blacklist = document.getElementById("canaryBlacklistStatus");
  if (!dot || !text || !badge) return;
  if (active) {
    dot.className = "status-dot online";
    text.textContent = "Protection Active";
    badge.innerHTML = "● ACTIVE";
    badge.style.color = "#22c55e";
    badge.style.borderColor = "rgba(34,197,94,0.15)";
    badge.style.background = "rgba(34,197,94,0.1)";
    if (blacklist) blacklist.textContent = "Clean — no strikes";
  } else {
    dot.className = "status-dot offline";
    text.textContent = "Protection Disabled";
    badge.innerHTML = "● INACTIVE";
    badge.style.color = "var(--text-dim)";
    badge.style.borderColor = "var(--border)";
    badge.style.background = "transparent";
    if (blacklist) blacklist.textContent = "Unknown";
  }
}

// ── Health Check ───────────────────────────────────────────────
async function fetchHealth() {
  try {
    const resp = await fetch(`${API_BASE}/api/health`);
    const hs = document.getElementById("healthStatus");
    if (!resp.ok) {
      if (hs) { hs.textContent = "⚠️ Unreachable"; hs.style.color = "var(--red)"; }
      return;
    }
    const data = await resp.json();
    if (hs) { hs.textContent = "● Healthy"; hs.style.color = "#22c55e"; }
    const hb = document.getElementById("healthBlock");
    if (hb) hb.textContent = data.tasks_succeeded || "—";
    const hp = document.getElementById("healthPending");
    if (hp) hp.textContent = data.tasks_pending ?? "—";
    const hsu = document.getElementById("healthSucceeded");
    if (hsu) hsu.textContent = data.tasks_succeeded ?? "—";
    const hw = document.getElementById("healthWorkers");
    if (hw) hw.textContent = data.workers_active ?? "—";
    const ht = document.getElementById("healthTreasury");
    if (ht) ht.textContent = (data.treasury_usdt || 0).toFixed(2) + " USDT";
  } catch(err) {
    const hs = document.getElementById("healthStatus");
    if (hs) { hs.textContent = "⚠️ Offline"; hs.style.color = "var(--red)"; }
  }
}

// ── Role Switching ─────────────────────────────────────────────
let _savedVaultTaskId = null;

function switchRole(role) {
  if (currentRole === "consumer" && role !== "consumer") _savedVaultTaskId = _currentVaultTaskId;
  currentRole = role;
  document.querySelectorAll(".role-tab").forEach(t => t.classList.toggle("active", t.dataset.role === role));
  document.querySelectorAll(".tab-content").forEach(t => t.classList.toggle("active", t.id === "tab-" + role));
  if (role === "consumer" && _savedVaultTaskId && !_currentVaultTaskId) {
    _currentVaultTaskId = _savedVaultTaskId;
    const vsb = document.getElementById("vaultStatusBadge");
    if (vsb) {
      vsb.textContent = "READY";
      vsb.style.background = "rgba(222,255,154,0.1)";
      vsb.style.color = "var(--neon)";
    }
  }
  if (role === "developer") fetchPendingTasks();
}

// ── Settlement Feed SSE ────────────────────────────────────────
(function(){
  const feed = document.getElementById('consoleFeed');
  if (!feed) return;
  let cnt = 0, vol = 0;
  const elCnt = document.getElementById('consoleFeedCount');
  const elVol = document.getElementById('consoleFeedVol');

  function addEntry(data) {
    const action = data.action || 'settle';
    const isPass = action !== 'refund' && action !== 'pool_shortfall';
    const taskId = (data.task_id || '').slice(0, 8);
    const amt = data.amounts ? (data.amounts.total_deducted || data.amounts.user_deduction || 0) / 1000000 : 0;
    const skillLabel = data.detail ? data.detail.match(/skill=(\S+)/) : null;
    const skillName = skillLabel ? skillLabel[1] : taskId;
    cnt++;
    vol += amt;
    const d = document.createElement('div');
    d.className = `feed-entry-c ${isPass ? 'pass' : 'refund'}`;
    d.innerHTML = `<span class="fc-time">${new Date(data.ts * 1000).toLocaleTimeString()}</span><span class="fc-main"><span class="fc-skill">${skillName}</span><span class="fc-score ${isPass ? 'pass' : 'refund'}">${isPass ? '✓' : '✗'} ${action}</span><span class="fc-split">${amt.toFixed(4)} USDC</span><span class="fc-dex">${data.action}</span></span>`;
    feed.insertBefore(d, feed.firstChild);
    while (feed.children.length > 15) feed.removeChild(feed.lastChild);
    if (elCnt) elCnt.textContent = cnt;
    if (elVol) elVol.textContent = vol.toFixed(4);
  }

  let eventSource = null;
  function connectSSE() {
    if (eventSource) eventSource.close();
    eventSource = new EventSource(`${API_BASE}/api/v2/feed/stream`);
    eventSource.onmessage = (ev) => { try { addEntry(JSON.parse(ev.data)); } catch(e) { console.warn("SSE parse:", ev.data); } };
    eventSource.onerror = () => setTimeout(connectSSE, 5000);
  }
  setTimeout(connectSSE, 2000);
})();

// ── Skill Upload Drag & Drop ───────────────────────────────────
(function(){
  const zone = document.getElementById('skillDropZone');
  const input = document.getElementById('skillFileInput');
  const btn = document.getElementById('uploadSkillBtn');
  const status = document.getElementById('uploadStatus');
  const info = document.getElementById('dzFileInfo');
  let selectedFile = null;
  if (!zone) return;

  zone.addEventListener('click', () => input?.click());
  zone.addEventListener('dragover', (e) => { e.preventDefault(); zone.classList.add('drag-over'); });
  zone.addEventListener('dragleave', () => zone.classList.remove('drag-over'));
  zone.addEventListener('drop', (e) => {
    e.preventDefault();
    zone.classList.remove('drag-over');
    if (e.dataTransfer.files.length > 0) handleFile(e.dataTransfer.files[0]);
  });
  if (input) {
    input.addEventListener('change', () => { if (input.files.length > 0) handleFile(input.files[0]); });
  }

  function handleFile(file) {
    if (!file.name.endsWith('.zip')) { toast('Only .zip files are accepted', 'error'); return; }
    if (file.size > 10 * 1024 * 1024) { toast('File exceeds 10 MB limit', 'error'); return; }
    selectedFile = file;
    zone.classList.add('has-file');
    if (info) { info.style.display = 'block'; info.textContent = '📎 ' + file.name + ' (' + (file.size / 1024).toFixed(1) + ' KB)'; }
    if (btn) btn.disabled = false;
    if (status) { status.textContent = 'Ready to upload — ' + file.name; status.style.color = 'var(--neon)'; }
    toast('Selected: ' + file.name, 'info');
  }
  window.handleSkillFile = handleFile;
})();

const uploadSkill = async function() {
  const fileInput = document.getElementById('skillFileInput');
  const btn = document.getElementById('uploadSkillBtn');
  const status = document.getElementById('uploadStatus');
  const file = fileInput?.files[0];
  if (!file) { toast('Select a ZIP file first', 'error'); return; }
  if (!walletAddress) { toast('Connect your wallet first', 'error'); return; }

  if (btn) { btn.disabled = true; btn.textContent = '⏳ Uploading…'; }
  if (status) { status.textContent = 'Uploading ' + file.name + ' …'; status.style.color = 'var(--text-dim)'; }

  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('user_id', walletAddress);
    const authMsg = 'AIMS_UPLOAD:' + walletAddress + ':' + file.name;
    const sig = await signer.signMessage(authMsg);
    const sigHex = sig.startsWith('0x') ? sig.slice(2) : sig;

    const resp = await fetch(API_BASE + '/api/skills/upload', {
      method: 'POST',
      headers: { 'X-Wallet-Address': walletAddress, 'X-Signature': sigHex, 'X-Timestamp': Math.floor(Date.now() / 1000).toString() },
      body: formData,
    });

    if (resp.ok) {
      const data = await resp.json();
      toast('✅ Skill uploaded: ' + (data.skill_id || 'registered'), 'success');
      if (status) { status.textContent = '✅ Uploaded — refresh skills list'; status.style.color = '#22c55e'; }
      if (btn) { btn.textContent = '⬆ Upload Another'; btn.disabled = false; }
      consumerLog('success', '📦 Skill uploaded: ' + (data.skill_id || file.name));
      await fetchDiscovery();
    } else {
      const err = await resp.json().catch(() => ({}));
      toast('Upload failed: ' + (err.detail || resp.statusText), 'error');
      if (status) { status.textContent = '❌ Upload failed — ' + (err.detail || resp.statusText); status.style.color = 'var(--red)'; }
      if (btn) { btn.textContent = '⬆ Upload Skill'; btn.disabled = false; }
    }
  } catch (err) {
    toast('Upload error: ' + err.message, 'error');
    if (status) { status.textContent = '❌ Error: ' + err.message; status.style.color = 'var(--red)'; }
    if (btn) { btn.textContent = '⬆ Upload Skill'; btn.disabled = false; }
  }
};

// ── Recharge Reserves ──────────────────────────────────────────
const rechargeReserves = async function(amount) {
  if (!walletAddress) { toast('Connect your wallet first', 'error'); return; }
  if (!amount || amount <= 0) { toast('Enter a valid amount', 'error'); return; }
  toast('Depositing ' + amount.toFixed(2) + ' USDC…', 'info');
  try {
    const body = JSON.stringify({ user_id: walletAddress, amount });
    const headers = await smartHeaders(body);
    const resp = await fetch(API_BASE + '/api/wallet/deposit', { method: 'POST', headers, body });
    if (resp.ok) {
      const data = await resp.json();
      consumerDepositedUsdc += amount;
      const rt = document.getElementById('rechargeTotal');
      if (rt) rt.textContent = consumerDepositedUsdc.toFixed(2) + ' USDC';
      toast('✅ Deposited ' + amount.toFixed(2) + ' USDC — balance: ' + (data.new_balance || '?').toFixed(2), 'success');
      consumerLog('success', '💰 Recharge ' + amount.toFixed(2) + ' USDC → balance ' + (data.new_balance || '?').toFixed(2));
      await refreshBalance();
      const rb = document.getElementById('rechargeBalance');
      if (rb) rb.textContent = (data.new_balance || 0).toFixed(2) + ' USDC';
    } else {
      const err = await resp.json().catch(() => ({}));
      toast('Deposit failed: ' + (err.detail || resp.statusText), 'error');
    }
  } catch (err) { toast('Deposit error: ' + err.message, 'error'); }
};

// ── Audit Ledger ───────────────────────────────────────────────
const fetchAudit = async function(taskFilter) {
  const container = document.getElementById('auditLedgerBody');
  if (!container) return;
  try {
    let url = API_BASE + '/api/admin/audit';
    if (taskFilter) url += '?task_id=' + encodeURIComponent(taskFilter);
    const resp = await fetch(url);
    if (!resp.ok) { container.innerHTML = '<div class="empty-state"><div class="big-icon">⚠️</div>Audit API unavailable (HTTP ' + resp.status + ')</div>'; return; }
    const data = await resp.json();
    const ledger = data.ledger || data.audit_ledger || [];
    if (ledger.length === 0) { container.innerHTML = '<div class="empty-state"><div class="big-icon">📭</div>No audit entries yet — execute and settle tasks to populate the ledger</div>'; return; }
    container.innerHTML = `<table><thead><tr><th>Time</th><th>Action</th><th>Task</th><th>Amount</th><th>Roles</th></tr></thead><tbody>
      ${ledger.slice(0, 50).map(e => {
        const ts = e.ts ? new Date(e.ts * 1000).toLocaleTimeString() : '—';
        const action = (e.action || '—');
        const isPass = action !== 'refund';
        const amt = e.amounts ? ((e.amounts.total_deducted || e.amounts.user_deduction || 0) / 1000000).toFixed(4) : (e.amount || 0).toFixed(4);
        const taskId = (e.task_id || e.taskId || '').slice(0, 12);
        const roles = e.roles || {};
        const roleStr = Object.values(roles).slice(0, 2).map(a => (a || '').slice(0, 6)).join('…');
        return `<tr><td style="color:var(--text-dim);font-size:.6rem">${ts}</td><td class="${isPass ? 'tx-pass' : 'tx-refund'}">${action}</td><td style="font-family:monospace;font-size:.6rem">${taskId || '—'}</td><td style="color:var(--neon)">${amt}</td><td class="tx-role">${roleStr || '—'}</td></tr>`;
      }).join('')}
    </tbody></table>${ledger.length > 50 ? '<div style="text-align:center;padding:.5rem;font-size:.65rem;color:var(--text-dim)">… showing 50 of ' + ledger.length + ' entries</div>' : ''}`;
  } catch (err) { container.innerHTML = '<div class="empty-state"><div class="big-icon">⚠️</div>Error loading audit: ' + err.message + '</div>'; }
};

// ── Withdraw Funds ─────────────────────────────────────────────
const withdrawFunds = async function() {
  if (!walletAddress) { toast('Connect your wallet first', 'error'); return; }
  const amt = parseFloat(document.getElementById('withdrawAmt')?.value);
  if (!amt || amt <= 0) { toast('Enter a valid withdraw amount', 'error'); return; }
  toast('Withdrawing ' + amt.toFixed(2) + ' USDC…', 'info');
  try {
    const body = JSON.stringify({ user_id: walletAddress, amount: amt });
    const headers = await smartHeaders(body);
    const resp = await fetch(API_BASE + '/api/wallet/withdraw', { method: 'POST', headers, body });
    if (resp.ok) {
      const data = await resp.json();
      toast('✅ Withdrew ' + amt.toFixed(2) + ' USDC — tx: ' + data.tx_id, 'success');
      consumerLog('success', '💸 Withdrew ' + amt.toFixed(2) + ' USDC — tx=' + data.tx_id);
      await refreshBalance();
      const rb = document.getElementById('rechargeBalance');
      if (rb) rb.textContent = data.new_balance.toFixed(2) + ' USDC';
    } else {
      const err = await resp.json().catch(() => ({}));
      toast('Withdraw failed: ' + (err.detail || resp.statusText), 'error');
      consumerLog('error', '💸 Withdraw failed: ' + (err.detail || resp.statusText));
    }
  } catch (err) { toast('Withdraw error: ' + err.message, 'error'); }
};

// ── Fiat / Credit Card Deposit ─────────────────────────────────
const fiatDeposit = async function(amount) {
  if (!walletAddress) { toast('Connect your wallet first', 'error'); return; }
  if (!amount || amount <= 0) { toast('Enter a valid amount', 'error'); return; }
  toast('💳 Processing $' + amount.toFixed(2) + ' credit card payment…', 'info');
  try {
    const body = JSON.stringify({ user_id: walletAddress, amount, card_token: 'tok_mock_' + Math.random().toString(36).slice(2, 10) });
    const headers = await smartHeaders(body);
    const resp = await fetch(API_BASE + '/api/wallet/fiat-deposit', { method: 'POST', headers, body });
    if (resp.ok) {
      const data = await resp.json();
      consumerDepositedUsdc += amount;
      const rt = document.getElementById('rechargeTotal');
      if (rt) rt.textContent = consumerDepositedUsdc.toFixed(2) + ' USDC';
      toast('✅ Credit card deposit successful! $' + amount.toFixed(2) + ' → ' + data.new_balance.toFixed(2) + ' USDC', 'success');
      consumerLog('success', '💳 Fiat deposit $' + amount.toFixed(2) + ' (Stripe mock) → balance ' + data.new_balance.toFixed(2) + ' USDC, tx=' + data.tx_id);
      await refreshBalance();
      const rb = document.getElementById('rechargeBalance');
      if (rb) rb.textContent = data.new_balance.toFixed(2) + ' USDC';
    } else {
      const err = await resp.json().catch(() => ({}));
      toast('Card payment failed: ' + (err.detail || resp.statusText), 'error');
    }
  } catch (err) { toast('Fiat deposit error: ' + err.message, 'error'); }
};

// ── User History Ledger ────────────────────────────────────────
const fetchHistory = async function(typeFilter) {
  const container = document.getElementById('userHistoryBody');
  if (!container) return;
  if (!walletAddress) { container.innerHTML = '<div class="empty-state"><div class="big-icon">🔌</div>Connect your wallet to view history</div>'; return; }
  try {
    const url = API_BASE + '/api/wallet/history?user_id=' + encodeURIComponent(walletAddress) + '&limit=50';
    const resp = await fetch(url);
    if (!resp.ok) { container.innerHTML = '<div class="empty-state"><div class="big-icon">⚠️</div>History API unavailable (HTTP ' + resp.status + ')</div>'; return; }
    const data = await resp.json();
    let entries = data.entries || [];
    if (typeFilter) entries = entries.filter(e => (e.type || '') === typeFilter);
    if (entries.length === 0) { container.innerHTML = '<div class="empty-state"><div class="big-icon">📭</div>No history entries found' + (typeFilter ? ' for type "' + typeFilter + '"' : '') + '</div>'; return; }
    container.innerHTML = `<table><thead><tr><th>Time</th><th>Type</th><th>Amount</th><th>Description</th><th>Tx ID</th></tr></thead><tbody>
      ${entries.map(e => {
        const ts = e.timestamp ? new Date(e.timestamp * 1000).toLocaleString() : '—';
        const type = e.type || '—';
        const amt = (e.amount || 0);
        const amtStr = amt >= 0 ? amt.toFixed(2) : '(' + Math.abs(amt).toFixed(2) + ')';
        const desc = (e.description || '—').slice(0, 50);
        const txId = (e.tx_id || '').slice(0, 12);
        return `<tr><td style="color:var(--text-dim);font-size:.6rem;white-space:nowrap">${ts}</td><td><span class="history-type ${type}">${type}</span></td><td style="color:${type === 'withdraw' ? 'var(--amber)' : 'var(--neon)'};font-weight:600">${amtStr}</td><td style="font-size:.6rem;color:var(--text-dim);max-width:180px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${desc}</td><td style="font-family:monospace;font-size:.6rem;color:var(--text-dim)">${txId || '—'}</td></tr>`;
      }).join('')}
    </tbody></table>${entries.length >= 50 ? '<div style="text-align:center;padding:.5rem;font-size:.65rem;color:var(--text-dim)">Showing last 50 entries</div>' : ''}`;
  } catch (err) { container.innerHTML = '<div class="empty-state"><div class="big-icon">⚠️</div>Error loading history: ' + err.message + '</div>'; }
};

// ── Boost From Market ──────────────────────────────────────────
const boostFromMarket = async function(taskId) {
  if (!walletAddress) { toast("Connect your wallet first", "error"); return; }
  try {
    const vaultPanel = document.getElementById("vaultPanel");
    if (vaultPanel) { showVaultPanel(taskId); vaultPanel.scrollIntoView({ behavior: "smooth" }); }
    const ba = document.querySelector("#boostAmount");
    if (ba) ba.style.display = "block";
    toast("Ready to boost " + taskId.slice(0,12), "info");
  } catch(e) { toast("boostFromMarket error: " + e.message, "error"); }
};

// ── API Key Management ─────────────────────────────────────────
const fetchApiKeys = async function() {
  const container = document.getElementById("apiKeyList");
  const jwt = localStorage.getItem("aims_jwt");
  if (!jwt) { if (container) container.innerHTML = '<div style="color:var(--text-dim);padding:.5rem">Not authenticated.</div>'; return; }
  try {
    const resp = await fetch(API_BASE + "/api/auth/api-keys", { headers: jwtHeaders() });
    if (!resp.ok) { if (container) container.innerHTML = '<div style="color:var(--red);padding:.5rem">Failed to load keys.</div>'; return; }
    const data = await resp.json();
    if (!data.keys || data.keys.length === 0) { if (container) container.innerHTML = '<div style="color:var(--text-dim);padding:.5rem">No API keys generated yet.</div>'; return; }
    if (container) {
      container.innerHTML = '<table style="width:100%;border-collapse:collapse;font-size:.75rem"><thead><tr>' +
        '<th style="text-align:left;padding:.4rem .5rem;border-bottom:1px solid rgba(222,255,154,0.08);color:var(--text-dim);font-weight:400">Label</th>' +
        '<th style="text-align:left;padding:.4rem .5rem;border-bottom:1px solid rgba(222,255,154,0.08);color:var(--text-dim);font-weight:400">Key Prefix</th>' +
        '<th style="text-align:left;padding:.4rem .5rem;border-bottom:1px solid rgba(222,255,154,0.08);color:var(--text-dim);font-weight:400">Created</th>' +
        '<th style="text-align:left;padding:.4rem .5rem;border-bottom:1px solid rgba(222,255,154,0.08);color:var(--text-dim);font-weight:400">Last Used</th>' +
        '<th style="padding:.4rem .5rem;border-bottom:1px solid rgba(222,255,154,0.08)"></th></tr></thead><tbody>' +
        data.keys.map(k => '<tr>' +
          '<td style="padding:.35rem .5rem;color:var(--text)">' + (k.label || "—") + '</td>' +
          '<td style="padding:.35rem .5rem"><code style="color:var(--neon);font-size:.7rem">' + k.key_prefix + '</code></td>' +
          '<td style="padding:.35rem .5rem;color:var(--text-dim)">' + new Date(k.created_at * 1000).toLocaleDateString() + '</td>' +
          '<td style="padding:.35rem .5rem;color:var(--text-dim)">' + (k.last_used_at ? new Date(k.last_used_at * 1000).toLocaleDateString() : "Never") + '</td>' +
          '<td style="padding:.35rem .5rem"><button class="btn btn-sm" style="background:rgba(255,107,107,0.1);color:var(--red);border:1px solid rgba(255,107,107,0.15);padding:.15rem .5rem;font-size:.65rem" onclick="revokeApiKey(' + k.id + ')">Revoke</button></td>' +
        '</tr>').join("") + '</tbody></table>';
    }
  } catch(e) { if (container) container.innerHTML = '<div style="color:var(--red);padding:.5rem">Error: ' + e.message + '</div>'; }
};

const createApiKey = async function() {
  const label = document.getElementById("apiKeyLabel")?.value.trim();
  const resultDiv = document.getElementById("apiKeyResult");
  const jwt = localStorage.getItem("aims_jwt");
  if (!jwt) { toast("Not authenticated", "error"); return; }
  try {
    const resp = await fetch(API_BASE + "/api/auth/api-keys", { method: "POST", headers: jwtHeaders(), body: JSON.stringify({ label }) });
    if (!resp.ok) { toast("Failed to create API key", "error"); return; }
    const data = await resp.json();
    if (resultDiv) {
      resultDiv.innerHTML = '<div style="background:rgba(52,211,153,0.08);border:1px solid rgba(52,211,153,0.15);border-radius:6px;padding:.75rem;margin-bottom:.5rem">' +
        '<div style="color:#34d399;font-weight:600;font-size:.75rem;margin-bottom:.35rem">✅ API Key Generated</div>' +
        '<div style="font-size:.72rem;color:var(--text-dim);margin-bottom:.25rem">Copy this key now — it will not be shown again:</div>' +
        '<div style="background:var(--bg);padding:.5rem;border-radius:4px;word-break:break-all;font-family:monospace;color:var(--neon);font-size:.72rem;user-select:all" onclick="navigator.clipboard.writeText(this.textContent);toast(\'Copied!\',\'success\')">' + data.api_key + '</div>' +
        '<div style="font-size:.65rem;color:var(--text-dim);margin-top:.35rem">Click to copy | Prefix: <code style="color:var(--neon)">' + data.key_prefix + '</code></div></div>';
    }
    const akl = document.getElementById("apiKeyLabel");
    if (akl) akl.value = "";
    fetchApiKeys();
  } catch(e) { if (resultDiv) resultDiv.innerHTML = '<div style="color:var(--red);font-size:.75rem">Error: ' + e.message + '</div>'; }
};

const revokeApiKey = async function(keyId) {
  if (!confirm("Revoke this API key? It will stop working immediately.")) return;
  const jwt = localStorage.getItem("aims_jwt");
  if (!jwt) { toast("Not authenticated", "error"); return; }
  try {
    const resp = await fetch(API_BASE + "/api/auth/api-keys/" + keyId, { method: "DELETE", headers: jwtHeaders() });
    if (resp.ok) { toast("API key revoked", "success"); fetchApiKeys(); }
    else { toast("Failed to revoke key", "error"); }
  } catch(e) { toast("Error: " + e.message, "error"); }
};

// ── Auto-connect & Event Listeners ──────────────────────────────
if (typeof window.ethereum !== "undefined") {
  window.ethereum.request({ method: "eth_accounts" }).then(accounts => {
    if (accounts.length > 0) connectWallet();
  }).catch(() => {});
}
if (typeof window.ethereum !== "undefined") {
  window.ethereum.on("accountsChanged", (accounts) => {
    if (accounts.length === 0) {
      walletAddress = "";
      const cb = document.getElementById("connectBtn");
      if (cb) { cb.textContent = "Connect Wallet"; cb.classList.remove("connected"); }
      const wa = document.getElementById("walletAddress");
      if (wa) wa.textContent = "";
      const bd = document.getElementById("balanceDisplay");
      if (bd) bd.style.display = "none";
      const tb = document.getElementById("trialBadge");
      if (tb) tb.style.display = "none";
      toast("Wallet disconnected", "warn");
    } else { connectWallet(); }
  });
}

// ── Page Init ──────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", async function() {
  fetchHealth();
  fetchDiscovery();
  const rc = document.getElementById("rechargeContract");
  if (rc) rc.textContent = CONTRACT_ADDRESS;
  switchBillingMode('pay_per_task');
  updateCanaryStatus(true);

  // Expose all async functions to global scope for onclick handlers
  window.fetchCreditScore = fetchCreditScore;
  window.publishTask = publishTask;
  window.fetchPendingTasks = fetchPendingTasks;
  window.claimTask = claimTask;
  window.oneClickIntegrate = oneClickIntegrate;
  window.fetchIntegrationStatus = fetchIntegrationStatus;
  window.simulateVaultPayment = simulateVaultPayment;
  window.boostReward = boostReward;
  window.addContributorRow = addContributorRow;
  window.removeContributorRow = removeContributorRow;
  window.saveContributors = saveContributors;
  window.pollVaultStatus = pollVaultStatus;
  window.uploadSkill = uploadSkill;
  window.rechargeReserves = rechargeReserves;
  window.fetchAudit = fetchAudit;
  window.withdrawFunds = withdrawFunds;
  window.fiatDeposit = fiatDeposit;
  window.fetchHistory = fetchHistory;
  window.boostFromMarket = boostFromMarket;
  window.fetchApiKeys = fetchApiKeys;
  window.createApiKey = createApiKey;
  window.revokeApiKey = revokeApiKey;

  try { await fetchDiscovery(); } catch (e) { console.warn("Page init — fetchDiscovery failed:", e.message); }
  try { await fetchApiKeys(); } catch (e) { console.warn("Page init — fetchApiKeys skipped:", e.message); }
  if (typeof window.ethereum !== "undefined") {
    try {
      const accounts = await window.ethereum.request({ method: "eth_accounts" });
      if (accounts.length > 0) await connectWallet();
    } catch (e) { console.warn("Page init — wallet reconnect skipped:", e.message); }
  }
});
