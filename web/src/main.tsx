import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { AppProviders } from "@/app/providers";
import { createAppRouter } from "@/app/router";
import { applyTheme, getInitialTheme } from "@/lib/theme";
import "@/styles/global.css";

applyTheme(getInitialTheme());

const router = createAppRouter();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <AppProviders>
      <RouterProvider router={router} future={{ v7_startTransition: true }} />
    </AppProviders>
  </StrictMode>,
);
