import { indiaToday } from "./utils";

describe("indiaToday", () => {
  afterEach(() => jest.useRealTimers());

  it("follows India's date, not UTC's, across the 18:30 UTC boundary", () => {
    jest.useFakeTimers().setSystemTime(new Date("2026-06-14T18:29:59Z"));
    expect(indiaToday()).toBe("2026-06-14");
    jest.setSystemTime(new Date("2026-06-14T18:30:00Z"));
    expect(indiaToday()).toBe("2026-06-15");
  });
});
