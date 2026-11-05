This system design plan translates the "Ghost Inventory" problem into a **Zero-LLM Agentic Architecture**. By replacing probabilistic AI with a deterministic state machine, we create a highly reliable, cost-effective, and auditable "Inventory Auditor Agent" that e-commerce owners can trust with their revenue.

Here is the exact structural plan, logic, and component breakdown for delivering this pipeline as a premium freelance service.

---

### System Overview: The Inventory Auditor Agent
*   **Agent Persona:** A deterministic, rules-based auditor that continuously monitors inventory drift between the storefront (Shopify) and the physical warehouse (3PL/WMS).
*   **Core Philosophy:** "Assume the physical warehouse is the source of truth, but verify before altering the storefront to prevent accidental overselling."
*   **Architecture Pattern:** Sense (n8n) → Target & Delegate (n8n Code) → Fetch & Compute (Windmill WAC) → Suspend for Human Truth (Windmill Approval) → Execute via Standardized Tool (n8n MCP/API) → Report (n8n).

---

### 1. The Sensor & Trigger Layer (n8n)
*The agent’s sensory nervous system that wakes up, evaluates the environment, and decides what needs auditing to respect API rate limits.*

*   **The Wake-Up Trigger (Schedule Node):**
    *   **Logic:** The agent wakes up daily at 2:00 AM local warehouse time (when physical stock movements have ceased).
*   **The Heuristic Sensor (n8n Code Node):**
    *   *Problem:* Fetching all 50,000 SKUs daily will hit Shopify API limits and cost money in 3PL API calls.
    *   *Heuristic Logic:* The Code Node queries the database (or yesterday's orders) to build a **"Target Audit List"**. It targets:
        1.  SKUs that had >5 sales yesterday (high velocity = high risk of drift).
        2.  SKUs that had a return or cancellation yesterday (reverse logistics drift).
        3.  A random 5% sample of "dead stock" (to catch slow-moving ghost inventory).
*   **The Router (Switch Node):**
    *   If the Target Audit List is empty, the agent terminates (saves compute).
    *   If the list has >0 items, the agent packages the list into a structured JSON payload and delegates it to Windmill via an HTTP Webhook.

### 2. The Deterministic Planner (Windmill Workflows as Code)
*The DAG (Directed Acyclic Graph) that manages parallel execution, state tracking, and human-in-the-loop suspensions.*

*   **Step 1: Parallel Fetching (Windmill `parallel()` & `task()`):**
    *   The agent receives the Target Audit List (e.g., 500 SKUs).
    *   It splits the list into batches of 50.
    *   Using `parallel()` with a `concurrency_limit`, it dispatches child jobs to fetch current Shopify stock and 3PL WMS stock simultaneously. This ensures the data represents the *exact same millisecond* in time, preventing false drift caused by API lag.
*   **Step 2: The Deterministic Brain (Windmill Python Script):**
    *   The fetched data is passed to a Python script. This is the agent's "brain" replacing an LLM.
    *   **Scoring Algorithm:** It calculates `Drift Score = (Shopify_Qty - WMS_Qty)`.
    *   **Categorization (State Machine):**
        *   *State A (Perfect Match):* Drift == 0.
        *   *State B (Safe Hidden Stock):* WMS_Qty > Shopify_Qty. (The warehouse has more than the website thinks).
        *   *State C (Ghost Stock Danger):* Shopify_Qty > WMS_Qty. (The website is selling items that don't exist).
        *   *State D (Transit Noise):* Drift is within a 2% margin and the SKU is currently flagged as "in transit" in the WMS.
*   **Step 3: Conditional Branching (Windmill DAG Branches):**
    *   *Branch A (Perfect Match / Transit Noise):* Log to internal database and silently terminate.
    *   *Branch B (Safe Hidden Stock):* Auto-execute an update to *increase* Shopify stock (Safe to sell more).
    *   *Branch C (Ghost Stock Danger):* Route to the **Suspension Protocol**.

### 3. The Suspension Protocol (Human-in-the-Loop)
*Replacing the LLM's "ask user for clarification" with a zero-worker-waste physical audit step.*

*   **The Suspend Step (Windmill `waitForApproval()`):**
    *   The agent pauses the DAG. Compute costs drop to $0.
    *   Windmill automatically generates a rich UI (via Windmill Apps) containing a table of the "Ghost Stock" SKUs.
    *   **The Action:** Windmill sends an automated Slack/Email message to the Warehouse Manager containing a magic link to the Windmill App.
    *   **The Form:** The manager walks the physical aisles, counts the bins, and types the *actual physical count* into the Windmill App form, then clicks "Approve & Sync".
*   **The Deterministic Timeout:**
    *   If the warehouse manager does not respond within 12 hours, the agent executes a fail-safe heuristic: it automatically forces Shopify stock to `0` for those specific SKUs to prevent customer chargebacks and negative reviews.

### 4. The Standardized Tool Executor (n8n MCP & API Nodes)
*How the agent physically alters the environment without hardcoding API keys into the compute engine.*

*   **The MCP Tool Registry:**
    *   Instead of Windmill talking directly to Shopify (which requires managing Shopify API tokens inside Windmill), Windmill acts as the client to n8n's MCP Server (or a dedicated n8n Webhook acting as a tool endpoint).
    *   **The Tool:** n8n holds a specialized workflow named `Update_Shopify_Inventory`.
*   **Execution:**
    *   Once the Warehouse Manager approves the counts in Windmill, Windmill passes the final, human-verified JSON array to the n8n Tool.
    *   n8n receives the payload, utilizes its built-in Shopify Node (which handles GraphQL batching, rate limiting, and automatic retries), and pushes the updates to the live store.
    *   *Why this is agentic:* The agent didn't just "guess" the fix; it verified the physical state and used a standardized, governed tool to mutate the digital environment.

### 5. The Report & Close Loop (n8n)
*Closing the agentic loop and providing transparency to the business owner.*

*   **The Callback Webhook:**
    *   Once n8n successfully updates Shopify, it sends a final callback webhook back to Windmill to mark the job as `Complete`.
*   **The Agentic Summary (n8n):**
    *   n8n generates a daily "Audit Report" summarizing:
        *   Total SKUs audited.
        *   Ghost stock prevented (e.g., "Stopped 45 oversells").
        *   Hidden revenue unlocked (e.g., "Increased stock on 12 items, unlocking estimated $4,000 in potential sales").
    *   n8n posts this summary to the company's main `#operations` Slack channel and saves a PDF to Google Drive for the owner's morning review.

---

### 6. Handling Edge Cases & "Agentic" Reflexes
To make this a premium freelance deliverable, you must design deterministic reflexes for system failures:

*   **Reflex 1: 3PL API Outage (The "Blind Agent"):**
    *   If the 3PL API returns a 503 error during the Fetch phase, the Windmill `retry` policy triggers 3 times with exponential backoff. If it still fails, the agent classifies the environment as "Blind" and aborts the run. It triggers an n8n alert to IT: *"Cannot audit today. WMS blind."* It will *not* alter Shopify stock blindly.
*   **Reflex 2: The "Flash Sale" Lock (State Locking):**
    *   If the agent detects (via n8n webhook) that a Shopify Flash Sale script was just activated, it immediately sets a global variable `is_lockdown = true`. The 2 AM auditor will check this variable and refuse to lower inventory counts during a high-traffic event, preventing the agent from accidentally pulling down stock during a viral TikTok moment.

### Freelance Delivery Framework
When pitching this to a client, you are not selling "scripts." You are selling an **Autonomous Inventory Controller**.

1.  **Phase 1: Sensor Calibration:** You spend week one analyzing their past 30 days of cancelled orders due to "out of stock" and tuning the n8n Code Node heuristics to target their specific problem SKUs.
2.  **Phase 2: Shadow Mode:** You run the Windmill DAG in "Mock Mode" where it calculates the drift and posts to Slack, but *blocks* the final n8n MCP execution. The warehouse manager reviews the agent's accuracy.
3.  **Phase 3: Agentic Autonomy:** You flip the switch. The agent now autonomously corrects safe discrepancies and uses `waitForApproval()` for dangerous ones, effectively acting as a 24/7 automated warehouse manager.