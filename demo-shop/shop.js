/* Fernleaf: a fictional demo shop for testing First User.
   Nothing here is real. There are no payments and no data leaves the browser: the cart lives in
   this browser's localStorage and the "order" is only a message on the page. */

// ===== PLANTED BUG: change this one line to fix it ===========================
const PLANTED_BUG_CART_ADD = true; // true = "Add to cart" does not add anything and throws an error; false = works
// ==============================================================================

const PRODUCTS = {
  monstera: { name: "Monstera deliciosa", price: 24 },
  "snake-plant": { name: "Snake plant", price: 18 },
  pothos: { name: "Golden pothos", price: 14 },
};

const CART_KEY = "fernleaf-demo-cart";
let memoryCart = {}; // used when localStorage is blocked

function readCart() {
  try {
    return JSON.parse(localStorage.getItem(CART_KEY) || "{}");
  } catch (error) {
    return memoryCart;
  }
}

function writeCart(cart) {
  memoryCart = cart;
  try {
    localStorage.setItem(CART_KEY, JSON.stringify(cart));
  } catch (error) {
    /* private mode: the in-memory copy is used */
  }
}

function cartCount() {
  return Object.values(readCart()).reduce((total, qty) => total + qty, 0);
}

function showCartCount() {
  document.querySelectorAll("[data-cart-count]").forEach((node) => {
    node.textContent = String(cartCount());
  });
}

// State the cart summary widget is meant to keep (only the planted bug touches it).
const cartSummary = {};

function addToCart(id) {
  if (PLANTED_BUG_CART_ADD) {
    // The bug: this reads a list that was never created, so it throws a TypeError
    // ("Cannot read properties of undefined") before anything is saved.
    cartSummary.lines[id].qty += 1;
  }
  const cart = readCart();
  cart[id] = (cart[id] || 0) + 1;
  writeCart(cart);
  showCartCount();
}

function setUpAddButtons() {
  document.querySelectorAll("[data-add-to-cart]").forEach((button) => {
    button.addEventListener("click", () => {
      // The button always looks pressed ...
      button.setAttribute("aria-pressed", "true");
      button.textContent = "Added ✓";
      // ... but with the bug on, this line throws and the cart is never updated.
      addToCart(button.dataset.addToCart);
    });
  });
}

function money(value) {
  return "$" + value.toFixed(2);
}

function renderCartPage() {
  const body = document.getElementById("cart-body");
  if (!body) return;
  const cart = readCart();
  const ids = Object.keys(cart).filter((id) => PRODUCTS[id] && cart[id] > 0);
  const empty = document.getElementById("cart-empty");
  const table = document.getElementById("cart-table");
  const checkout = document.getElementById("checkout-button");
  const count = document.getElementById("cart-items");
  let total = 0;
  body.innerHTML = "";
  ids.forEach((id) => {
    const line = PRODUCTS[id].price * cart[id];
    total += line;
    const row = document.createElement("tr");
    [PRODUCTS[id].name, String(cart[id]), money(line)].forEach((text) => {
      const cell = document.createElement("td");
      cell.textContent = text;
      row.appendChild(cell);
    });
    body.appendChild(row);
  });
  count.textContent = String(cartCount());
  document.getElementById("cart-total").textContent = money(total);
  empty.hidden = ids.length > 0;
  table.hidden = ids.length === 0;
  checkout.disabled = ids.length === 0;
  checkout.addEventListener("click", () => {
    window.location.href = "checkout.html";
  });
}

function setUpCheckout() {
  const form = document.getElementById("checkout-form");
  if (!form) return;
  const empty = document.getElementById("checkout-empty");
  const status = document.getElementById("order-status");
  const hasItems = cartCount() > 0;
  form.hidden = !hasItems;
  empty.hidden = hasItems;
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    writeCart({}); // the demo order is not sent anywhere; the cart is just emptied
    showCartCount();
    form.hidden = true;
    status.hidden = false;
  });
}

document.addEventListener("DOMContentLoaded", () => {
  showCartCount();
  setUpAddButtons();
  renderCartPage();
  setUpCheckout();
});
