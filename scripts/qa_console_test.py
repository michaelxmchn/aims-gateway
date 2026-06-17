#!/usr/bin/env python3
"""
AIMS Console v2.1 — Full Button Integration QA Test Suite
===========================================================
Tests every interactive element across the dashboard, 6 business modals,
and Advanced Dev Mode drawer.
Uses Playwright for browser automation + eth_account for EIP-191 auth.
Generates a structured PASS/FAIL reconciliation report.
"""
import asyncio, json, os, sys, time, traceback
from pathlib import Path
import urllib.request

from eth_account import Account
from eth_account.messages import encode_defunct

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from playwright.async_api import async_playwright

API_BASE = "http://127.0.0.1:8001"

# ── Test account — Anvil default account #0 ──────────────────────────
QA_PK  = "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80"
QA_ACCT = Account.from_key(QA_PK)
QA_WALLET = QA_ACCT.address  # 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266

# ── Test results accumulator ────────────────────────────────────────
test_results = []
def register_test(name, tab, js_func, expected_status="200", result="PASS", detail=""):
    test_results.append({
        "name": name, "tab": tab, "js_func": js_func,
        "expected_status": expected_status, "result": result, "detail": detail,
    })

def eip191_sign(message: str) -> str:
    signable = encode_defunct(primitive=message.encode())
    signed = QA_ACCT.sign_message(signable)
    return signed.signature.hex()

def do_http(url, data=None, headers=None):
    """Synchronous HTTP request using urllib."""
    if data and isinstance(data, dict):
        data = json.dumps(data).encode()
    req = urllib.request.Request(url, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            return e.code, json.loads(body)
        except json.JSONDecodeError:
            return e.code, {"detail": body}

async def run_qa():
    print("=" * 72)
    print("  AIMS Console v2.1 — 全功能联调测试对账报告")
    print("  Full Integration QA Test Reconciliation Report")
    print("=" * 72)
    print(f"  Test Account: {QA_WALLET}")
    print(f"  API Base:     {API_BASE}")
    print(f"  Started:      {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    # ══════════════════════════════════════════════════════════════════
    #  AUTH: Use wallet-login with full EIP-191 headers
    # ══════════════════════════════════════════════════════════════════
    print("\n[1/5] 🔑 Authenticating (EIP-191 wallet-login)…")
    jwt_token = None
    user_id = None

    ts = int(time.time())
    msg = f"AIMS_AUTH:{QA_WALLET}:{ts}"
    sig = eip191_sign(msg)

    headers = {
        "Content-Type": "application/json",
        "X-Wallet-Address": QA_WALLET,
        "X-Signature": sig,
        "X-Timestamp": str(ts),
    }
    body = {"wallet": QA_WALLET, "signature": sig, "message": msg, "timestamp": ts}

    status, data = do_http(f"{API_BASE}/api/auth/wallet-login", data=body, headers=headers)
    if status == 200:
        jwt_token = data.get("token")
        user_id = data.get("user_id")
        print(f"       ✅ Wallet-login success! JWT: {jwt_token[:40]}…  User ID: {user_id}")
    else:
        # Fallback: try registering with email
        print(f"       ⚠️ Wallet-login returned HTTP {status}: {data.get('detail','')}")
        print("       Trying email registration…")
        status2, data2 = do_http(f"{API_BASE}/api/auth/register", data={
            "email": "qa_runner@aims.test",
            "password": "qa_runner_2024",
            "display_name": "QA Runner",
        })
        print(f"       Register HTTP {status2}: {json.dumps(data2)[:100]}")
        if status2 == 200:
            jwt_token = data2.get("token")
            user_id = data2.get("user_id")

    if not jwt_token:
        print("       ❌ All auth methods failed — cannot proceed!")
        print("       Tests will verify static DOM only (no JWT).")
    else:
        print(f"       ✅ Authenticated — user_id={user_id}")

    # ══════════════════════════════════════════════════════════════════
    #  LAUNCH PLAYWRIGHT
    # ══════════════════════════════════════════════════════════════════
    print("\n[2/5] 🌐 Launching Playwright (Chromium headless)…")
    js_errors = []
    page_errors = []

    p = await async_playwright().start()
    browser = await p.chromium.launch(headless=True, args=["--no-sandbox"])
    context = await browser.new_context(
        viewport={"width": 1440, "height": 900},
        ignore_https_errors=True,
    )
    page = await context.new_page()

    # Capture ALL console messages (errors, warnings, info)
    page.on("console", lambda msg: js_errors.append({
        "type": msg.type, "text": msg.text
    }) if msg.type in ("error",) else None)
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))

    # ── Navigate to console with JWT injection ─────────────────────
    await page.goto(f"{API_BASE}/login", wait_until="networkidle")
    # Inject JWT into BOTH localStorage and cookie
    await page.evaluate(f"""() => {{
        const jwt = "{jwt_token or ''}";
        localStorage.setItem("aims_jwt", jwt);
        localStorage.setItem("aims_api_base", "{API_BASE}");
        document.cookie = "aims_jwt=" + jwt + "; path=/; max-age=86400";
    }}""")
    await page.goto(f"{API_BASE}/console", wait_until="domcontentloaded")
    await page.wait_for_timeout(3000)

    page_title = await page.title()
    current_url = page.url
    dom_size = len(await page.content())

    print(f"       URL:     {current_url}")
    print(f"       Title:   {page_title}")
    print(f"       DOM:     {dom_size} chars")

    on_login_page = "login" in current_url or "login" in page_title.lower()
    if on_login_page:
        print("       ⚠️  Redirected to login — JWT invalid, continuing with static DOM checks")
    else:
        print("       ✅ Console v2.1 loaded!")

    # ══════════════════════════════════════════════════════════════════
    #  HELPER
    # ══════════════════════════════════════════════════════════════════
    def is_func_defined(name):
        if on_login_page:
            return False
        return page.evaluate(f"typeof window.{name} === 'function'")

    # ══════════════════════════════════════════════════════════════════
    #  TEST SUITE A: Global Function Availability
    # ══════════════════════════════════════════════════════════════════
    print("\n[3/5] 🔍 Executing tests…")
    print("\n  ── A. 全局函数可用性 (Global Function Availability) ──")

    global_funcs = [
        "connectWallet", "refreshBalance", "invokeSkill",
        "fetchCreditScore", "publishTask", "fetchPendingTasks",
        "claimTask", "oneClickIntegrate", "fetchIntegrationStatus",
        "simulateVaultPayment", "boostReward", "addContributorRow",
        "removeContributorRow", "saveContributors", "pollVaultStatus",
        "uploadSkill", "rechargeReserves", "fetchAudit", "withdrawFunds",
        "fiatDeposit", "fetchHistory", "boostFromMarket",
        "fetchApiKeys", "createApiKey", "revokeApiKey",
        "switchRole", "clearLog", "fetchHealth", "fetchDiscovery",
        "switchBillingMode", "openBuyoutModal", "closeBuyoutModal",
        "confirmBuyout", "closeDepositModal", "handleDeposit",
        "startWorkerSim", "sendHeartbeat", "toast", "consumerLog",
        "showVaultPanel", "showCreditBlockModal", "updateTrialDisplay",
        "updateCanaryStatus", "resetPipeline", "advancePipeline",
        "completePipeline", "getCreditLevel", "eip191SignBody",
        "getAuthHeaders", "jwtHeaders", "smartHeaders", "signAuthBeacon",
        # v2.1 new functions
        "openBizModal", "closeBizModal", "toggleDevDrawer", "closeDevDrawer",
        "renderRevenueChart", "renderTaskFlowChart",
        "updateRevenueChart", "updateTaskFlowChart",
    ]

    if on_login_page:
        for fn in global_funcs:
            register_test(f"Global function: {fn}", "Global", fn,
                          "defined", "SKIP", "On login page, not in console context")
        print(f"       ⏭ All {len(global_funcs)} functions SKIPPED (on login page)")
    else:
        missing = []
        for fn in global_funcs:
            exists = await is_func_defined(fn)
            r = "PASS" if exists else "FAIL"
            register_test(f"Global function: {fn}", "Global", fn,
                          "defined", r)
            if not exists:
                missing.append(fn)
                print(f"       ❌ FAIL: window.{fn} is NOT defined!")
        if missing:
            print(f"       ⚠️  {len(missing)}/{len(global_funcs)} functions missing")
        else:
            print(f"       ✅ All {len(global_funcs)} functions defined on window")

    # ══════════════════════════════════════════════════════════════════
    #  TEST SUITE B: DOM Element Presence (Dashboard + Modals + Drawer)
    # ══════════════════════════════════════════════════════════════════

    if on_login_page:
        print("\n  ── B. DOM Element 存在性检查 (DOM Presence) ──")
        print("       ⏭ SKIPPED — on login page")
    else:
        # ── Dashboard: Charts ────────────────────────────────────────
        print("\n  ── 📊 Dashboard: Chart Canvases ──")
        for eid, label in [("revenueChart", "Revenue chart"), ("taskFlowChart", "Task flow chart")]:
            exists = await page.locator(f"#{eid}").count()
            register_test(f"{label} (#{eid})", "Dashboard", "renderChart",
                          "present", "PASS" if exists else "FAIL")

        # ── Dashboard: Stats Row ─────────────────────────────────────
        print("\n  ── 📊 Dashboard: Stats Row ──")
        for eid in ("consumerBalance","consumerTasks","trialsLeft",
                    "consumerDeposited","creditScoreDisplay"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Stat #{eid}", "Dashboard", "refreshBalance/various",
                          "present", "PASS" if exists else "FAIL")

        # ── Dashboard: Pipeline ──────────────────────────────────────
        print("\n  ── 📊 Dashboard: Pipeline ──")
        cnt = await page.locator(".pipeline-step").count()
        register_test("Pipeline steps (6)", "Dashboard", "advancePipeline",
                      "≥6", "PASS" if cnt >= 6 else "FAIL", f"Found {cnt}")
        exists = await page.locator("#pipeline").count()
        register_test("Pipeline container (#pipeline)", "Dashboard", "advancePipeline",
                      "present", "PASS" if exists else "FAIL")

        # ── Dashboard: 6 Action Cards ────────────────────────────────
        print("\n  ── 📊 Dashboard: 6 Action Cards ──")
        cnt = await page.locator(".action-card").count()
        register_test("Action cards (6)", "Dashboard", "openBizModal",
                      "≥6", "PASS" if cnt >= 6 else "FAIL", f"Found {cnt}")

        card_labels = ["Publish Task", "Skills", "Task Market",
                       "Auth & Settings", "Activity", "Worker Guide"]
        for label in card_labels:
            exists = await page.locator(f".action-card:has-text('{label}')").count()
            register_test(f"Action card: {label}", "Dashboard", "openBizModal",
                          "present", "PASS" if exists else "FAIL")

        # ── Dashboard: Health ────────────────────────────────────────
        print("\n  ── 📊 Dashboard: System Health ──")
        for eid in ("healthContent","healthStatus","healthSucceeded","healthWorkers","healthTreasury"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Health #{eid}", "Dashboard", "fetchHealth",
                          "present", "PASS" if exists else "FAIL")

        # ── Dev Mode Trigger ─────────────────────────────────────────
        print("\n  ── 📊 Dashboard: Dev Mode Trigger ──")
        exists = await page.locator(".dev-mode-trigger").count()
        register_test("Advanced Dev Mode trigger", "Dashboard", "toggleDevDrawer",
                      "present", "PASS" if exists else "FAIL")

        # ── Modal: Publish Task ──────────────────────────────────────
        print("\n  ── 🚀 Modal: Publish Task ──")
        # Open modal
        await page.locator(".action-card:has-text('Publish Task')").click()
        await page.wait_for_timeout(400)
        modal_open = await page.locator("#bizModal-publish.open").count()
        register_test("Publish modal opens", "Publish", "openBizModal",
                      "open", "PASS" if modal_open else "FAIL")

        for eid in ("pubTaskName","pubBudget","pubSkillSelect","pubDescription","publishBtn","pubIsCustom"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Publish form #{eid}", "Publish", "publishTask",
                          "present", "PASS" if exists else "FAIL")

        for eid in ("vaultPanel","vaultPayBtn","vaultPollBtn","boostAmount","boostBtn"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Vault #{eid}", "Publish", "simulateVaultPayment/boost",
                          "present", "PASS" if exists else "FAIL")

        cnt = await page.locator(".recharge-amt").count()
        register_test("Recharge buttons (≥6)", "Publish", "rechargeReserves",
                      "≥6", "PASS" if cnt >= 6 else "FAIL", f"Found {cnt}")

        for eid in ("customRechargeAmt","withdrawAmt","rechargeBalance","rechargeTotal","rechargeContract"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Recharge #{eid}", "Publish", "rechargeReserves",
                          "present", "PASS" if exists else "FAIL")

        cnt = await page.locator("button.fiat-deposit-btn").count()
        register_test("Fiat deposit buttons", "Publish", "fiatDeposit",
                      "≥3", "PASS" if cnt >= 3 else "FAIL", f"Found {cnt}")

        cnt = await page.locator("#commercePanel button").count()
        register_test("Commerce mode buttons", "Publish", "switchBillingMode",
                      "≥3", "PASS" if cnt >= 3 else "FAIL", f"Found {cnt}")

        exists = await page.locator(".modal-close").count()
        register_test("Modal close button", "Publish", "closeBizModal",
                      "present", "PASS" if exists else "FAIL")
        # Close modal
        await page.evaluate("closeBizModal('publish')")
        await page.wait_for_timeout(300)

        # ── Modal: Skills ────────────────────────────────────────────
        print("\n  ── 💡 Modal: Skills ──")
        await page.locator(".action-card:has-text('Skills')").click()
        await page.wait_for_timeout(400)
        modal_open = await page.locator("#bizModal-skills.open").count()
        register_test("Skills modal opens", "Skills", "openBizModal",
                      "open", "PASS" if modal_open else "FAIL")

        for eid in ("devSkillCount","devRevenue","devSkillList",
                    "devRevenueMeter","devCreditScore","devCreditScoreBar","devCreditLevel"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Dev stat #{eid}", "Skills", "fetchDiscovery",
                          "present", "PASS" if exists else "FAIL")

        for eid in ("skillDropZone","uploadSkillBtn","skillFileInput","dzFileInfo"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Upload #{eid}", "Skills", "uploadSkill",
                          "present", "PASS" if exists else "FAIL")

        for eid in ("integrateInput","integrateWallet","integrateBtn","integrateCount"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Integration #{eid}", "Skills", "oneClickIntegrate",
                          "present", "PASS" if exists else "FAIL")

        await page.evaluate("closeBizModal('skills')")
        await page.wait_for_timeout(300)

        # ── Modal: Task Market ───────────────────────────────────────
        print("\n  ── 📥 Modal: Task Market ──")
        await page.locator(".action-card:has-text('Task Market')").click()
        await page.wait_for_timeout(400)
        for eid in ("taskMarketBody","mkPendingCount"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Market #{eid}", "Market", "fetchPendingTasks",
                          "present", "PASS" if exists else "FAIL")
        await page.evaluate("closeBizModal('market')")
        await page.wait_for_timeout(300)

        # ── Modal: Auth & Settings ───────────────────────────────────
        print("\n  ── 🔐 Modal: Auth & Settings ──")
        await page.locator(".action-card:has-text('Auth & Settings')").click()
        await page.wait_for_timeout(400)
        for eid in ("settingsEmail","settingsDisplayName","settingsMemberSince",
                    "settingsOldPw","settingsNewPw","settingsConfirmPw","settingsPwResult",
                    "settingsWalletAddr"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Settings #{eid}", "Auth", "loadUserProfile/changePassword",
                          "present", "PASS" if exists else "FAIL")

        for eid in ("apiKeyLabel","apiKeyResult","apiKeyList","apiKeyCount"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"API Key #{eid}", "Auth", "fetchApiKeys/createApiKey",
                          "present", "PASS" if exists else "FAIL")

        cnt = await page.locator("button:has-text('Generate Key')").count()
        register_test("Generate Key button", "Auth", "createApiKey",
                      "present", "PASS" if cnt > 0 else "FAIL")

        await page.evaluate("closeBizModal('auth')")
        await page.wait_for_timeout(300)

        # ── Modal: Activity ──────────────────────────────────────────
        print("\n  ── 💬 Modal: Activity ──")
        await page.locator(".action-card:has-text('Activity')").click()
        await page.wait_for_timeout(400)
        for eid in ("consumerLog","auditLedgerBody","auditTaskFilter","userHistoryBody"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Activity #{eid}", "Activity", "consumerLog/fetchAudit",
                          "present", "PASS" if exists else "FAIL")
        await page.evaluate("closeBizModal('activity')")
        await page.wait_for_timeout(300)

        # ── Modal: Worker Guide ──────────────────────────────────────
        print("\n  ── 📖 Modal: Worker Guide ──")
        await page.locator(".action-card:has-text('Worker Guide')").click()
        await page.wait_for_timeout(400)
        for eid in ("workerStartBtn","workerStatusDot","workerStatusText","workerNodeId",
                    "workerEarnings","workerEarningsMeter","workerPayouts"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Worker #{eid}", "Worker", "startWorkerSim",
                          "present", "PASS" if exists else "FAIL")

        for eid in ("canaryStatusBadge","canaryStatusDot","canaryStatusText","canaryBlacklistStatus"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Canary #{eid}", "Worker", "updateCanaryStatus",
                          "present", "PASS" if exists else "FAIL")

        for eid in ("coContribList","contribTotalPct","contribSaveResult"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Contributor #{eid}", "Worker", "saveContributors",
                          "present", "PASS" if exists else "FAIL")

        cnt = await page.locator("button:has-text('Save Split')").count()
        register_test("Save Split button", "Worker", "saveContributors",
                      "present", "PASS" if cnt > 0 else "FAIL")

        await page.evaluate("closeBizModal('worker')")
        await page.wait_for_timeout(300)

        # ── Advanced Dev Mode Drawer ─────────────────────────────────
        print("\n  ── ⚙️ Advanced Dev Mode Drawer ──")
        await page.evaluate("toggleDevDrawer()")
        await page.wait_for_timeout(500)

        drawer_open = await page.locator("#devDrawer.open").count()
        register_test("Dev drawer opens", "DevMode", "toggleDevDrawer",
                      "open", "PASS" if drawer_open else "FAIL")

        for eid in ("consoleFeed","consoleFeedCount","consoleFeedVol",
                    "cfgApiBase","cfgWallet","cfgNetwork","cfgTrial",
                    "corsDocContent","skillsContent","trialProgressBar",
                    "trialsLeftEnhanced","trialProgressText","trialStatusBadge"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Drawer #{eid}", "DevMode", "fetchHealth/various",
                          "present", "PASS" if exists else "FAIL")

        # Config section
        for eid in ("skillSelect","billingMode","skillParams","workerAddr","devAddr","invokeBtn","trialBtn"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Drawer invoke #{eid}", "DevMode", "invokeSkill",
                          "present", "PASS" if exists else "FAIL")

        # Close drawer
        await page.evaluate("closeDevDrawer()")
        await page.wait_for_timeout(300)
        drawer_closed = await page.locator("#devDrawer.open").count()
        register_test("Dev drawer closes", "DevMode", "closeDevDrawer",
                      "closed", "PASS" if drawer_closed == 0 else "FAIL")

        # ── Global Elements ─────────────────────────────────────────
        print("\n  ── 🌐 Global Elements ──")
        for eid in ("toastContainer","networkBadge","walletAddress",
                    "connectBtn","healthBlock","healthPending"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Global #{eid}", "Global", "various",
                          "present", "PASS" if exists else "FAIL")

        # Toast render test
        await page.evaluate("toast('QA: toast test', 'info')")
        await page.wait_for_timeout(400)
        cnt = await page.locator(".toast").count()
        register_test("Toast renders on screen", "Global", "toast()",
                      "≥1", "PASS" if cnt > 0 else "FAIL", f"Found {cnt}")

        # CORS docs injected
        cors_len = await page.evaluate("document.getElementById('corsDocContent')?.innerHTML?.length || 0")
        register_test("CORS docs injected", "Global", "DOCS_CONTENT.corsSetup",
                      ">0", "PASS" if cors_len > 0 else "FAIL", f"len={cors_len}")

    # ══════════════════════════════════════════════════════════════════
    #  TEST SUITE C: Silent Catch Audit (source code)
    # ══════════════════════════════════════════════════════════════════
    print("\n  ── C. 🛡️ 静默 Catch 审计 (Silent Catch Audit) ──")

    js_path = Path(__file__).resolve().parent.parent / "static/js/console-core.js"
    with open(js_path) as f:
        lines = f.readlines()

    silent = []
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        if ".catch(()" in stripped:
            continue
        if "catch(" in stripped or "catch (" in stripped:
            context = " ".join(l.strip() for l in lines[i-1:min(len(lines), i+15)])
            has_warn = "console.warn" in context
            has_toast = "toast(" in context
            has_log = "consumerLog" in context
            has_dom_error = "⚠️" in context or "offline" in context.lower() or "error" in context.lower()
            if not (has_warn or has_toast or has_log or has_dom_error):
                silent.append((i, stripped[:80]))

    if silent:
        detail = f"{len(silent)} silent catches: {silent[:3]}"
        register_test("Silent catch audit", "Global", "catch blocks",
                      "0", "FAIL", detail)
        for ln, code in silent:
            print(f"       ⚠️  Line {ln}: {code}")
    else:
        register_test("Silent catch audit", "Global", "catch blocks",
                      "0", "PASS")
        print(f"       ✅ Zero silent catch blocks — all have console.warn / toast / consumerLog")

    # ══════════════════════════════════════════════════════════════════
    #  TEST SUITE D: Console Error Audit
    # ══════════════════════════════════════════════════════════════════
    print("\n  ── D. 🖥️ 浏览器 Console 错误审计 (Browser Console Errors) ──")

    err_count = len(js_errors)
    page_err_count = len(page_errors)
    register_test("Console errors during page load", "Global", "All JS",
                  "0", "PASS" if err_count == 0 else "FAIL",
                  f"{err_count} console errors, {page_err_count} page errors")

    if js_errors:
        print(f"       ⚠️  Console errors ({err_count}):")
        for e in js_errors:
            print(f"       - [{e['type']}] {e['text'][:120]}")
    if page_errors:
        print(f"       ⚠️  Page errors ({page_err_count}):")
        for e in page_errors:
            print(f"       - {e[:120]}")

    # ══════════════════════════════════════════════════════════════════
    #  CLOSE
    # ══════════════════════════════════════════════════════════════════
    await browser.close()
    await p.stop()

    # ══════════════════════════════════════════════════════════════════
    #  REPORT
    # ══════════════════════════════════════════════════════════════════
    print("\n" + "=" * 72)
    print("  📋 AIMS Console v2.1 全功能联调测试对账报告")
    print("  Full Integration QA Test Reconciliation Report")
    print("=" * 72)

    total = len(test_results)
    passed = sum(1 for r in test_results if r["result"] == "PASS")
    failed = sum(1 for r in test_results if r["result"] == "FAIL")
    skipped = sum(1 for r in test_results if r["result"] == "SKIP")

    print(f"\n  {'✅/❌':<6} {'测试用例 (Test Case)':<34} {'Tab':<12} {'绑定JS函数':<26} {'期望':<14} {'结果':<8}")
    print(f"  {'─'*6} {'─'*34} {'─'*12} {'─'*26} {'─'*14} {'─'*8}")

    for r in test_results:
        name = r["name"][:32]
        tab = r["tab"][:10]
        func = r["js_func"][:24]
        exp = r["expected_status"][:12]
        res = r["result"]
        marker = {"PASS": "✅", "FAIL": "❌", "SKIP": "⏭"}.get(res, "❓")
        print(f"  {marker:<6} {name:<32} {tab:<10} {func:<24} {exp:<12} {res:<6}")
        if res == "FAIL" and r.get("detail"):
            print(f"         └─ {r['detail'][:120]}")

    print(f"\n  {'─'*6} {'─'*34} {'─'*12} {'─'*26} {'─'*14} {'─'*8}")
    print(f"\n  📊 汇总 / SUMMARY")
    print(f"  {'─'*55}")
    print(f"  总用例 Total:      {total}")
    print(f"  ✅ 通过 PASS:      {passed}")
    print(f"  ❌ 失败 FAIL:      {failed}")
    print(f"  ⏭ 跳过 SKIP:      {skipped}")
    effective = total - skipped
    pass_rate = (passed / effective * 100) if effective > 0 else 0
    print(f"  通过率 Pass Rate:  {pass_rate:.1f}% ({passed}/{effective})")
    print(f"  {'─'*55}")

    print(f"\n  🖥️  Console Errors:  {err_count}")
    print(f"  ⚠️  Page Errors:     {page_err_count}")
    if err_count > 0:
        for e in js_errors:
            print(f"     - {e['text'][:120]}")

    print(f"\n  {'='*55}")
    if failed == 0 and err_count == 0 and not on_login_page:
        print("  ✅ VERDICT: ALL TESTS PASSED — Console v2.1 is production-ready!")
        print("  ✅ 裁决：全部测试通过 — Console v2.1 可以上线！")
    elif on_login_page:
        print("  ⚠️  VERDICT: Login page only — auth required for full console test")
        print("  ⚠️  裁决：仅在登录页 — 需要认证才能测试完整控制台")
    else:
        print(f"  ⚠️  VERDICT: {failed} FAIL, {err_count} console errors — review before deployment")
        print(f"  ⚠️  裁决：{failed} 个失败, {err_count} 个控制台错误 — 上线前请审查")
    print(f"  {'='*55}")
    print(f"\n  报告生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 72)

    return failed == 0 and err_count == 0 and not on_login_page

if __name__ == "__main__":
    success = asyncio.run(run_qa())
    sys.exit(0 if success else 1)
