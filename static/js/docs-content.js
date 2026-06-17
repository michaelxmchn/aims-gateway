// ════════════════════════════════════════════════════════════════
//  AIMS Gateway Console v2 — Platform Documentation Content
//  Extracted from console.html for modular maintainability
//  ════════════════════════════════════════════════════════════════

const DOCS_CONTENT = {
  corsSetup: `
<p><strong style="color:#fff">API Base URL:</strong> <code id="corsApiBase" style="color:var(--neon);background:rgba(222,255,154,0.06);padding:0.15rem 0.4rem;border-radius:3px">http://127.0.0.1:8000</code></p>
<p><strong style="color:#fff">Backend CORS config</strong> — add to <code style="color:var(--neon)">src/gateway/server.py</code> before any routes:</p>
<pre style="background:#0a0f1a;padding:1rem;border-radius:6px;margin-top:0.5rem;overflow-x:auto;font-size:0.7rem;color:#cbd5e1">from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Dev only! Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)</pre>
<p style="margin-top:0.5rem"><strong style="color:#fff">Headers required</strong> for authenticated POST requests:</p>
<pre style="background:#0a0f1a;padding:0.75rem 1rem;border-radius:6px;margin-top:0.25rem;font-size:0.7rem;color:#cbd5e1">X-Wallet-Address: 0x...
X-Signature: &lt;EIP-191 personal_sign hex&gt;
X-Timestamp: &lt;UNIX seconds&gt;
Content-Type: application/json</pre>`,

  integrationGuide: `
<p>Enter a <strong style="color:#fff">Skill name</strong> (e.g. <code style="color:var(--neon)">amazon_scraper</code>) or a <strong style="color:#fff">third-party API URL</strong>.
The system auto-detects the type and binds <strong style="color:#a78bfa">70%</strong> streaming revenue to your wallet.
No CLI, no SDK, no configuration files.</p>`,

  skillUploadGuide: `
Package your Python Skill into a <strong style="color:#fff">ZIP archive</strong> with a <code style="color:var(--neon)">manifest.json</code> and <code style="color:var(--neon)">main.py</code>. The gateway auto-registers the Skill, extracts metadata, and makes it available for invocation. <strong>DRM obfuscation</strong> via <code style="color:var(--neon)">aims-cli publish</code> recommended for production.`,

  devModeNote: `<strong style="color:var(--amber);">⚠️ Dev-mode upload:</strong> Skills are registered in-memory. For DRM-protected publishing with AES-256 encryption, EIP-191 signing, and on-chain registration, use <code style="color:var(--neon)">aims-cli publish</code> from the CLI SDK.`,

  consumerDashboardHint: `Invoke AI skills with your wallet — EIP-191 signed, on-chain settled. <strong style="color:#34d399">First task free per Skill.</strong>`,

  developerDashboardHint: `Your skills, your <strong style="color:#a78bfa">70%</strong> streaming revenue — settled on-chain every task. Use <code style="color:var(--neon)">aims-cli publish</code> for DRM protection.`,

  workerDashboardHint: `Run an AIMS node — earn <strong style="color:#22c55e">25% commission</strong> selling residential bandwidth`,

  trialBannerText: `Every wallet gets <strong style="color:#34d399">1 free invocation per Skill</strong> — zero USDC required. <strong>LLM-as-a-Judge</strong> arbitrates quality; failed trials don't count.`,

  freeTrialNote: `✓ Free trial available for this Skill`,
};
