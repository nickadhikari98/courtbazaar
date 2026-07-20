import { api } from "./api";

/* The single earnings engine every capability="can_earn" role plugs into —
   same axios-wrapper shape as leadsApi.js/reviewsApi.js/practiceApi.js. */

export async function getEarningsMe() {
  const { data } = await api.get("/earnings/me");
  return data;
}

export async function withdrawEarnings(amount, bankAccount, bankIfsc) {
  const { data } = await api.post("/earnings/withdraw", {
    amount, bank_account: bankAccount || undefined, bank_ifsc: bankIfsc || undefined,
  });
  return data;
}

export async function getEarningsSettlements() {
  const { data } = await api.get("/earnings/settlements");
  return data;
}

export async function getWallet() {
  const { data } = await api.get("/wallet");
  return data; // { balance, transactions }
}
