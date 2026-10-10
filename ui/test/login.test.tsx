/**
 * The sign-in page (v3 slice 24): a development stand-in, and it must say so in every state -
 * off, signed out, failed, signed in - because a stand-in that looked like real sign-in is how
 * one ends up in production.
 */
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { LoginView } from "@/components/LoginView";

afterEach(cleanup);

const text = (element: Element) => (element.textContent ?? "").replace(/\s+/g, " ").trim();
const states = {
  off: { enabled: false, identity: null, failed: false },
  "signed out": { enabled: true, identity: null, failed: false },
  failed: { enabled: true, identity: null, failed: true },
  "signed in": { enabled: true, identity: { user: "alice", property: "sandbox" }, failed: false },
};

describe("the sign-in page", () => {
  for (const [name, props] of Object.entries(states)) {
    it(`${name}: says it is a development stand-in, not production authentication`, () => {
      const page = render(<LoginView {...props} />).container;
      const notice = page.querySelector("[data-stand-in]")!;
      expect(text(notice)).toContain("Development stand-in");
      expect(text(notice)).toContain("not production authentication");
    });
  }

  it("off: offers nothing to sign in to", () => {
    const page = render(<LoginView {...states.off} />).container;
    expect(page.querySelector("form")).toBeNull();
    expect(text(page)).toContain("Authentication is off");
  });

  it("signed out: a form posting a user and a password", () => {
    const page = render(<LoginView {...states["signed out"]} />).container;
    expect(page.querySelector("input[name=user]")).not.toBeNull();
    expect(page.querySelector("input[name=password][type=password]")).not.toBeNull();
  });

  it("failed: one sentence that does not say which half was wrong", () => {
    const page = render(<LoginView {...states.failed} />).container;
    expect(text(page.querySelector("[role=alert]")!)).toBe("Those credentials do not match a development user.");
  });

  it("signed in: who, for which one property, and a way out", () => {
    const page = render(<LoginView {...states["signed in"]} />).container;
    expect(text(page)).toContain("Signed in as alice for property sandbox");
    expect(page.querySelector("button")!.textContent).toBe("Sign out");
  });
});
