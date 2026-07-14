import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@/index.css";
import App from "@/App";

// "ResizeObserver loop completed with undelivered notifications" is a benign
// browser warning (fired by any ResizeObserver-driven UI, e.g. cmdk's popover
// height animation) — harmless, but left unhandled it surfaces as a fatal-looking
// full-screen error in CRA's dev overlay. Suppress only this exact message;
// every other runtime error still surfaces normally.
window.addEventListener("error", (e) => {
  if (e.message === "ResizeObserver loop completed with undelivered notifications." ||
      e.message === "ResizeObserver loop limit exceeded") {
    e.stopImmediatePropagation();
  }
});

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
