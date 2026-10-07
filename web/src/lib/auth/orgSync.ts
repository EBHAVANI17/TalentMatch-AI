/**
 * Cross-tab organization switching. Tabs share one session (localStorage), so when one tab
 * switches organization the others must reload instead of showing the old organization's data.
 * BroadcastChannel where available; the storage event as a fallback (older Safari).
 */
const CHANNEL = "tm-auth";
const STORAGE_KEY = "tm-org-switch";
// BroadcastChannel also delivers to other listeners in the sending tab; skip our own messages.
const TAB_ID = Math.random().toString(36).slice(2);

interface SwitchMessage {
  type: "org-switched";
  organizationId: string;
  from: string;
  at: number;
}

export function announceOrgSwitch(organizationId: string): void {
  const message: SwitchMessage = { type: "org-switched", organizationId, from: TAB_ID, at: Date.now() };
  try {
    if (typeof BroadcastChannel !== "undefined") {
      const channel = new BroadcastChannel(CHANNEL);
      channel.postMessage(message);
      channel.close();
    }
  } catch {
    // fall through to the storage event
  }
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(message)); // fires "storage" in other tabs
  } catch {
    // storage unavailable (private mode); the 409 check on writes still protects data
  }
}

/** Calls `handler` when another tab switches organization. Returns an unsubscribe function. */
export function onOrgSwitchElsewhere(handler: (organizationId: string) => void): () => void {
  const accept = (data: unknown) => {
    const message = data as Partial<SwitchMessage> | null;
    if (message?.type !== "org-switched" || message.from === TAB_ID) return;
    if (typeof message.organizationId === "string") handler(message.organizationId);
  };
  let channel: BroadcastChannel | null = null;
  if (typeof BroadcastChannel !== "undefined") {
    channel = new BroadcastChannel(CHANNEL);
    channel.onmessage = (e) => accept(e.data);
  }
  const onStorage = (e: StorageEvent) => {
    if (e.key !== STORAGE_KEY || !e.newValue) return;
    try {
      accept(JSON.parse(e.newValue));
    } catch {
      // ignore malformed values
    }
  };
  window.addEventListener("storage", onStorage);
  return () => {
    channel?.close();
    window.removeEventListener("storage", onStorage);
  };
}
