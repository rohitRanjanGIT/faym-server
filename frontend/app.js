// Simple vanilla-JS dashboard for the Payout backend.
// Served same-origin from FastAPI, so API base is just "".

const $ = (sel) => document.querySelector(sel);
let currentUser = "john_doe";

// ---- API helper -----------------------------------------------------------
async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(path, {
    method,
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = res.status === 204 ? null : await res.json().catch(() => null);
  if (!res.ok) {
    const msg = data?.detail || data?.error || `Request failed (${res.status})`;
    throw new Error(msg);
  }
  return data;
}

// ---- Toast ----------------------------------------------------------------
let toastTimer;
function toast(message, ok = true) {
  const el = $("#toast");
  el.textContent = message;
  el.className = `toast show ${ok ? "ok" : "err"}`;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.className = "toast"), 3200);
}

// ---- Formatting -----------------------------------------------------------
const rupee = (n) =>
  "₹" + Number(n).toLocaleString("en-IN", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const pill = (status) => `<span class="pill ${status}">${status}</span>`;
const signClass = (n) => (n < 0 ? "neg" : n > 0 ? "pos" : "");

// ---- Renderers ------------------------------------------------------------
function renderBalance(balance) {
  $("#balance").textContent = rupee(balance.withdrawable_balance_rupees);
  $("#currentUser").textContent = currentUser;
  renderLedger(balance.ledger);
}

function renderLedger(ledger) {
  const body = $("#ledgerTable tbody");
  if (!ledger.length) {
    body.innerHTML = `<tr class="empty"><td colspan="5">No ledger entries yet</td></tr>`;
    return;
  }
  body.innerHTML = ledger
    .map((e) => {
      const bal = e.balance_after_rupees == null ? "—" : rupee(e.balance_after_rupees);
      return `<tr>
        <td>${e.id}</td>
        <td>${e.entry_type}</td>
        <td class="${signClass(e.amount_rupees)}">${rupee(e.amount_rupees)}</td>
        <td>${bal}</td>
        <td class="muted">${e.note ?? ""}</td>
      </tr>`;
    })
    .join("");
}

function renderSales(sales) {
  const body = $("#salesTable tbody");
  if (!sales.length) {
    body.innerHTML = `<tr class="empty"><td colspan="6">No sales yet — add one above</td></tr>`;
    return;
  }
  body.innerHTML = sales
    .map((s) => {
      const actions = s.reconciled
        ? `<span class="muted">settled</span>`
        : `<div class="actions">
             <button class="btn sm green" data-approve="${s.id}">Approve</button>
             <button class="btn sm red" data-reject="${s.id}">Reject</button>
           </div>`;
      return `<tr>
        <td>${s.id}</td>
        <td>${s.brand}</td>
        <td>${rupee(s.earning_rupees)}</td>
        <td>${pill(s.status)}</td>
        <td>${rupee(s.advance_paid_rupees)}</td>
        <td class="right">${actions}</td>
      </tr>`;
    })
    .join("");
}

function renderWithdrawals(rows) {
  const body = $("#withdrawalsTable tbody");
  if (!rows.length) {
    body.innerHTML = `<tr class="empty"><td colspan="4">No withdrawals yet</td></tr>`;
    return;
  }
  body.innerHTML = rows
    .map((w) => {
      const actions =
        w.status === "initiated"
          ? `<div class="actions">
               <button class="btn sm green" data-complete="${w.id}">Complete</button>
               <button class="btn sm red" data-fail="${w.id}">Fail</button>
             </div>`
          : `<span class="muted">${w.failure_reason ?? "—"}</span>`;
      return `<tr>
        <td>${w.id}</td>
        <td>${rupee(w.amount_rupees)}</td>
        <td>${pill(w.status)}</td>
        <td class="right">${actions}</td>
      </tr>`;
    })
    .join("");
}

// ---- Load everything for the current user ---------------------------------
async function refresh() {
  try {
    const [balance, sales, withdrawals] = await Promise.all([
      api(`/users/${currentUser}/balance`).catch(() => ({
        withdrawable_balance_rupees: 0,
        ledger: [],
      })),
      api(`/users/${currentUser}/sales`).catch(() => []),
      api(`/users/${currentUser}/withdrawals`).catch(() => []),
    ]);
    renderBalance(balance);
    renderSales(sales);
    renderWithdrawals(withdrawals);
  } catch (err) {
    toast(err.message, false);
  }
}

// ---- Events ---------------------------------------------------------------
$("#loadBtn").addEventListener("click", () => {
  const v = $("#userInput").value.trim();
  if (!v) return;
  currentUser = v;
  refresh();
});

$("#saleForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/sales", {
      method: "POST",
      body: {
        user_id: currentUser,
        brand: $("#saleBrand").value,
        earning: parseFloat($("#saleEarning").value),
      },
    });
    toast("Sale created");
    refresh();
  } catch (err) {
    toast(err.message, false);
  }
});

$("#advanceBtn").addEventListener("click", async () => {
  try {
    const r = await api(`/jobs/advance-payout?user_id=${encodeURIComponent(currentUser)}`, {
      method: "POST",
    });
    toast(`Advance job: ${r.advances_made} paid (${rupee(r.total_advance_rupees)})`);
    refresh();
  } catch (err) {
    toast(err.message, false);
  }
});

$("#withdrawForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    await api("/withdrawals", {
      method: "POST",
      body: { user_id: currentUser, amount: parseFloat($("#withdrawAmount").value) },
    });
    toast("Withdrawal initiated");
    $("#withdrawAmount").value = "";
    refresh();
  } catch (err) {
    toast(err.message, false);
  }
});

// Delegated clicks for the dynamic table buttons.
document.addEventListener("click", async (e) => {
  const t = e.target;
  try {
    if (t.dataset.approve) {
      await reconcile(t.dataset.approve, "approved");
    } else if (t.dataset.reject) {
      await reconcile(t.dataset.reject, "rejected");
    } else if (t.dataset.complete) {
      await api(`/withdrawals/${t.dataset.complete}/complete`, { method: "POST" });
      toast("Withdrawal completed");
      refresh();
    } else if (t.dataset.fail) {
      await api(`/withdrawals/${t.dataset.fail}/fail`, {
        method: "POST",
        body: { status: "failed", reason: "manual fail from dashboard" },
      });
      toast("Payout failed — amount credited back");
      refresh();
    }
  } catch (err) {
    toast(err.message, false);
  }
});

async function reconcile(saleId, status) {
  await api("/reconcile", {
    method: "POST",
    body: { items: [{ sale_id: Number(saleId), status }] },
  });
  toast(`Sale ${saleId} ${status}`);
  refresh();
}

// ---- Init -----------------------------------------------------------------
refresh();
