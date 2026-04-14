# Payment Model Architecture: Open-Source MCP with Paid Value-Add

## The Core Insight

The code is free. The intelligence is paid.

```mermaid
graph TB
    subgraph "FREE — Open Source Code"
        A[Google API Wrappers<br/>70+ tools] --> B[Gmail, Drive, Calendar<br/>Docs, Sheets, Chat, etc.]
        C[Auth System<br/>OAuth + API Keys] --> B
        D[x402 Payment Protocol<br/>EIP-3009 Settlement] --> B
    end

    subgraph "PAID — Hosted Intelligence"
        E[Qdrant Embeddings<br/>384d MiniLM + ColBERT]
        F[Template Library<br/>47 Jinja2 macros]
        G[Module Wrapper<br/>5000+ LOC introspection]
        H[LLM Sampling<br/>Context enrichment]
        I[Privacy Vault<br/>Per-session crypto PII]
    end

    B -.->|self-host = free| J[Self-Hosted Server]
    E & F & G & H & I -->|connect to hosted = paid| K[Hosted Platform]

    style A fill:#2d7d46,color:white
    style C fill:#2d7d46,color:white
    style D fill:#2d7d46,color:white
    style E fill:#c44569,color:white
    style F fill:#c44569,color:white
    style G fill:#c44569,color:white
    style H fill:#c44569,color:white
    style I fill:#c44569,color:white
```

---

## Where the Value Lives

### Layer 1: Commodity (Free) — Google API Wrappers

```mermaid
graph LR
    subgraph "Commodity Layer — Anyone Can Build This"
        direction TB
        Client[MCP Client] --> Tools
        Tools[70+ Google API Tools]
        Tools --> Gmail[Gmail<br/>search, send, reply, labels]
        Tools --> Drive[Drive<br/>list, upload, share]
        Tools --> Cal[Calendar<br/>events, scheduling]
        Tools --> Docs[Docs/Sheets/Slides<br/>CRUD operations]
        Tools --> Chat[Chat<br/>spaces, messages]
        Tools --> More[Forms, Photos, People, Tasks]
    end

    style Tools fill:#555,color:white
    style Client fill:#333,color:white
```

**Cost to replicate:** Days of work, well-documented Google APIs.
**Our cost to operate:** $0 (user's Google quota consumed, not ours).
**Monetization:** None — this is the open-source promise.

### Layer 2: Curated Intelligence (Pro) — Hosted Embeddings + Templates

```mermaid
graph TB
    subgraph "Value Layer — Requires Hosted Infrastructure"
        direction TB

        subgraph "Qdrant Semantic Search"
            Q1[mcp_tool_responses<br/>Every past tool result indexed]
            Q2[mcp_gchat_cards_v8<br/>3400+ card patterns]
            Q3[mcp_payment_receipts<br/>Usage audit trail]
            Q1 & Q2 & Q3 --> Embed[FastEmbed MiniLM-L6-v2<br/>384-dim vectors]
            Q2 --> ColBERT[ColBERT Multi-Vector<br/>128-dim token-level matching]
        end

        subgraph "Template Library"
            T1[colorful_email.j2<br/>Responsive email layouts]
            T2[workspace_dashboard.j2<br/>Analytics dashboards]
            T3[linkedin_digest.j2<br/>Social digest cards]
            T4[photo_album_email.j2<br/>Photo galleries]
            T5[47 templates total]
        end

        subgraph "Card Builder Pipeline"
            DSL[DSL Notation<br/>§δƁᵬℊǵ◦▼] --> Parse[Structure Parser]
            Parse --> Search[Semantic Search<br/>Similar past cards]
            Search --> Build[SmartCardBuilderV2<br/>3700+ LOC]
            Build --> Render[Jinja2 + Context<br/>Auto-resource injection]
            Render --> Card[Google Chat Card]
        end
    end

    style Embed fill:#e17055,color:white
    style ColBERT fill:#e17055,color:white
    style DSL fill:#6c5ce7,color:white
    style Build fill:#6c5ce7,color:white
```

**Cost to replicate:** Weeks of work + ongoing curation of card patterns and templates.
**Our cost to operate:** ~$50-150/mo (Qdrant cloud) + compute.
**Monetization:** Pro tier — access to hosted embeddings, search, templates, and the card builder.

### Layer 3: Platform Intelligence (Enterprise) — LLM + Module System

```mermaid
graph TB
    subgraph "Platform Layer — Deep Infrastructure"
        direction TB

        subgraph "LLM Sampling Middleware"
            S1[Resource-Aware Prompting<br/>Inject user workspace stats]
            S2[Historical Pattern Matching<br/>Query past successful patterns]
            S3[Macro Discovery<br/>Suggest relevant templates]
            S4[DSL Error Recovery<br/>LLM corrects malformed DSL]
            S1 & S2 & S3 & S4 --> Sample[ctx.sample → Claude API<br/>Direct token cost]
        end

        subgraph "Module Wrapper System"
            MW1[Dynamic Python Introspection<br/>Reflects any module]
            MW2[13 Specialized Mixins<br/>Search, Graph, Embedding, Cache...]
            MW3[Symbol Generation<br/>Unicode DSL for components]
            MW4[Relationship Discovery<br/>Inter-component dependencies]
            MW1 & MW2 & MW3 & MW4 --> Wrap[Wrapped Module<br/>MCP-discoverable components]
        end

        subgraph "Privacy Vault"
            PV1[HKDF-SHA256 Key Derivation<br/>Per-session Fernet keys]
            PV2[PII Scanner<br/>Pattern + denylist detection]
            PV3[Token Masking<br/>PRIVATE:token_N placeholders]
            PV1 & PV2 & PV3 --> Vault[Crypto-Bound PII Vault<br/>Server-side only]
        end
    end

    style Sample fill:#d63031,color:white
    style Wrap fill:#0984e3,color:white
    style Vault fill:#00b894,color:white
```

**Cost to replicate:** Months of engineering — module wrapper alone is 5000+ LOC.
**Our cost to operate:** ~$0.001-0.01/sample (LLM tokens) + compute.
**Monetization:** Enterprise tier — sampling costs passed through, full platform access.

---

## How the Payment Flow Works

```mermaid
sequenceDiagram
    participant Client as MCP Client
    participant MW as Payment Middleware
    participant Tiers as Tier Registry
    participant Session as Session Store
    participant x402 as x402 Facilitator
    participant Chain as Base (On-Chain)

    Client->>MW: call_tool("send_dynamic_card", {...})
    MW->>Tiers: get_required_tier("send_dynamic_card")
    Tiers-->>MW: "pro"

    MW->>Session: get_session_tier(session_id)
    Session-->>MW: "free" (no payment yet)

    MW->>Session: check_github_star()
    Session-->>MW: not verified

    MW->>Session: check_free_trial()
    Session-->>MW: expired / exhausted

    MW-->>Client: 402 Payment Required<br/>tier: "pro", amount: 0.01 USDC<br/>meta.x402.paymentRequired = base64(...)

    Note over Client: Client wallet signs<br/>EIP-3009 authorization<br/>(off-chain, zero gas)

    Client->>MW: call_tool("send_dynamic_card", {_x402_payment: "base64..."})
    MW->>x402: verify_payment(signed_payload)
    x402-->>MW: ✓ valid signature

    MW->>MW: Execute tool (card builder runs)
    MW-->>Client: Tool result + card output

    MW->>x402: settle_payment(payload)
    x402->>Chain: transferWithAuthorization<br/>0.001 USDC moves on-chain
    x402-->>MW: settlement_tx_hash

    MW->>Session: cache: tier="pro", TTL=60min
    MW->>Session: store HMAC-signed receipt

    Note over Client,Chain: Subsequent Pro tool calls<br/>use cached session for 60 min
```

---

## Tier Enforcement: Two-Layer Defense

```mermaid
graph TB
    subgraph "Layer 1: Visibility (SessionToolFilteringMiddleware)"
        LT[list_tools request] --> Check1{Session tier?}
        Check1 -->|free| Hide[Hide Pro+Enterprise tools<br/>Client only sees 70 free tools]
        Check1 -->|pro| Show1[Show Free + Pro tools]
        Check1 -->|enterprise| Show2[Show all tools]
    end

    subgraph "Layer 2: Enforcement (X402PaymentMiddleware)"
        CT[call_tool request] --> Check2{Tool tier required?}
        Check2 -->|free| Pass[Execute immediately]
        Check2 -->|pro/enterprise| Check3{Session authorized?}
        Check3 -->|yes| Pass
        Check3 -->|no| Block[Return 402 with<br/>tier-specific amount]
    end

    Hide -.->|Tool invisible, but if<br/>called directly...| CT
    Show1 --> CT
    Show2 --> CT

    style Hide fill:#e17055,color:white
    style Block fill:#e17055,color:white
    style Pass fill:#2d7d46,color:white
```

---

## Onboarding Funnel

```mermaid
graph TD
    New[New User Connects] --> Auth{Authenticated?}
    Auth -->|No| FreeOnly[Free tier only<br/>70+ Google API tools]
    Auth -->|OAuth/API Key| Onboard[Session created]

    Onboard --> Trial{Free trial<br/>available?}
    Trial -->|First time| StartTrial[7-day trial / 50 calls<br/>Pro tier unlocked]
    Trial -->|Expired| CheckStar{Starred repo<br/>on GitHub?}

    StartTrial --> UsePro[Use Pro tools<br/>Card builder, search, templates]
    UsePro --> TrialEnd{Trial expired?}
    TrialEnd -->|No| UsePro
    TrialEnd -->|Yes| CheckStar

    CheckStar -->|Yes| StarPro[Pro tier FREE<br/>Renewable every 30 days]
    CheckStar -->|No| PayWall{Need Pro tools?}

    PayWall -->|No| FreeOnly
    PayWall -->|Yes| Pay[x402 Payment<br/>0.01 USDC/session]
    Pay --> ProAccess[Pro tier for 60 min]

    PayWall -->|Enterprise| PayMore[x402 Payment<br/>0.05 USDC/session]
    PayMore --> EntAccess[Enterprise tier for 120 min]

    style StartTrial fill:#00b894,color:white
    style StarPro fill:#00b894,color:white
    style Pay fill:#6c5ce7,color:white
    style PayMore fill:#6c5ce7,color:white
    style FreeOnly fill:#555,color:white
```

---

## Revenue Model

```mermaid
pie title Revenue Sources (Projected)
    "Pro Subscriptions ($9.99/mo)" : 40
    "Enterprise Subscriptions ($29.99/mo)" : 30
    "Per-Session x402 Payments" : 20
    "Sampling Cost Pass-Through" : 10
```

### Cost vs. Revenue at Scale

```mermaid
graph LR
    subgraph "Monthly Costs (~$150-260)"
        C1[Qdrant Cloud<br/>$50-150]
        C2[Compute<br/>$30-60]
        C3[LLM Sampling<br/>$20-50]
    end

    subgraph "Break-Even Scenarios"
        B1[5 Enterprise + 10 Pro<br/>= $250/mo]
        B2[25 per-session payments/day<br/>= $225/mo]
        B3[Mixed: subs + per-session<br/>= $200-400/mo]
    end

    C1 & C2 & C3 --> BE[Break-even:<br/>~15-20 paid users]
    BE --> B1 & B2 & B3

    style BE fill:#fdcb6e,color:black
```

---

## Receipt & Metering Pipeline

```mermaid
graph LR
    subgraph "Per Tool Call"
        Tool[Tool Executes] --> Receipt[Create HMAC Receipt<br/>payer + tool + amount + tier]
        Receipt --> Session[Store in Session<br/>6 SessionKeys]
        Receipt --> Qdrant[Fire-and-Forget<br/>Qdrant Upsert]
    end

    subgraph "Qdrant Receipt Collection"
        Qdrant --> Idx1[Index: payer_wallet]
        Qdrant --> Idx2[Index: tool_name]
        Qdrant --> Idx3[Index: timestamp_unix]
        Qdrant --> Idx4[Index: amount]
        Qdrant --> Idx5[Index: tier]
        Qdrant --> Idx6[Index: network]
    end

    subgraph "Usage Queries"
        Idx1 & Idx3 --> Q1[Revenue by wallet<br/>over time]
        Idx2 & Idx4 --> Q2[Revenue by tool<br/>most popular]
        Idx5 & Idx3 --> Q3[Tier conversion<br/>free → pro → enterprise]
        Idx6 --> Q4[Chain distribution<br/>Base vs Ethereum]
    end

    style Receipt fill:#e17055,color:white
    style Qdrant fill:#0984e3,color:white
```

---

## What's On-Chain vs. Off-Chain

```mermaid
graph TB
    subgraph "On-Chain (Base Sepolia/Mainnet)"
        OC1[transferWithAuthorization calldata<br/>from, to, value, nonce, signature]
        OC2[USDC Transfer Event<br/>from → to, amount]
        OC3[Settlement TX Hash<br/>Publicly verifiable]
    end

    subgraph "Facilitator Only (HTTPS, not on-chain)"
        F1[PaymentPayload envelope<br/>x402Version, scheme]
        F2[resource.url<br/>mcp://workspace.mcp/tool/send_dynamic_card]
        F3[extensions.mcpBinding<br/>emailHash, sessionPrefix, timestamp]
    end

    subgraph "Server Only (In-Memory + Qdrant)"
        S1[HMAC-Signed Receipt<br/>Full payer identity]
        S2[Session Data<br/>email, google_sub, provenance]
        S3[Privacy Vault<br/>Encrypted PII tokens]
    end

    style OC1 fill:#2d7d46,color:white
    style OC2 fill:#2d7d46,color:white
    style OC3 fill:#2d7d46,color:white
    style F1 fill:#fdcb6e,color:black
    style F2 fill:#fdcb6e,color:black
    style F3 fill:#fdcb6e,color:black
    style S1 fill:#e17055,color:white
    style S2 fill:#e17055,color:white
    style S3 fill:#e17055,color:white
```

---

## Architectural Summary

| Concern | Where It Lives | How It's Enforced |
|---------|---------------|-------------------|
| **Tool classification** | `middleware/payment/tiers.py` — TierDefinition registry | `get_tier_for_tool()` → None/pro/enterprise |
| **Tool visibility** | `middleware/session_tool_filtering_middleware.py` | Premium tools hidden from `list_tools` |
| **Payment gating** | `middleware/payment/middleware.py` | 402 response with tier-specific amount |
| **x402 settlement** | `middleware/payment/x402_server.py` + Coinbase facilitator | EIP-3009 verify → execute → settle |
| **Identity binding** | `middleware/payment/receipt.py` | HMAC receipt ties wallet to email/sub |
| **Receipt storage** | `middleware/payment/receipt_store.py` → Qdrant | Fire-and-forget, indexed for billing |
| **GitHub star check** | `middleware/payment/github_stars.py` (planned) | Public API check, session-cached |
| **Free trial** | `middleware/payment/trial.py` (planned) | Per-email-hash, Qdrant-persisted counter |
| **Usage metering** | `middleware/payment/metering.py` (planned) | Qdrant queries over receipt collection |
| **Sampling costs** | `middleware/sampling_middleware.py` | Token count → supplementary receipt |
