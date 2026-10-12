/* Fernleaf (fictional demo shop): the order summary on the checkout page.
   Reads the same cart as shop.js (readCart, PRODUCTS, money); load this file after shop.js. */

function renderOrderSummary() {
  const summary = document.getElementById("order-summary");
  if (!summary || typeof readCart !== "function") return;
  const list = document.getElementById("order-lines");
  const empty = document.getElementById("order-empty");
  const filled = document.getElementById("order-filled");
  const cart = readCart();
  const ids = Object.keys(cart).filter((id) => PRODUCTS[id] && cart[id] > 0);
  let total = 0;
  list.textContent = "";
  ids.forEach((id) => {
    const line = PRODUCTS[id].price * cart[id];
    total += line;
    const row = document.createElement("tr");
    [PRODUCTS[id].name, String(cart[id]), money(line)].forEach((text) => {
      const cell = document.createElement("td");
      cell.textContent = text;
      row.appendChild(cell);
    });
    list.appendChild(row);
  });
  document.getElementById("order-total").textContent = money(total);
  empty.hidden = ids.length > 0;
  filled.hidden = ids.length === 0;
  // The page already has a "cart is empty" line; show only one.
  const pageEmpty = document.getElementById("checkout-empty");
  if (pageEmpty) pageEmpty.hidden = true;
}

document.addEventListener("DOMContentLoaded", () => {
  renderOrderSummary();
  const form = document.getElementById("checkout-form");
  if (form) {
    // shop.js empties the cart on submit; the order is placed, so the summary goes with the form.
    form.addEventListener("submit", () => {
      document.getElementById("order-summary").hidden = true;
    });
  }
});
