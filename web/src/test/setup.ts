import "@testing-library/jest-dom/vitest";
import { cleanup, configure } from "@testing-library/react";
import { afterEach } from "vitest";

// Test files run in parallel; full-app renders can take more than the 1s default under load.
configure({ asyncUtilTimeout: 4000 });

afterEach(() => {
  cleanup();
  localStorage.clear();
});
