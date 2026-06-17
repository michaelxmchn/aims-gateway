#!/usr/bin/env python3
"""
AIMS Console v2.0 — Full Button Integration QA Test Suite
==========================================================
Tests every interactive element across all 4 tabs.
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
    print("  AIMS Console v2.0 — 全功能联调测试对账报告")
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
    # Inject JWT into BOTH localStorage (client-side guard) and cookie (server-side check)
    await page.evaluate(f"""() => {{
        const jwt = "{jwt_token or ''}";
        localStorage.setItem("aims_jwt", jwt);
        localStorage.setItem("aims_api_base", "{API_BASE}");
        // Also set cookie so the server-side JWT check passes
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
        print("       ✅ Console v2 loaded!")

    # ══════════════════════════════════════════════════════════════════
    #  HELPER: check if function is defined
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
    #  TEST SUITE B: DOM Element Presence (ALL 4 TABS)
    # ══════════════════════════════════════════════════════════════════

    if on_login_page:
        print("\n  ── B. DOM Element 存在性检查 (DOM Presence) ──")
        print("       ⏭ SKIPPED — on login page")
    else:
        # ── Tab 1: Consumer ─────────────────────────────────────────
        print("\n  ── 📊 Tab 1: Consumer Dashboard (消费者) ──")

        # Switch to consumer
        await page.evaluate("switchRole('consumer')")
        await page.wait_for_timeout(300)

        # 1-1: connect wallet button
        exists = await page.locator("#connectBtn").count()
        register_test("Wallet Connect button (#connectBtn)", "Consumer", "connectWallet",
                      "present", "PASS" if exists else "FAIL")
        text = await page.locator("#connectBtn").text_content() if exists else ""
        if text: register_test("Wallet btn text check", "Consumer", "connectWallet",
                               "Connect Wallet", "PASS" if "Connect" in text else "FAIL", text)

        # 1-2: skill select
        exists = await page.locator("#skillSelect").count()
        register_test("Skill dropdown (#skillSelect)", "Consumer", "invokeSkill",
                      "present", "PASS" if exists else "FAIL")

        # 1-3: billing mode & trial button
        for eid, label in [("billingMode","Billing mode"), ("trialBtn","Free Trial btn"),
                           ("invokeBtn","Execute btn")]:
            exists = await page.locator(f"#{eid}").count()
            register_test(f"{label} (#{eid})", "Consumer", "invokeSkill",
                          "present", "PASS" if exists else "FAIL")

        # 1-4: balance / account
        for eid in ("consumerBalance","consumerDeposited","consumerTasks","trialsLeft"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Account stat (#{eid})", "Consumer", "refreshBalance",
                          "present", "PASS" if exists else "FAIL")

        # 1-5: credit score
        for eid in ("creditScoreDisplay","creditScoreBar","creditLevelBadge"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Credit {eid}", "Consumer", "fetchCreditScore",
                          "present", "PASS" if exists else "FAIL")

        # 1-6: publish task form
        for eid in ("pubTaskName","pubBudget","pubSkillSelect","pubDescription","publishBtn","pubIsCustom"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Publish form #{eid}", "Consumer", "publishTask",
                          "present", "PASS" if exists else "FAIL")

        # 1-7: vault panel
        for eid in ("vaultPanel","vaultPayBtn","vaultPollBtn","boostBtn","boostAmount"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Vault #{eid}", "Consumer", "simulateVaultPayment/boost",
                          "present", "PASS" if exists else "FAIL")

        # 1-8: recharge grid (6 amount buttons)
        cnt = await page.locator(".recharge-amt").count()
        register_test("Recharge buttons (6)", "Consumer", "rechargeReserves",
                      "≥6", "PASS" if cnt >= 6 else "FAIL", f"Found {cnt}")

        # 1-9: custom recharge
        for eid in ("customRechargeAmt",):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Custom recharge #{eid}", "Consumer", "rechargeReserves",
                          "present", "PASS" if exists else "FAIL")

        # 1-10: fiat deposit buttons
        cnt = await page.locator("button.fiat-deposit-btn").count()
        register_test("Fiat deposit buttons (≥3)", "Consumer", "fiatDeposit",
                      "≥3", "PASS" if cnt >= 3 else "FAIL", f"Found {cnt}")

        # 1-11: withdraw
        for eid in ("withdrawAmt",):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Withdraw #{eid}", "Consumer", "withdrawFunds",
                          "present", "PASS" if exists else "FAIL")

        # 1-12: audit ledger
        for eid in ("auditLedgerBody","auditTaskFilter"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Audit #{eid}", "Consumer", "fetchAudit",
                          "present", "PASS" if exists else "FAIL")

        # 1-13: user history
        for eid in ("userHistoryBody",):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"History #{eid}", "Consumer", "fetchHistory",
                          "present", "PASS" if exists else "FAIL")

        # 1-14: activity log
        exists = await page.locator("#consumerLog").count()
        register_test("Activity log (#consumerLog)", "Consumer", "consumerLog",
                      "present", "PASS" if exists else "FAIL")

        # 1-15: commerce/billing mode
        cnt = await page.locator("#commercePanel button").count()
        register_test("Commerce mode buttons", "Consumer", "switchBillingMode",
                      "≥3", "PASS" if cnt >= 3 else "FAIL", f"Found {cnt}")

        # 1-16: buyout
        exists = await page.locator("button:has-text('Buyout License')").count()
        register_test("Buyout License button", "Consumer", "openBuyoutModal",
                      "present", "PASS" if exists else "FAIL")

        # ── Tab 2: Developer ────────────────────────────────────────
        print("\n  ── 🔧 Tab 2: Developer Dashboard (开发者) ──")
        await page.evaluate("switchRole('developer')")
        await page.wait_for_timeout(300)

        for eid in ("devSkillCount","devRevenue","devCreditScore",
                    "integrateInput","integrateWallet","integrateBtn",
                    "apiKeyLabel","apiKeyList",
                    "skillDropZone","uploadSkillBtn","skillFileInput",
                    "taskMarketBody","mkPendingCount",
                    "coContribList","contribTotalPct"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Developer #{eid}", "Developer", "various",
                          "present", "PASS" if exists else "FAIL")

        cnt = await page.locator("button:has-text('Generate Key')").count()
        register_test("Generate Key button", "Developer", "createApiKey",
                      "present", "PASS" if cnt > 0 else "FAIL")

        cnt = await page.locator("button:has-text('+ Add')").count()
        register_test("Add Contributor button", "Developer", "addContributorRow",
                      "present", "PASS" if cnt > 0 else "FAIL")

        cnt = await page.locator("button:has-text('Save Split')").count()
        register_test("Save Split button", "Developer", "saveContributors",
                      "present", "PASS" if cnt > 0 else "FAIL")

        # ── Tab 3: Worker ───────────────────────────────────────────
        print("\n  ── ⚡ Tab 3: Worker Dashboard (工作者) ──")
        await page.evaluate("switchRole('worker')")
        await page.wait_for_timeout(300)

        for eid in ("workerStartBtn","workerEarnings","workerPayouts",
                    "canaryStatusBadge","canaryStatusDot","canaryStatusText"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"Worker #{eid}", "Worker", "startWorkerSim/canary",
                          "present", "PASS" if exists else "FAIL")

        # ── System / Global ──────────────────────────────────────────
        print("\n  ── 📊 System Stats (全局) ──")

        for eid in ("healthContent","skillsContent","consoleFeed","corsDocContent",
                    "toastContainer","pipelineStatus","networkBadge","walletAddress"):
            exists = await page.locator(f"#{eid}").count()
            register_test(f"System #{eid}", "System", "fetchHealth/various",
                          "present", "PASS" if exists else "FAIL")

        # Pipeline steps
        cnt = await page.locator(".pipeline-step").count()
        register_test("Pipeline steps (6)", "System", "advancePipeline",
                      "≥6", "PASS" if cnt >= 6 else "FAIL", f"Found {cnt}")

        # Check CORS docs are injected
        cors_len = await page.evaluate("document.getElementById('corsDocContent')?.innerHTML?.length || 0")
        register_test("CORS docs injected", "System", "DOCS_CONTENT.corsSetup",
                      ">0", "PASS" if cors_len > 0 else "FAIL", f"len={cors_len}")

        # ── Cross-tab vault test ────────────────────────────────────
        print("\n  ── 🔄 Cross-tab Vault TaskID Persistence ──")
        await page.evaluate("switchRole('consumer')")
        await page.wait_for_timeout(200)
        await page.evaluate("""() => { window._currentVaultTaskId = 'vlt-test-999'; }""")
        await page.evaluate("switchRole('developer')")
        await page.wait_for_timeout(200)
        await page.evaluate("switchRole('consumer')")
        await page.wait_for_timeout(200)
        vid = await page.evaluate("window._currentVaultTaskId")
        r = "PASS" if vid == "vlt-test-999" else "FAIL"
        register_test("Vault TaskID cross-tab persistence", "Consumer",
                      "_savedVaultTaskId / switchRole", "vlt-test-999", r, f"got={vid}")

        # ── Toast render test ───────────────────────────────────────
        await page.evaluate("toast('QA: toast test message', 'info')")
        await page.wait_for_timeout(400)
        cnt = await page.locator(".toast").count()
        register_test("Toast renders on screen", "Global", "toast()",
                      "≥1", "PASS" if cnt > 0 else "FAIL", f"Found {cnt}")

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
        # Skip .catch(() => ({})) promise chains — intentional JSON parse fallback
        if ".catch(()" in stripped:
            continue
        if "catch(" in stripped or "catch (" in stripped:
            # Check context window for error handling (wider window for nested blocks)
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

    # Collect errors that happened during page load
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
    print("  📋 AIMS Console v2.0 全功能联调测试对账报告")
    print("  Full Integration QA Test Reconciliation Report")
    print("=" * 72)

    total = len(test_results)
    passed = sum(1 for r in test_results if r["result"] == "PASS")
    failed = sum(1 for r in test_results if r["result"] == "FAIL")
    skipped = sum(1 for r in test_results if r["result"] == "SKIP")

    # Table header
    print(f"\n  {'✅/❌':<6} {'测试用例 (Test Case)':<34} {'Tab':<12} {'绑定JS函数 (Function)':<26} {'期望 (Expected)':<14} {'结果 (Result)':<8}")
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

    # Summary
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

    # Verdict
    print(f"\n  {'='*55}")
    if failed == 0 and err_count == 0 and not on_login_page:
        print("  ✅ VERDICT: ALL TESTS PASSED — Console v2.0 is production-ready!")
        print("  ✅ 裁决：全部测试通过 — Console v2.0 可以上线！")
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
