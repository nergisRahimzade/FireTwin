import { describe, expect, it } from "vitest";
import { STARTER_QUESTIONS, citationUrl } from "./chat.logic";

describe("citationUrl", () => {
  it("reads a plain URL and one with a label in front", () => {
    expect(citationUrl("https://psi.nasa.gov/x")).toBe("https://psi.nasa.gov/x");
    expect(citationUrl("source_url: https://psi.nasa.gov/physci/PSI-99")).toBe("https://psi.nasa.gov/physci/PSI-99");
  });
  it("gives null when there is no URL (synthetic placeholders)", () => {
    expect(citationUrl("synthetic-seed (placeholder, not NASA data)")).toBeNull();
  });
});

it("offers the three starter questions from the plan", () => {
  expect(STARTER_QUESTIONS).toHaveLength(3);
});
